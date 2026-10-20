"""Routing battery for the four 2026-09-17 gap docs. Run after ANY change to
their filenames or USE WHEN lines (recall does no stemming; the filename is
the title and scores 6/word). Both directions: the doc must fire on the
phrasings Barry actually uses and stay quiet on neighbours' asks."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))

import recall  # noqa: E402

CASES = [
    ("BusinessOps", "whats my margin on MgO 10 if i run BIG15, do the math", "business-math"),
    ("BusinessOps", "is that right? check that number for me", "business-math"),
    ("BusinessOps", "what does it cost per feeding vs the emerald harvest cal-mag", "business-math"),
    ("CIO", "run the numbers on a 5500 bionova reorder", "business-math"),
    ("Marketing", "a hydro shop in denver wants to carry bionova, how do i pitch them wholesale", "selling-wholesale"),
    ("CIO", "they said they can get it cheaper from global garden, what do i say", "selling-wholesale"),
    ("BusinessOps", "the shop owner asked for net 30 on a first order", "selling-wholesale"),
    ("Operations", "put the supplier shortlist in a spreadsheet on my desk", "writing-real-documents"),
    ("Operations", "write it up as a word doc i can print", "writing-real-documents"),
    ("CIO", "send me a one pager on the wholesale plan", "writing-real-documents"),
    ("Creative", "the homepage isnt converting, redesign the hero section for mobile", "high-level-web-design"),
    ("Engineer", "critique the product page layout and the checkout flow", "high-level-web-design"),
    ("Creative", "wireframe a new landing page for gotchoback", "high-level-web-design"),
    # quiet on neighbours
    ("BusinessOps", "morning, how you doing", "(nothing)"),
    ("Creative", "make me a product shot of the silution bottle", "(not high-level-web-design)"),
    ("Engineer", "the backend is throwing 500s on /api/chat", "(not high-level-web-design)"),
    ("Marketing", "write the wednesday grower tip email", "(not selling-wholesale)"),
    ("BusinessOps", "what does cali pro grow cost me wholesale", "(not selling-wholesale)"),
]


def main() -> int:
    p = f = 0
    for off, msg, want in CASES:
        _, names = recall.recall_for_message(off, msg)
        if want == "(nothing)":
            ok = not names
        elif want.startswith("(not "):
            ok = not any(want[5:-1] in n for n in names)
        else:
            ok = any(want in n for n in names)
        p += ok
        f += (not ok)
        print(("PASS" if ok else "FAIL"), f"{off:12} {msg[:56]:58} -> {names[:3]}")
    print(f"\n{p} pass / {f} fail")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
