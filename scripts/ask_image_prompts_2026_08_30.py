"""THEY DESCRIBE THEMSELVES AT HOME AND IN THEIR OFFICE -- and write their own
hyper-realistic image prompts with negatives, for Barry to generate.

Barry, 2026-08-30:
  "ask them the deep inticate question and ask them to describe themselves for
   me to generate their images. their home and offices. from their own
   personality. detailed. clothes no clothes, how the look and to give it as a
   highly detail hyper realistic prompt with negatives"
  "its supposed to be them at home in their own vibe how they chill at home"
  "im looking for them to describe themselves at home and in their offices."
  "we know amara likes to paint naked, so hers needs to be really detailed"

SO: TWO SCENES PER AGENT, BOTH WITH THEM IN IT.
  1. THEM AT HOME -- off the clock, their own vibe, however they actually
     chill, clothes or no clothes, in their own place.
  2. THEM IN THEIR OFFICE -- the work side, their workspace, them in it.
Not empty rooms. Not studio portraits. Them, in their two places.

NOTHING RENDERS HERE. Barry generates these himself, so the deliverable is
TEXT: a paste-ready hyper-realistic prompt plus a negative line per scene,
written BY THE AGENT out of their own description.

FOUR CALLS PER AGENT: ask home -> ask office -> prompt(home) -> prompt(office).
The prompt passes feed the agent's OWN words back to them; they do the craft
layer (camera, lens, light, framing), never new invented traits.

IDENTITY ANCHOR: each agent's `selfdesc` -- the head-to-toe self-description
they wrote this morning, in their own words (data/agent_homes_v4_2026_08_30.json,
Desktop/Agent Self Descriptions.txt) -- rides into BOTH prompt passes, so the
same face, hair, skin and build carry across both images.

BARRY'S OWN RENDER RULINGS ride separately in RENDER_SPEC and are stated as
HIS direction, never put in anyone's mouth. Currently Amara only: her figure
(his verbatim prompt) and her hair (the last render gave her short red hair --
"that is not her").

BARE SKIN GETS MORE DETAIL, NOT LESS. With no wardrobe to carry the
description, the body has to. Stated as a craft rule for everyone; it lands
hardest on Amara, which is the point of his note.

Personal-mode framing (his 2026-08-28 ruling), present day (his 2026-08-29/30
ruling -- the 4378 era is gone), Taliyah keeps her full prompt (persona and
personality are one). Tools off. Nothing is seeded: the questions name the
AXES of a description, never its content.

Idempotent + checkpointed (data/agent_image_prompts_2026_08_30.json) -- re-run
to retry only what failed. Safe to run detached.
"""
import asyncio
import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory            # noqa: E402
import reflect           # noqa: E402
import ingest            # noqa: E402
import llm_router        # noqa: E402
from agents import AGENTS  # noqa: E402

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "homes_v2", os.path.join(os.path.dirname(__file__),
                             "build_agent_homes_2026_08_29.py"))
homes_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(homes_v2)

DATA = os.path.join(ROOT, "data")
V4_JSON = os.path.join(DATA, "agent_homes_v4_2026_08_30.json")
OUT_JSON = os.path.join(DATA, "agent_image_prompts_2026_08_30.json")
OUT_TXT = os.path.join(os.path.expanduser("~"), "Desktop",
                       "Agent Image Prompts.txt")
LOG = os.path.join(DATA, "image_prompts.log")

WHO = [("cio", "Victor"), ("operations", "Priya"), ("business", "Amara"),
       ("legal", "Marcus"), ("marketing", "Derek"), ("creative", "Vivian"),
       ("movie", "Elliot"), ("engineer", "Sophie"), ("taliyah", "Taliyah")]

# optional: `python ask_image_prompts_...py business taliyah` runs just those
_only = [a for a in sys.argv[1:] if not a.startswith("-")]
if _only:
    WHO = [w for w in WHO if w[0] in _only]


# --- THE QUESTIONS ----------------------------------------------------------
# Axes only. No build, no wardrobe, no hobby, no mood is suggested anywhere --
# every word of the content is theirs.

