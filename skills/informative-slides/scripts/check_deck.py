#!/usr/bin/env python3
"""Check an informative-slides HTML deck.

Usage: python3 check_deck.py <deck.html> [--no-browser]

Per slide (<section class="slide">), on the Korean text:
  - title exists, is a noun phrase (not a -다/-요/-니다 sentence), is not a generic label
  - every non-cover slide has a lead, and the lead is one sentence
  - word budget (어절) excluding the source line
  - numbers come with a .source line
  - every abbreviation / metric code / model name on the slide has its plain name on that slide
Per deck:
  - cover first, summary second, closing last; the summary has a .recap
  - lang="ko" and lang="en" elements pair up
  - every data-diagram has a <template id="diagram-..."> definition
  - method slides (data-layout="method"): one narration per figure step, 3 sentences / 45 words per step
  - figure text: every symbol (Q, Kᵀ, S₁₁) appears once with its plain name in the same figure
  - prints the titles in order so the storyline can be read on its own
  - with Chrome/Chromium/Edge installed, renders ?check at every step and reports slides that overflow,
    diagram problems, figure text smaller than 1.0% of the slide width, and lines that wrap without <br>

Exit code 1 when any ERROR is found.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr", "path", "rect", "circle", "line"}
GENERIC = {
    "overview", "introduction", "background", "agenda", "summary", "results", "conclusion", "next steps",
    "q&a", "appendix", "architecture", "status", "method", "analysis", "comparison", "problem",
    "개요", "소개", "배경", "목차", "요약", "결과", "결론", "향후 계획", "다음 단계", "질의응답", "부록", "구조",
    "현황", "문제", "문제점", "방법", "분석", "비교", "성능", "시스템 구조", "해결 방안",
}
COMMON = {
    "AI", "API", "URL", "PDF", "HTML", "CSS", "UI", "UX", "CEO", "CTO", "CFO", "IT", "ID", "OK", "PC", "USB",
    "KST", "UTC", "USD", "KRW", "EU", "US", "UK", "FAQ", "TBD", "GPU", "CPU", "IBM", "AWS", "MD",
}
WORDS = {"summary": 50, "default": 60}
TOKEN = re.compile(r"(?<![A-Za-z0-9@/._-])[A-Za-z][A-Za-z0-9@]{1,11}(?![A-Za-z0-9@._-])")
PLACEHOLDER = re.compile(r"\[(?:확인 필요|TBD|TODO)[^\]]*\]")


def is_abbr(t):
    if t in COMMON or re.fullmatch(r"[QH][1-4]", t):
        return False
    if re.fullmatch(r"(?=(?:.*[A-Z]){2})[A-Za-z0-9@]+", t):  # RAG, nDCG@10, MRR@5, DLQ
        return True
    return bool(re.fullmatch(r"[A-Za-z]{1,4}\d+(?:@\d+)?", t))  # A10, T4, p95, p99


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def cls(self):
        return set((self.attrs.get("class") or "").split())


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur, self.skip = self.root, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, d):
        if not self.skip:
            self.cur.children.append(d)


def walk(n):
    for c in n.children:
        if isinstance(c, Node):
            yield c
            yield from walk(c)


def text(n, skip=lambda x: False, lang="ko"):
    """Visible text in one language: elements marked with the other lang are skipped."""
    out = []
    for c in n.children:
        if isinstance(c, str):
            out.append(c)
        elif c.tag == "br":
            out.append("\n")
        elif not skip(c) and c.attrs.get("lang", lang) == lang and c.tag != "template":
            out.append(" " + text(c, skip, lang) + " ")
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


def one_line(s):
    return re.sub(r"\s+", " ", s).strip()


def hangul_ratio(s):
    letters = [ch for ch in s if ch.isalpha()]
    return sum("가" <= ch <= "힣" for ch in letters) / len(letters) if letters else 0


def find_chrome():
    cands = [os.environ.get("CHROME"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
             shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("msedge")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def browser_overflow(path):
    chrome = find_chrome()
    if not chrome:
        return None, "no Chrome/Chromium/Edge found; open the deck with ?check in a browser instead"
    res = []
    for lang in ("ko", "en"):
        url = pathlib.Path(path).resolve().as_uri() + f"?check&lang={lang}"
        with tempfile.TemporaryDirectory() as prof:
            try:
                out = subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}",
                                      "--window-size=1600,900", "--virtual-time-budget=8000", "--dump-dom", url],
                                     capture_output=True, text=True, timeout=90).stdout
            except (subprocess.TimeoutExpired, OSError) as e:
                return None, f"browser check failed: {e}"
        m = re.search(r'data-overflow="([^"]*)"', out)
        if not m:
            return None, "browser check produced no result; open the deck with ?check in a browser instead"
        if m.group(1) != "none":
            res += [(int(x), lang, "content overflows the slide; split the slide or shorten text") for x in m.group(1).split(",")]
        d = re.search(r'data-diagram="([^"]*)"', out)
        if d and d.group(1) not in ("none", ""):
            import html as _html
            names = {"text-out": "diagram: text outside its box", "text-overlap": "diagram: texts overlap",
                     "label-on-box": "diagram: label overlaps another box",
                     "edge-cross": "diagram: arrow crosses a box it does not connect", "out-of-figure": "diagram: element outside the figure",
                     "small-text": "diagram: text smaller than 1.0% of the slide width (shown size first); enlarge the font, shorten the text or split the figure",
                     "wrap": "line breaks where there is no <br>; break it at a meaning boundary yourself, shorten it, or split the slide"}
            for item in _html.unescape(d.group(1)).split(";"):
                parts = item.split("|", 2)
                if len(parts) == 3 and parts[0].isdigit():
                    res.append((int(parts[0]), lang, f'{names.get(parts[1], parts[1])}: "{parts[2]}"'))
    return res, None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(2)
    path = args[0]
    src = pathlib.Path(path).read_text(encoding="utf-8")
    b = Builder()
    b.feed(src)
    slides = [n for n in walk(b.root) if n.tag == "section" and "slide" in n.cls]
    if not slides:
        print('ERROR: no <section class="slide"> found')
        sys.exit(1)
    issues, titles = [], []

    for i, s in enumerate(slides, 1):
        layout = s.attrs.get("data-layout") or ("cover" if "cover" in s.cls else "")
        t_el = next((n for n in walk(s) if "title" in n.cls), None)
        title = one_line(text(t_el)) if t_el else ""
        titles.append((i, layout, title))
        if not title:
            issues.append(("ERROR", i, "no .title"))
        else:
            core = re.sub(r"^[^:：]{1,12}[:：]\s*", "", title).strip().lower()
            if title.lower() in GENERIC or core in GENERIC:
                issues.append(("ERROR", i, f'generic title "{title}"; name the object, aspect and scope'))
            if hangul_ratio(title) > 0.3 and re.search(r"(다|요|니다)[.!]?$", title):
                issues.append(("ERROR", i, f'sentence title "{title}"; use a noun phrase and put the sentence in .lead'))
            units = sum(1 if "\uac00" <= ch <= "\ud7a3" else 0.55 for ch in title)
            lim_u = 26 if layout == "cover" else 40
            if units > lim_u and "\n" not in text(t_el):
                issues.append(("WARN", i, f"title is {units:.0f} width units (Hangul 1, other 0.55; limit {lim_u}); move detail to the subtitle or break with <br>"))

        if layout != "cover":
            leads = [n for n in walk(s) if "lead" in n.cls]
            if layout != "summary" and len(leads) != 1:
                issues.append(("ERROR", i, f"{len(leads)} .lead elements; a slide has exactly one message sentence"))
            for n in leads:
                lt = text(n)
                if len(re.findall(r"[.!?](?:\s|$)", lt)) > 1:
                    issues.append(("WARN", i, "lead has more than one sentence; keep one message per slide"))
                if lt.count("\n") > 1:
                    issues.append(("WARN", i, "lead runs past two lines"))
        if layout == "summary":
            for n in walk(s):
                if n.tag == "li" or "recap" in n.cls:
                    for line in text(n).split("\n"):
                        if sum("\uac00" <= ch <= "\ud7a3" for ch in line) > 30:
                            issues.append(("WARN", i, f'summary line too long: "{one_line(line)[:30]}…"; use a short phrase (30 Hangul max)'))
        if layout == "summary" and not any("recap" in n.cls for n in walk(s)):
            issues.append(("WARN", i, "summary has no .recap (why, what, how)"))

        is_src = lambda n: "source" in n.cls
        # 방법 설명 장: 단계 설명(.narration)은 분량을 따로 센다(원칙 8)
        is_narr = lambda n: "narration" in n.cls
        if layout == "method":
            figs = [n for n in walk(s) if "data-steps" in n.attrs]
            narr = [n for n in walk(s) if "data-only" in n.attrs]
            if not figs:
                issues.append(("WARN", i, 'method slide has no figure with data-steps; highlight the part each step explains'))
            if not narr:
                issues.append(("WARN", i, 'method slide has no .narration <p data-only="k">; write 2-3 sentences per step'))
            n_fig = max((len(f.attrs["data-steps"].split(";")) for f in figs), default=0)
            n_narr = len({n.attrs["data-only"] for n in narr})
            if figs and narr and n_fig != n_narr:
                issues.append(("WARN", i, f"figure has {n_fig} steps but the narration has {n_narr}; write one narration per step"))
            for n in narr:
                nt = text(n, lambda x: "step-name" in x.cls)
                sents = len(re.findall(r"[.!?](?:\s|$)", nt))
                w = len(nt.split())
                if sents > 3 or w > 45:
                    issues.append(("WARN", i, f'step {n.attrs["data-only"]} narration has {sents} sentences, {w} words (limit 3 sentences, 45 words); split the step'))
                if not any("step-name" in x.cls for x in walk(n)):
                    issues.append(("WARN", i, f'step {n.attrs["data-only"]} narration has no .step-name label'))
        body = text(s, lambda n: is_src(n) or is_narr(n))
        words = len(body.split())
        lim = WORDS.get(layout, WORDS["default"])
        if words > lim and layout != "cover":
            issues.append(("WARN", i, f"{words} words (limit {lim}); split the slide"))
        has_source = any(is_src(n) and text(n) for n in walk(s))
        body_wo = text(s, lambda n: is_src(n) or "title" in n.cls or "eyebrow" in n.cls or n.tag == "svg")
        if layout not in ("cover", "closing") and re.search(r"\d", body_wo) and not has_source:
            issues.append(("WARN", i, "numbers on the slide but no .source"))

        full = one_line(text(s))
        local_def = set()
        for n in walk(s):
            if n.tag == "dfn" or "defs" in n.cls:
                local_def.update(TOKEN.findall(text(n)))
        seen = set()
        for m in TOKEN.finditer(full):
            t = m.group(0)
            if t in seen or not is_abbr(t):
                continue
            seen.add(t)
            before = full[max(0, m.start() - 14):m.start()]
            ok = t in local_def or re.match(r"\s*[(（]", full[m.end():]) or ("(" in before and ")" not in before.split("(")[-1])
            if not ok:
                issues.append(("WARN", i, f'"{t}" without its plain name on this slide; write "쉬운 이름 ({t})"'))
        # 원칙 2: 원자료 기호(B안, 1안, 시나리오 C)는 그 장에서 내용 이름과 함께 써야 한다. 지시어로 다른 내용을 가리키지 않는다.
        for lab in sorted(set(re.findall(r"(?:[A-Z]|[0-9]+)안|시나리오 [A-Z0-9](?![0-9가-힣])", full))):
            if not re.search(r"[(（]\s*" + re.escape(lab) + r"\s*[)）]", full):
                issues.append(("WARN", i, f'"{lab}" used as a name; write what it is with the label in parentheses, e.g. "메시지 큐 방식({lab})"'))
        demo = re.findall(r"(?:^|\s)(해당|위의|앞서|전자|후자|이것|그것|이 방식|그 방식|이 문제|그 문제|이 안|그 안)(?=\s|$|[,.)])", full)
        for d in sorted(set(demo)):
            issues.append(("WARN", i, f'demonstrative "{d}" points outside the sentence; name the thing instead'))
        # 원칙 3: 의인화. 사람이 아닌 대상이 말하거나 보여 주는 것처럼 쓴 표현
        for pm in sorted(set(re.findall(r"((?:말해|보여|알려|증명해)\s?(?:준다|주는|주고|주며|줌)|이야기한다|알아서)", full))):
            issues.append(("WARN", i, f'personification "{pm}"; write what actually happens or who does it'))
        if re.search(r"결론\s*\d|결론\s*[:：]|결론 요약", full):
            issues.append(("WARN", i, 'the word "결론" used as a label; name the content instead (요약 항목은 번호만)'))
        for ph in PLACEHOLDER.findall(full):
            issues.append(("INFO", i, f"placeholder to fill: {ph}"))

    layouts = [t[1] for t in titles]
    if layouts[0] != "cover":
        issues.append(("WARN", 1, 'first slide is not the cover (class="slide cover")'))
    if len(slides) > 3 and (len(layouts) < 2 or layouts[1] != "project"):
        issues.append(("WARN", 2, 'slide 2 is not data-layout="project"; introduce the project before the summary'))
    if len(slides) > 3 and "summary" not in layouts[1:4]:
        issues.append(("WARN", 3, 'no data-layout="summary" slide after the project introduction'))
    if "project" in layouts and "summary" in layouts and layouts.index("summary") < layouts.index("project"):
        issues.append(("WARN", layouts.index("summary") + 1, "summary comes before the project introduction"))
    if layouts[-1] != "closing":
        issues.append(("WARN", len(slides), 'last slide is not data-layout="closing"'))

    if not re.search(r'<html[^>]*style="[^"]*--project:\s*#[0-9a-fA-F]{6}', src):
        issues.append(("WARN", 0, '<html> has no style="--project:#RRGGBB"; run scripts/project_identity.py and set the project color'))
    for i, (_, layout, _) in enumerate(titles, 1):
        if layout in ("cover", "closing") and not any("project" in n.cls for n in walk(slides[i - 1])):
            issues.append(("WARN", i, f'{layout} slide has no .project (project name)'))
        if layout == "cover" and not any("summary" in n.cls for n in walk(slides[i - 1])):
            issues.append(("WARN", i, 'cover has no .summary (one line saying what the project is)'))
    if not re.search(r'<html[^>]*data-ratio="\d+(?:\.\d+)?:\d+(?:\.\d+)?"', src):
        issues.append(("WARN", 0, '<html> has no data-ratio="W:H"; the template sets the slide and PDF page ratio from it'))
    body_html = src[src.find("<body"):]
    ko = len(re.findall(r'\blang="ko"', body_html))
    en = len(re.findall(r'\blang="en"', body_html))
    if ko != en:
        issues.append(("ERROR", 0, f'lang="ko" ({ko}) and lang="en" ({en}) counts differ; every text needs both'))
    used = set(re.findall(r'data-(?:diagram|detail)="([^"]+)"', src))
    defined = set(re.findall(r'<template id="diagram-([^"]+)"', src))
    for d in sorted(used - defined):
        issues.append(("ERROR", 0, f'data-diagram="{d}" has no <template id="diagram-{d}">'))

    # 원칙 2·7: 그림 안의 기호(Q, Kᵀ, S₁₁)는 그림마다 한 번은 내용 이름과 함께 쓴다("질문 행렬 Q").
    sym = re.compile(r"(?<![A-Za-z0-9가-힣×])([A-Z])[₀-₉ᵀ]*(?![A-Za-z0-9×])")
    for tid, body in re.findall(r'<template id="diagram-([^"]+)">(.*?)</template>', src, re.S):
        texts = [re.sub(r"\\[()]|\\(?:mathrm|text|top|tilde|hat|bar)|[{}^_]", " ", re.sub(r"<[^>]+>", "", t))
                 for t in re.findall(r'<text(?![^>]*lang="en")[^>]*>(.*?)</text>', body, re.S)]
        letters = sorted({m.group(1) for t in texts for m in sym.finditer(t)})
        for L in letters:
            named = any(re.search(r"[가-힣]{2,}[가-힣\s·]*\(?\s*" + L + r"(?![A-Za-z])", t) or
                        re.search(L + r"[₀-₉ᵀ]*\s*[(（][^)）]*[가-힣]{2,}", t) for t in texts)
            if not named:
                issues.append(("WARN", 0, f'diagram-{tid}: symbol "{L}" has no plain name in the figure; write it once with its name, e.g. "<내용 이름> {L}"'))

    # 수식 표기: 유니코드 첨자 글자는 덱 글꼴에 없어 다른 글꼴로 그려지고 간격이 벌어진다. \( K_j^{\top} \)로 쓴다
    body_src = re.sub(r"<script.*?</script>|<style.*?</style>", "", src, flags=re.S)
    uni = sorted(set(re.findall(r"[\u2080-\u209C\u1D2C-\u1D6A\u2C7C\u2070\u2071\u2074-\u207F]", body_src)))
    if uni:
        issues.append(("WARN", 0, f'Unicode sub/superscript letters {" ".join(uni)}; write math as \\( K_j^{{\\top}} \\) instead (they fall back to another font and leave gaps)'))

    if "--no-browser" not in sys.argv:
        over, note = browser_overflow(path)
        if over is None:
            issues.append(("INFO", 0, note))
        for i, lang, msg in over or []:
            issues.append(("ERROR", i, f"{msg} ({lang})"))

    print(f"Deck: {path}  ({len(slides)} slides)\n")
    print("Titles in order (read these alone: they should state the whole argument):")
    for i, layout, t in titles:
        print(f"  {i:>2}. [{layout or '-'}] {t}")
    print()
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for lvl, i, msg in sorted(issues, key=lambda x: (order[x[0]], x[1])):
        print(f"{lvl:5} {'slide ' + str(i) if i else 'deck'}: {msg}")
    n_err = sum(x[0] == "ERROR" for x in issues)
    print(f"\n{n_err} error(s), {sum(x[0] == 'WARN' for x in issues)} warning(s)")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
