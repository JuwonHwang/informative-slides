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
        if self.path == "/__ping":
            return self._reply(200)
        if self.path.startswith("/__pdf/"):
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
        if self.path != "/__feedback":
            return self._reply(404, b"not found")
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        rel = urllib.parse.unquote(data.get("deck", "")).lstrip("/")
        deck = (ROOT / rel).resolve()
        if ROOT not in deck.parents or deck.suffix not in (".html", ".htm") or not deck.exists():
            return self._reply(400, b"bad deck path")
        base = deck.with_suffix("")
        pathlib.Path(f"{base}-feedback.md").write_text(data.get("markdown", ""), encoding="utf-8")
        pathlib.Path(f"{base}-feedback.json").write_text(
            json.dumps(data.get("json", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        done = pathlib.Path(f"{base}-feedback.done")
        if data.get("done"):
            done.write_text("done\n", encoding="utf-8")
        elif done.exists():
            done.unlink()
        return self._reply(200)

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
    server.serve_forever()
