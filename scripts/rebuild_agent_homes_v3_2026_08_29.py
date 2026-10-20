"""HOMES v3 REBUILD (Barry, 2026-08-29: "all the images of my agents are ugly
and fucked up... we ask them all again. remove memories of the old questions
and their answers, dont correct anything but fucked up generations").

What changes vs v2: the RENDER ENGINE. SDXL ignored their answers (framing,
wardrobe, props — measured in the A/B); Qwen-Image obeys them. Identity comes
from a Qwen-Edit face pass with each agent's face reference — no IP-Adapter.

Stages (idempotent, checkpointed to data/agent_homes_v3_2026_08_29.json):
  0 PURGE  — supersede my-home / my-home-self facts (BACKUP first), archive
             old renders to assets/homes/_v2_backup/. my-appearance is KEPT:
             it describes the avatar portraits Barry rendered and likes —
             "dont correct anything but fucked up generations."
  1 ASK    — same two questions (his wording), personal mode, fresh answers
             (reroll-means-reask: old answers are NOT reused).
  2 RENDER — room = Qwen t2i 1664x928; at-home self = Qwen t2i scene, then
             Qwen-Edit face pass from agent_face_<id>.png. Render flag held
             for the whole phase so chats/reflections can't kill it.
  3 SEED   — re-teach my-home + my-home-self from the new answers.

    ./venv/Scripts/python.exe scripts/rebuild_agent_homes_v3_2026_08_29.py
"""
import asyncio
import json
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import memory            # noqa: E402
import ingest            # noqa: E402
import reflect           # noqa: E402
import llm_router        # noqa: E402
import comfy_image       # noqa: E402
from agents import AGENTS  # noqa: E402
import qwen_t2i          # noqa: E402
import qwen_edit         # noqa: E402

# Reuse v2's ask machinery verbatim -- questions + personal-mode system.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "homes_v2", os.path.join(os.path.dirname(__file__),
                             "build_agent_homes_2026_08_29.py"))
homes_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(homes_v2)

DATA = os.path.join(ROOT, "data")
V3_JSON = os.path.join(DATA, "agent_homes_v3_2026_08_29.json")
FACES_JSON = homes_v2.FACES_JSON
HOMES_DIR = homes_v2.HOMES_DIR
INPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "input")
# NOT homes_v3_build.log -- the launcher .bat redirects stdout there and the
# open handle denies python's append on Windows (hit live 2026-08-29).
LOG = os.path.join(DATA, "homes_v3_progress.log")

# Barry's standing art direction on HIS character (2026-08-28) -- kept.
# Taliyah's v2 hint is DROPPED: it enforced her OLD answer; fresh ask rules.
RENDER_HINTS = {
    "business": ("Her figure: balanced and curvy, not skinny, not fat, fit "
                 "and soft in the right places, full natural breasts, a full "
                 "round butt, completely at ease in her own skin."),
}

# IDENTITY LEADS (2026-08-29, after TWO wrong-race Victors in one night).
# The neutral vision captions deliberately avoid demographic words, and
# feature-soup loses: "deep brown skin" + "almond-shaped eyes" rendered an
# East Asian man. A plain demographic phrase up front is what the generator
# actually obeys. These are FAITHFUL READS OF THE PORTRAITS THE AGENTS CHOSE
# AND BARRY INSTALLED (opened at native res, 2026-08-29) plus his own seeds
# (business=Greek, creative=British Black) -- descriptions of his approved
# images, not invented canon.
IDENTITY_LEADS = {
    "cio": "a Black man with deep brown skin and closely cropped black hair",
    # v2 lead (2026-08-29 QA): "warm tan + auburn" rendered her PALE-Irish;
    # the tan needs to be unmissable and the auburn demoted to "soft".
    "operations": "a woman with warm golden-tan light-brown skin, deep brown "
                  "eyes, a few light freckles, and long dark brown hair with "
                  "soft auburn tones at the ends",
    "business": "a Greek woman with olive-tan skin, light freckles across "
                "her nose and cheeks, hazel eyes and shoulder-length dark "
                "auburn-brown hair with copper ends",
    "legal": "a Black man with brown skin, short dark hair and striking "
             "green-hazel eyes",
    "marketing": "a middle-aged Asian man with graying dark hair and "
                 "brown eyes",
    # v2 lead (QA): dense freckle-speckle covered her face; her portrait has
    # smooth skin. Say so, and keep the gem stud explicit.
    "creative": "a British Black woman with rich brown smooth clear skin, "
                "dark wavy hair, brown eyes, a single tiny sparkling gem "
                "stud under her right eye and gold hoop earrings",
    "movie": "a man with olive skin, dark wavy hair, gold-hazel eyes, dark "
             "eyeliner and a pierced eyebrow",
    "engineer": "a pale-skinned young woman with platinum white hair "
                "carrying pastel rainbow strands, bright green eyes, "
                "freckles and red lipstick",
    "taliyah": "a Black woman with rich brown skin, long curly dark hair, "
               "amber eyes, purple eyeshadow and red lipstick",
}


