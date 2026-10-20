"""Correct Vor'Shara's asset handle + record her location handle.

Barry, 2026-08-29: "for future reference its @lady-vor-shara-vel
@loc_lady-vors-sanctum"

Canon has said "@Vorshara" since the 2026-08-14 rename, which explicitly
listed her as NOT RENAMED. That was wrong -- her Higgsfield element is named
`lady-vor-shara-vel`, so "@Vorshara" resolves to nothing and every prompt
Elliot writes for her silently loses her reference.

Appends a correction block rather than rewriting the 08-14 rename records --
superseded wording stays on record (house rule).

Writes BOTH canon copies and asserts byte-identical.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
BEGIN = "<!-- BEGIN VORSHARA HANDLES 2026-08-29 -->"
END = "<!-- END VORSHARA HANDLES 2026-08-29 -->"

BLOCK = f"""{BEGIN}

## HANDLE CORRECTION -- VOR'SHARA (Barry, 2026-08-29)

His words: "for future reference its @lady-vor-shara-vel @loc_lady-vors-sanctum"

**@Vorshara IS WRONG AND HAS ALWAYS BEEN WRONG.** The 2026-08-14 rename record
below lists her as "NOT RENAMED", but her actual Higgsfield element is named
`lady-vor-shara-vel`. A handle only works if it matches the element name, so
"@Vorshara" resolves to NOTHING and the reference is silently lost -- the
render still comes out, just without her.

| Use this | Not this |
|---|---|
| `@lady-vor-shara-vel` | ~~@Vorshara~~ |
| `@loc_lady-vors-sanctum` (her office/chambers) | -- |

**Her sanctum now has a handle.** This is the SECOND place-handle in the whole
project; the rule that only @TALIA carries an @ is superseded to that extent.

⚠️ **SHE HAS THREE CHARACTER ELEMENTS** in his library -- `lady-vor-shara-vel`,
`Lady-Vor'Shara-Vel` (the 6'4" fixer description), and one marked failed. Use
the handle above. If she comes back off-model, a different element resolved.

⚠️ **CHECK @Yannah BEFORE TRUSTING IT.** Her element appears to be named
`char_yonnah` -- different spelling (yonnah, not yannah) AND a `char_` prefix.
If that is the only element she has, `@Yannah` resolves to nothing exactly the
way `@Vorshara` did. Barry has not confirmed this one; ASK before writing it
into a batch of prompts.

**THE GENERAL RULE THIS TEACHES:** a handle is the ELEMENT'S NAME, not the
character's name. They drifted apart without anyone noticing because a missing
reference does not error -- it just quietly generates someone else.

{END}"""


def splice(t):
    if BEGIN in t and END in t:
        return t.split(BEGIN)[0] + BLOCK + t.split(END)[1]
    return t.rstrip() + "\n\n" + BLOCK + "\n"


def main():
    disk = open(DISK, encoding="utf-8").read()
    new = splice(disk)
    assert new.count(BEGIN) == 1
    open(DISK, "w", encoding="utf-8").write(new)

    with memory.get_db() as conn:
        row = conn.execute("SELECT content FROM facts WHERE id=592").fetchone()
        nf = splice(row["content"])
        assert nf.count(BEGIN) == 1
        conn.execute("UPDATE facts SET content=? WHERE id=592", (nf,))

    with memory.get_db() as conn:
        stored = conn.execute(
            "SELECT content FROM facts WHERE id=592").fetchone()[0]
    on_disk = open(DISK, encoding="utf-8").read()
    assert "@lady-vor-shara-vel" in stored
    assert stored == on_disk, "DRIFT between fact 592 and disk"
    print(f"canon {len(disk):,} -> {len(on_disk):,}; handles corrected, "
          "both copies byte-identical.")


if __name__ == "__main__":
    main()
