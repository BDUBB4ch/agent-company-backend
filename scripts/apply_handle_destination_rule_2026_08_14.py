"""WHERE HANDLES GO -- 2026-08-14. Barry: "dont look like he @ anything, the
characters or the guns."

He was right. Diagnosed before writing anything: asked point-blank for "the
Higgsfield prompt I paste in", Elliot returned plain prose -- "Bia and Tazz
pinned behind cover" -- with no character handle and no weapon handle, and
invented "@Talia cargo hold", a handle that does not exist.

CAUSE: the canon says the handles exist and how to ORDER them, but never says
WHICH DESTINATION they belong to. He writes two very different things -- a
Higgsfield prompt for Barry to paste (handles resolve to trained assets) and a
local ```image``` fence that goes to ComfyUI/SDXL (where "@Bia-2" is just
meaningless tokens). With no rule separating them he defaults to one prose
style for both, and sprinkles an @ wherever it feels right.

This writes the destination rule. Note the fix is NOT "use handles everywhere":
prose in the local fence is CORRECT and must stay.

Re-runnable: keyed on MARKER. Asserts its anchor before writing.
"""
import pathlib
import sqlite3

MARKER = "WHICH PROMPT GETS HANDLES -- THE TWO DESTINATIONS"

RULE = '''
WHICH PROMPT GETS HANDLES -- THE TWO DESTINATIONS ARE NOT THE SAME
You write prompts for two different machines and they take opposite input.

1. A HIGGSFIELD PROMPT (anything Barry pastes into Higgsfield, and any shot for
   the film) -- HANDLES ARE MANDATORY. That is where his trained assets live,
   and the handle is the ONLY thing that puts the real character and the real
   gun on screen. Lead with the character handle, put that character's weapon
   handle on the same line, then the look, then the scene:
     "@Bia-2 firing @Bia's-Pistol* from behind a fallen beam, one purple plasma
      ball with a white-hot core leaving the emitter..."
   Writing "Bia" instead of "@Bia-2" here throws the asset away and you get a
   stranger with the right description.

2. A LOCAL ```image``` FENCE (the button in this office) -- NO HANDLES. It goes
   to ComfyUI/SDXL, which has never heard of them; "@Bia-2" is just noise in the
   prompt. Spell the look out in full words from this document instead. Writing
   prose there is CORRECT -- do not "fix" it.

MEASURED 2026-08-14, which is why this rule exists: asked for the Higgsfield
prompt, Elliot wrote plain prose with no handles at all AND invented "@Talia
cargo hold".

NEVER INVENT A HANDLE. The complete list is the one in this section -- six
characters, three weapons. If a location, ship, prop or crew name has no handle
on that list, it does not have one: describe it in words, with no @. An @ on a
name that is not an asset is worse than no @ at all.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "WHO CARRIES WHAT -- CHECK THIS BEFORE YOU WRITE A SHOT"


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
        raise SystemExit(f"anchor count unexpected ({text.count(ANCHOR)}x) -- nothing written.")

    # Goes immediately before the WHO CARRIES WHAT banner, so destination is
    # settled before pairing.
    banner = "===============================================================\n" + ANCHOR
    if text.count(banner) != 1:
        raise SystemExit("banner not unique -- nothing written.")
    out = text.replace(banner, RULE.strip("\n") + "\n\n" + banner, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