def _person_features(cap):
    """Strip the portrait caption down to PERSON features. The raw caption
    describes the portrait's SETTING too ('stands in a workshop...') which
    pollutes the scene, and buried appearance loses -- Victor rendered as a
    white man with 'deep brown skin' sitting mid-prompt (measured 03:26).
    Front position is weight, and the features must be setting-free."""
    keep = []
    for s in (cap or "").replace("\n", " ").split(". "):
        low = s.lower()
        if any(w in low for w in ("room", "background", "behind", "backdrop",
                                  "setting", "workshop", "stands in",
                                  "wall", "shelf", "shelves", "table")):
            continue
        keep.append(s.strip().rstrip("."))
    return ". ".join([s for s in keep if s])[:700]


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


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
    """Supersede the old home/self facts + archive old renders. Run-once
    (guarded by the backup file existing)."""
    backup_path = os.path.join(DATA, "backup_homes_v2_facts_2026-08-29.json")
    if os.path.exists(backup_path):
        log("[purge] already done (backup exists)")
        return
    backup = []
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, content FROM facts WHERE "
            "source_name IN ('my-home.md','my-home-self.md') AND status='active'"
        ).fetchall()
        for r in rows:
            backup.append({k: r[k] for k in r.keys()})
        conn.executemany("UPDATE facts SET status='superseded' WHERE id=?",
                         [(r["id"],) for r in rows])
    json.dump(backup, open(backup_path, "w", encoding="utf-8"), indent=1)
    log(f"[purge] superseded {len(backup)} facts -> {os.path.basename(backup_path)}")
    arch = os.path.join(HOMES_DIR, "_v2_backup")
    os.makedirs(arch, exist_ok=True)
    moved = 0
    for aid in AGENTS:
        for suffix in ("", "_me"):
            p = os.path.join(HOMES_DIR, f"{aid}{suffix}.png")
            if os.path.exists(p):
                shutil.move(p, os.path.join(arch, f"{aid}{suffix}.png"))
                moved += 1
    log(f"[purge] archived {moved} old renders -> homes/_v2_backup/")


async def ask():
    backend, model = memory.get_active_generation()
    homes = homes_v2._load(V3_JSON)
    for aid, agent in AGENTS.items():
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        office = agent["office_name"]
        h = homes.get(aid, {})
        for key, question, label in (
                ("answer", homes_v2.QUESTION, "home"),
                ("athome", homes_v2.QUESTION_SELF, "at-home self")):
            if h.get(key):
                log(f"[ask] skip {first} {label} (have answer)")
                continue
            reply = await llm_router.generate(
                backend, homes_v2._ask_system(aid, agent, first, backend, model),
                [{"role": "user", "content": question}],
                model=model, use_tools=False, use_thinking=False,
                office_name=office)
            if not reply or reply.startswith("["):
                log(f"[ask] {first} {label}: FAILED ({(reply or '')[:60]})")
                continue
            h.update({"first": first, "office": office, key: reply.strip()})
            homes[aid] = h
            homes_v2._save(V3_JSON, homes)
            log(f"[ask] {first}: {label} {len(reply)} chars")
    return homes


