"""HOMES + OFFICES v4 -- Priya, Amara, Taliyah, Sophie. PRESENT DAY.

Barry, 2026-08-30: "redo the office and homes now, add sophie too" (after
"tomorrow we redo Priya, Amara and Taliya's office and home. Amara now has
short red hair, that is not her").

WHY ALL FOUR GET RE-ASKED, not just re-rendered. Their v3 answers were given
under the 4378 framing Barry has since dropped ("they seem to not like being in
that time"), and two of the four are visibly broken because of it:
  - TALIYAH REFUSED THE QUESTION: "I don't actually know what's in 4378 -
    that's your space, I'm just the office agent." Her room was rendered from
    a refusal.
  - SOPHIE PUT HERSELF IN BARRY'S LIVING ROOM: "the corner of Barry's living
    room... not a room I occupy in the traditional sense." She has no home of
    her own in that answer.
Amara's and Priya's home answers were actually GOOD (Amara's even says "The
studio. Not the office. Not the server room. My space.") -- the failure there
was the RENDER, not the words. They are still re-asked, because the era is
gone and stale words must never be re-rendered (his standing rule).

WHAT IS FIXED HERE:
1. PRESENT DAY everywhere. No "4378" in any question or prompt.
2. AMARA'S LOOK, from HER OWN WORDS (fact 1612, saved verbatim tonight):
   thick unruly eyebrows, SHOULDER-LENGTH espresso-to-coppery-chestnut hair.
   "Amara now has short red hair, that is not her." Stated positively, because
   the Lightning LoRA runs at cfg 1.0 where negatives are dead.
3. AMARA'S FIGURE from the two full-body references Barry made himself.
4. OFFICES too -- their own workspace, in their own words, unoccupied like the
   existing office plates.

Engine: Qwen t2i, then a Qwen-Edit face pass. Barry's call: "i thought this
editor or qwen thing could keep up, if this next time fail, we will try sdxl
again" -- so Qwen gets this one shot.

Idempotent + checkpointed (data/agent_homes_v4_2026_08_30.json): re-run to
retry only what failed. Safe to run detached.
"""
import asyncio
import json
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory            # noqa: E402
import reflect           # noqa: E402
import llm_router        # noqa: E402
import ingest            # noqa: E402
from agents import AGENTS  # noqa: E402
import comfy_image       # noqa: E402
import qwen_t2i          # noqa: E402
import qwen_edit         # noqa: E402

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "homes_v2", os.path.join(os.path.dirname(__file__),
                             "build_agent_homes_2026_08_29.py"))
homes_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(homes_v2)

DATA = os.path.join(ROOT, "data")
V4_JSON = os.path.join(DATA, "agent_homes_v4_2026_08_30.json")
HOMES_DIR = homes_v2.HOMES_DIR
OFFICES_DIR = os.path.join(ROOT, "..", "AgentDashboard", "assets", "offices")
INPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "input")
LOG = os.path.join(DATA, "homes_v4_progress.log")

WHO = ["operations", "business", "taliyah", "engineer"]

# NOTE: the checkpoint dict already uses "office" for the OFFICE NAME
# ("BusinessOps"), inherited from v2. The workspace answer is keyed
# "workspace" for that reason -- naming it "office" made every workspace
# question silently skip as "have answer" (caught live 02:19).

# --- the questions, PRESENT DAY ---------------------------------------------
# v3's wording verbatim minus the era. "in 4378" is the only thing removed
# from QUESTION/QUESTION_SELF -- the axes are still Barry's, the content still
# entirely theirs.
QUESTION = homes_v2.QUESTION.replace(" in 4378", "")
QUESTION_SELF = homes_v2.QUESTION_SELF

