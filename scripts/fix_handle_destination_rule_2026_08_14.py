"""CORRECTION to the destination rule written earlier on 2026-08-14.

I wrote "a local ```image``` fence takes NO handles". That is WRONG, and Barry
caught the thread that exposed it ("the characters we trained needs a name
change too"). comfy_image.py has had a character @mention -> LoRA map since
2026-07-31: an @handle in a local prompt is exactly what loads his trained
likeness. The rule that IS true is narrower -- weapons have no local LoRA.

Replaces the wrong paragraph in place. Re-runnable: keyed on MARKER.
"""
import pathlib
import sqlite3

MARKER = "the CHARACTER handles work in BOTH places"

OLD = '''2. A LOCAL ```image``` FENCE (the button in this office) -- NO HANDLES. It goes
   to ComfyUI/SDXL, which has never heard of them; "@Bia-2" is just noise in the
   prompt. Spell the look out in full words from this document instead. Writing
   prose there is CORRECT -- do not "fix" it.'''

NEW = '''2. A LOCAL ```image``` FENCE (the button in this office) -- CHARACTER handles
   YES, WEAPON handles NO. The backend keeps a character-handle -> trained-LoRA
   map (comfy_image.py, since 2026-07-31), so "@Bia-2" is what actually loads
   Barry's trained likeness of her; writing "Bia" there gets you a stranger.
   Weapons are different: nothing has been trained on them locally, so SPELL
   THE GUN OUT IN WORDS in a local fence -- "her energy revolver", not
   "@Bia's-Pistol*". Add the look from this document around it; the trained
   likeness carries the face, not the wardrobe or the scene.

   So the CHARACTER handles work in BOTH places and the weapon handles are
   Higgsfield-only. The backend also rewrites a handle to the token the LoRA was
   actually trained on before it reaches the model -- the 2026-08-14 rename
   renamed Barry's asset library, it did not retrain any weights -- so you write
   the new handle and the plumbing handles the rest.'''

REPO = pathlib.Path(__file__).resolve().parent.parent


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
    if text.count(OLD) != 1:
        raise SystemExit(f"anchor missing/not unique ({text.count(OLD)}x) -- nothing written.")

    out = text.replace(OLD, NEW, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
