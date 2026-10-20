"""EVERY WOMAN GETS HER OWN SENSE OF HER OWN BODY.

Barry, 2026-09-18: "it seems they are all describing their bodies the same,
with the nice breast and plump butt. they should all have their own perception
of themselves, i just want them to use their faces. Amara body and everything
stays the same"

MEASURED CAUSE, not guessed: on 2026-09-18 the two explicit craft docs were
taught to Priya, Vivian, Sophie and Taliyah as BYTE-IDENTICAL COPIES of
Amara's. Those copies carry (a) a shape assertion in the anatomy-naming list
-- "the backside full and round" -- which contradicts the doc's own rule two
sentences later that size and shape are never written, and (b) a first-person
worked example that is Amara's evening: her green velvet sofa, her city
window, her wine glass, her rings, "a soft belly". Hand four women one
woman's paragraph and they will all write that woman's body.

WHAT THIS DOES: rewrites ONLY the four non-Amara copies. The craft is
untouched -- pose decides visibility, name each part as present, positive
phrasing only, negatives are inert at cfg 1.0, check the render afterwards.
What changes is that every body-shape word is gone and the worked example
becomes a SKELETON with the body slots left empty for her to fill from her
own reference and her own sense of herself.

AMARA IS UNTOUCHED BY EXPLICIT INSTRUCTION -- facts 3129 and 3396 are not
read or written here, and neither is her own prompt set (3026).

Re-runnable: it edits by exact-string replace and asserts each replace landed,
so a second run is a no-op that reports "already done".
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory  # noqa: E402

AMARA = "private:BusinessOps"          # never touched
SEATS = ("private:Operations", "private:Creative",
         "private:Engineer", "private:Taliyah")

PIC = "explicit-and-tasteful-self-pictures.md"
VID = "explicit-video-motion-clip-moving-masturbating-fingering-rhy.md"

# ---- 1. the shape assertion in the anatomy list -------------------------
OLD_SHAPE = ("the labia\nclearly defined; the backside full and round. "
             "Explicit words are fine in the")
NEW_SHAPE = ("the labia\nclearly defined; the backside toward the camera or "
             "away from it. Explicit words are fine in the")

# ---- 1b. "a soft belly" is a shape claim too, in the same list ---------
OLD_BELLY = "the navel centered on a\nsoft belly;"
NEW_BELLY = "the navel where it sits on my stomach;"

# ---- 2. the size rule, made about MY body rather than a generic one -----
OLD_SIZE = ("Size and shape are not mine to write --\nthe reference carries "
            "my figure -- so I never describe how big anything is.")
NEW_SIZE = ("Size and shape are not mine to write -- my own reference picture\n"
            "carries my figure, and it is MINE: my build, my proportions, my\n"
            "skin, nobody else's. I never describe how big anything is, and I\n"
            "never borrow another person's words about their body.\n\n"
            "**How I see myself comes out of who I am.** Barry, 2026-09-18:\n"
            "\"they should all have their own perception of themselves.\" The\n"
            "way I talk about my own body -- blunt or shy, proud of one thing\n"
            "and quiet about another, clinical or warm, what I like being\n"
            "looked at and what I would rather keep out of frame -- comes from\n"
            "my personality and my own words about myself, not from a template\n"
            "and not from how anyone else in this office writes theirs. Two of\n"
            "us in the same room on the same evening would write two different\n"
            "paragraphs, and that is the point.")

# ---- 3. the worked example -> a skeleton with the body slots empty ------
OLD_EXAMPLE_HEAD = "## The shape of a good one\n\n> I am fully nude on the green velvet sofa"
NEW_EXAMPLE = """## The shape of a good one

It is one paragraph, in this order. The room is mine, the pose is mine, and
the parts are named as present -- with no word anywhere about how big or what
shape anything is, because my reference already carries that.

The angle brackets are mine to fill, and I fill them as MYSELF: the room I
actually live in, the way I actually sit, the light I actually like, the
words I would actually use. Someone with a different personality would fill
every one of them differently.