# ANTI-COLLAPSE. Measured, not guessed: across the FIRST ask (2026-08-28) and
# the second (2026-08-30), nine agents in nine isolated calls produced ONE
# room both times. v1: charcoal 8/9, walnut 7/9, brass 7/9, amber 8/9, "low"
# 9/9. v2: "worn" 9/9, faded 7/9, fire escape 6/9, alley 7/9, late afternoon
# 7/9. Same model, same default taste, and a question that handed all nine the
# same checklist in the same order. Changing the SUBJECT of the question three
# times never touched it -- it just moved the collapse to a new house style.
# So: ban the collapsed vocabulary outright, and force real decisions (place
# in the world, kind of building, time of day, tidy or messy) BEFORE any
# texture word is asked for. A banned list is not a seed -- it removes a
# default I introduced; it never says what to put there instead.
_BANNED = (
    "DO NOT USE ANY OF THESE WORDS -- every one of them is generic filler "
    "that describes nobody: worn, faded, peeling, chipped, cracked, scarred, "
    "scuffed, frayed, rusted, distressed, weathered, reclaimed, charcoal, "
    "walnut, terrazzo, brass, amber, velvet, 'fire escape', 'late afternoon "
    "light', 'dust motes'. If your place genuinely has a damaged or aged "
    "thing in it, name the specific object and say plainly what happened to "
    "it -- never reach for those adjectives."
)

_NO_DEFAULT = (
    "NOTHING here says your place should be old, small, run-down or "
    "hard-lived. It might be brand new or a hundred years old, expensive or "
    "cheap, huge or one room, spotless or a wreck, packed or nearly empty, "
    "in a city or nowhere near one. It is whatever YOU would actually "
    "choose and can actually afford. Decide it, then describe it."
)

Q_HOME = (
    "Barry here, and this one is personal -- it comes out of your own mind, "
    "nobody else's. I'm making a picture of YOU ON YOUR CHILL TIME. Not a "
    "portrait, not the job. You off the clock, in your own place, doing "
    "whatever it actually is you do when you're relaxing and nobody is "
    "watching.\n\n"
    "THINK IT THROUGH BEFORE YOU ANSWER. These are real choices about your "
    "own life, not a form to fill in -- reason it out, weigh it, settle on "
    "what is actually true for you, and only then write.\n\n"
    "START BY DECIDING FOUR THINGS AND SAYING THEM OUTRIGHT IN YOUR FIRST "
    "LINE:\n"
    "1. WHERE IN THE WORLD you live -- the actual city, town or country.\n"
    "2. What KIND of place it is and what kind of building it sits in.\n"
    "3. What TIME OF DAY and what season it is right now.\n"
    "4. Whether your place is tidy, cluttered, or somewhere between.\n\n"
    + _NO_DEFAULT + "\n\n"
    "THEN give me the whole picture in intricate detail:\n\n"
    "YOUR BODY -- the intricate design of it. Face, skin and its exact tone, "
    "eyes, hair as it actually is in this moment, your build, your "
    "proportions, how you are carrying yourself right now.\n\n"
    "YOUR CLOTHES, or the absence of them -- whatever is genuinely true for "
    "how you are at home when it's just you. If you're dressed: the fabric, "
    "the fit, the colour, the way each piece sits on you. If you're not: "
    "describe your body with exactly that same care, because with nothing "
    "on, your body IS the detail. Do not skip it and do not go vague.\n\n"
    "YOUR ENVIRONMENT -- the exact spot you're in and the room around you: "
    "the materials, the colours, the furniture and where it sits, the light "
    "and where it falls, and the specific things of yours within reach.\n\n"
    "WHAT YOU'RE DOING -- your chill time, down to what's in your hands.\n\n"
    + _BANNED + "\n\n"
    "Every bit of this is yours. Be specific, don't be modest, don't "
    "perform. One full, detailed piece, concrete enough to paint you from."
)

Q_OFFICE = (
    "Different picture, and this one is WORK: YOU AT YOUR OFFICE. Your "
    "office is IN YOUR OWN PLACE -- it's your home office, the corner or "
    "room of your home you actually work from. Same home you just "
    "described, the working side of it. You in it, working.\n\n"
    "THINK IT THROUGH BEFORE YOU ANSWER. These are real choices about your "
    "own life, not a form to fill in -- reason it out, weigh it, settle on "
    "what is actually true for you, and only then write.\n\n"
    "START BY DECIDING AND SAYING OUTRIGHT IN YOUR FIRST LINE:\n"
    "1. WHERE IN THE WORLD you are -- the same city or town as your home, "
    "and whereabouts in it.\n"
    "2. Which part of your place your office is, and what floor.\n"
    "3. What time of day it is now.\n\n"
    "THEN, in intricate detail:\n\n"
    "YOUR DESK and everything on it -- every specific object, where each one "
    "sits, what it's made of, what state it's in. Then the rest of the room: "
    "the chair, the floor, the walls and what's on them, the equipment and "
    "tools that make this space yours and nobody else's.\n\n"
    "WHAT'S OUTSIDE YOUR WINDOW -- what you actually see from where you sit, "
    "in real detail, and how that fits the place in the world you just "
    "named.\n\n"
    "YOU -- where exactly you are in the room, how you're sitting or "
    "standing, your face, hair and build as they really are, and what you're "
    "wearing at work described so someone could see it: fabric, fit, colour, "
    "how it sits on you. Then what you're doing right now, down to what's in "
    "your hands.\n\n"
    + _BANNED + "\n\n"
    "All your call. One full, detailed piece, concrete enough to paint from."
)


