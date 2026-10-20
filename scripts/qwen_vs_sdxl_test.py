"""The Qwen-Image acceptance test (2026-08-28c handoff): ONE agent, ONE
identical prompt, both engines, side by side for Barry.

Test subject: Taliyah's at-home self -- chosen because her SDXL portrait
wardrobe (gray sweatpants / faded black tee) is a KNOWN, named SDXL failure
from the homes v2 build. Every clause in the prompt is checkable against
her own words in data/agent_homes_2026_08_29.json.

SDXL renders through backend.comfy_image.generate_image -- the real
production path with its trained negative embeddings -- so the champion
fights at full strength, not a strawman.

    ./venv/Scripts/python.exe scripts/qwen_vs_sdxl_test.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

# Assembled in the homes-v2 shape: Barry's framing words first, wardrobe,
# room, then the v6 tail. Identical string to both engines.
PROMPT = (
    "Hyper realistic full body view from the feet up. Intricate details "
    "and design. A young woman relaxing at home, completely at ease. She "
    "wears a faded black t-shirt with the hem worn thin and gray "
    "sweatpants, sleeves rolled up to her elbows, barefoot, messy dark "
    "hair pulled back with a black hair tie, a faint smudge of ink on her "
    "left hand. The room: a dim den lit by a single floor lamp with a "
    "brass base, a worn leather couch with a crack on its left side "
    "patched with dark fabric, a low oak side table holding a chipped "
    "ceramic mug and a stack of three hardcover books with a warped "
    "paperback on top, half-closed blinds catching the last blue of "
    "evening, bare floorboards with a thin frayed runner. Full body shot "
    "with the whole figure in frame, subject filling most of the frame, "
    "face clearly visible sharp and detailed, perfectly formed hands with "
    "exactly five fingers, natural relaxed hands, mid-activity candid "
    "moment, photorealistic, raw photo, clear even skin, intricately "
    "detailed clothing and rich detailed environment, cinematic lighting, "
    "year 4378"
)

SEED = 43780828  # fixed for reproducibility; seeds don't transfer across engines


async def render_sdxl():
    import comfy_image
    res = await comfy_image.generate_image(
        PROMPT, seed=SEED)
    print(f"SDXL -> {res}", flush=True)
    return res


def render_qwen():
    import qwen_t2i
    return qwen_t2i.run(PROMPT, prefix="qwen_vs_sdxl", seed=SEED,
                        width=1024, height=1024)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "sdxl"):
        asyncio.run(render_sdxl())
    if which in ("both", "qwen"):
        render_qwen()