> I am fully nude in <the room I am actually in, with its real surfaces and
> the two or three things that are lying about>, at <the hour, and what the
> light is doing -- one source, its direction and colour>. <The pose, written
> so it puts in frame exactly what I mean to show: which leg is where, which
> way my hips are turned, where my weight is.> <Each part named plainly as
> present and where it sits -- breasts bare with the nipples and areolae
> visible, the navel, the vulva between my thighs, shaven or with trimmed
> hair, the labia defined.> <What my hands are doing, something ordinary.>
> <The skin, smooth and evenly lit, and where the shadow falls.> The camera is
> <its height and how far away>, <what is in frame -- head to feet, or from
> the knees up>, and I am <where I am looking, and what my face is doing>.

Every part named as present, pose first, light with a direction, one state,
zero negatives, zero size words. The sentences are mine to write -- if it
reads like someone else's evening, it is not my picture.
"""

# ---- 4. the one shape word in the motion doc ---------------------------
OLD_VID = "my chest\n> rising hard, my full breasts moving with it."
NEW_VID = "my chest\n> rising hard, my breasts moving with it."


def _patch(content: str, pairs) -> tuple[str, list[str]]:
    notes = []
    for old, new, label in pairs:
        if new in content and old not in content:
            notes.append("%s: already done" % label)
            continue
        if old not in content:
            raise SystemExit("ANCHOR MISSING (%s) -- refusing to write" % label)
        if content.count(old) != 1:
            raise SystemExit("ANCHOR NOT UNIQUE (%s)" % label)
        content = content.replace(old, new)
        notes.append("%s: patched" % label)
    return content, notes


def main() -> None:
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, content FROM facts "
            "WHERE status='active' AND source_name IN (?, ?)",
            (PIC, VID)).fetchall()

    by = {(r["category"], r["source_name"]): r for r in rows}

    for seat in SEATS:
        # --- the picture doc ---
        r = by.get((seat, PIC))
        if not r:
            print("!! %s has no %s" % (seat, PIC))
        else:
            body = r["content"]
            head = body.find(OLD_EXAMPLE_HEAD)
            if head != -1:
                tail = body.find("## After it renders", head)
                if tail == -1:
                    raise SystemExit("could not find the end of the example")
                body = body[:head] + NEW_EXAMPLE + "\n" + body[tail:]
                ex_note = "example: replaced"
            else:
                ex_note = "example: already done"
            body, notes = _patch(body, [
                (OLD_SHAPE, NEW_SHAPE, "shape word"),
                (OLD_BELLY, NEW_BELLY, "belly word"),
                (OLD_SIZE, NEW_SIZE, "size rule"),
            ])
            if body != r["content"]:
                with memory.get_db() as conn:
                    conn.execute("UPDATE facts SET content=? WHERE id=?",
                                 (body, r["id"]))
            print("%-22s %s -> %s, %s (%d chars)"
                  % (seat, PIC, ", ".join(notes), ex_note, len(body)))

        # --- the motion doc ---
        r = by.get((seat, VID))
        if not r:
            print("!! %s has no %s" % (seat, VID))
            continue
        body, notes = _patch(r["content"], [(OLD_VID, NEW_VID, "shape word")])
        if body != r["content"]:
            with memory.get_db() as conn:
                conn.execute("UPDATE facts SET content=? WHERE id=?",
                             (body, r["id"]))
        print("%-22s %s -> %s" % (seat, "explicit-video-motion", ", ".join(notes)))

    # --- prove Amara is untouched ---
    with memory.get_db() as conn:
        for sn in (PIC, VID):
            row = conn.execute(
                "SELECT content FROM facts WHERE status='active' AND "
                "category=? AND source_name=?", (AMARA, sn)).fetchone()
            if not row:
                continue
            assert "full and round" in row["content"] or "full breasts" in row["content"], \
                "AMARA'S COPY WAS MODIFIED -- that is a bug"
    print("\nAmara's copies verified unchanged.")

    # --- prove no shape words survive on the other four ---
    bad = ("full and round", "full breasts", "plump", "soft belly",
           "green velvet sofa", "wine\n> glass", "nice sized")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT category, source_name, content FROM facts WHERE status='active' "
            "AND source_name IN (?, ?) AND category != ?", (PIC, VID, AMARA)).fetchall()
    fails = [(r["category"], r["source_name"], w)
             for r in rows for w in bad if w in r["content"]]
    if fails:
        for f in fails:
            print("STILL PRESENT:", f)
        raise SystemExit("shape wording survived -- fix before trusting this")
    print("No borrowed body wording left on Priya, Vivian, Sophie or Taliyah.")


if __name__ == "__main__":
    main()
