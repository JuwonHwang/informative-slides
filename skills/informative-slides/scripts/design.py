#!/usr/bin/env python3
"""Design catalog: write the chosen look of every design element into the template CSS.

Usage:
  python3 design.py apply    write the selected design into assets/template.html (the design:begin block)
  python3 design.py css      print the compiled CSS

assets/design/catalog.json lists components. Each component has properties. A property is a number (written to
a CSS variable) or a choice (each option sets CSS variables and/or adds a CSS rule). "selected" holds the value
of each property that differs from its default. The template reads the CSS variables with the defaults as
fallbacks, so an empty selection draws the template's original look.
"""
import json
import pathlib
import re
import sys

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
CATALOG = ASSETS / "design" / "catalog.json"
TEMPLATE = ASSETS / "template.html"
BLOCK = re.compile(r"(/\* design:begin[^\n]*\n)(.*?)(/\* design:end \*/)", re.S)


def fmt_num(p, v):
    v = max(p["min"], min(p["max"], float(v)))
    s = f"{round(v, 3):g}"
    return s + p["unit"] if p["unit"] not in ("", "x") else s


def component_css(comp, values):
    decl, rules = {}, []
    for key, p in comp["props"].items():
        val = values.get(key, p["default"])
        if p["type"] == "num":
            if float(val) != float(p["default"]):
                decl[p["var"]] = fmt_num(p, val)
        else:
            opt = p["options"].get(str(val)) or p["options"][str(p["default"])]
            decl.update(opt.get("vars", {}))
            if opt.get("rule"):
                rules.append(opt["rule"])
    return decl, rules


def compile_css(cat):
    out = []
    for comp in cat["components"].values():
        decl, rules = component_css(comp, comp.get("selected", {}))
        if not decl and not rules:
            continue
        out.append(f"/* {comp['name']} */")
        if decl:
            out.append(":root{" + ";".join(f"{k}:{v}" for k, v in decl.items()) + "}")
        out.extend(rules)
    return "\n".join(out) + ("\n" if out else "")


def apply():
    html = TEMPLATE.read_text(encoding="utf-8")
    if not BLOCK.search(html):
        raise SystemExit("no /* design:begin */ ... /* design:end */ block in the template")
    css = compile_css(json.loads(CATALOG.read_text(encoding="utf-8")))
    TEMPLATE.write_text(BLOCK.sub(lambda m: m.group(1) + css + m.group(3), html, count=1), encoding="utf-8")


def main():
    a = sys.argv[1:]
    if a[:1] == ["apply"]:
        apply()
        print(f"wrote the selected design into {TEMPLATE}")
    elif a[:1] == ["css"]:
        print(compile_css(json.loads(CATALOG.read_text(encoding="utf-8"))), end="")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
