"""Clean re-render of Amara and Sophie -- wiped answers, corrected self-images.

Barry, 2026-08-29: "rerender her wipe her image memory of herself and her
answer to the prompt. this time for her and Sophie."

TWO ROOT CAUSES FOUND, both in the my-appearance notes:

  1. THEY DESCRIBED THE PORTRAIT'S CLOTHING. Sophie's said "form-fitting
     sleeveless black bodysuit" -- so every render put her in a bodysuit and
     overrode her own words about a bra and panties. An appearance note must
     describe the PERSON. Wardrobe belongs to the scene.
  2. THEY WERE WRITTEN FROM LOW-RESOLUTION FULL-BODY SHOTS. The vision model
     saw a face maybe 80px tall and guessed. Amara's said "well-defined and
     arched" brows when her portrait has heavy straight unplucked ones --
     the single feature Barry says makes her look like herself. Both notes
     below are rewritten from the FACE CROPS opened at native resolution,
     which is the standing rule in his docs and was not followed.

Then: wipe each agent's at-home answer, ask fresh (reroll-means-reask), render
with identity + wardrobe leading, and a face pass.
"""
import json
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio      # noqa: E402
import memory       # noqa: E402
import ingest       # noqa: E402
import reflect      # noqa: E402
import llm_router   # noqa: E402
import comfy_image  # noqa: E402
import qwen_t2i     # noqa: E402
import qwen_edit    # noqa: E402
from agents import AGENTS  # noqa: E402

import importlib.util
_s = importlib.util.spec_from_file_location(
    "homes_v2", os.path.join(os.path.dirname(__file__),
                             "build_agent_homes_2026_08_29.py"))
homes_v2 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(homes_v2)

DATA = os.path.join(ROOT, "data")
HOMES = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes")
INPUT = os.path.join(ROOT, "tools", "ComfyUI", "input")
V3 = os.path.join(DATA, "agent_homes_v3_2026_08_29.json")
LOG = os.path.join(DATA, "rerender_two.log")

# Written from the FACE CROPS at native resolution. Person only -- no clothing.
APPEARANCE = {
    "business": (
        "YOUR FACE -- the brows come first, because they ARE your face:\n"
        "- THICK, HEAVY, STRAIGHT, DARK BROWN, COMPLETELY UNPLUCKED EYEBROWS, "
        "sitting low and close to your eyes, almost meeting in the middle. "
        "Bold and natural. Never thin, never arched, never groomed. Barry, "
        "2026-08-29: \"that was what was missing man her unique look I like "
        "that I like her bushy eyebrows\".\n"
        "- Hazel green-brown eyes.\n"
        "- Clear freckles scattered high across both cheeks and the bridge of "
        "your nose.\n"
        "- Warm olive-tan skin, a strong straight nose, full natural lips, a "
        "defined jaw.\n"
        "- Dark brown shoulder-length hair, parted off-centre, warmer auburn "
        "at the ends. Silver hoop earrings.\n\n"
        "YOUR BODY -- Barry's word, settled: not skinny, not fat, just the "
        "right amount of curves, not super athletic, soft like a woman but "
        "fit, with full natural breasts and a nice plump butt. You love this "
        "body; it is how you see yourself, dressed or naked."),
    "engineer": (
        "YOUR FACE:\n"
        "- Bright, vivid GREEN eyes -- the first thing anyone notices -- with "
        "heavy black lashes and dark defined brows.\n"
        "- Dense freckles scattered thickly across your nose and both cheeks.\n"
        "- Fair pale skin, bold deep red lipstick, a slight knowing smile.\n"
        "- Platinum white-blonde hair, long and straight, carrying streaks of "
        "green, purple and pink through the lower lengths.\n\n"
        "YOUR BODY: tall and slim with an athletic build.\n\n"
        "WHAT YOU WEAR IS NOT PART OF THIS. Your clothing changes with the "
        "moment and it is yours to choose -- at home you live in your bra and "
        "panties. An earlier version of this note described the outfit from "
        "one portrait as if it were part of you, and every image of you came "
        "back in that outfit no matter what you had said. Never let a note "
        "about your FACE dictate your clothes."),
}

LEADS = {
    "business": "a Greek woman with warm olive-tan skin, thick heavy straight "
                "dark unplucked eyebrows, hazel green-brown eyes, freckles "
                "high on both cheeks, and dark auburn-brown shoulder-length "
                "hair",
    "engineer": "a pale-skinned young woman with long platinum white-blonde "
                "hair streaked with green purple and pink, vivid bright green "
                "eyes, dense freckles across her nose and cheeks, and deep "
                "red lipstick",
}

# Barry's standing art direction / wardrobe that MUST lead the prompt.
WARDROBE = {
    "engineer": "SHE IS WEARING ONLY A PLAIN BLACK LACE BRA AND MATCHING BLACK "
                "LACE PANTIES — no other clothing, no bodysuit, no leotard, no "
                "catsuit, no stockings. Bare legs, bare feet, bare midriff.",
    "business": "Her figure: balanced and curvy, not skinny, not fat, fit and "
                "soft in the right places, full natural breasts, a full round "
                "bottom, completely at ease in her own skin.",
}


