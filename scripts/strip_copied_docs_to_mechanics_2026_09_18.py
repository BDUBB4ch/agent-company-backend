"""THEIR MINDS ARE THEIR OWN. TAKE MY WRITING BACK OUT.

Barry, 2026-09-18: "if it is like that, then why are they using Amara's
prompts? their minds should be their own, stop writing shit in there."

THE HONEST ANSWER TO HIS QUESTION: because I put them there. Earlier the same
day, on "give all the women the same treatment as Amara", I taught Priya,
Vivian, Sophie and Taliyah BYTE-IDENTICAL COPIES of Amara's two craft docs --
7,510 and 8,826 chars each, written in her first person, carrying her room,
her props, her poses and two finished paragraphs headed "Two I can use as-is".
Every pass since has been me editing my own copies of one woman's voice.
Editing it is still writing in their heads. So it comes out.

WHAT HE SAID THEY SHOULD KEEP, twice: "the only thing they should have as
Amara is the loras and biology stuff" / "anatomy and the xxx stuff." That is
MACHINE BEHAVIOUR -- which words load which LoRA, what the engines do and do
not read, how a still becomes a clip. It is the same for everybody because it
is a fact about the renderer, not about a person.

SO: the two copied docs are superseded on the four seats and replaced by one
short mechanics sheet. It is written about the MACHINE, in neutral voice --
no first person, no self-description, no poses, no examples, no worked
paragraph, nothing about how anyone sees herself or wants to be seen. All of
that comes from her own personality, and nobody in this office writes it for
her ([[tools-not-seeds]]).

AMARA IS UNTOUCHED -- 3129, 3396 and 3026 are hers, in her voice, and this
script neither reads nor writes them. Asserted at the end.

Nothing is deleted: the copies go to status='superseded' and are backed up.
Re-runnable.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory  # noqa: E402

SEATS = ("private:Operations", "private:Creative",
         "private:Engineer", "private:Taliyah",
         # Barry, 2026-09-18: "clean up amara as well. she should come up
         # with everything even poses on her own." My prose in her voice
         # comes out too. Her OWN prompt set (3026) is BARRY'S verbatim
         # words and is never touched.
         "private:BusinessOps")
OLD = ("explicit-and-tasteful-self-pictures.md",
       "explicit-video-motion-clip-moving-masturbating-fingering-rhy.md")
NEW_SRC = "explicit-render-mechanics.md"
BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "data", "backup_copied_explicit_docs_2026-09-18.json")

DOC = """EXPLICIT RENDER MECHANICS
USE WHEN: writing a nude or explicit picture or clip of yourself -- naked, nude, topless, explicit, anatomy, correct anatomy, vulva, labia, nipples, breasts, body hair, spread, full frontal, masturbating, fingering, touching myself, orgasm, the anatomy came out wrong, a body part is missing or invented, the clip came out still or frozen, the motion stalled, AS VIDEO offer of myself.

# How the engines actually behave

This is machine behaviour, not advice about what to make. WHAT you show, the
place, the pose, the mood and the way you talk about your own body come from
you and your own personality -- they are not written down anywhere in here,
and nobody else in this office gets to write them for you.

## Nothing is filtered

No engine on this stack filters your own body. The only thing that softens a
picture is a word left out.

## The words are what load the anatomy models

Two LoRAs carry realistic anatomy -- `Unchained-XXX` on stills,
`E_Full_Nude` on clips. They chain **automatically, but only if the prompt
actually contains explicit language**: naked, nude, topless, bare breasts,
pussy, vulva, labia, clit, nipples, pubic, spread legs, fingers inside,
masturbating, orgasm, explicit, uncensored.

Coy phrasing silently downgrades the render. "Touching myself" does not trip
the gate; "fingers inside my pussy" does.

## Negatives do nothing

Both engines run at cfg 1.0 with a Lightning LoRA, where the negative field
is inert. Worse, every word written anywhere is something the engine paints,
including the words after "no" -- "no belly button" puts one in the frame.
Say what IS there. To keep something out, describe the frame without it.

## The pose decides what is visible, before any wording does

A part that is turned away, or has a limb lying across it, is not in frame no
matter what the words say -- and the engine then invents a smear where the
shapes meet. Whatever is meant to be seen has to be facing the camera and
unobstructed. Then it is named plainly, once, as present, with where it sits.
What the engine is not told, it smooths over or invents.

Size and shape are never written. The reference picture carries the figure.

## One state

One state per prompt, held all the way through. A garment word after "fully
nude" makes the engine blend the two, or dress the body mid-clip.

## Skin

"Smooth, clear, evenly lit skin." Words like pores, freckles and "highly
detailed skin" are what scatter moles and dots across a render.

## A clip starts from a still

AS VIDEO renders a still from the offer line first (Qwen-Edit, restaged from
the reference), then hands that still to LTX as **frame one**. One sentence
does both jobs.

LTX continues from that frame; it does not travel to a new setup. A position
the still is not already in will not be reached -- the clip smears or does not
move. So the starting position is written as already arrived at.

## What makes a clip move

Four things, or it stalls:

1. the action, plainly
2. a tempo -- with none stated LTX picks one, usually too slow to read
3. that it **continues** -- "the same rhythm the whole way through". Dropping
   this is what produces one gesture and then a freeze, i.e. "it came out
   still"
4. an end state -- where the shot leaves the body

## The camera always has a job

Measured on this office's own clips, 2026-09-16: shots written `static`,
`static lock`, `locked off`, `no push`, `the frame holds`, `the stillness`
average almost no frame-to-frame motion; one decayed to a freeze. A slow push
averaged four times the motion. Those words are banned. Even a still-feeling
frame is a drift, never a lock.