QUESTION_OFFICE = (
    "Different one: your WORKSPACE -- the place you actually do the job. "
    "Not your home, this is the work side. Describe the room we'd see if we "
    "walked into where you work, in rich, intricate detail: the desk or "
    "bench and what's on it, the materials and colors, where the light comes "
    "from, what's on the walls, what's out the window, the specific objects "
    "and tools that make it unmistakably YOUR workspace and nobody else's. "
    "One full paragraph, concrete and visual enough to paint from."
)

# --- identity ----------------------------------------------------------------
# Portrait-faithful leads (v3, QA-tuned against Barry's own reactions), with
# the distinctive features from each agent's OWN saved self-description folded
# in where the v3 lead was missing them. Amara's eyebrows are the whole reason
# this run exists: "Yeah that was what's was missing man her unique look I like
# that I like her bushy eyebrows I like her look."
# NO FRECKLES IN RENDER PROMPTS (Barry, 2026-08-30): "lets do away with
# freckles unless yo do them right, every body that has them looks speckled.
# freckles are faint mostly and tinly, not chocolate chip sized." Any freckle
# word makes this generator paint coarse dots -- already a known flaw on
# Taliyah's, Sophie's and Vivian's arms and cheeks. So they come OUT of the
# prompt entirely. Their own descriptions still say freckles; this is
# substitute-at-render, never an edit of anyone's words.
IDENTITY_LEADS = {
    "operations": "a woman with warm golden-tan light-brown skin, deep brown "
                  "eyes, and long dark chestnut-brown hair falling in soft "
                  "waves with copper tones at the ends",
    # HER OWN WORDS drive this one. Hair length and color are stated
    # positively and repeated, because cfg 1.0 kills negatives and the last
    # render gave her SHORT RED hair.
    "business": "a Greek woman with olive-tan skin, hazel eyes, and THICK "
                "UNRULY DARK EYEBROWS "
                "trimmed to a sharp arch -- her most distinctive feature. Her "
                "hair is SHOULDER-LENGTH and layered, dark espresso brown "
                "fading to coppery chestnut at the ends, long enough to touch "
                "her shoulders",
    "taliyah": "a Black woman with rich brown skin, long curly dark hair, "
               "amber eyes, purple eyeshadow and red lipstick",
    "engineer": "a pale-skinned young woman with platinum white hair carrying "
                "pastel rainbow strands, bright green eyes and red lipstick",
}

# BARRY'S OWN PROMPT for Amara's figure, verbatim (2026-08-30) -- what he
# actually typed into Higgsfield over her original image to build the thicker
# version he approved. The earlier Claude-written hint said "fit", which points
# the WRONG WAY on the one axis he specified; his instruction is explicitly
# NOT ATHLETIC. His words are the spec.
RENDER_HINTS = {
    "business": ("Her figure: not overly athletic but soft like a woman with "
                 "a nice plump butt and bigger breasts, five foot nine, "
                 "completely at ease in her own skin."),
}

# His own full-body renders of Amara (Aug 28) -- clothed + underwear.
AMARA_BODY_SRC = os.path.join(
    os.path.expanduser("~"), "Desktop", "Dubb's Stuff",
    "B Dubb's AI agents Stuff", "Amara full Body 2.png")
AMARA_BODY_REF = "v4_amara_body.png"

PRESENT_DAY = ("photorealistic, present day, real-world materials and "
               "furniture, no science fiction technology, no holograms, no "
               "glowing panels, no floating objects")

# NO GIBBERISH LETTERING. Priya's first workspace render came back with a
# whiteboard covered in nonsense words -- the classic diffusion text
# failure, and against Barry's own standing "no text or logos in images"
# rule. Stated POSITIVELY (blank surfaces) because the Lightning LoRA runs
# at cfg 1.0, where negative prompts do nothing at all.
NO_TEXT = ("Every whiteboard, note, screen, page, poster and label in the "
           "frame is completely blank or shows only abstract marks and "
           "shapes -- no readable words, letters, numbers or logos anywhere")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _flag(on):
    p = os.path.join(DATA, "video_rendering.flag")
    try:
        if on:
            with open(p, "w") as fh:
                fh.write(str(time.time()))
        else:
            os.remove(p)
    except OSError:
        pass