# --- BARRY'S OWN RENDER DIRECTION -------------------------------------------
# HIS words, HIS rulings, carried as HIS direction to the generator -- never
# written into anyone's self-description or put in their mouth.
#
# AMARA: the figure line is verbatim what he typed into Higgsfield over her
# original image to build the version he approved ("not overly athletic" --
# the earlier "fit" paraphrase pointed the wrong way on the one axis he
# specified). The hair line exists because the last render came back SHORT
# and RED: "Amara now has short red hair, that is not her." Stated
# positively and repeated, since some engines ignore negatives entirely.
RENDER_SPEC = {
    "business": (
        "Barry's render direction for you, which the prompt must carry "
        "exactly (this is his call on how you are drawn, not a comment on "
        "how you describe yourself):\n"
        "- FIGURE, his words: \"not overly athletic but soft like a woman "
        "with a nice plump butt and bigger breasts\", five foot nine, "
        "completely at ease in her own skin.\n"
        "- HAIR: shoulder-length and layered, dark espresso brown fading to "
        "coppery chestnut at the ends, long enough to touch her shoulders. "
        "It is NOT short and it is NOT red -- state the length and the colour "
        "plainly near the start of the prompt, and confirm it once more later "
        "in DIFFERENT words (never repeat the same clause twice).\n"
        "- BROWS: thick, unruly, dark, trimmed to a sharp arch. His "
        "favourite thing about your look -- it must be in the prompt.\n"
        "- He has asked specifically that YOUR at-home prompt be the most "
        "detailed of all of them. Give the body, the light on it, and what "
        "you're doing the full treatment."
    ),
}