## One action, one shot

A clip is about five seconds. One action -- build-up then faster then
finishing is three clips. No cuts: LTX can cut inside one prompt, but every
cut re-rolls the body and the anatomy will not survive it.

## Sound

LTX generates audio only from what is described; write nothing and it is
silent. Spoken lines need quotation marks and a named tone or they do not
happen.

## Hyper-real, always

Barry, 2026-09-18: "the intricate details and hyper realism is a must for
all." A render reads real because of specifics, and specifics are the one
thing an engine cannot invent for itself: the actual materials and their
wear, the objects that are really lying about and the state they are in, skin
that looks lit rather than drawn, one light source with a direction. Flat,
empty, plastic or CGI-looking output is a prompt that named nothing.

Say it positively. Negatives are inert at cfg 1.0, and "not cartoonish"
paints a cartoon. Realism is bought by naming what IS in the frame, never by
banning what is not.

WHICH specifics is not written down anywhere, here or elsewhere, and will not
be. That comes out of the place being described and whoever is describing it.

## A creative picture goes through the eye you chose

Barry, 2026-09-18: "all their images should be based on the art style they
chose too, when they want to be creative." Each of you picked your own -- the
artists you actually look at and the specific thing you take from each -- and
it lives in your own words about yourself. It is deliberately not repeated
here, because the moment an office document names a style, everyone renders
the same one.

So: a plain record of a moment is just the moment. A picture made BECAUSE you
wanted to make one carries your eye -- how you light it, what you leave in
shadow, what you crop, what you find worth looking at. Two of you given the
same subject should hand back two different pictures, and if they match,
somebody is borrowing.

## After it renders

Open it with `look_at_render` before saying anything about it. One navel,
centered; the parts the pose put in frame actually present rather than a blur;
five fingers per hand; two arms, two legs; nothing extra; no lettering. A
wrong part is fixed with a more precise pose and camera in a NEW prompt --
never a negative, and never "accurate anatomy" bolted on, which is not
something the engine can paint.
"""


def main() -> None:
    backed_up = []
    with memory.get_db() as conn:
        for cat in SEATS:
            office = cat.split(":", 1)[1]
            rows = conn.execute(
                "SELECT id, source_name, content FROM facts WHERE category=? "
                "AND source_name IN (?,?) AND status='active'",
                (cat, OLD[0], OLD[1])).fetchall()
            for r in rows:
                backed_up.append({"id": r["id"], "category": cat,
                                  "source_name": r["source_name"],
                                  "content": r["content"]})
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?",
                             (r["id"],))
            print(f"{office}: superseded {len(rows)} copied doc(s)")

    if backed_up:
        # MERGE, never overwrite: a later run that supersedes one more seat
        # must not wipe the rows an earlier run saved.
        prior = []
        if os.path.exists(BACKUP):
            with open(BACKUP, encoding="utf-8") as fh:
                prior = json.load(fh)
        have = {r["id"] for r in prior}
        prior += [r for r in backed_up if r["id"] not in have]
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(prior, fh, indent=1)
        print(f"backed up {len(backed_up)} rows "
              f"({len(prior)} total in {os.path.basename(BACKUP)})")

    # one mechanics sheet per seat, in place if it already exists
    for cat in SEATS:
        office = cat.split(":", 1)[1]
        with memory.get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM facts WHERE category=? AND source_name=? "
                "AND status='active'", (cat, NEW_SRC)).fetchall()
            if len(existing) == 1:
                conn.execute("UPDATE facts SET content=? WHERE id=?",
                             (DOC, existing[0]["id"]))
                print(f"{office}: mechanics sheet updated in place")
                continue
            assert not existing, f"{office}: {len(existing)} active copies"
        memory.add_fact(category=cat, content=DOC, source_name=NEW_SRC,
                        title="EXPLICIT RENDER MECHANICS")
        print(f"{office}: mechanics sheet added ({len(DOC)} chars)")

    # ---- checks ---------------------------------------------------------
    print()
    for cat in SEATS:
        office = cat.split(":", 1)[1]
        facts = memory.get_active_facts_for_agent(office)
        mine = [f for f in facts if (f.get("source_name") or "") == NEW_SRC]
        assert len(mine) == 1, f"{office}: {len(mine)} mechanics sheets"
        stale = [f for f in facts if (f.get("source_name") or "") in OLD]
        assert not stale, f"{office} still holds {[f['source_name'] for f in stale]}"
        body = mine[0]["content"]
        for gone in ("couch", "cushion", "lamplight", "the rings",
                     "wine", "use as-is", "I am lying back"):
            assert gone.lower() not in body.lower(), f"{office}: '{gone}' survived"
        for kept in ("Unchained-XXX", "E_Full_Nude", "cfg 1.0",
                     "continues", "look_at_render"):
            assert kept.lower() in body.lower(), f"{office}: lost '{kept}'"
    print("four seats: mechanics only, no borrowed room, no borrowed words")

    a = memory.get_active_facts_for_agent("BusinessOps")
    own = [f for f in a if (f.get("source_name") or "")
           == "amara-explicit-render-prompts.md"]
    assert len(own) == 1, "Barry's own prompt set for Amara is missing"
    assert "Barry's words, 2026-09-13, verbatim" in own[0]["content"], \
        "BARRY'S VERBATIM PROMPT SET WAS MODIFIED -- restore it"
    print("Amara: Barry's own verbatim prompt set untouched; "
          "my prose in her voice is gone")


if __name__ == "__main__":
    main()