def purge():
    """Clear the four agents' old home/self answers and archive their old
    renders. His standing rule: a re-roll re-ASKS -- stale words are never
    re-rendered. Facts are superseded, never deleted; renders are moved, not
    binned."""
    backup_path = os.path.join(DATA, "backup_homes_v3_facts_2026-08-30.json")
    if os.path.exists(backup_path):
        log("[purge] already done")
        return
    offices = {AGENTS[a]["office_name"] for a in WHO}
    backup = []
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, content FROM facts WHERE "
            "source_name IN ('my-home.md','my-home-self.md','my-office.md') "
            "AND status='active'").fetchall()
        hit = [r for r in rows if r["category"].split(":", 1)[-1] in offices]
        for r in hit:
            backup.append({k: r[k] for k in r.keys()})
        conn.executemany("UPDATE facts SET status='superseded' WHERE id=?",
                         [(r["id"],) for r in hit])
    json.dump(backup, open(backup_path, "w", encoding="utf-8"), indent=1)
    log(f"[purge] superseded {len(backup)} facts -> {os.path.basename(backup_path)}")

    arch = os.path.join(HOMES_DIR, "_v3_backup")
    os.makedirs(arch, exist_ok=True)
    moved = 0
    for aid in WHO:
        for name in (f"{aid}.png", f"{aid}_me.png"):
            src = os.path.join(HOMES_DIR, name)
            if os.path.exists(src):
                shutil.move(src, os.path.join(arch, name))
                moved += 1
        src = os.path.join(OFFICES_DIR, f"{aid}.png")
        if os.path.exists(src):
            shutil.move(src, os.path.join(arch, f"office_{aid}.png"))
            moved += 1
    log(f"[purge] archived {moved} renders -> homes/_v3_backup/")


async def ask():
    backend, model = memory.get_active_generation()
    data = homes_v2._load(V4_JSON)
    for aid in WHO:
        agent = AGENTS[aid]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        office = agent["office_name"]
        h = data.get(aid, {})
        for key, question, label in (
                ("answer", QUESTION, "home"),
                ("athome", QUESTION_SELF, "at-home self"),
                ("workspace", QUESTION_OFFICE, "workspace")):
            if h.get(key):
                log(f"[ask] skip {first} {label} (have answer)")
                continue
            sys_prompt = homes_v2._ask_system(aid, agent, first, backend, model)
            # THE ERA IS GONE (Barry, 2026-08-29/30). Two of these four broke
            # on it last time -- Taliyah refused the question outright and
            # Sophie placed herself in Barry's living room. Said plainly, once.
            sys_prompt += (
                "\n## WHEN AND WHERE THIS IS\nPresent day, ordinary world -- "
                "not the future, no far-future setting. You have your own "
                "place, a real one, yours alone and not Barry's and not the "
                "office. It is as real as anything else about you, and you "
                "know it the way anyone knows their own home.\n")
            reply = await llm_router.generate(
                backend, sys_prompt, [{"role": "user", "content": question}],
                model=model, use_tools=False, use_thinking=True,
                office_name=office)
            if not reply or reply.startswith("[") or len(reply) < 120:
                log(f"[ask] {first} {label}: FAILED/short ({(reply or '')[:70]})")
                continue
            h.update({"first": first, "office": office, key: reply.strip()})
            data[aid] = h
            homes_v2._save(V4_JSON, data)
            log(f"[ask] {first}: {label} {len(reply)} chars")
    return data


