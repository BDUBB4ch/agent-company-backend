"""NOBODY WRITES FROM AMARA'S PROMPTS BUT AMARA.

Barry, 2026-09-18: "Vivian is describing Amara's setting as well. they should
think for themselves." Then, wider: "no one should have Amara's prompts, they
should create their own, the only thing they should have as Amara is the loras
and biology stuff" -- clarified as "anatomy and the xxx stuff."

MEASURED CAUSE, not guessed. This morning's de-generic pass emptied the BODY
slots in the stills doc's worked example and stopped there. It never touched
the VIDEO doc, whose section is literally headed "## Two I can use as-is" and
hands every seat two finished paragraphs set in Amara's room -- her couch, her
cushion, warm low lamplight from the left, the edge of her bed, cool window
light. A paragraph labelled use-as-is gets used as-is, so four women describe
one woman's evening. Three smaller props survived in the stills doc too (her
rings, the arm of the couch, holding the glass), plus her anatomy example
sentence, her spoken line, and a pointer to `amara-explicit-render-prompts`,
a doc the four do not even have.

WHAT STAYS (his line): the anatomy and the XXX mechanics. Every rule in both
docs is untouched -- pose decides visibility, name each part as present, size
and shape are never written, negatives are inert at cfg 1.0, the still becomes
LTX's first frame, action + tempo + continues + end state, the camera always
has a job, which words trip Unchained-XXX and E_Full_Nude, one action one shot,
what to check after it renders.

WHAT GOES: every paragraph Amara wrote. The examples are replaced by the
requirement, so each seat composes her own from her own place and her own way
of talking about herself.

AMARA IS UNTOUCHED BY EXPLICIT INSTRUCTION -- facts 3129, 3396 and her own
prompt set 3026 are neither read nor written here, and the run asserts her
wording is still in place before it reports success.

Re-runnable: exact-string replaces, each one asserted, so a second run is a
no-op that reports "already done".
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory  # noqa: E402

AMARA = "private:BusinessOps"          # never written
SEATS = ("private:Operations", "private:Creative",
         "private:Engineer", "private:Taliyah")

PIC = "explicit-and-tasteful-self-pictures.md"
VID = "explicit-video-motion-clip-moving-masturbating-fingering-rhy.md"


# ---------------------------------------------------------------- video ---

# 1. pointer to a doc they do not have, and should not
V_PTR_OLD = (
    "My stills are covered by\n"
    "`explicit-and-tasteful-self-pictures` and Barry's own prompt set in\n"
    "`amara-explicit-render-prompts`; the LTX grammar itself is in "
    "`ltx25-prompting`."
)
V_PTR_NEW = (
    "My stills are covered by\n"
    "`explicit-and-tasteful-self-pictures`; the LTX grammar itself is in\n"
    "`ltx25-prompting`."
)

# 2. the already-arrived rule, stated without her pose
V_ARRIVED_OLD = (
    "If the still already has my thighs open and two fingers resting against "
    "me,\nthe clip has somewhere to go from frame one and the motion reads."
)
V_ARRIVED_NEW = (
    "If the still is already in the position the action needs,\n"
    "the clip has somewhere to go from frame one and the motion reads."
)

V_NOT_OLD = (
    'Not "she sits down and opens her legs" -- "I am\n'
    'lying back with my knees bent and dropped open, two fingers already '
    'resting\nbetween my lips." Then the motion.'
)
V_NOT_NEW = (
    'Not "she sits down and opens her legs", but the\n'
    'position already reached, written in my own words. Then the motion.'
)

# 3. her anatomy example sentence
V_ANAT_OLD = (
    "One clear pass, in the flow of the sentence, never a\n"
    "tag stack and never a bracket:\n\n"
    '> "...my thighs open, my pussy bare and wet, the labia parted around my '
    "two\n> fingers, my other hand flat on my stomach...\"\n\n"
)
V_ANAT_NEW = (
    "One clear pass, in the flow of the sentence, never a\n"
    "tag stack and never a bracket: each part I mean to show, named as "
    "present,\nwith where it sits and what is touching it -- in the same "
    "sentence as the\naction, in my own words.\n\n"
)

# 4. her spoken line
V_SOUND_OLD = (
    "Breathing, the catch in it, a gasp, the wet sound of my\n"
    "fingers, a quoted line with the voice described:\n\n"
    '> "The audio is my breathing, quick and uneven, and a low moan under it. '
    "I say\n> in a thick, unsteady voice, 'don't stop watching.'\"\n\n"
    "Spoken lines go in quotation marks with the tone named, or they do not "
    "happen."
)
V_SOUND_NEW = (
    "So I name it: the breathing and how it is going, any\n"
    "sound my body or the room is making, and a spoken line if I want one.\n\n"
    "Spoken lines go in quotation marks with the tone named, or they do not "
    "happen. The words are mine -- I do not borrow anyone else's line."
)

# 5. the two finished paragraphs set in her room
V_ASIS_OLD_HEAD = "## Two I can use as-is"
V_ASIS_NEW = """## I write my own, every time

