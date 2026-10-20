"""Drop 'camel toe' from Bia's prompt guardrails.

Barry, 2026-08-10: "i dont mind camel toe. if it happens then it happens. that was
from when Bia was going to be a survivalist ... but going to different planets, but
i changed that."

So that item was written for an ABANDONED version of the character and no longer
applies. The REST of his guardrail list is untouched -- he carved out this one item,
he did not withdraw the list.
"""
import pathlib
import sqlite3

OLD = "  - no sexual framing / crotch emphasis / camel toe"
NEW = """  - no sexual framing / crotch emphasis
    (NOTE, Barry 2026-08-10: "camel toe" was dropped from this line -- "i dont mind
     camel toe. if it happens then it happens." It belonged to an ABANDONED concept
     where Bia was a survivalist travelling to different planets; he changed that,
     so the restriction went with it. Not something to seek out or frame a shot
     around -- simply no longer a defect if it occurs naturally in the wardrobe.)"""

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
        print(f"disk canon -> {len(s):,} chars")
    else:
        print("disk canon: guardrail line not found")

    conn = sqlite3.connect(REPO / "data" / "brain.db")
    t, ok = patch(conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0])
    if ok:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (t,))
        conn.commit()
        print(f"fact 592   -> {len(t):,} chars")
    else:
        print("fact 592: guardrail line not found")


if __name__ == "__main__":
    main()
