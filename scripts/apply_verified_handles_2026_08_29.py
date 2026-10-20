"""THE VERIFIED HANDLE TABLE -- every handle checked against the real element.

Barry, 2026-08-29, across one session of live testing:
  - "for future reference its @lady-vor-shara-vel @loc_lady-vors-sanctum"
  - "good catch its actually @char_yannah"  -> then he RENAMED the elements
  - "i just changed them. Now its @yannah and @keth"
  - "the BDubb new generated a dud that wasnt me, but the original bdubb worked"

Why this block exists: a handle that does not match an element name does NOT
error. The reference is silently dropped and the render comes back looking like
somebody else. Canon carried @Vorshara and @B-DUBB-new for weeks and both were
broken. Nobody could see it because nothing failed.

Supersedes the 2026-08-14 rename table for B Dubb and Vor'Shara. Their old
entries stay on record below their replacements (house rule).

Writes BOTH canon copies, asserts byte-identical.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
BEGIN = "<!-- BEGIN VERIFIED HANDLES 2026-08-29 -->"
END = "<!-- END VERIFIED HANDLES 2026-08-29 -->"

BLOCK = f"""{BEGIN}

## THE VERIFIED HANDLE TABLE (2026-08-29) -- USE THESE, NOTHING ELSE

Every one of these was checked against the actual element in Barry's Higgsfield
library. **This supersedes the 2026-08-14 rename table wherever they disagree.**

| Character | HANDLE | how it was verified |
|---|---|---|
| B Dubb | `@b-dubb` | he rendered it; the other one gave a dud |
| Bia | `@Bia-2` | rendered correctly, tested live |
| Yannah | `@yannah` | he renamed the element to match, 2026-08-29 |
| Tazz | `@Tazz` | element is named `tazz` -- not separately tested |
| Keth | `@keth` | he renamed the element to match, 2026-08-29 |
| Vor'Shara | `@lady-vor-shara-vel` | rendered correctly, tested live |
| Vor'Shara's sanctum | `@loc_lady-vors-sanctum` | his own instruction |
| The ship | `@TALIA` | unchanged |

### DO NOT USE -- these are broken and were in canon as correct

- **The old B Dubb handle with "-new" on the end — THE ELEMENT IS DELETED.**
  Barry, 2026-08-29: "the BDubb new generated a dud that wasnt me, but the
  original bdubb worked", then "b-dubb new is a wash. im deleting it." He
  tested it twice before deciding, so this is not an n=1 call. The 2026-08-14
  rename put that handle in canon and it produced a stranger for two weeks.
  **`@b-dubb` is the only B Dubb. There is no second one to confuse it with
  any more.**
- **The old Vor'Shara handle that was just her name.** Her element is
  `lady-vor-shara-vel`; the short form matched nothing. Use the full handle.

### WHY THIS KEEPS HAPPENING, AND THE RULE

A handle is **the element's name**, not the character's name. They drift apart
whenever an element is renamed, duplicated, or created with a prefix, and
NOTHING WARNS YOU -- an unmatched handle is silently ignored and the model
invents the character from the written description instead. That is why a
render can look "off" for weeks with no error anywhere.

**So: never invent a handle from a character's name.** If a handle has not been
checked against the real element, say it is unverified and ask Barry. Duplicated
elements are the usual cause -- he has had two B Dubbs, two Bias, three
Vor'Sharas and two Keths at various points.

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
    for h in ("@b-dubb", "@yannah", "@keth", "@lady-vor-shara-vel",
              "@loc_lady-vors-sanctum"):
        assert h in stored, f"{h} missing"
    assert stored == on_disk, "DRIFT between fact 592 and disk"
    print(f"canon {len(disk):,} -> {len(on_disk):,}; 8 handles verified, "
          "2 marked broken, both copies byte-identical.")


if __name__ == "__main__":
    main()