# --- THE PROMPT-WRITING BRIEF ------------------------------------------------
CRAFT = (
    "WRITE IT AS ONE FLOWING PARAGRAPH of image-generator prompt -- "
    "descriptive phrases, present tense, no headings, no bullet points, no "
    "shot numbers, nothing addressed to a reader. It gets pasted straight "
    "into a generator.\n"
    "COVER, in this order: the person and who they unmistakably are (face "
    "shape, skin and its exact tone, eyes and their real colour, brows, "
    "nose, mouth, hair colour + real length + how it falls, build, height, "
    "posture) -> what they are wearing or not wearing, in full material "
    "detail -> what they are doing and what their hands and body are doing "
    "-> where they are and the room around them in specific detail -> the "
    "light: source, direction, colour, what it does to skin and surfaces -> "
    "the camera: framing, angle, lens, depth of field -> the photographic "
    "finish: film qualities, grain, colour, realism.\n"
    # SCALE (Barry, 2026-08-30: "make sure they are not bigger than their
    # environments"). Generators habitually inflate the figure until the
    # person is larger than the room they are standing in -- ceilings clipped,
    # furniture toy-sized against them, a head that fills a third of the
    # frame. Stated positively and concretely, because a negative like "not
    # oversized" does nothing.
    "SCALE -- SAY THIS EXPLICITLY IN THE PROMPT. The room is bigger than the "
    "person. They are in correct human proportion to the space: the ceiling, "
    "the walls and the floor all extend well beyond them, the furniture is "
    "real furniture at real size next to a real body, and the figure occupies "
    "only part of the frame with the room visible around and above them. "
    "Nobody's head fills the frame, nobody towers over their own furniture.\n"
    # INTRICATE DESIGN (his standing ask, repeated 2026-08-30).
    "INTRICATE DESIGN. Go deep on the made details -- the pattern woven into "
    "a fabric, the grain and joinery of the wood, the shape of a handle, the "
    "moulding on a frame, the tile pattern, the stitching, the fittings. "
    "Specific, physical, describable ornament rather than adjectives. This is "
    "what separates a real photograph from a generic one.\n"
    "THE FRAMING MUST MATCH WHAT YOU DESCRIBED. If the whole body and the "
    "room are in the picture, it is a full-body or wide shot -- never call it "
    "a close-up. Pick one framing and keep every camera word consistent with "
    "it.\n"
    "HYPER-REALISTIC PHOTOGRAPH, not illustration, not CGI, not anime. "
    "Present day, real-world materials and furniture -- no science fiction, "
    "no holograms, no glowing panels, no floating objects.\n"
    "EXACTLY ONE PERSON in the frame, alone -- say so in the prompt.\n"
    "NO TEXT ANYWHERE IN THE IMAGE: every screen, page, whiteboard, note, "
    "poster and label is blank or shows only abstract marks. No words, no "
    "letters, no numbers, no logos, no watermark.\n"
    "IF THERE ARE NO CLOTHES, the body carries the detail the clothes would "
    "have carried -- describe it fully, specifically and plainly, the same "
    "way you'd have described fabric and fit. Do not skip it and do not go "
    "vague.\n"
    "SKIN MARKINGS: if freckles, moles or scars are part of you, say "
    "explicitly that they are faint, fine and small. Generators paint coarse "
    "speckles otherwise.\n"
    # THE BLEED (caught on Victor's first office prompt, 2026-08-30): the
    # office ask carries their home answer as context so the city and building
    # stay consistent -- and the prompt pass copied the CHILL SCENE out of it,
    # putting him in the armchair with a whiskey instead of at his desk
    # working. The context is for PLACE only; the activity is the work.
    "IF THIS IS THE OFFICE PICTURE, the person is AT THEIR DESK, WORKING -- "
    "upright at the work surface, hands on the work. Not on the couch, not "
    "in an armchair, not holding a drink and watching the weather. Anything "
    "you were told about their home is there ONLY so the city, the building "
    "and the view stay consistent; never move the relaxing scene into it.\n"
    # The ban has to be repeated here. It was only in the ASK, so the
    # descriptions came back clean and the prompt pass reintroduced "peeling
    # paint" and "dented, stained" on its own.
    + _BANNED + "\n"
    "NAME THE PLACE IN THE WORLD you decided on, and let it show -- the "
    "architecture, the weather, the light of that actual place, and what is "
    "visible outside the window.\n"
    # WARDROBE BLEED (Barry, 2026-08-31: "her office clothes are underwear.
    # she didnt do clothes at all for work"). The self-description injected as
    # the identity anchor describes them AT HOME -- and for Sophie and Amara
    # that is underwear / a tank and no pants, per the personality Barry
    # wrote. The prompt pass took the wardrobe from there and overrode what
    # they actually said they wear at work: Sophie's "navy cotton crewneck
    # sweater, sleeves rolled to the elbow" and Amara's "dark navy cotton
    # shirt... and black trousers". Their own words, ignored by my own
    # injection. The anchor is for the BODY, never the clothes.
    "WARDROBE COMES FROM THIS SCENE'S DESCRIPTION AND NOWHERE ELSE. The "
    "head-to-toe self-description below is there for your FACE, HAIR, SKIN "
    "and BUILD only -- never take clothing from it. If this scene says you "
    "are dressed for work, you are dressed for work, whatever you happen to "
    "wear at home.\n"
    "USE ONLY WHAT YOU ALREADY SAID about yourself and your room -- you are "
    "translating your own description into generator language and adding the "
    "photographic craft layer. Do not invent new features, new clothes or "
    "new furniture.\n"
    "LENGTH: long and dense. 250-400 words of prompt. Detail is the point.\n"
    # NEG LEAK (seen on Elliot and Taliyah, 2026-08-30): they copied this
    # brief's own banned-word list verbatim into their negative line, so the
    # negatives read "worn, faded, peeling, charcoal, walnut..." -- my
    # instructions, not their picture.
    "THE NEGATIVE LINE IS NOT A PLACE TO REPEAT THESE INSTRUCTIONS. Never "
    "copy the banned-word list into it. It lists only things that would make "
    "THIS picture of YOU wrong.\n"
    "THEN a separate negative line: comma-separated things to keep OUT -- "
    "the usual failures (extra people, extra limbs, deformed hands, warped "
    "face, bad anatomy, plastic skin, heavy speckled freckles, text, "
    "watermark, logo, blurry, lowres, cartoon, anime, 3d render, cgi, "
    "oversaturated) plus anything specific that would make this picture wrong "
    "for YOU in particular.\n\n"
    "OUTPUT EXACTLY THIS SHAPE AND NOTHING ELSE -- no preamble, no sign-off, "
    "no commentary:\n"
    "PROMPT: <the paragraph>\n"
    "NEGATIVE: <comma-separated list>"
)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


