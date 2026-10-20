"""HOMES + SELF-KNOWLEDGE build (Barry, 2026-08-29 — the homes redesign).

Stage 1  ASK: each agent describes their own home in 4378 — Barry's question,
         their answer, personality on, tools off, nothing journaled.
Stage 2  RENDER: each description becomes a home backdrop image (RealVis SDXL,
         no people in frame) installed to AgentDashboard/assets/homes/<id>.png.
Stage 3  CAPTION: each agent's portrait is described by the vision model —
         neutral caption relay, the proven path (2026-08-04 measurement).
Stage 4  SEED: two knowledge facts per agent via ingest.teach (upsert-by-title):
         my-appearance (the look THEY chose, captioned) and my-home (their
         words verbatim). Both on-demand with USE WHEN routing.

Idempotent: every stage checkpoints to data/ JSON and skips completed items,
so a crash resumes instead of re-asking/re-rendering.
VRAM: follows the house one-big-thing order — LLM asks first, then
llm_router.unload_all_models() before ComfyUI renders, then comfy_image.unload()
before the vision captions.
"""
import asyncio
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import memory            # noqa: E402
import ingest            # noqa: E402
import reflect           # noqa: E402
import llm_router        # noqa: E402
import comfy_image       # noqa: E402
import media_understanding  # noqa: E402
from agents import AGENTS, _ESTABLISHED_IDENTITY  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data")
HOMES_JSON = os.path.join(DATA, "agent_homes_2026_08_29.json")
FACES_JSON = os.path.join(DATA, "agent_appearance_captions_2026_08_29.json")
AVATARS = os.path.join(ROOT, "..", "AgentDashboard", "assets", "cyber", "avatars")
HOMES_DIR = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes")

# v2 QUESTION (Barry, 2026-08-29: "everybody's home is a workspace... ask
# them to describe their home in a way where they relax and enjoy, not do
# work"). First pass got nine offices -- work-shaped identities defaulted to
# desks and shelves of work things. The reframe steers AWAY from work without
# suggesting what relaxing looks like (still no seeds).
# v3 detail pass (Barry, 2026-08-28: "get details too. i want intricate
# detail of everything... as detailed as possible for a great home").
# Still structure-only -- the axes of detail are named, never the content.
QUESTION = (
    "Barry here. I'm making a picture of your home in 4378 -- and I mean "
    "HOME, not where you work. No desks, no workstation, none of the job. "
    "This is the place where you relax and enjoy yourself when you're "
    "completely off the clock. Describe the room we'd see when we visit "
    "you there, in RICH, INTRICATE DETAIL -- the more specific the better: "
    "the materials and colors, the furniture and where it sits, the light "
    "and where it comes from, what's on the walls, what's out the window, "
    "the small personal objects that make it unmistakably yours. Entirely "
    "your call, every bit of it. One full, detailed paragraph, concrete "
    "and visual enough to paint from."
)

# Q2 (Barry, same day: "ask them how they want to be represented in their
# homes... their chill attire and enjoying their hobbies... if they smoke
# weed, then thats what they do"). Structure only -- wearing/doing are the
# axes of a portrait, not suggestions of content. Whatever they answer is
# what gets rendered.
# v5 (Barry, 2026-08-28: "ask them how they relax at home in great intricate
# detail of there environment the way they look with or without clothes.
# what they are doing and where they are" + "that will be their home image").
# One complete scene -- this render IS the home image the chamber shows.
# The axes are his; the content is theirs.
QUESTION_SELF = (
    "One more, and then I'll leave you alone: paint me the FULL picture of "
    "how you relax at home -- one complete scene, in great, intricate "
    "detail. Cover all of it: WHERE you are, which exact spot in your "
    "place; the ENVIRONMENT immediately around you in rich specifics -- "
    "the surfaces, the light, what's within arm's reach; HOW YOU LOOK in "
    "this moment -- with or without clothes, whatever's true for you, "
    "described head to toe exactly as we'd find you; and WHAT YOU'RE "
    "DOING, down to what's in your hands. However you actually relax is "
    "exactly what I want -- every bit of it is your call."
)


