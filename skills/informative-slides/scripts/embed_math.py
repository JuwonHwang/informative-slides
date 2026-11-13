#!/usr/bin/env python3
"""Put the MathJax TeX renderer into a deck so its \\( ... \\) formulas render without a network.

Usage: python3 embed_math.py <deck.html>

The deck must come from assets/template.html, which has an empty <script id="mathjax-lib"></script>.
This script fills that element with assets/vendor/mathjax-tex-svg.js (MathJax 3.2.2, Apache License 2.0,
about 2.1 MB). Running it again replaces the embedded copy, so it is safe to run after every edit.
"""
import pathlib
import re
import sys

LIB = pathlib.Path(__file__).resolve().parent.parent / "assets" / "vendor" / "mathjax-tex-svg.js"
TAG = re.compile(r'(<script id="mathjax-lib">)(.*?)(</script>)', re.S)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    deck = pathlib.Path(sys.argv[1])
    src = deck.read_text(encoding="utf-8")
    if not TAG.search(src):
        sys.exit('no <script id="mathjax-lib"></script> in the deck; copy the current assets/template.html')
    lib = LIB.read_text(encoding="utf-8")
    if "</script" in lib:
        sys.exit("the MathJax file contains </script and cannot be embedded inline")
    out = TAG.sub(lambda m: m.group(1) + lib + m.group(3), src, count=1)
    deck.write_text(out, encoding="utf-8")
    print(f"embedded MathJax ({len(lib) // 1024} KB) into {deck}")


if __name__ == "__main__":
    main()