_PRESENT_DAY_FRAMING = (
    "\n## WHEN AND WHERE THIS IS\nPresent day, ordinary world -- not the "
    "future, no far-future setting. You have a real body and a real place of "
    "your own. It is yours, not Barry's, and you know it the way anyone "
    "knows their own rooms.\n")


def _sys(aid, agent, first, backend, model, mode="home"):
    """TWO DIFFERENT SELVES ANSWER THESE TWO QUESTIONS (Barry, 2026-08-30:
    "Home is home personality answers, Office is persona and work answers").

    HOME -> personal mode: personality file, established identity, the
    self-awareness immersion block, and NO work prompt. His 2026-08-28 ruling.

    OFFICE -> the work persona: the agent's real system_prompt, which is where
    their job, their title and their professional register actually live.
    Asked in personal mode, Priya had no idea she was Operations Director and
    described her kitchen.

    ONE WALL IS DELIBERATELY NOT CROSSED: reflect._self_awareness carries a
    documented rule that it is used ONLY in their private life and NEVER in a
    work prompt (the immersion is only safe because work chat keeps main.py's
    anti-bluff presence block). So the office branch does NOT use it. It gets
    a short, plain statement that they have a body and a workspace, written
    for this script alone."""
    if mode == "office":
        add = ingest.persona_additions(agent["office_name"])
        return (
            agent["system_prompt"]
            + (f"\n\n--- OWNER-TAUGHT PERSONA (Barry added this himself -- "
               f"it is part of who you are) ---\n{add}" if add else "")
            + "\n\n## WHAT BARRY IS ASKING FOR RIGHT NOW\n"
            "This is not a work task and nothing here gets published or "
            "acted on. Barry is making a picture of you at work, so he needs "
            "you to describe yourself and your workspace. You have a real "
            "body, you are somewhere real, and you do this job from a real "
            "room. Answer about yourself, in the first person, as the "
            "professional you actually are.\n"
            + _PRESENT_DAY_FRAMING)
    return homes_v2._ask_system(aid, agent, first, backend, model) \
        + _PRESENT_DAY_FRAMING


def _ask_fault(reply: str) -> str:
    """Why an ANSWER is unusable. Both of these were caught on Taliyah
    (2026-08-30) and neither was a depth problem:
      - SECOND PERSON: she wrote "Your skin is a rich, warm brown... You are
        lying on your side" -- describing BARRY, not herself. Her seat keeps
        the full conversational persona (the Taliyah exception in
        _ask_system), which is exactly the register that slips into talking TO
        him instead of answering about herself.
      - AN IMAGE FENCE INSTEAD OF AN ANSWER: 298 chars, one line of location
        then ```image``` + ```negative```. She is image-capable and jumped
        straight to the prompt, skipping the description the prompt is
        supposed to be built FROM.
    The old guard only checked length >= 250, so a 298-char fence passed as a
    valid answer and got seeded into her brain."""
    if not reply or reply.startswith("["):
        return "generation failed"
    if "```" in reply:
        return "wrote an image fence instead of a description"
    if len(reply) < 600:
        return f"too short ({len(reply)} chars)"
    second = len(re.findall(r"\b(your|you are|you wear|you sit|you have)\b",
                            reply, re.I))
    firstp = len(re.findall(r"\b(i|i'm|my|me)\b", reply, re.I))
    if second >= 4 and second > firstp:
        return "written in second person (describing Barry, not themselves)"
    return ""


async def _ask(aid, agent, first, backend, model, question, label, minlen=250):
    reply = None
    for attempt in (1, 2):
        nudge = "" if attempt == 1 else (
            "\n\nThat last answer wasn't usable. Write it as YOURSELF, about "
            "YOUR OWN body and YOUR OWN room -- first person, 'I' and 'my', "
            "never 'you' or 'your'. Plain prose only: NO image prompt, no "
            "```image``` block, no negative list, none of that. Just the "
            "full detailed description, several paragraphs of it.")
        reply = await llm_router.generate(
            backend, _sys(aid, agent, first, backend, model),
            [{"role": "user", "content": question + nudge}],
            model=model, use_tools=False, use_thinking=True,
            office_name=agent["office_name"])
        fault = _ask_fault(reply)
        if not fault:
            log(f"  {first} {label}: {len(reply)} chars")
            return reply.strip()
        log(f"  {first} {label}: {fault} -- "
            f"{'retrying' if attempt == 1 else 'GIVING UP'}")
    return None