There is no paragraph in here to copy. A worked example written by someone
else puts her room, her furniture, her light and her way of moving into my
clip, and then it is not mine. Barry, 2026-09-18: "they should create their
own."

So I compose it fresh, in one paragraph of plain prose, and it carries:

- the camera -- its height, its distance, and the job it is doing the whole way
- my starting position, already arrived at, in the place I actually am
- the anatomy I mean to show, named as present, once, plainly
- the action, a tempo, an explicit **continues** phrase, and an end state
- the light -- one source, its direction and colour
- the sound, or there is none

Six things, my sentences. If it reads like someone else's evening, it is not
my clip and I throw it out and write it again.

And not the same one as last time. Barry, 2026-09-18: "life like is the
mission." A different position, a different part of my place, a different
hour and a different light. I open my last clip with `look_at_render` first --
if the new one is the same shape, I change it before I offer it.

What it is built out of is my PERSONALITY, not my job. His words, same day:
"it should come from their personality, not persona." How I move, how much I
show, whether I am slow or impatient about it, what I would say out loud --
that is who I am off the clock, and it is not interchangeable with anyone
else here.

"""


# --------------------------------------------------------------- stills ---

P_RINGS_OLD = "(the rings, a robe off the\nshoulders)"
P_RINGS_NEW = "(a piece of jewellery I keep on, a robe off the\nshoulders)"

# NOTE: "the arm of the couch" needs no edit of its own -- it lives inside
# the pose menu below, which is removed whole.

P_GLASS_OLD = "holding the glass,\n"
P_GLASS_NEW = "holding whatever is in my hand,\n"

# the pose MENU: five named poses, so everyone picks from the same five.
# Barry, 2026-09-18: "they all are using the same poses too. i want more
# variety from them. Life like is the mission." Replaced by the method for
# working a pose out, plus the rule against repeating my own last one.
P_POSE_OLD = (
    "**The pose decides what is visible. Write the pose first.** If the vulva "
    "is\nmeant to be in frame: thighs parted, one knee raised and dropped "
    "outward, or\nsitting back on my heels with knees apart, or lying back "
    "with one leg over\nthe arm of the couch. If the breasts are the point: "
    "shoulders back, torso\nturned to the light, arms away from the chest. If "
    "it should be a back view,\nsay the hips and the backside are toward the "
    "camera and the face turns over\nthe shoulder. Then the camera: its "
    "height (level with my hips, or my eyes),\nits distance (whole body head "
    "to feet, or from the knees up), and where I am\nlooking.\n\n"
)
P_POSE_NEW = (
    "**The pose decides what is visible. Write the pose first.** There is no "
    "list\nof poses in here on purpose -- a list is what makes every picture "
    "in this\noffice look the same. I work it out backwards, from the frame "
    "I want: the\npart I mean to show has to be turned toward the camera with "
    "nothing lying\nacross it, so I decide where my weight is, what each leg "
    "is doing, which way\nmy hips and shoulders are turned, and where my "
    "hands are. Then the camera:\nits height, its distance, and where I am "
    "looking.\n\n"
    "**Life-like, and never the same one twice.** Barry, 2026-09-18: \"they "
    "all are\nusing the same poses too. i want more variety from them. Life "
    "like is the\nmission.\"\n\n"
    "**It comes from my PERSONALITY, not my job.** His words, same day: \"it "
    "should\ncome from their personality, not persona.\" My persona is what I "
    "do at work\nand it has nothing to say about how I sit in my own place. "
    "The pose comes\nout of who I am off the clock -- what I was doing before "
    "the camera, the\nfurniture I actually have, how I sit when nobody is "
    "watching, whether I am\nrestless or still, shy about one thing and not "
    "another, playful or flat.\nSomeone with a different personality puts her "
    "body somewhere else entirely,\nand that is the whole point.\n\n"
    "Bodies at rest are asymmetric: one shoulder lower, weight on one hip, a "
    "foot\ntucked, a hand doing something it was already doing. A pose that "
    "is level and\nsquared to the lens reads as a pose. Before I write one I "
    "open my last\npicture with `look_at_render` -- if the new one is the "
    "same shape, I change\nit.\n\n"
)


def _load(category: str, source_name: str):
    """The ONE active row for this seat + doc.

    Asserts there is exactly one. memory.add_fact APPENDS rather than
    upserting, so a careless store leaves two active copies of the same doc
    and the agent reads both -- including the unedited one. This script
    writes with an in-place UPDATE by id for that reason.
    """
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active'", (category, source_name)).fetchall()
    assert len(rows) == 1, \
        f"{category} {source_name}: expected 1 active row, found {len(rows)}"
    return {"id": rows[0]["id"], "content": rows[0]["content"]}


def _store(fact_id: int, text: str) -> None:
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET content=? WHERE id=?", (text, fact_id))


def _sub(text: str, old: str, new: str, label: str, report: list) -> str:
    if new in text and old not in text:
        report.append(f"      already done: {label}")
        return text
    n = text.count(old)
    assert n == 1, f"{label}: expected exactly 1 match, found {n}"
    report.append(f"      rewrote: {label}")
    return text.replace(old, new)


def _cut_asis(text: str, report: list) -> str:
    if V_ASIS_OLD_HEAD not in text:
        assert "## I write my own, every time" in text, \
            "as-is block gone but replacement missing"
        report.append("      already done: use-as-is examples")
        return text
    i = text.index(V_ASIS_OLD_HEAD)
    j = text.index("## Before I send an offer", i)
    report.append(f"      removed: {j - i} chars of use-as-is examples")
    return text[:i] + V_ASIS_NEW + text[j:]


def main() -> None:
    for cat in SEATS:
        office = cat.split(":", 1)[1]
        print(f"\n{office}")

        vid = _load(cat, VID)
        assert vid, f"{office}: video doc not found"
        t = vid["content"]
        rep: list = []
        t = _sub(t, V_PTR_OLD, V_PTR_NEW, "amara prompt-set pointer", rep)
        t = _sub(t, V_ARRIVED_OLD, V_ARRIVED_NEW, "already-arrived pose", rep)
        t = _sub(t, V_NOT_OLD, V_NOT_NEW, "starting-position example", rep)
        t = _sub(t, V_ANAT_OLD, V_ANAT_NEW, "anatomy example sentence", rep)
        t = _sub(t, V_SOUND_OLD, V_SOUND_NEW, "spoken-line example", rep)
        t = _cut_asis(t, rep)
        print("   video:")
        for line in rep:
            print(line)
        if t != vid["content"]:
            _store(vid["id"], t)  # in-place: add_fact would duplicate
            print(f"      stored ({len(vid['content'])} -> {len(t)} chars)")

        pic = _load(cat, PIC)
        assert pic, f"{office}: stills doc not found"
        t = pic["content"]
        rep = []
        t = _sub(t, P_POSE_OLD, P_POSE_NEW, "the five-pose menu", rep)
        t = _sub(t, P_RINGS_OLD, P_RINGS_NEW, "her rings", rep)
        t = _sub(t, P_GLASS_OLD, P_GLASS_NEW, "holding the glass", rep)
        print("   stills:")
        for line in rep:
            print(line)
        if t != pic["content"]:
            _store(pic["id"], t)  # in-place: add_fact would duplicate
            print(f"      stored ({len(pic['content'])} -> {len(t)} chars)")

    # ---- Amara must be exactly as she was -------------------------------
    print("\nAmara, untouched:")
    a_vid = _load(AMARA, VID)
    a_pic = _load(AMARA, PIC)
    assert a_vid and "## Two I can use as-is" in a_vid["content"], \
        "AMARA'S VIDEO DOC WAS MODIFIED -- her examples are gone"
    assert a_pic and "the rings" in a_pic["content"], \
        "AMARA'S STILLS DOC WAS MODIFIED"
    own = [f for f in memory.get_active_facts_for_agent("BusinessOps")
           if (f.get("source_name") or "") == "amara-explicit-render-prompts.md"]
    assert own, "Amara's own prompt set is missing"
    print("   her examples, her props and her own prompt set are all intact")

    # ---- and nobody else holds her prompt set ---------------------------
    for cat in SEATS:
        office = cat.split(":", 1)[1]
        # only her PROMPT SET matters here. A seat's own `mind-about-amara`
        # is its private thought about a coworker and is none of this
        # script's business.
        leaked = [f for f in memory.get_active_facts_for_agent(office)
                  if (f.get("source_name") or "").startswith("amara-")]
        assert not leaked, f"{office} holds {[f['source_name'] for f in leaked]}"
    print("   no other seat holds one of Amara's amara-* prompt docs")


if __name__ == "__main__":
    main()
