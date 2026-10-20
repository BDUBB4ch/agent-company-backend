"""Battery for the 2026-08-25 Glock -> @B-Dubb's-Banger rename.

Two mechanisms, both Elliot-only:
  1. main._fix_weapon_handles  -- rewrites a described gun into its handle
     inside ```image``` fences, iff the owner's handle is in the same fence.
  2. comfy_image.normalize_mentions -- turns the handle back into plain words
     for local SDXL, where no weapon LoRA exists.

Run after any change to _WEAPON_HANDLE_FIXES or WEAPON_HANDLE_WORDS.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import comfy_image as ci  # noqa: E402

# Load only the two pieces we need out of main.py -- importing main boots
# FastAPI, the watchdog hooks and the whole agent stack.
src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
ns = {"re": re}
exec(src[src.index("_WEAPON_HANDLE_FIXES = ["):src.index("_IMAGE_FENCE_BODY_RE")], ns)
ns["_IMAGE_FENCE_BODY_RE"] = re.compile(r"(```image\s*\n)(.*?)(```)", re.DOTALL)
exec(src[src.index("def _fix_weapon_handles"):src.index("def _fix_voice_lock_brackets")], ns)
fix = ns["_fix_weapon_handles"]

FENCE = "```image\n{}\n```"
fails = []


def check(name, got, want, mode="in"):
    ok = (want in got) if mode == "in" else (want not in got)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        print(f"         wanted {'' if mode == 'in' else 'NOT '}{want!r}")
        print(f"         got    {got!r}")
        fails.append(name)


print("\n-- 1. fence rewrite: old trademark -> handle --")
for label, body in [
    ("bare 'Glock .40'", "@B-DUBB-new rises, Glock .40 level, pendant swinging"),
    ("'his Glock'", "@B-DUBB-new in the crate, his Glock drawn, muzzle up"),
    ("'.40 caliber pistol'", "@B-DUBB-new raises his .40 caliber pistol"),
    ("'the black glock' lowercase", "@B-DUBB-new, the black glock up"),
]:
    out = fix(FENCE.format(body))
    check(f"{label} -> handle", out, "@B-Dubb's-Banger")
    check(f"{label} -- trademark gone", out.lower(), "glock", mode="not")

print("\n-- 2. the owner guard still holds --")
out = fix(FENCE.format("A site guard with a glock at the fence line"))
check("no owner handle -> NOT rewritten", out, "@B-Dubb's-Banger", mode="not")
out = fix(FENCE.format("@Bia-2 alone, energy revolver up"))
check("Bia's own weapon still converts", out, "@Bia's-Pistol*")

print("\n-- 3. prose outside a fence is never touched --")
prose = "He kept the Glock low as he moved through the tree line."
check("directing prose untouched", fix(prose), prose)

print("\n-- 4. local SDXL: handle -> plain words, LoRA still loads --")
out = ci.normalize_mentions("@B-DUBB-new raises @B-Dubb's-Banger, pendant catching light")
check("handle became words", out, "his black pistol with chrome accents")
check("no junk handle left", out, "@B-Dubb", mode="not")
check("B Dubb LoRA token present", out, "@BDUBB")
check("character LoRA resolves",
      str(ci.mentioned_characters("@B-DUBB-new with @B-Dubb's-Banger")), "bdubb")
check("weapon handle ALONE loads no character",
      str(ci.mentioned_characters("@B-Dubb's-Banger on the deck")), "bdubb", mode="not")

print("\n-- 5. no trademark left in the canon or the pinned card --")
import sqlite3  # noqa: E402
con = sqlite3.connect(ROOT / "data" / "brain.db")
card = con.execute("select content from facts where id=705").fetchone()[0]
canon = con.execute("select content from facts where id=592").fetchone()[0]
check("pinned anchors card clean", card, "Glock", mode="not")
check("canon: only the 3 alien silhouette anchors remain",
      str(canon.count("Glock")), "3")

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