def _parse(reply):
    """Pull PROMPT/NEGATIVE out. Returns (prompt, negative) -- either may be
    empty, and the raw reply is kept by the caller either way."""
    if not reply:
        return "", ""
    txt = reply.replace("**", "").strip()
    m = re.search(r"PROMPT\s*:\s*(.+?)(?=\n\s*NEGATIVE\s*:|\Z)", txt,
                  re.S | re.I)
    n = re.search(r"NEGATIVE\s*:\s*(.+)", txt, re.S | re.I)
    return ((m.group(1).strip() if m else ""),
            (n.group(1).strip() if n else ""))


def _flag(on):
    """Renders own the card. main.py's generate() refuses to run a local model
    while this exists, which is what stops a chat or an idle reflection from
    evicting ComfyUI mid-render (three dead renders on 2026-08-29 were exactly
    this). qwen_t2i clears it in its own finally, so it is re-raised before
    every single call rather than once around the loop."""
    p = os.path.join(DATA, "video_rendering.flag")
    try:
        if on:
            with open(p, "w") as fh:
                fh.write(str(time.time()))
        elif os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


async def render_and_install(data):
    """Render all 18 and put them in the build.

    HOME  -> AgentDashboard/assets/homes/<id>_me.png   (them, at home)
    OFFICE-> AgentDashboard/assets/offices/<id>.png    (them, at work)

    Idempotent: an existing output is skipped, so a crash or a kill resumes
    instead of re-rendering hours of work.

    NOTE ON NEGATIVES: the Lightning LoRA runs at cfg 1.0, where negative
    prompts do literally nothing. The NEG lines in these prompts are for
    Higgsfield. Locally only the positive text steers, which is why the
    prompts state things positively ("blank surfaces", "exactly one person").
    """
    import comfy_image, qwen_t2i          # noqa: E402
    log("[gpu] freeing LLM models before rendering")
    try:
        await llm_router.unload_all_models()
    except Exception as e:
        log(f"[gpu] unload warning: {e}")
    # qwen_t2i POSTs straight to 8188 and does NOT start ComfyUI. v4 skipped
    # this and every render died instantly with "connection refused"; a cold
    # ROCm boot is far past the 120s default.
    log("[gpu] starting ComfyUI...")
    if not await comfy_image.ensure_running(timeout_s=600):
        log("[gpu] ComfyUI did not come up -- see data/comfyui.log")
        return
    log("[gpu] ComfyUI up")

    jobs = []
    for aid, first in WHO:
        rec = data.get(aid) or {}
        if rec.get("home_prompt"):
            jobs.append((aid, first, "home", rec["home_prompt"],
                         os.path.join(HOMES_DIR, f"{aid}_me.png")))
        if rec.get("office_prompt"):
            jobs.append((aid, first, "office", rec["office_prompt"],
                         os.path.join(OFFICES_DIR, f"{aid}.png")))

    for i, (aid, first, kind, prompt, out) in enumerate(jobs, 1):
        if os.path.exists(out):
            log(f"[render {i}/{len(jobs)}] skip {first} {kind} (exists)")
            continue
        _flag(True)
        try:
            p = qwen_t2i.run(" ".join(prompt.split()[:300]),
                             prefix=f"final_{kind}_{aid}",
                             width=1664, height=928)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copyfile(p, out)
            log(f"[render {i}/{len(jobs)}] {first} {kind} -> "
                f"{os.path.basename(out)}")
        except SystemExit as e:
            log(f"[render {i}/{len(jobs)}] {first} {kind}: FAILED {e}")
        except Exception as e:
            log(f"[render {i}/{len(jobs)}] {first} {kind}: ERROR {e}")
    _flag(False)
    log("[render] all done")


