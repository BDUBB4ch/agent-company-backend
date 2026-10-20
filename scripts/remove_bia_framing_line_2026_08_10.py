"""Remove the camera-framing sentence from Bia's FIGURE block.

Barry, 2026-08-10: "No low angles up at her, no rear or crotch framing as the
subject, no arched-back pin-up posing. we can get rid of that line."

That sentence was CLAUDE'S elaboration, not his. His own guardrail list from the
same day ("no pin-up posing", "no sexual framing / crotch emphasis / camel toe",
"documentary realism") is untouched -- he pointed at my restatement, not at his
own list.
"""
import pathlib
import sqlite3

OLD = """    realism" still stand. Her figure reads through BUILD and WARDROBE FIT, never through
    the camera leering -- no low angles up at her, no crotch or rear framing as the subject
    of the shot, no arched-back posing."""
NEW = """    realism" still stand. Her figure reads through BUILD and WARDROBE FIT."""

REPO = pathlib.Path(__file__).resolve().parent.parent


def patch(text: str) -> tuple:
    if OLD in text:
        return text.replace(OLD, NEW, 1), True
    return text, False


def main() -> None:
    disk = REPO / "data" / "barry-character-canon.md"
    s, ok = patch(disk.read_text(encoding="utf-8"))
    if ok:
        disk.write_text(s, encoding="utf-8")
        print(f"disk canon -> {len(s):,} chars (line removed)")
    else:
        print("disk canon: line not found (already removed?)")

    conn = sqlite3.connect(REPO / "data" / "brain.db")
    t, ok = patch(conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0])
    if ok:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (t,))
        conn.commit()
        print(f"fact 592   -> {len(t):,} chars (line removed)")
    else:
        print("fact 592: line not found (already removed?)")


if __name__ == "__main__":
    main()