def _room(desc, out, prefix, label, first):
    if os.path.exists(out):
        log(f"[{label}] skip {first} (exists)")
        return
    if not desc:
        log(f"[{label}] {first}: no answer, skipped")
        return
    body = " ".join(desc.split()[:250])
    try:
        p = qwen_t2i.run(
            body + f" Interior environment, unoccupied, no people anywhere in "
                   f"frame, {PRESENT_DAY}. {NO_TEXT}.",
            prefix=prefix, width=1664, height=928)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copyfile(p, out)
        log(f"[{label}] {first}: -> {os.path.basename(out)}")
    except SystemExit as e:
        log(f"[{label}] {first}: FAILED {e}")


def render(data):
    os.makedirs(HOMES_DIR, exist_ok=True)
    # Amara's body reference, staged once (his own render).
    if os.path.isfile(AMARA_BODY_SRC):
        shutil.copyfile(AMARA_BODY_SRC,
                        os.path.join(INPUT_DIR, AMARA_BODY_REF))
        log(f"[stage] Amara body ref -> {AMARA_BODY_REF}")
    _flag(True)
    try:
        for aid in WHO:
            h = data.get(aid) or {}
            first = h.get("first", aid)

            _flag(True)   # qwen_t2i clears its own flag in a finally
            _room(h.get("workspace"), os.path.join(OFFICES_DIR, f"{aid}.png"),
                  f"v4_office_{aid}", "office", first)
            _flag(True)
            _room(h.get("answer"), os.path.join(HOMES_DIR, f"{aid}.png"),
                  f"v4_room_{aid}", "room", first)

            # --- them, at home ---
            _flag(True)
            out_me = os.path.join(HOMES_DIR, f"{aid}_me.png")
            if os.path.exists(out_me):
                log(f"[self] skip {first} (exists)")
                continue
            if not h.get("athome"):
                log(f"[self] {first}: no answer, skipped")
                continue
            lead = IDENTITY_LEADS.get(aid, "")
            hint = RENDER_HINTS.get(aid, "")
            me = " ".join(h["athome"].split()[:220])
            # ONE PERSON, SAID UP FRONT AND AGAIN AT THE END (2026-08-30).
            # Nothing in the first version said they were alone, and Qwen
            # filled the wide 16:9 frame with a SECOND FIGURE -- Amara and
            # Sophie both came back doubled. Positive phrasing only; the
            # Lightning LoRA runs at cfg 1.0 where negatives do nothing.
            prompt = ("A solo portrait of ONE SINGLE PERSON, completely alone. "
                      "Hyper realistic full body view from the feet up. "
                      "Intricate details and design. "
                      + (f"The person is {lead}. " if lead else "")
                      + (f"{hint} " if hint else "")
                      + "The scene: " + me
                      + " The whole figure is in frame with the room around "
                        "them, face clearly visible and detailed, natural "
                        "relaxed hands, completely smooth clear even skin with an "
                        "unblemished uniform complexion, candid "
                        "mid-activity moment. She is by herself: exactly one "
                        "person in the entire picture, nobody else anywhere in "
                        "the frame, no second figure, no reflection of another "
                        f"person. {PRESENT_DAY}. {NO_TEXT}.")
            try:
                scene = qwen_t2i.run(prompt, prefix=f"v4_self_{aid}",
                                     width=1664, height=928)
            except SystemExit as e:
                log(f"[self] {first}: scene FAILED {e}")
                continue

            # --- face pass (refinement, never a transplant) ---
            _flag(True)
            face_ref = f"agent_face_{aid}.png"
            if not os.path.isfile(os.path.join(INPUT_DIR, face_ref)):
                log(f"[self] {first}: no face ref, keeping raw scene")
                shutil.copyfile(scene, out_me)
                continue
            staged = f"v4_scene_{aid}.png"
            shutil.copyfile(scene, os.path.join(INPUT_DIR, staged))
            current = scene
            try:
                edited = qwen_edit.run(
                    [staged, face_ref],
                    "Modify the person's face in image 1 so it matches the "
                    # HAIR COLOUR PINNED TO IMAGE 1 (2026-08-30). The face pass
                    # imports the reference crop's COLOUR CAST -- Priya came
                    # back BLUE-HAIRED, the identical failure v3 hit. Image 2
                    # is a reference for facial FEATURES only, never colour.
                    "face of the person in image 2 -- same facial features "
                    "and same face shape -- while keeping the pose, body, "
                    "clothing, room, lighting AND THE EXACT HAIR COLOUR of "
                    "image 1 completely unchanged. Do not recolour the hair "
                    "or the skin.",
                    prefix=f"v4_me_{aid}")
                current = edited
                log(f"[self] {first}: face pass ok")
            except SystemExit as e:
                log(f"[self] {first}: face pass FAILED ({e}) -- raw scene kept")

            # --- Amara only: proportions from Barry's own body render ---
            if aid == "business" and os.path.isfile(
                    os.path.join(INPUT_DIR, AMARA_BODY_REF)):
                _flag(True)
                staged2 = f"v4_amara_stage2.png"
                shutil.copyfile(current, os.path.join(INPUT_DIR, staged2))
                try:
                    current = qwen_edit.run(
                        [staged2, AMARA_BODY_REF],
                        "Adjust the body proportions and figure of the woman "
                        "in image 1 to match the body proportions of the "
                        "woman in image 2: not overly athletic but soft like "
                        "a woman, with a nice plump butt and bigger breasts. "
                        "Keep the face, hairstyle, clothing, pose, room and "
                        "lighting of image 1 exactly as they are. Do not add "
                        "any clothing from image 2.",
                        prefix="v4_amara_body")
                    log("[self] Amara: proportions pass ok")
                except SystemExit as e:
                    log(f"[self] Amara: proportions pass FAILED ({e})")
            shutil.copyfile(current, out_me)
            log(f"[self] {first}: -> homes/{aid}_me.png")
    finally:
        _flag(False)


