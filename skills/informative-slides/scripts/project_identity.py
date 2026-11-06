#!/usr/bin/env python3
"""Read or create the slide identity used on the cover and closing slides.

Usage:
  python3 project_identity.py <project dir> [--name NAME] [--summary "한 줄 설명"] [--color "#RRGGBB"]
                              [--presenter NAME] [--org "소속"] [--team "팀"] [--logo <file>] [--no-org]

Two stores:
  user profile  ~/.config/informative-slides/profile.json (INFORMATIVE_SLIDES_HOME overrides the folder).
                presenter, org (affiliation), team, logo. Asked once, the first time the plugin is used,
                and reused in every project. The logo file is copied into the same folder.
                org = "" means "no affiliation".
  project       <project dir>/slides/identity.json. name, summary (one line saying what the project is),
                color. Reused by every deck of the same project.

Defaults: name = git repository top folder name, else the folder name; color = computed from the name.
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


def default_name(project):
    try:
        top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if top:
            return pathlib.Path(top).name
    except (OSError, subprocess.TimeoutExpired):
        pass
    return project.resolve().name


def profile_home():
    return pathlib.Path(os.environ.get("INFORMATIVE_SLIDES_HOME", pathlib.Path.home() / ".config" / "informative-slides"))


def data_uri(f):
    mime = mimetypes.guess_type(str(f))[0] or ("image/svg+xml" if f.suffix.lower() == ".svg" else "image/png")
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print(__doc__)
        sys.exit(2)
    project = pathlib.Path(args[0])
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

    # project identity
    f = project / "slides" / "identity.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
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
    out = {"project": dict(keep, file=str(f)), "profile": dict(profile or {}, file=str(pf)), "ask": ask, "notes": notes}
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
