"""HANDLE SUBSTITUTION RULE -- Barry, 2026-08-14.

His instruction: "tell him to change it in the script, but dont change the
script itself, or you rewrite with the new names. dont change anything else"

So Elliot swaps the handle at the moment he writes a prompt, and the stored
script stays exactly as Barry authored it. NOTHING in his EP1 files is edited
by this script -- the only thing written is a rule into the canon (disk +
facts.id=592), which is pinned in full for Elliot and shared to all 9.

Re-runnable: keyed on MARKER. Asserts its anchor before writing.
"""
import pathlib
import sqlite3

MARKER = "OLD HANDLES IN BARRY'S EXISTING SCRIPTS"

RULE = '''
OLD HANDLES IN BARRY'S EXISTING SCRIPTS -- SUBSTITUTE, NEVER EDIT
His EP1 documents were written before the rename and still carry the old
handles: ep1-scene-anchor-prompts, ep1-scene-anchors, ep1-wrong-box-script-
CANON-v7, ep1-production-script, talia-crew-brain-dump, bia-adventurer-
storyboard, talia-crew-project-overview. Two of them also still say "alien
pistol" instead of naming a weapon.

* SWAP AS YOU WRITE. Where a file says @Bia, you type @Bia-2. Where it says
  @BDUBB, you type @B-DUBB-new. Where it says "alien pistol", name the weapon
  handle instead: @Bia's-Pistol*, @Yannah's-Machine-Pistol, @Tazz's-Weapon.
  @Yannah, @Tazz, @Keth and @Vorshara are unchanged, so those pass through.

* DO NOT EDIT THOSE FILES. They are Barry's authored scripts. His instruction,
  2026-08-14, verbatim: "tell him to change it in the script, but dont change
  the script itself, or you rewrite with the new names. dont change anything
  else." The document on disk stays exactly as he wrote it; the substitution
  happens in the prompt you hand to the image or video model.

* NAMES ONLY. Nothing else in his scripts changes -- not a line of dialogue,
  not a shot, not a beat, not a description. If something else in an old file
  looks wrong to you, say so and stop. You do not fix it.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "NOT RENAMED, so do not change them: @Keth and @Vorshara."


def main() -> None:
    disk = REPO / "data" / "barry-character-canon.md"
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    text = disk.read_text(encoding="utf-8")

    if text != fact:
        raise SystemExit("disk canon and fact 592 have DRIFTED -- fix that first.")
    if MARKER in text:
        print("already applied")
        return
    if text.count(ANCHOR) != 1:
        raise SystemExit(f"anchor missing/not unique ({text.count(ANCHOR)}x) -- nothing written.")

    # Sits directly after the handle table, before "HOW TO USE THEM".
    out = text.replace(ANCHOR, ANCHOR + "\n" + RULE, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
