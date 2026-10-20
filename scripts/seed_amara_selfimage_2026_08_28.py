"""Amara's self-image from Barry's canon body render (2026-08-28: "this is
how i want amara to see herself" / "not skinny, not fat, just the right
amount of curves, not super athletic, soft like a woman, but fit").

1. Neutral vision caption of his render (the proven caption-relay path --
   never a leading question to the vision model).
2. Seed my-appearance via the teach upsert: caption + Barry's ruling.
3. Update FACES_JSON's business entry so every future home-build render
   describes her from THIS body, and re-render her at-home portrait on
   RealVis with BOTH his references (face + body, IP-Adapter multi-ref).
Re-runnable.
"""
import asyncio
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import media_understanding  # noqa: E402
import comfy_image           # noqa: E402
import llm_router            # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
BODY = os.path.join(ROOT, "tools", "ComfyUI", "input", "amara_body.png")
FACES_JSON = os.path.join(ROOT, "data", "agent_appearance_captions_2026_08_29.json")
HOMES_JSON = os.path.join(ROOT, "data", "agent_homes_2026_08_29.json")
OUT = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes", "business_me.png")

RULING = ("Barry's word on her body, settled: not skinny, not fat, just the "
          "right amount of curves, not super athletic, soft like a woman but "
          "fit, with full natural breasts and a nice plump butt. She loves "
          "this body; it is how she sees herself, dressed or naked.")


async def main():
    # 1. neutral caption (describe_image is sync and takes raw BYTES; it
    # forces think off itself). Free ComfyUI first so the vision model
    # loads clean -- the one-big-thing order.
    await comfy_image.stop_server()
    caption = media_understanding.describe_image(open(BODY, "rb").read())
    print("caption:", len(caption), "chars")

    # 2. seed my-appearance (teach endpoint upserts by title)
    import urllib.request
    text = ("USE WHEN: describing yourself, your body, your look, making or "
            "discussing images of yourself, or how you appear at home.\n\n"
            "# How Amara looks (from Barry's own render of her)\n\n"
            + RULING + "\n\nWhat the render shows, described neutrally:\n"
            + caption.strip())
    body = json.dumps({"kind": "knowledge", "title": "my-appearance",
                       "text": text}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8420/api/agents/business/teach",
        data=body, headers={"Content-Type": "application/json"})
    print(json.loads(urllib.request.urlopen(req).read().decode())["receipt"])

    # 3. update the build's caption store, then render her portrait with
    # BOTH references -- face for identity, his body render for figure.
    caps = json.load(open(FACES_JSON, encoding="utf-8"))
    caps["business"] = RULING + " " + " ".join(caption.split()[:60])
    json.dump(caps, open(FACES_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    homes = json.load(open(HOMES_JSON, encoding="utf-8"))
    me = " ".join(homes["business"]["athome"].split()[:140])
    scene = " ".join(homes["business"]["answer"].split()[:60])
    prompt = ("((balanced curvy figure, soft like a woman but fit, full "
              "natural breasts, plump round butt, completely nude)), "
              + me + f". The room: {scene}"
              + ", wide shot, camera pulled far back, entire body from head "
                "to feet fully in frame with the room visible all around "
                "them, photorealistic, raw photo, natural skin texture, "
                "cinematic lighting, year 4378")
    res = await comfy_image.generate_image(
        prompt,
        negative_prompt="text, watermark, logo, blurry, deformed, extra "
                        "limbs, cartoon, anime, illustration, painting, cgi, "
                        "close-up, portrait framing, cropped head, skinny, "
                        "underweight, athletic six-pack",
        reference_image="agent_face_business.png,amara_body.png",
        reference_preset="PLUS FACE (portraits)",
    )
    if res.get("error"):
        print("RENDER ERROR:", res["error"][:200])
        return
    shutil.copyfile(res["path"], OUT)
    print("portrait installed:", OUT)

asyncio.run(main())