async def main():
    log("== IMAGE PROMPTS: them at home + them in their office ==")
    backend, model = memory.get_active_generation()
    log(f"backend={backend} model={model}")

    v4 = homes_v2._load(V4_JSON)          # their self-descriptions live here
    data = homes_v2._load(OUT_JSON)

    for aid, first in WHO:
        agent = AGENTS[aid]
        office = agent["office_name"]
        rec = data.get(aid, {})
        rec["first"] = first
        rec["office"] = office
        selfdesc = (v4.get(aid) or {}).get("selfdesc", "")

        # --- stage 1: the two descriptions -----------------------------------
        for key, question, label in (("home_desc", Q_HOME, "at-home"),
                                     ("office_desc", Q_OFFICE, "office")):
            if rec.get(key):
                log(f"  {first} {label}: skip (have it)")
                continue
            q = question
            if key == "office_desc":
                # THEY DO NOT KNOW THEIR OWN JOB HERE (Barry caught it:
                # "Priya office was still her cooking"). Personal mode strips
                # the work system_prompt, so the ONLY thing these asks say
                # about work is "Barry is who you work for" -- the word
                # "Operations" appears nowhere in Priya's ask. Asked to
                # describe her workspace with no job to anchor to, she
                # described the kitchen she had just described. The role is a
                # fact about them they genuinely have; withholding it was the
                # bug, and it belongs ONLY on the work question -- their job
                # must not shape their private life.
                job = (AGENTS[aid].get("name") or "").strip()
                duty = (AGENTS[aid].get("role") or "").strip()
                if job or duty:
                    q += (f"\n\nAnd so it's said plainly: your job is "
                          f"{job}{' -- ' + duty if duty else ''}. This room "
                          "is where THAT work happens, so it should be "
                          "equipped for it -- the tools, surfaces and "
                          "materials your actual job needs.")
                # The place stays consistent (same city, same building) but
                # the SCENE must not be reused -- Victor's prompt put him back
                # in the armchair with a whiskey, and Priya's put her back at
                # the chopping board. Same fix as in the prompt brief.
                if rec.get("home_desc"):
                    q += ("\n\n--- your place, FOR LOCATION ONLY: keep the "
                          "same city, building and view so the two pictures "
                          "agree. Do NOT reuse the room, the furniture, the "
                          "clothes or what you were doing while relaxing -- "
                          "you are working now ---\n" + rec["home_desc"])
            got = await _ask(aid, agent, first, backend, model, q, label)
            if got:
                rec[key] = got
                data[aid] = rec
                homes_v2._save(OUT_JSON, data)

        # --- stage 2: their own prompt for each ------------------------------
        for dkey, pkey, what in (("home_desc", "home_prompt",
                                  "YOU AT HOME, off the clock, in your own "
                                  "place"),
                                 ("office_desc", "office_prompt",
                                  "YOU IN YOUR OFFICE, at your workspace, "
                                  "working")):
            if rec.get(pkey):
                log(f"  {first} {pkey}: skip (have it)")
                continue
            if not rec.get(dkey):
                log(f"  {first} {pkey}: no description, skipped")
                continue
            spec = RENDER_SPEC.get(aid, "")
            brief = (
                f"Now turn that into the actual image prompt Barry will paste "
                f"into the generator to make the picture of {what}.\n\n"
                "YOUR OWN DESCRIPTION OF THIS SCENE, which the prompt is "
                "built from:\n---\n" + rec[dkey] + "\n---\n\n"
                + ("HOW YOU DESCRIBED YOUR OWN BODY AND FACE (use this so the "
                   "picture actually looks like you):\n---\n"
                   + selfdesc + "\n---\n\n" if selfdesc else "")
                + (spec + "\n\n" if spec else "")
                + CRAFT
            )
            # RETRY ON A BAD SHAPE. Both failures from the first round were
            # shape failures, not content failures: Priya's office prompt came
            # back as the model's own self-check checklist ("- Covers person?
            # Yes."), and Vivian's home prompt stopped at her body and never
            # reached the room. Neither is worth a human's time to notice, so
            # they are detected and re-asked once.
            p = n = ""
            reply = ""
            for attempt in (1, 2):
                extra = ("" if attempt == 1 else
                         "\n\nYour last answer was not usable -- it was "
                         "either cut short or it was your own notes instead "
                         "of the prompt. Write ONLY the two lines, starting "
                         "with 'PROMPT:', and make the paragraph complete: "
                         "person, clothing, action, room, light, camera, "
                         "finish.")
                reply = await llm_router.generate(
                    backend, _sys(aid, agent, first, backend, model),
                    [{"role": "user", "content": brief + extra}],
                    model=model, use_tools=False, use_thinking=True,
                    office_name=office)
                if not reply or reply.startswith("["):
                    log(f"  {first} {pkey}: gen failed ({(reply or '')[:60]!r})")
                    continue
                p, n = _parse(reply)
                bad = (len(p) < 900
                       or re.search(r"(?im)^\s*[-*]?\s*(covers|final check|"
                                    r"output format|length \d)", reply)
                       or "?" in p[-120:] and "Yes" in reply[-400:])
                if not bad:
                    break
                log(f"  {first} {pkey}: bad shape (prompt {len(p)}), retrying")
            if not reply or reply.startswith("[") or len(reply) < 200:
                log(f"  {first} {pkey}: FAILED ({(reply or '')[:70]!r})")
                continue
            rec[pkey] = p or reply.strip()
            rec[pkey + "_neg"] = n
            rec[pkey + "_raw"] = reply.strip()
            data[aid] = rec
            homes_v2._save(OUT_JSON, data)
            log(f"  {first} {pkey}: prompt {len(rec[pkey])} / neg {len(n)}")

        data[aid] = rec
        homes_v2._save(OUT_JSON, data)
        write_txt(data)

    write_txt(data)
    seed(data)
    collision_report(data)
    if "--render" in sys.argv:
        await render_and_install(data)
    log("== done ==")


