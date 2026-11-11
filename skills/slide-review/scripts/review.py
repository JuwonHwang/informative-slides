#!/usr/bin/env python3
"""Open a deck in the review screen on a local port, or stop the review server.

Usage:
  python3 review.py open <deck.html> [--root <dir>] [--no-browser]
  python3 review.py stop
  python3 review.py status

open
  Reuses the running review server when its root folder contains the deck. Otherwise it starts
  review_server.py in the background on a free local port (from 8765 up, 127.0.0.1 only), with the
  deck's git repository top folder as root (or the deck's folder, or --root). Then it opens the
  review page in the browser and prints:
    url       review page
    feedback  <deck>-feedback.md, written as the reader types
    done      <deck>-feedback.done, created when the reader presses 검수 완료
  When the previous review round of this deck was finished (<deck>-feedback.done exists), its
  feedback files are moved to <deck>-feedback-history/<time>.md|.json and the new round starts empty.
  An unfinished round (no .done) is kept and continues.
stop
  Stops the server started by this script.

The server's pid, port and root are kept in ~/.config/informative-slides/review-server.json
(INFORMATIVE_SLIDES_HOME overrides the folder).
"""
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path(os.environ.get("INFORMATIVE_SLIDES_HOME", pathlib.Path.home() / ".config" / "informative-slides"))
STATE = HOME / "review-server.json"


def alive(state):
    if not state:
        return False
    try:
        os.kill(state["pid"], 0)
        with urllib.request.urlopen(f"http://127.0.0.1:{state['port']}/__ping", timeout=2) as r:
            return r.read() == b"ok"
    except (OSError, ValueError, KeyError):
        return False


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def free_port(start=8765):
    for p in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    sys.exit("no free local port")


def git_top(path):
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return pathlib.Path(out) if out else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def stop(state):
    if state and alive(state):
        os.kill(state["pid"], signal.SIGTERM)
    STATE.unlink(missing_ok=True)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd = args[0]
    state = load()
    if cmd == "stop":
        stop(state)
        print(json.dumps({"stopped": True}))
        return
    if cmd == "status":
        print(json.dumps({"running": alive(state), **(state or {})}, ensure_ascii=False))
        return
    if cmd != "open" or len(args) < 2:
        print(__doc__)
        sys.exit(2)

    deck = pathlib.Path(args[1]).expanduser().resolve()
    if not deck.exists():
        sys.exit(f"deck not found: {deck}")
    root = pathlib.Path(args[args.index("--root") + 1]).resolve() if "--root" in args else (git_top(deck.parent) or deck.parent)

    if not (alive(state) and pathlib.Path(state["root"]) in [deck, *deck.parents]):
        if alive(state):
            stop(state)
        port = free_port()
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(HOME / "review-server.log", "a")
        proc = subprocess.Popen([sys.executable, str(HERE / "review_server.py"), str(root), "--port", str(port)],
                                stdout=log, stderr=log, start_new_session=True)
        state = {"pid": proc.pid, "port": port, "root": str(root)}
        for _ in range(50):
            if alive(state):
                break
            time.sleep(0.1)
        else:
            sys.exit(f"review server did not start; see {HOME / 'review-server.log'}")
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 지난 회차가 검수 완료로 끝났으면 그 의견을 기록 폴더로 옮겨 새 회차를 빈 상태로 시작한다.
    # 검수 완료 전이면 이어서 하는 중이므로 그대로 둔다.
    base = deck.with_suffix("")
    done = pathlib.Path(f"{base}-feedback.done")
    archived = None
    if done.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(done.stat().st_mtime))
        hist = pathlib.Path(f"{base}-feedback-history")
        hist.mkdir(exist_ok=True)
        for ext in ("md", "json"):
            f = pathlib.Path(f"{base}-feedback.{ext}")
            if f.exists():
                f.rename(hist / f"{stamp}.{ext}")
        done.unlink()
        archived = str(hist)
    pathlib.Path(f"{base}-feedback.sent").unlink(missing_ok=True)

    rel = deck.relative_to(pathlib.Path(state["root"]))
    url = f"http://localhost:{state['port']}/__review/" + urllib.parse.quote(str(rel))
    # 열린 검수 화면이 있으면 그 화면이 새 덱·새 회차로 내용을 바꾼다. 없을 때만 브라우저 탭을 연다.
    req = urllib.request.Request(f"http://127.0.0.1:{state['port']}/__open", method="POST",
                                 data=json.dumps({"deck": str(rel)}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        opened = json.loads(r.read())
    switched = bool(opened.get("connected"))
    if switched:
        # 열린 화면이 새 회차로 바뀌었다는 신호를 6초까지 기다린다. 화면이 닫혔거나 브라우저가 뒤 탭의 신호를 늦추면 새 탭을 연다
        switched = False
        for _ in range(24):
            time.sleep(0.25)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{state['port']}/__seen", timeout=2) as r:
                    seen = json.loads(r.read())
            except OSError:
                break
            if seen.get("round") == opened.get("round"):
                switched = True
                break
    if not switched and "--no-browser" not in args:
        webbrowser.open(url)
    print(json.dumps({"url": url, "port": state["port"], "root": state["root"],
                      "feedback": f"{base}-feedback.md", "done": f"{base}-feedback.done",
                      "archived_previous_round": archived,
                      "shown_in": "existing review tab" if switched else "new browser tab"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
