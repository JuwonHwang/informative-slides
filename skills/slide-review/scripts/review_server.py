#!/usr/bin/env python3
"""Serve decks for review and store feedback next to each deck.

Usage: python3 review_server.py <dir> [--port 8765] [--open <deck.html relative to dir>]

Serves <dir> over http://localhost:<port>/. The review page
  http://localhost:<port>/__review/<deck path>
shows the deck inside a feedback screen (assets/review.html). Feedback is sent here:
  POST /__feedback  {"deck": "<path>", "markdown": "...", "json": {...}, "done": bool}
writes <deck>-feedback.md and <deck>-feedback.json beside the deck, and when
done is true also writes <deck>-feedback.done (an agent can wait on that file).
GET /__ping returns "ok" so the page knows a server is present.
GET /__pdf/<deck path>?lang=ko|en renders the deck to PDF with headless Chrome/Chromium/Edge
(one slide per page, size from the deck's @page rule) and returns it as a download.
"""
import http.server
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = pathlib.Path(args[0] if args else ".").resolve()
SHELL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "review.html"
FONTS = pathlib.Path(__file__).resolve().parent.parent / "assets" / "fonts"
# 검수 화면과 PDF가 같은 글꼴을 쓰도록 덱에 넣는 글꼴 정의. 덱 파일은 바꾸지 않는다.
FONT_CSS = "".join(
    f'@font-face{{font-family:"Pretendard";font-weight:{w};font-style:normal;'
    f'src:url(/__font/Pretendard-{n}.woff2) format("woff2")}}'
    for w, n in [(400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")])
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765


# 수명: 열린 검수 화면이 30초마다 /__heartbeat를 보낸다. 열린 화면이 없는 상태가 CLOSED_LIMIT초,
# 또는 사용자 조작이 없는 상태가 IDLE_LIMIT초 이어지면 서버가 종료한다. 검수 완료를 받으면 바로 종료한다.
CLOSED_LIMIT = int(os.environ.get("REVIEW_CLOSED_LIMIT", 600))
IDLE_LIMIT = int(os.environ.get("REVIEW_IDLE_LIMIT", 3600))
START = time.time()
LAST_SEEN = START      # 마지막 heartbeat
LAST_ACTIVE = START    # 마지막 사용자 조작(클릭, 키, 의견 입력, 저장)
SERVER = None
# 검수 완료 뒤에는 의견을 받지 않고 HTML·PDF 저장만 처리한다. 화면이 닫히면 FINISHED_CLOSED초, 조작이 없으면 FINISHED_IDLE초 뒤 종료한다.
FINISHED = False
# 검수 화면 하나를 계속 쓴다: review.py open이 /__open으로 열 덱을 바꾸면, 열린 화면이 heartbeat 응답에서 덱과 회차를 받아 다시 연다.
TARGET = None   # 루트 기준 덱 경로
ROUND = 0       # /__open마다 1 증가
FINISHED_CLOSED = int(os.environ.get("REVIEW_FINISHED_CLOSED", 60))
FINISHED_IDLE = int(os.environ.get("REVIEW_FINISHED_IDLE", 600))


def shutdown_later(delay=1.0):
    threading.Timer(delay, lambda: SERVER and SERVER.shutdown()).start()


def watchdog():
    while True:
        time.sleep(15)
        now = time.time()
        if FINISHED and (now - LAST_SEEN > FINISHED_CLOSED or now - LAST_ACTIVE > FINISHED_IDLE):
            sys.stderr.write("review finished and screen closed or idle; stopping\n")
            return shutdown_later(0)
        if now - LAST_SEEN > CLOSED_LIMIT:
            sys.stderr.write(f"no open review screen for {CLOSED_LIMIT}s; stopping\n")
            return shutdown_later(0)
        if now - LAST_ACTIVE > IDLE_LIMIT:
            sys.stderr.write(f"no activity for {IDLE_LIMIT}s; stopping\n")
            return shutdown_later(0)


def find_chrome():
    cands = [os.environ.get("CHROME"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
             shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("msedge")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def fix_mediabox(body, w_pt, h_pt):
    """Set every /MediaBox and /CropBox to [0 0 w h], then rebuild the xref table. Returns (body, failures)."""
    fmt = lambda v: f"{v:.4f}".rstrip("0").rstrip(".")
    box = f"[0 0 {fmt(w_pt)} {fmt(h_pt)}]".encode()
    new = re.sub(rb"(/MediaBox|/CropBox)(\s*)\[[^\]]*\]", lambda m: m.group(1) + m.group(2) + box, body)
    if new == body:
        return body, 0
    xi = new.rfind(b"\nxref")
    ti = new.find(b"trailer", xi)
    head = re.match(rb"\nxref\s*\n0 (\d+)\s*\n", new[xi:])
    if xi < 0 or ti < 0 or not head:
        return body, 1  # cross-reference stream or unusual layout: leave the file untouched
    size = int(head.group(1))
    pos = {int(m.group(1)): m.start(1) for m in re.finditer(rb"(?:^|[\r\n])(\d+) 0 obj", new[:xi])}
    rows = [b"0000000000 65535 f \n"]
    for n in range(1, size):
        rows.append(f"{pos[n]:010d} 00000 n \n".encode() if n in pos else b"0000000000 65535 f \n")
    table = b"\nxref\n0 " + str(size).encode() + b"\n" + b"".join(rows)
    out = new[:xi] + table + new[ti:]
    out = re.sub(rb"startxref\s*\n\d+", b"startxref\n" + str(xi + 1).encode(), out)
    return out, 0


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _reply(self, code, body=b"ok"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global LAST_SEEN, LAST_ACTIVE
        if self.path == "/__ping":
            return self._reply(200)
        if self.path.startswith("/__heartbeat"):
            LAST_SEEN = time.time()
            if "active=1" in self.path:
                LAST_ACTIVE = LAST_SEEN
            body = json.dumps({"target": TARGET, "round": ROUND, "finished": FINISHED}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return None
        if self.path.startswith("/__mtime/"):
            f = (ROOT / urllib.parse.unquote(urllib.parse.urlparse(self.path).path[len("/__mtime/"):])).resolve()
            if ROOT not in f.parents or not f.is_file():
                return self._reply(404, b"0")
            return self._reply(200, str(f.stat().st_mtime).encode())
        if self.path.startswith("/__pdf/"):
            LAST_ACTIVE = time.time()
            return self._pdf()
        if self.path.startswith("/__font/"):
            f = (FONTS / pathlib.Path(urllib.parse.unquote(self.path[len("/__font/"):])).name)
            if not f.exists():
                return self._reply(404, b"no font")
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "font/woff2")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        if self.path.startswith("/__render/"):
            return self._render()
        if self.path.startswith("/__review/"):
            body = SHELL.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().do_GET()

    def _render(self):
        """Serve the deck with the bundled Pretendard @font-face added; other files under /__render/ come from ROOT."""
        u = urllib.parse.urlparse(self.path)
        rel = urllib.parse.unquote(u.path[len("/__render/"):])
        f = (ROOT / rel).resolve()
        if ROOT not in f.parents or not f.is_file():
            return self._reply(404, b"not found")
        body = f.read_bytes()
        ctype = "application/octet-stream"
        if f.suffix in (".html", ".htm"):
            html = body.decode("utf-8")
            tag = f'<style id="review-fonts">{FONT_CSS}</style>'
            html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + tag, html, count=1) if "<head" in html else tag + html
            body, ctype = html.encode("utf-8"), "text/html; charset=utf-8"
        else:
            import mimetypes
            ctype = mimetypes.guess_type(str(f))[0] or ctype
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None

    def _render_pdf(self, rel, lang, ratio_q, width_q):
        deck = (ROOT / rel.lstrip("/")).resolve()
        if ROOT not in deck.parents or deck.suffix not in (".html", ".htm") or not deck.exists():
            return None, "bad deck path"
        chrome = find_chrome()
        if not chrome:
            return None, "Chrome, Chromium, Edge 중 하나가 필요하다"
        params = {"lang": lang, "steps": "pages"}  # 단계가 있는 장은 단계마다 한 쪽
        if re.fullmatch(r"\d+(?:\.\d+)?:\d+(?:\.\d+)?", ratio_q or ""):
            params["ratio"] = ratio_q
        if re.fullmatch(r"\d+(?:\.\d+)?", width_q or "") and 0 < float(width_q) <= 60:
            params["w"] = width_q
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "deck.pdf"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={tmp}/p",
                             "--no-pdf-header-footer", "--virtual-time-budget=10000",
                            f"--print-to-pdf={out}",
                            f"http://127.0.0.1:{PORT}/__render/" + urllib.parse.quote(rel.lstrip("/")) + "?" + urllib.parse.urlencode(params)],
                           capture_output=True, timeout=120)
            if not out.exists():
                return None, "pdf render failed"
            body = out.read_bytes()
        # 쪽 크기를 요청한 비율과 가로 길이에 정확히 맞춘다. Chrome은 쪽 크기를 반올림한다(예: 675 → 675.12pt).
        src_ratio = re.search(r'<html[^>]*data-ratio="(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)"', deck.read_text(encoding="utf-8"))
        rw, rh = (map(float, params["ratio"].split(":")) if "ratio" in params
                  else (float(src_ratio.group(1)), float(src_ratio.group(2))) if src_ratio else (16.0, 9.0))
        w_pt = float(params.get("w", 16)) * 72
        body, bad = fix_mediabox(body, w_pt, w_pt * rh / rw)
        if bad:
            return None, "PDF 쪽 크기를 맞추지 못했다"
        return body, None

    def _pdf(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        rel = urllib.parse.unquote(u.path[len("/__pdf/"):])
        body, err = self._render_pdf(rel, qs.get("lang", ["ko"])[0], qs.get("ratio", [""])[0], qs.get("w", [""])[0])
        if err:
            return self._reply(500, err.encode())
        name = urllib.parse.quote(pathlib.Path(rel).stem + ".pdf")
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{name}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None

    def do_POST(self):
        """action: save (입력 중 저장), send (피드백 보내기: 지금까지의 의견을 기록 폴더로 옮기고 .sent를 만든다),
        done (검수 완료: send와 같이 옮기고 .done을 만든 뒤 서버를 종료한다)."""
        global LAST_ACTIVE, FINISHED, TARGET, ROUND
        if self.path == "/__open":
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            rel = urllib.parse.unquote(data.get("deck", "")).lstrip("/")
            deck = (ROOT / rel).resolve()
            if ROOT not in deck.parents or not deck.exists():
                return self._reply(400, b"bad deck path")
            TARGET, ROUND, FINISHED = rel, ROUND + 1, False
            LAST_ACTIVE = time.time()
            connected = time.time() - LAST_SEEN < 10
            body = json.dumps({"round": ROUND, "connected": connected}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return None
        if self.path != "/__feedback":
            return self._reply(404, b"not found")
        if FINISHED:
            return self._reply(409, "검수가 끝나 의견을 받지 않는다".encode())
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        rel = urllib.parse.unquote(data.get("deck", "")).lstrip("/")
        deck = (ROOT / rel).resolve()
        if ROOT not in deck.parents or deck.suffix not in (".html", ".htm") or not deck.exists():
            return self._reply(400, b"bad deck path")
        LAST_ACTIVE = time.time()
        action = data.get("action") or ("done" if data.get("done") else "save")
        base = deck.with_suffix("")
        md, js = pathlib.Path(f"{base}-feedback.md"), pathlib.Path(f"{base}-feedback.json")
        md.write_text(data.get("markdown", ""), encoding="utf-8")
        js.write_text(json.dumps(data.get("json", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        if action == "save":
            return self._reply(200)
        hist = pathlib.Path(f"{base}-feedback-history")
        hist.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        sent_md = hist / f"{stamp}.md"
        md.rename(sent_md)
        js.rename(hist / f"{stamp}.json")
        signal = pathlib.Path(f"{base}-feedback.{'done' if action == 'done' else 'sent'}")
        signal.write_text(str(sent_md) + "\n", encoding="utf-8")
        if action == "done":
            FINISHED = True
        return self._reply(200, str(sent_md).encode())

    def log_message(self, fmt, *a):
        msg = fmt % a
        if "__feedback" in msg or "code 5" in msg:
            sys.stderr.write(msg + "\n")


if __name__ == "__main__":
    # 지정한 포트가 사용 중이면(다른 프로그램, 이전 서버) 다음 빈 포트를 쓴다. 사용 중인 포트에 연결하면 다른 서버의 화면이 열린다.
    server = None
    for port in range(PORT, PORT + 50):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit(f"no free port in {PORT}-{PORT + 49}")
    if port != PORT:
        print(f"port {PORT} is in use; using {port}")
    PORT = port
    print(f"serving {ROOT} at http://localhost:{PORT}/")
    if "--open" in sys.argv:
        import threading, webbrowser
        url = f"http://localhost:{PORT}/__review/" + urllib.parse.quote(sys.argv[sys.argv.index("--open") + 1].lstrip("/"))
        threading.Timer(0.5, webbrowser.open, [url]).start()
        print(f"review page: {url}")
    sys.stdout.flush()
    SERVER = server
    threading.Thread(target=watchdog, daemon=True).start()
    server.serve_forever()