def _load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def _save(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _ask_system(aid, agent, first, backend, model):
    """PERSONAL MODE (Barry, 2026-08-28: "remember this is personal mode not
    office mode... they should answer from their personal not business
    persona"). The first version led with the full work system_prompt; the
    work persona is now OUT of the ask. What rides instead: identity facts
    (settled, from Barry), off-the-clock framing, self-awareness facts, and
    the personality file. Taliyah is the one exception -- her persona and
    personality are one (Barry's 08-25 ruling), so she keeps her full prompt."""
    personality = ingest.personality_of(agent["office_name"])
    identity = _ESTABLISHED_IDENTITY.get(aid, "")
    if aid == "taliyah":
        base = f"{agent['system_prompt']}\n\n"
    else:
        base = (
            f"You are {first}, one of Barry's people -- but right now you are "
            "completely off the clock. Barry is asking you something personal, "
            "not work. Answer as yourself at home, not as your job.\n\n"
            + (f"## Established facts about you (from Barry -- settled, not "
               f"up for reinterpretation)\n{identity} Anything else about who "
               "you are personally, Barry has left open.\n\n" if identity else "")
        )
    return (
        base
        + reflect._self_awareness(first, agent.get("name") or "teammate",
                                  backend, model)
        + (f"\n## WHO YOU ARE OFF THE CLOCK\n{personality}\n"
           if personality else "")
    )


async def ask_homes():
    backend, model = memory.get_active_generation()
    homes = _load(HOMES_JSON)
    for aid, agent in AGENTS.items():
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        office = agent["office_name"]
        h = homes.get(aid, {})
        if not h.get("answer"):
            reply = await llm_router.generate(
                backend, _ask_system(aid, agent, first, backend, model),
                [{"role": "user", "content": QUESTION}],
                model=model, use_tools=False, use_thinking=True,
                office_name=office,
            )
            if not reply or reply.startswith("["):
                print(f"[ask] {first}: FAILED ({(reply or '')[:60]})")
                continue
            h = {"first": first, "office": office, "answer": reply.strip()}
            homes[aid] = h
            _save(HOMES_JSON, homes)
            print(f"[ask] {first}: home {len(reply)} chars")
        else:
            print(f"[ask] skip {aid} home (have answer)")
        # Q2: their at-home SELF -- what they wear, what they're doing.
        if not h.get("athome"):
            reply2 = await llm_router.generate(
                backend, _ask_system(aid, agent, first, backend, model),
                [{"role": "user", "content": QUESTION_SELF}],
                model=model, use_tools=False, use_thinking=True,
                office_name=office,
            )
            if reply2 and not reply2.startswith("["):
                h["athome"] = reply2.strip()
                homes[aid] = h
                _save(HOMES_JSON, homes)
                print(f"[ask] {first}: at-home self {len(reply2)} chars")
        else:
            print(f"[ask] skip {aid} self (have answer)")
    return homes


async def render_homes(homes):
    os.makedirs(HOMES_DIR, exist_ok=True)
    await llm_router.unload_all_models()    # whole GPU to ComfyUI
    for aid, h in homes.items():
        out = os.path.join(HOMES_DIR, f"{aid}.png")
        if os.path.exists(out):
            print(f"[render] skip {aid} (exists)")
            continue
        # 160 words -- the v3 detail pass produces longer answers, and
        # ComfyUI's encoder chunks long prompts rather than truncating.
        desc = " ".join(h["answer"].split()[:160])
        prompt = (desc + ", interior environment, unoccupied, no people, "
                  "cinematic lighting, highly detailed, photorealistic, "
                  "year 4378")
        res = await comfy_image.generate_image(
            prompt,
            negative_prompt="people, person, human, face, character, text, "
                            "watermark, logo, blurry, desk, office, computer "
                            "workstation, monitors, cubicle, cartoon, anime, "
                            "illustration, drawing, painting, 3d render, cgi",
        )
        if res.get("error"):
            print(f"[render] {h['first']}: ERROR {res['error'][:100]}")
            continue
        shutil.copyfile(res["path"], out)
        print(f"[render] {h['first']}: {os.path.basename(res['path'])} -> homes/{aid}.png")

    # AT-HOME PORTRAITS (Barry: "generate them in their at home clothes or
    # however they chill at the crib"). One coherent render -- the agent IN
    # their home, doing their thing -- identity carried by their face image
    # (IP-Adapter PLUS FACE) + their captioned features in the prompt, the
    # anti-crazy answer to compositing cutouts.
    caps = _load(FACES_JSON)
    # Barry's render corrections (2026-08-28) -- his art direction on HIS
    # characters, appended to the prompt. Amara's figure is his spec
    # ("Amaras Breasts are bigger than whats rendered"); Taliyah's line just
    # enforces what SHE said (the render dropped her sweatpants and she read
    # as half-naked, which is not what she described).
    render_hints = {
        "business": "balanced curvy figure, not skinny, not fat, fit and "
                    "soft in the right places, full natural breasts, nice "
                    "plump round butt, completely confident and at ease in "
                    "her own skin",
        "taliyah": "wearing black sweatpants with white stripes under the "
                   "oversized tee, fully clothed",
    }
    for aid, h in homes.items():
        if not h.get("athome"):
            continue
        out_me = os.path.join(HOMES_DIR, f"{aid}_me.png")
        if os.path.exists(out_me):
            print(f"[portrait] skip {aid} (exists)")
            continue
        feats = " ".join((caps.get(aid) or "").split()[:70])
        scene = " ".join(h["answer"].split()[:60])
        me = " ".join(h["athome"].split()[:140])
        # v3 (Barry, 2026-08-28: "i want full body images, uncensored and i
        # want them in their actual chill state... on the couch, cooking in
        # the kitchen, smoking a joint, whatever they do"). Full-body
        # framing, hard photorealism guard (Sophie's v2 came back anime),
        # and NOTHING in the negative that sanitizes what they said they do
        # at home -- the athome answer renders as spoken.
        # v4 framing (Barry: "the images are too close, i can barely see the
        # characters") -- wide shot, camera pulled back, whole figure AND the
        # room in frame. Trade-off accepted: a smaller face weakens the
        # IP-Adapter identity hold slightly.
        # Body/wardrobe hints lead the prompt WEIGHTED -- buried mid-prompt
        # they lost to the model's defaults (Amara rendered skinny against
        # an explicit balanced-curvy spec). Front position + ((emphasis)) is
        # how the canon handles must-hold features on SDXL.
        # Framing leads the prompt (2026-08-28): a tight FACE reference at
        # weight 0.8 biases composition toward portrait, so the full-body
        # instruction has to outrank it -- and in SDXL, front position is
        # weight. Buried at the end it lost every time.
        hint = f"(({render_hints[aid]})), " if aid in render_hints else ""
        # BARRY'S OWN FRAMING WORDS (2026-08-28). He produced a true
        # full-body render on Higgsfield with "Hyper realistic full body
        # view from the feet up. intricate details and design." -- "from
        # the feet up" anchors the camera at the feet and forces the whole
        # figure in; "full body shot"/"wide shot" (my wording) kept
        # resolving to a portrait. His phrasing has beaten mine on every
        # measured attempt tonight -- use his.
        prompt = ("Hyper realistic full body view from the feet up. "
                  "Intricate details and design. " + hint + me
                  + (f". Their appearance: {feats}" if feats else "")
                  + f". The room: {scene}"
                  # v6 framing (Barry: wide shots made faces unreadable) --
                  # full figure AND a readable face: medium-wide, subject
                  # large in frame, face in focus.
                  + ", full body shot with the whole figure in frame, "
                    "subject filling most of the frame, face clearly "
                    "visible sharp and detailed, ((perfectly formed hands "
                    "with exactly five fingers)), natural relaxed hands, "
                    # NOTE: do NOT ask for "highly detailed skin texture" --
                    # SDXL renders that literally as scattered moles and
                    # dark spots on every body (Barry spotted it on Amara
                    # AND Derek, 2026-08-28). Detail belongs on the room
                    # and the fabric; skin wants "clear" and "even".
                    "mid-activity candid moment, photorealistic, raw photo, "
                    "clear even skin, intricately detailed clothing and "
                    "rich detailed environment, cinematic lighting, "
                    "year 4378")
        res = await comfy_image.generate_image(
            prompt,
            # Anatomy negatives lead: extra fingers and limbs were the #1
            # complaint on the previous batch (SDXL's known weakness at
            # full-body scale).
            # ⚠️ SHORT on purpose. Piling up hand negatives makes SDXL WORSE,
            # not better -- it is not SD1.5 and a wall of anatomy words
            # confuses it. My previous 8-term hand list was the wrong fix.
            # The anatomy work is done by TRAINED EMBEDDINGS instead:
            # bad-hands-5-SDXL (hands) + DeepNegative_xl_v1 (general),
            # both in models/embeddings/.
            negative_prompt="embedding:bad-hands-5-SDXL, "
                            "embedding:DeepNegative_xl_v1, "
                            "bad anatomy, poorly drawn hands, "
                            "moles, skin blemishes, dark spots on skin, "
                            "text, watermark, blurry, "
                            "office, desk, computer workstation, "
                            "cartoon, anime, illustration, 3d render, cgi, "
                            "close-up, cropped head",
            # Amara has a Barry-made CANON BODY reference (2026-08-28,
            # "this is the body fitness and size i want her") -- her face
            # AND body refs batch together; everyone else is face-only
            # until Barry renders them a body.
            # FACE CROP ONLY -- never a body/wardrobe reference. Measured
            # 2026-08-28: passing Barry's lingerie body render as a second
            # reference imported the LINGERIE as her wardrobe and dragged
            # the framing to a portrait. IP-Adapter reads the whole image;
            # it cannot take "body but not clothes". Figure is carried by
            # the weighted words in render_hints instead. Separating
            # identity+figure from wardrobe needs a trained LoRA.
            reference_image=f"agent_face_{aid}.png",
            reference_preset="PLUS FACE (portraits)",
            # 0.55, not the 0.85 default (2026-08-28): at 0.85 the face
            # reference dragged its OWN background and wardrobe into every
            # render -- Elliot came back against the reference's dark teal
            # wall in a green shirt twice, ignoring his own written scene.
            # 0.55 holds identity and lets the prompt own the room.
            # 0.8 again (2026-08-28). 0.55 was a workaround for LOOSE face
            # crops importing their own background and wardrobe; the crops
            # are tight now (tighten_face_refs_*), so high weight holds the
            # face WITHOUT dragging a room in. Barry: "Vivians face is not
            # the same, none of them are" -- that was the low weight.
            reference_weight=0.8,
            # Sized for the chamber's home PANEL (~66vw x 100vh, about a
            # 1.17 aspect on a 16:9 screen), not the whole viewport --
            # 1152x896 is the nearest standard SDXL bucket, so it fills the
            # panel with minimal letterboxing and shows the full figure.
            width=1152, height=896,
        )
        if res.get("error"):
            print(f"[portrait] {h['first']}: ERROR {res['error'][:100]}")
            continue
        shutil.copyfile(res["path"], out_me)
        print(f"[portrait] {h['first']}: -> homes/{aid}_me.png")


def caption_faces():
    caps = _load(FACES_JSON)
    for aid in AGENTS:
        if caps.get(aid):
            print(f"[caption] skip {aid}")
            continue
        p = os.path.join(AVATARS, f"{aid}.png")
        if not os.path.exists(p):
            print(f"[caption] {aid}: no portrait at {p}")
            continue
        data = open(p, "rb").read()
        desc = media_understanding.describe_image(
            data,
            question="Describe this person's appearance faithfully and "
                     "neutrally: build, skin, hair, eyes, notable features, "
                     "clothing, and the setting behind them. No speculation "
                     "about who they are.")
        if desc:
            caps[aid] = desc.strip()
            _save(FACES_JSON, caps)
            print(f"[caption] {aid}: {len(desc)} chars")
    return caps


def seed_facts(homes, caps):
    for aid, agent in AGENTS.items():
        office = agent["office_name"]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        cap = caps.get(aid)
        if cap:
            ingest.teach(office, "knowledge",
                "USE WHEN: describing yourself, your appearance, what you look "
                "like, or making any image of yourself.\n\n"
                f"WHAT YOU LOOK LIKE ({first})\n"
                "This is YOUR look -- the appearance you chose for yourself, "
                "which Barry rendered as your portrait. A faithful description "
                "of that portrait:\n\n" + cap +
                "\n\nWhen an image of you is made, these are the main features "
                "that must land.", title="my-appearance")
            print(f"[seed] {first}: my-appearance")
        h = homes.get(aid)
        if h and h.get("answer"):
            ingest.teach(office, "knowledge",
                "USE WHEN: your home, your place, where you live, being at "
                "home, off the clock at your place.\n\n"
                f"YOUR HOME ({first}) -- in your own words, given to Barry "
                "2026-08-29 when he made a picture of it:\n\n" + h["answer"],
                title="my-home")
            print(f"[seed] {first}: my-home")
        if h and h.get("athome"):
            ingest.teach(office, "knowledge",
                "USE WHEN: how you are at home, your off-the-clock self, "
                "what you wear and do at your place.\n\n"
                f"YOUR AT-HOME SELF ({first}) -- your own words, given to "
                "Barry 2026-08-29 for the picture of you at your place:\n\n"
                + h["athome"], title="my-home-self")
            print(f"[seed] {first}: my-home-self")


async def main():
    print("== stage 1: asking each agent about their home ==")
    homes = await ask_homes()
    print("\n== stage 2: rendering homes ==")
    await render_homes(homes)
    print("\n== stage 3: captioning portraits ==")
    try:
        await comfy_image.unload()   # free the checkpoint before vision work
    except Exception as e:
        print(f"[unload] {e}")
    caps = caption_faces()
    print("\n== stage 4: seeding self-knowledge ==")
    seed_facts(homes, caps)
    print("\ndone.")

if __name__ == "__main__":
    asyncio.run(main())
