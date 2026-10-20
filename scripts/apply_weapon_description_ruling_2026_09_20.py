"""Barry's tightened weapon ruling, 2026-09-20 (later the same night).

His words: "dont mention it at all, unless its being used in that scene. it be
part of their description. @bia's-pistol in her holster on her leg as an
example. but it should just be in their bio and desription as part of their
outfit."

This REPLACES the "HOW TO WRITE IT" paragraph written earlier tonight, which
said to name the carry as part of the look in plain words. He has now ruled
that a stowed weapon is not mentioned in a shot AT ALL -- it lives in the
character's bio/description as part of the outfit, and nothing else.

Edits BOTH canon copies (fact 592 + disk), asserts them byte-identical after,
and regenerates the derived anchors card so the PINNED copy Elliot reads every
message carries it too -- the step that was missed earlier tonight and is why
he put a pistol in Yannah's hand in SHOT 01.
"""
import glob
import os
import shutil
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
BAK = os.path.join(ROOT, "data", f"backup_canon_before_weapon_description_2026-09-20.md")

OLD = """HOW TO WRITE IT: name the carry as part of the LOOK, in plain words --
"@Yannah's thigh holster", "@Tazz's blaster racked across her back on its
magnetic mount", "@b-dubb's pistol on his belt"."""

NEW = """HOW TO WRITE IT -- TIGHTENED BY BARRY 2026-09-20, HIS WORDS:
"dont mention it at all, unless its being used in that scene. it be part of
their description. @bia's-pistol in her holster on her leg as an example. but
it should just be in their bio and desription as part of their outfit."

So: A STOWED WEAPON IS NOT MENTIONED IN A SHOT AT ALL. Not by handle, and not
in plain words either. Do not write "her thigh holster", do not write "the
pistol at her hip", do not write "blaster racked across her back". If the
weapon is not being drawn, raised, fired or put away on this beat, it does not
appear in the shot's text in any form.

IT LIVES IN THE CHARACTER'S BIO AND DESCRIPTION, as part of the outfit -- the
same place their boots and their jacket live. That is where Barry's example
belongs: "@Bia's-Pistol* in her holster on her leg". Written once, there, as
part of who she is.

WHY IT STILL RENDERS: their reference image already wears it. Bia's character
reference carries a holstered sidearm on her hip, thigh rigs and a utility
belt, so the holstered gun comes through on every restage without anyone
naming it. Anything the generator will not hold reliably belongs one step
earlier, in the reference asset -- and for stowed weapons it is already there.

WHEN IT IS IN USE, the weapon handle goes in, on the same line as its carrier,
and it binds the real asset."""


def main() -> int:
    disk = open(DISK, encoding="utf-8").read()
    cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
    db = [c for c in cands if "brain" in os.path.basename(c)] or cands
    cur = sqlite3.connect(db[0]).cursor()
    cur.execute("select id, content from facts where source_name='barry-character-canon.md' "
                "and status='active'")
    fid, fact = cur.fetchone()

    if NEW[:60] in disk:
        print("already applied -- nothing to do")
        return 0

    assert disk.count(OLD) == 1, f"disk: expected 1 match, got {disk.count(OLD)}"
    assert fact.count(OLD) == 1, f"fact: expected 1 match, got {fact.count(OLD)}"

    shutil.copy2(DISK, BAK)
    print(f"backup -> {BAK}")

    new_disk = disk.replace(OLD, NEW)
    new_fact = fact.replace(OLD, NEW)
    open(DISK, "w", encoding="utf-8").write(new_disk)
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new_fact, fid))

    # the two copies drifting is the documented canon failure -- assert
    cur.execute("select content from facts where id=?", (fid,))
    stored = cur.fetchone()[0]
    assert stored == open(DISK, encoding="utf-8").read(), "canon copies DRIFTED"
    print(f"both copies updated and byte-identical: {len(stored):,} chars")

    # ---- regenerate the DERIVED pinned card (the step missed earlier) -------
    out = subprocess.run(
        [os.path.join(ROOT, "venv", "Scripts", "python.exe"),
         os.path.join(ROOT, "scripts", "build_anchors_card_2026_08_21.py")],
        capture_output=True, text=True)
    print("anchors card:", out.stdout.strip() or out.stderr.strip()[:200])

    cur.execute("select content from facts where source_name='character-anchors-card.md' "
                "and status='active'")
    card = cur.fetchone()[0]
    print("\nPINNED card now carries the ruling:",
          "NOT MENTIONED IN A SHOT AT ALL" in card)
    print("  and his own example:", "in her holster on her leg" in card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