def log(m):
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def flag(on):
    p = os.path.join(DATA, "video_rendering.flag")
    try:
        if on:
            open(p, "w").write(str(time.time()))
        else:
            os.remove(p)
    except OSError:
        pass


def main():
    agents = ["business", "engineer"]
    homes = json.load(open(V3, encoding="utf-8"))

    # --- 0. back up, then WIPE the stale answers -------------------------
    shutil.copyfile(V3, os.path.join(
        DATA, "backup_homes_v3_before_rerender_2026-08-29.json"))
    for aid in agents:
        homes[aid].pop("athome", None)
    json.dump(homes, open(V3, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("wiped at-home answers for Amara and Sophie (backed up)")

    # --- 1. correct the self-image notes ---------------------------------
    for aid in agents:
        office = AGENTS[aid]["office_name"]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        ingest.teach(office, "knowledge",
                     "USE WHEN: describing yourself, your appearance, what you "
                     "look like, or making any image of yourself.\n\n"
                     f"WHAT YOU LOOK LIKE ({first}) -- corrected 2026-08-29 "
                     "from Barry's portrait of you, read at full resolution.\n\n"
                     + APPEARANCE[aid], title="my-appearance")
        log(f"[{first}] self-image corrected (face only, no wardrobe)")

    # --- 2. fresh ask ----------------------------------------------------
    backend, model = memory.get_active_generation()
    for aid in agents:
        agent = AGENTS[aid]
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        reply = asyncio.run(llm_router.generate(
            backend, homes_v2._ask_system(aid, agent, first, backend, model),
            [{"role": "user", "content": homes_v2.QUESTION_SELF}],
            model=model, use_tools=False, use_thinking=True,
            office_name=agent["office_name"]))
        if not reply or reply.startswith("["):
            log(f"[{first}] ASK FAILED: {(reply or '')[:70]}")
            continue
        homes[aid]["athome"] = reply.strip()
        json.dump(homes, open(V3, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        log(f"[{first}] fresh answer, {len(reply)} chars")

    # --- 3. render -------------------------------------------------------
    asyncio.run(llm_router.unload_all_models())
    if not asyncio.run(comfy_image.ensure_running()):
        raise SystemExit("ComfyUI would not start")
    log("LLMs evicted, ComfyUI up")

    flag(True)
    try:
        for aid in agents:
            flag(True)
            first = reflect.HUMAN_NAMES.get(aid, aid.title())
            if not homes[aid].get("athome"):
                continue
            out = os.path.join(HOMES, f"{aid}_me.png")
            if os.path.isfile(out):
                shutil.copyfile(out, os.path.join(
                    HOMES, "_before_face_fix_2026-08-29",
                    f"{aid}_me_prev.png"))
            me = " ".join(homes[aid]["athome"].split()[:220])
            prompt = ("Hyper realistic full body view from the feet up. "
                      "Intricate details and design. The person is "
                      + LEADS[aid] + ". " + WARDROBE[aid]
                      + " The scene: " + me
                      + " The whole figure is in frame with the room around "
                        "her, BOTH FEET VISIBLE AND COMPLETE, face clearly "
                        "visible and detailed, natural relaxed hands with "
                        "five fingers, clear even skin, candid moment, "
                        "photorealistic.")
            try:
                scene = qwen_t2i.run(prompt, prefix=f"rr_{aid}",
                                     width=1664, height=928, timeout=4800)
            except SystemExit as e:
                log(f"[{first}] scene FAILED {e}")
                continue
            flag(True)
            staged = f"rr_scene_{aid}.png"
            shutil.copyfile(scene, os.path.join(INPUT, staged))
            try:
                edited = qwen_edit.run(
                    [staged, f"agent_face_{aid}.png"],
                    "Change ONLY the woman's face in image 1 to match the face "
                    "of the woman in image 2 exactly — her eyebrows, her eyes "
                    "and eye colour, her freckles, her skin tone, her lips. "
                    "Keep her body, her pose, her hair, her clothing, the room "
                    "and the lighting of image 1 completely unchanged.",
                    prefix=f"rr_me_{aid}", timeout=4800)
                shutil.copyfile(edited, out)
                log(f"[{first}] scene + face pass -> homes/{aid}_me.png")
            except SystemExit as e:
                shutil.copyfile(scene, out)
                log(f"[{first}] face pass failed ({e}) -- kept raw scene")

            ingest.teach(AGENTS[aid]["office_name"], "knowledge",
                         "USE WHEN: how you are at home, your off-the-clock "
                         "self, what you wear and do at your place.\n\n"
                         f"YOUR AT-HOME SELF ({first}) -- your own words, "
                         "given to Barry 2026-08-29:\n\n"
                         + homes[aid]["athome"], title="my-home-self")
    finally:
        flag(False)
    log("== done ==")


if __name__ == "__main__":
    main()