def seed(data):
    for aid in WHO:
        agent = AGENTS[aid]
        office = agent["office_name"]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        h = data.get(aid) or {}
        # ingest.teach(office, kind, TEXT, title=...) -- the title becomes the
        # source_name slug, so passing "my-home" REPLACES the existing fact
        # rather than duplicating it (teach upserts by title).
        for key, sn, use_when in (
            ("answer", "my-home",
             "your home, your place, where you live, being at home, off the "
             "clock at your place"),
            ("athome", "my-home-self",
             "how you are at home, your off-the-clock self, what you wear "
             "and do at your place"),
            ("workspace", "my-office",
             "your workspace, your office, your desk, where you actually do "
             "the job"),
        ):
            if not h.get(key):
                continue
            ingest.teach(
                office, "knowledge",
                f"USE WHEN: {use_when}.\n\n"
                f"({first}) -- in your own words, given to Barry 2026-08-30, "
                "present day:\n\n" + h[key],
                title=sn)
            log(f"[seed] {first}: {sn}")


async def main():
    log("== HOMES/OFFICES v4 (Priya, Amara, Taliyah, Sophie) -- present day ==")
    purge()
    data = await ask()
    log("[gpu] freeing models before rendering")
    try:
        await llm_router.unload_all_models()
    except Exception as e:
        log(f"[gpu] unload warning: {e}")
    # START COMFYUI. qwen_t2i/qwen_edit POST straight to port 8188 and do NOT
    # start it themselves -- v3 called this and v4 did not, which is the whole
    # reason the first four render attempts died instantly with "connection
    # refused". A cold ROCm boot after a reboot is well over the 120s default,
    # so the wait is generous here.
    log("[gpu] starting ComfyUI...")
    if not await comfy_image.ensure_running(timeout_s=600):
        log("[gpu] ComfyUI did not come up -- see data/comfyui.log")
        return
    log("[gpu] ComfyUI is up")
    render(data)
    seed(data)
    log("== v4 done ==")


if __name__ == "__main__":
    asyncio.run(main())