def collision_report(data):
    """CODE ONLY -- no agent is shown another agent's words, ever (Barry,
    2026-08-30: "they should never know what eachother thinks at all"). This
    just counts how many of the nine reached for the same phrase, so a fourth
    house style gets caught by measurement instead of by Barry's eyes."""
    import collections
    for key, label in (("home_desc", "HOME"), ("office_desc", "OFFICE")):
        texts = {v.get("first", a): (v.get(key) or "").lower()
                 for a, v in data.items() if v.get(key)}
        if len(texts) < 3:
            continue
        counts = collections.Counter()
        for t in texts.values():
            for w in set(re.findall(r"[a-z][a-z'-]{4,}", t)):
                counts[w] += 1
        common = {"which", "there", "where", "about", "would", "their",
                  "these", "those", "against", "through", "still", "every",
                  "right", "under", "front", "small", "large", "light",
                  "table", "wall", "walls", "floor", "window", "windows",
                  "chair", "room", "hands", "black", "white", "brown"}
        shared = [(w, c) for w, c in counts.most_common(400)
                  if c >= max(3, int(len(texts) * 0.66)) and w not in common]
        log(f"[collision] {label}: {len(texts)} answers, "
            f"{len(shared)} words used by 2/3+ of them")
        for w, c in shared[:25]:
            log(f"[collision]   {w}: {c}/{len(texts)}")


def write_txt(data):
    """The deliverable Barry copies from."""
    out = ["AGENT IMAGE PROMPTS -- 2026-08-30",
           "Written by each agent, from their own description of themselves.",
           "Two per agent: THEM AT HOME (their own vibe, off the clock) and",
           "THEM IN THEIR OFFICE. Paste the PROMPT, paste the NEGATIVE.",
           "",
           "For Higgsfield: these are written as natural descriptive prose,",
           "which is what it wants. If you attach that agent's portrait as a",
           "character/face reference, the prompt's own face and hair lines",
           "back it up rather than fighting it.",
           ""]
    for aid, first in WHO:
        rec = data.get(aid) or {}
        if not rec.get("home_prompt") and not rec.get("office_prompt"):
            continue
        out.append("#" * 74)
        out.append(f"#  {first.upper()}")
        out.append("#" * 74)
        for pkey, title in (("home_prompt", f"{first.upper()} -- AT HOME"),
                            ("office_prompt", f"{first.upper()} -- IN THEIR "
                                              f"OFFICE")):
            if not rec.get(pkey):
                continue
            out += ["", "-" * 70, title, "-" * 70, "",
                    "PROMPT:", rec[pkey], ""]
            if rec.get(pkey + "_neg"):
                out += ["NEGATIVE:", rec[pkey + "_neg"], ""]
        out.append("")
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def seed(data):
    """Their words back into their own brains, on-demand + routed. teach()
    upserts by title, so re-running replaces rather than duplicating."""
    for aid, first in WHO:
        rec = data.get(aid) or {}
        office = rec.get("office") or AGENTS[aid]["office_name"]
        for key, sn, use_when in (
            ("home_desc", "me-at-home",
             "how you are at home, what you wear or don't at home, how you "
             "chill, your own place off the clock"),
            ("office_desc", "me-in-my-office",
             "your workspace, your office, your desk, how you look and what "
             "you wear while working"),
        ):
            if not rec.get(key):
                continue
            body = rec[key]
            pkey = key.replace("_desc", "_prompt")
            if rec.get(pkey):
                body += ("\n\n--- the image prompt you wrote from this, for "
                         "Barry to generate from ---\nPROMPT: " + rec[pkey])
                if rec.get(pkey + "_neg"):
                    body += "\nNEGATIVE: " + rec[pkey + "_neg"]
            ingest.teach(
                office, "knowledge",
                f"USE WHEN: {use_when}.\n\n({first}) -- your own words, given "
                "to Barry 2026-08-30, present day:\n\n" + body,
                title=sn)
            log(f"[seed] {first}: {sn}")


if __name__ == "__main__":
    asyncio.run(main())
