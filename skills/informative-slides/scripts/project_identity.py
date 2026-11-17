#!/usr/bin/env python3
"""Read or create the slide identity used on the cover and closing slides.

Usage:
  python3 project_identity.py [<project dir>] [--name NAME] [--summary "한 줄 설명"] [--color "#RRGGBB"]
                              [--presenter NAME] [--org "소속"] [--team "팀"] [--logo <file>] [--no-org]

Two stores:
  user profile  ~/.config/informative-slides/profile.json (INFORMATIVE_SLIDES_HOME overrides the folder).
                presenter, org (affiliation), team, logo. Asked once, the first time the plugin is used,
                and reused in every project. The logo file is copied into the same folder.
                org = "" means "no affiliation".
  project       <project root>/.informative-slides/identity.json. name, summary (one line saying what the project is),
                color. Reused by every deck of the same project.

Project root: the top folder of the git repository that contains <project dir>; if it is not in a git
repository, <project dir> itself. <project dir> defaults to the current folder. Every deck and working file
of the skill goes in <project root>/.informative-slides/, one folder per repository, reported as out_dir.

Defaults: name = project root folder name; color = computed from the name.
The summary is written by the agent from the project's README or source material, not asked.

Rules for the color: text in this color must be readable on white (contrast 4.5:1 or more), and
it must not look like the meaning colors of the template (crit red #dc2626, new sky blue #0284c7).

Prints JSON: {"project": {...}, "profile": {...}, "logo_data_uri": ..., "ask": [...], "notes": [...]}
  ask contains "profile" when the user profile does not exist yet (ask the user once, then store it with
  --presenter/--org/--team/--logo or --no-org), and "summary" when the project summary is missing
  (write it from the README and store it with --summary).
"""
import base64
import colorsys
import hashlib
import json
import mimetypes
import pathlib
import subprocess
import sys

MEANING = {"crit": 0, "new": 199}  # hue (deg) of the template's meaning colors
HUE_GAP = 25
import os
import shutil


def lum(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_on_white(rgb):
    return 1.05 / (lum(rgb) + 0.05)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{round(c):02x}" for c in rgb)


def hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def fix_color(color, notes):
    r, g, b = (c / 255 for c in hex_to_rgb(color))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    hd = h * 360
    for name, mh in MEANING.items():
        if s > 0.25 and hue_dist(hd, mh) < HUE_GAP:
            hd = (mh + HUE_GAP * (1 if (hd - mh) % 360 < 180 else -1)) % 360
            notes.append(f"hue moved away from the {name} meaning color")
    while True:
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hd / 360, l, s))
        if contrast_on_white(rgb) >= 4.5 or l <= 0.05:
            break
        l -= 0.02
    out = rgb_to_hex(rgb)
    if out.lower() != color.lower():
        notes.append(f"color adjusted {color} -> {out} (contrast on white {contrast_on_white(rgb):.1f}:1)")
    return out


def color_from_name(name):
    hue = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16) % 360
    for mh in MEANING.values():
        if hue_dist(hue, mh) < HUE_GAP:
            hue = (hue + 2 * HUE_GAP) % 360
    return rgb_to_hex(tuple(c * 255 for c in colorsys.hls_to_rgb(hue / 360, 0.32, 0.62)))


def git_top(path):
    try:
        top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return pathlib.Path(top) if top else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def default_name(project):
    return project.resolve().name


def profile_home():
    return pathlib.Path(os.environ.get("INFORMATIVE_SLIDES_HOME", pathlib.Path.home() / ".config" / "informative-slides"))


def data_uri(f):
    mime = mimetypes.guess_type(str(f))[0] or ("image/svg+xml" if f.suffix.lower() == ".svg" else "image/png")
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    # 프로젝트 루트: 넘긴 폴더(없으면 현재 폴더)가 git 저장소 안이면 저장소 최상위 폴더, 아니면 그 폴더.
    # 저장 폴더와 프로젝트 이름이 같은 기준을 쓰고, 저장소 하나에 저장 폴더가 하나만 생긴다
    given = pathlib.Path(args[0] if args and not args[0].startswith("--") else ".").resolve()
    project = git_top(given) or given
    opt = lambda k: args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None
    notes = []

    # user profile (asked once, reused everywhere)
    home = profile_home()
    pf = home / "profile.json"
    profile = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else None
    touched = any(k in args for k in ("--presenter", "--org", "--team", "--logo", "--no-org"))
    if touched:
        profile = profile or {}
        for key in ("presenter", "org", "team"):
            if opt("--" + key) is not None:
                profile[key] = opt("--" + key)
        if "--no-org" in args:
            profile["org"] = ""
            profile.pop("logo", None)
        if opt("--logo"):
            src = pathlib.Path(opt("--logo")).expanduser()
            if not src.exists():
                print(json.dumps({"error": f"logo file not found: {src}"}, ensure_ascii=False))
                sys.exit(1)
            home.mkdir(parents=True, exist_ok=True)
            dst = home / ("logo" + src.suffix.lower())
            shutil.copyfile(src, dst)
            profile["logo"] = dst.name
            notes.append(f"logo copied to {dst}")
        home.mkdir(parents=True, exist_ok=True)
        pf.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 저장 폴더: 이 스킬이 만드는 덱과 중간 파일은 모두 <project>/.informative-slides/에 둔다.
    # 폴더 안의 .gitignore("*")가 폴더 전체를 git 추적에서 뺀다. 프로젝트의 .gitignore는 고치지 않는다.
    out_dir = project / ".informative-slides"
    out_dir.mkdir(parents=True, exist_ok=True)
    gi = out_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("# informative-slides 저장물. 이 폴더 전체를 git이 추적하지 않는다\n*\n", encoding="utf-8")
        notes.append(f"created {out_dir} (ignored by git)")

    # project identity. 이전 위치(<project>/slides/identity.json)에 있으면 그 값을 이어 쓴다
    f = out_dir / "identity.json"
    legacy = project / "slides" / "identity.json"
    src_f = f if f.exists() else legacy
    data = json.loads(src_f.read_text(encoding="utf-8")) if src_f.exists() else {}
    if src_f == legacy and legacy.exists():
        notes.append(f"read the identity from the old location {legacy}; it is now kept in {f}")
    for key in ("name", "summary", "color"):
        if opt("--" + key) is not None:
            data[key] = opt("--" + key)
    data.setdefault("name", default_name(project))
    if "color" not in data:
        data["color"] = color_from_name(data["name"])
        notes.append("color computed from the project name")
    data["color"] = fix_color(data["color"], notes)
    keep = {k: data[k] for k in ("name", "summary", "color") if k in data}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(keep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ask = []
    if profile is None:
        ask.append("profile")
    if not keep.get("summary"):
        ask.append("summary")
    out = {"project": dict(keep, file=str(f)), "root": str(project), "out_dir": str(out_dir), "profile": dict(profile or {}, file=str(pf)), "ask": ask, "notes": notes}
    if profile and profile.get("logo"):
        lf = home / profile["logo"]
        if lf.exists():
            out["logo_data_uri"] = data_uri(lf)
            if lf.stat().st_size > 300_000:
                notes.append(f"logo is {lf.stat().st_size // 1000} KB; a smaller file keeps the deck light")
        else:
            notes.append(f"profile logo not found: {lf}")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
