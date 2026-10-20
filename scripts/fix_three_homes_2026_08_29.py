"""Targeted fixes to three home portraits (Barry, 2026-08-29).

His notes: "Priya and Amara faces are differen but Amaras body if perfect.
Sophie is supposed to be in bra and panties, its part of her personality."

THREE DIFFERENT PROBLEMS, THREE DIFFERENT FIXES:

  AMARA  -- face only. Her BODY IS PERFECT and must not change, so this is a
            Qwen-Edit face pass on the EXISTING image. Never a re-render.
  PRIYA  -- same: face pass on the existing image.
  SOPHIE -- wardrobe. Her own answer says "plain black lace bra and matching
            panties" and it WAS in the prompt (word 180 of 220) -- the model
            overrode it with a bodysuit. Buried mid-prompt loses; this
            re-renders with the wardrobe FRONT-LOADED, right after the
            identity lead, the same fix that solved the wrong-race renders.

Her answer is NOT re-asked: he did not reject what she said, he rejected the
render of it. (reroll-means-reask applies when HIS words are stale, not when
the generator ignored good ones.)

Backs up every image it replaces. Holds the render flag throughout.
"""
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import json  # noqa: E402
import qwen_t2i    # noqa: E402
import qwen_edit   # noqa: E402

HOMES = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes")
INPUT = os.path.join(ROOT, "tools", "ComfyUI", "input")
DATA = os.path.join(ROOT, "data")
BACKUP = os.path.join(HOMES, "_before_face_fix_2026-08-29")
LOG = os.path.join(DATA, "fix_three_homes.log")


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


# identity leads, verbatim from the v3 build (faithful reads of the portraits
# Barry installed) -- reused so the face pass and the render agree.
LEADS = {
    "operations": "a woman with warm golden-tan light-brown skin, deep brown "
                  "eyes, a few light freckles, and long dark brown hair with "
                  "soft auburn tones at the ends",
    "engineer": "a pale-skinned young woman with platinum white hair carrying "
                "pastel rainbow strands, bright green eyes, freckles and red "
                "lipstick",
}


def face_pass(aid, lead):
    """Fix the face WITHOUT touching body, pose, wardrobe or room."""
    src = os.path.join(HOMES, f"{aid}_me.png")
    ref = f"agent_face_{aid}.png"
    if not os.path.isfile(src):
        log(f"[{aid}] no existing image, skipped")
        return
    if not os.path.isfile(os.path.join(INPUT, ref)):
        log(f"[{aid}] no face reference, skipped")
        return
    staged = f"facefix_{aid}.png"
    shutil.copyfile(src, os.path.join(INPUT, staged))
    try:
        out = qwen_edit.run(
            [staged, ref],
            "Change ONLY the woman's face in image 1 so it is the face of the "
            "woman in image 2 — her exact facial structure, her eyes, her nose "
            "and mouth, her skin tone, her hairline. She is "
            + lead + ". Keep her body, her figure, her pose, her hair length "
            "and style, her clothing, the room, the furniture and the lighting "
            "of image 1 completely unchanged. Do not restyle anything except "
            "the face.",
            prefix=f"facefix_{aid}", timeout=4800)
        shutil.copyfile(out, src)
        log(f"[{aid}] face pass -> homes/{aid}_me.png")
    except SystemExit as e:
        log(f"[{aid}] face pass FAILED: {e}")


def sophie_rerender():
    aid = "engineer"
    homes = json.load(open(os.path.join(
        DATA, "agent_homes_v3_2026_08_29.json"), encoding="utf-8"))
    me = " ".join(homes[aid]["athome"].split()[:220])
    # WARDROBE FRONT-LOADED -- this is the whole fix. In her own words.
    prompt = (
        "Hyper realistic full body view from the feet up. Intricate details "
        "and design. The person is " + LEADS["engineer"] + ". "
        "SHE IS WEARING ONLY A PLAIN BLACK LACE BRA AND MATCHING BLACK LACE "
        "PANTIES — no other clothing, no bodysuit, no leotard, no catsuit, no "
        "stockings, no shirt, no trousers. Bare legs, bare feet, bare midriff, "
        "bare shoulders. The scene: " + me
        + " The whole figure is in frame with the room around her, face "
          "clearly visible and detailed, natural relaxed hands, clear even "
          "skin, candid moment, photorealistic, year 4378.")
    p = qwen_t2i.run(prompt, prefix="fix_self_engineer",
                     width=1664, height=928, timeout=4800)
    staged = "fix_scene_engineer.png"
    shutil.copyfile(p, os.path.join(INPUT, staged))
    try:
        out = qwen_edit.run(
            [staged, f"agent_face_{aid}.png"],
            "Change ONLY the woman's face in image 1 so it matches the face of "
            "the woman in image 2 — her facial structure, eyes, skin tone and "
            "hairline. Keep her body, pose, her black lace bra and panties, "
            "the room and the lighting exactly as they are in image 1.",
            prefix="fix_me_engineer", timeout=4800)
        shutil.copyfile(out, os.path.join(HOMES, f"{aid}_me.png"))
        log("[engineer] re-rendered in bra and panties + face pass")
    except SystemExit as e:
        shutil.copyfile(p, os.path.join(HOMES, f"{aid}_me.png"))
        log(f"[engineer] face pass failed ({e}) -- kept the raw scene")


def main():
    # THE RULE FOR STANDALONE RENDER SCRIPTS, paid for three times on
    # 2026-08-29: evict the LLMs, START COMFYUI, raise the flag, clear it in
    # finally. This script shipped with only the flag half and died on its
    # very first call with a refused connection, having done nothing.
    import asyncio
    import llm_router
    import comfy_image
    asyncio.run(llm_router.unload_all_models())
    log("LLMs evicted")
    if not asyncio.run(comfy_image.ensure_running()):
        raise SystemExit("ComfyUI would not start")
    log("ComfyUI up")

    os.makedirs(BACKUP, exist_ok=True)
    for aid in ("business", "operations", "engineer"):
        src = os.path.join(HOMES, f"{aid}_me.png")
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(BACKUP, f"{aid}_me.png"))
    log(f"backed up 3 images -> {os.path.basename(BACKUP)}")

    flag(True)
    try:
        log("== AMARA: face only, body untouched ==")
        face_pass("business",
                  "a Greek woman with warm olive-tan skin, light freckles "
                  "across her nose and cheeks, hazel eyes and shoulder-length "
                  "dark auburn-brown hair")
        flag(True)
        log("== PRIYA: face only ==")
        face_pass("operations", LEADS["operations"])
        flag(True)
        log("== SOPHIE: re-render, wardrobe front-loaded ==")
        sophie_rerender()
    finally:
        flag(False)
    log("== done ==")


if __name__ == "__main__":
    main()
