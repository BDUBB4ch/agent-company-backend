"""@TALIA RULING -- Barry, 2026-08-14: "it is @talia, its a location and prop"

Two things settled:
  * The handle is @Talia, confirmed by him. V7 writes some slugs as plain
    "INT. TALIA -- CARGO HOLD" while ep1-production-script writes "INT. @TALIA
    -- CARGO HOLD" 96 times. The slug formatting in a script is not the prompt
    handle: in a PROMPT it is @Talia either way.
  * The ship is BOTH a location and a prop -- a location for interiors, the
    subject/prop itself for exteriors (EXT. @TALIA -- DEEP SPACE).

Replaces one paragraph in the names roster. Nothing else is touched, and no
file of Barry's is touched. Re-runnable: keyed on MARKER.
"""
import pathlib
import sqlite3

MARKER = "@TALIA IS BOTH A LOCATION AND A PROP"

OLD = '''LOCATIONS -- lifted verbatim from the scene slugs in Barry's own EP1 scripts.
Use HIS name for a place; do not rename it, do not "improve" it, and do not
invent a new one. @TALIA is the one that carries an @ in his own writing
("INT. @TALIA -- CARGO HOLD -- CONTINUOUS"), and he @s a character's room the
same way ("@TAZZ'S QUARTERS"). No other location carries an @ in his scripts,
so do not add one.'''

NEW = '''LOCATIONS -- lifted verbatim from the scene slugs in Barry's own EP1 scripts.
Use HIS name for a place; do not rename it, do not "improve" it, and do not
invent a new one.

@TALIA IS BOTH A LOCATION AND A PROP -- Barry ruled it 2026-08-14: "it is
@talia, its a location and prop." The ship is the LOCATION for every interior
(@TALIA -- CARGO HOLD, BRIDGE, COMMON AREA...) and is herself the PROP/SUBJECT
in an exterior (EXT. @TALIA -- DEEP SPACE, matte black hull, pale turquoise
running lights). Either way she is named @Talia in a prompt.

Do not be thrown by the scripts disagreeing with each other on this: V7 writes
some slugs plain ("INT. TALIA -- CARGO HOLD"), ep1-production-script writes
"INT. @TALIA -- CARGO HOLD" 96 times. SLUG FORMATTING IN A SCRIPT IS NOT THE
PROMPT HANDLE. In a prompt it is @Talia, always.

He @s a character's room the same way ("@TAZZ'S QUARTERS"). @Talia is the ONLY
place-name with a handle -- no other location carries an @ in his scripts, so
do not add one (it is BLACK SITE, never @BLACK_SITE).'''

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
