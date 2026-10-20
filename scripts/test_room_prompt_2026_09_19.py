"""Room-plate prompts: the furniture stays, the person goes.

Run after ANY change to main._room_only_prompt, _ROOM_PERSON_WORD or
_ROOM_SELF_POSITION.

    venv/Scripts/python.exe scripts/test_room_prompt_2026_09_19.py

WHY THIS EXISTS (2026-09-19). The `home` and `lab` slots are ROOM plates --
nobody in frame, Barry's "i do want that". Three seats had a person in theirs
anyway, for two reasons that both live in this one function:

  * the office appended ", no people, empty room" to the POSITIVE prompt, and
    a word after "no" still gets painted (his own realism rule); the negative
    field is inert on Qwen at cfg 1.0, so there was nowhere else for it to go.
  * they describe their own place in the FIRST PERSON, because that is how
    anyone describes where they live.

Both directions are tested, and the furniture cases are the ones that matter:
an over-eager stripper empties the room it is supposed to be rendering. Every
one of these came from a real description or a real near-miss found while
writing it -- "a ceramic mug SITTING on the desk" is why no verbs are matched,
"dried HERbs" is why the person words are word-bounded, and "My bedroom" is
why a bare possessive is deleted instead of dropping the clause.

No GPU, no model, no database writes: pure text in, text out.
"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

# Lift the function out of main.py rather than importing it -- importing main
# builds the whole FastAPI app (the reason preflight skips it too).
_SRC = open(os.path.join(_ROOT, "backend", "main.py"), encoding="utf-8").read()
_NS = {"re": re}
exec(_SRC[_SRC.index("_ROOM_SELF_POSITION = re.compile"):
          _SRC.index("def _person_first_name")], _NS)
exec(_SRC[_SRC.index("def _room_only_prompt"):
          _SRC.index("def _self_reference")], _NS)
_room_only_prompt = _NS["_room_only_prompt"]

TAIL = ("photorealistic interior photograph of the empty room itself, "
        "furniture and objects only")

# (label, description, must still be in the prompt, must NOT be, person name)
CASES = [
    # --- the room has to survive ------------------------------------------
    ("furniture verbs are not people",
     "a ceramic mug sitting on the desk, a lamp standing in the corner and a "
     "rug on the oak floor",
     ["mug", "lamp", "rug"], [], "Sophie"),
    ("hyphenated hand- is not a hand",
     "a hand-carved shelf and a hand-painted vase on the stone mantel by the "
     "window",
     ["hand-carved", "vase", "mantel"], [], "Sophie"),
    ("herbs is not her",
     "dried herbs in ceramic bowls, a mortar and pestle on the long wooden "
     "table",
     ["herbs", "mortar", "table"], [], "Ilnora"),
    ("a sofa may lean",
     "a worn sofa leans against the wall beside a small floor lamp and a "
     "woven rug",
     ["sofa", "lamp", "rug"], [], "Victor"),
    ("a bare possessive keeps its room",
     "My bedroom at night with tall windows, a brass bed and a wide oak "
     "writing desk",
     ["bedroom", "brass bed", "desk"], ["my "], "Ilnora"),
    ("positional self, furniture kept",
     "There is a bookshelf behind me with leather-bound manuals and a tall "
     "arched window",
     ["bookshelf", "manuals", "window"], [" me"], "Ilnora"),

    # --- the person has to go ---------------------------------------------
    ("first person and wardrobe",
     "a wide oak desk under the window, I am standing with one hand on it, "
     "wearing a green gown",
     ["desk", "window"], ["standing", "hand", "gown", "wearing"], "Ilnora"),
    ("their own name",
     "a charcoal chaise near the tall window, Sophie sitting on it in a black "
     "lace bra, hair loose",
     ["chaise", "window"], ["sophie", "bra", "hair"], "Sophie"),
    ("an absence is never stated",
     "a clean counter with a kettle and two mugs. No laptop. Nothing on the "
     "walls.",
     ["counter", "kettle"], ["no laptop", "nothing on the walls"], "Priya"),
    ("no one in it",
     "the room is quiet and lived-in with a faded rug, still -- no one in it",
     ["rug"], ["no one"], "Victor"),
    ("all person leaves a room, never the person",
     "I am standing there in my robe, hair loose, skin warm",
     [], ["standing", "robe", "hair", "skin"], "Sophie"),
]


def main() -> int:
    fails = 0
    for label, text, keep, drop, name in CASES:
        out = _room_only_prompt(text, name)
        low = out.lower()
        if TAIL not in out:
            print(f"  FAIL {label}\n        room clause missing: {out}")
            fails += 1
            continue
        body = low.replace(TAIL, " ")
        bad = [f"lost {w!r}" for w in keep if w.lower() not in body]
        bad += [f"kept {w!r}" for w in drop if w.lower() in body]
        print(("  ok   " if not bad else "  FAIL ") + label)
        if bad:
            print("        ->", out)
            print("        ", "; ".join(bad))
            fails += 1
    print()
    print("ALL PASS" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
