"""EVERY MENTION GETS THE HANDLE -- Barry, 2026-08-14: "everytime their name is
mentioned, it needs to be their @ name."

Adds the rule to the names roster in the canon. The same rule also went into the
system-prompt tail in main.py, which is the copy that demonstrably fires.

Re-runnable: keyed on MARKER.
"""
import pathlib
import sqlite3

MARKER = "EVERY MENTION GETS THE HANDLE"

RULE = '''
EVERY MENTION GETS THE HANDLE -- not just the first one
Barry, 2026-08-14: "everytime their name is mentioned, it needs to be their @
name." First mention, last mention, and every possessive in between:
  RIGHT: "@Bia-2 fires @Bia's-Pistol*, one plasma ball leaving @Bia-2's emitter"
  WRONG: "@Bia-2 fires, one plasma ball leaving Bia's emitter"
A bare name anywhere in a prompt is a miss, including inside a positive-locks
line at the end, where it is easiest to slip. If you name the character, you
name her with the handle.

The local pipeline understands the possessive form -- "@Bia-2's" loads her
trained LoRA exactly like "@Bia-2" and is rewritten to the trained token before
it reaches the model (comfy_image.py, _split_possessive). So writing it the way
Barry asked costs nothing locally.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "WEAPONS -- HIGGSFIELD ONLY."


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

    out = text.replace(ANCHOR, RULE.strip("\n") + "\n\n" + ANCHOR, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