def render(homes):
    os.makedirs(HOMES_DIR, exist_ok=True)
    caps = homes_v2._load(FACES_JSON)
    _flag(True)
    try:
        for aid, h in homes.items():
            _flag(True)  # re-assert: qwen_t2i clears it in its own finally
            first = h.get("first", aid)
            # --- the room ---
            out = os.path.join(HOMES_DIR, f"{aid}.png")
            if not os.path.exists(out) and h.get("answer"):
                desc = " ".join(h["answer"].split()[:250])
                try:
                    p = qwen_t2i.run(
                        desc + " Interior environment, unoccupied, no people "
                        "anywhere in frame, photorealistic, year 4378.",
                        prefix=f"v3_room_{aid}", width=1664, height=928)
                    shutil.copyfile(p, out)
                    log(f"[room] {first}: -> homes/{aid}.png")
                except SystemExit as e:
                    log(f"[room] {first}: FAILED {e}")
            elif os.path.exists(out):
                log(f"[room] skip {first} (exists)")
            # --- the at-home self scene ---
            _flag(True)
            out_me = os.path.join(HOMES_DIR, f"{aid}_me.png")
            if os.path.exists(out_me) or not h.get("athome"):
                if os.path.exists(out_me):
                    log(f"[self] skip {first} (exists)")
                continue
            feats = _person_features(caps.get(aid))
            me = " ".join(h["athome"].split()[:220])
            hint = RENDER_HINTS.get(aid, "")
            # IDENTITY LEADS (fix for the 03:26 white-Victor failure): who
            # the person IS comes right after the framing words, BEFORE the
            # scene -- front position is weight, in Qwen as in SDXL. The
            # demographic lead comes first (feature-soup alone flipped race
            # AGAIN at 04:15), then the caption features refine it.
            lead = IDENTITY_LEADS.get(aid, "")
            prompt = ("Hyper realistic full body view from the feet up. "
                      "Intricate details and design. "
                      + (f"The person is {lead}. " if lead else "")
                      + (f"More of their look: {feats}. " if feats else "")
                      + (f"{hint} " if hint else "")
                      + "The scene: " + me
                      + " The whole figure is in frame with the room around "
                        "them, face clearly visible and detailed, natural "
                        "relaxed hands, clear even skin, candid mid-activity "
                        "moment, photorealistic, year 4378.")
            scene_path = None
            try:
                scene_path = qwen_t2i.run(prompt, prefix=f"v3_self_{aid}",
                                          width=1664, height=928)
            except SystemExit as e:
                log(f"[self] {first}: scene FAILED {e}")
                continue
            # --- identity: Qwen-Edit face pass ---
            _flag(True)
            face_ref = f"agent_face_{aid}.png"
            if not os.path.isfile(os.path.join(INPUT_DIR, face_ref)):
                log(f"[self] {first}: no face ref, keeping raw scene")
                shutil.copyfile(scene_path, out_me)
                continue
            staged = f"v3_scene_{aid}.png"
            shutil.copyfile(scene_path, os.path.join(INPUT_DIR, staged))
            try:
                # Refinement, not transplant: the scene already carries the
                # right identity from the prompt (fixed above); this pass
                # only tightens the face to the reference. Asking the editor
                # to CHANGE race/identity wholesale was a measured silent
                # no-op (Victor, 03:26 -- pre and post byte-alike).
                edited = qwen_edit.run(
                    [staged, face_ref],
                    "Modify the person's face in image 1 so it matches the "
                    "face of the person in image 2 -- same facial features, "
                    "same skin tone, same hairstyle -- while keeping the "
                    "pose, body, clothing, room and lighting of image 1 "
                    "unchanged.",
                    prefix=f"v3_me_{aid}")
                shutil.copyfile(edited, out_me)
                log(f"[self] {first}: scene + face pass -> homes/{aid}_me.png")
            except SystemExit as e:
                log(f"[self] {first}: face pass FAILED ({e}) -- keeping raw scene")
                shutil.copyfile(scene_path, out_me)
    finally:
        _flag(False)


def seed(homes):
    for aid, agent in AGENTS.items():
        office = agent["office_name"]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        h = homes.get(aid) or {}
        if h.get("answer"):
            ingest.teach(office, "knowledge",
                "USE WHEN: your home, your place, where you live, being at "
                "home, off the clock at your place.\n\n"
                f"YOUR HOME ({first}) -- in your own words, given to Barry "
                "2026-08-29 when he made a picture of it:\n\n" + h["answer"],
                title="my-home")
            log(f"[seed] {first}: my-home")
        if h.get("athome"):
            ingest.teach(office, "knowledge",
                "USE WHEN: how you are at home, your off-the-clock self, "
                "what you wear and do at your place.\n\n"
                f"YOUR AT-HOME SELF ({first}) -- your own words, given to "
                "Barry 2026-08-29 for the picture of you at your place:\n\n"
                + h["athome"], title="my-home-self")
            log(f"[seed] {first}: my-home-self")


async def main():
    log("== HOMES v3 REBUILD start ==")
    purge()
    log("== stage 1: fresh asks ==")
    homes = await ask()
    missing = [a for a in AGENTS if not (homes.get(a, {}).get("answer")
                                         and homes.get(a, {}).get("athome"))]
    if missing:
        log(f"[warn] incomplete answers for {missing} -- rendering the rest; "
            "re-run the script to retry them")
    log("== stage 2: renders (Qwen + face pass) ==")
    await llm_router.unload_all_models()
    if not await comfy_image.ensure_running():
        raise SystemExit("ComfyUI would not start")
    render(homes)
    log("== stage 3: seeding ==")
    seed(homes)
    log("== HOMES v3 REBUILD done ==")


if __name__ == "__main__":
    asyncio.run(main())
