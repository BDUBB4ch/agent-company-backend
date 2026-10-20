"""One test reel through backend/reel_builder.py (Barry OK'd the GPU run 2026-09-24). 3 scenes, no music yet."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
os.chdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import reel_builder  # noqa: E402

PACKAGE = {
    "title": "TEST -- mugwort, the witch's herb",
    "mood": "spooky",
    "voice_agent": "ilnora",
    "scenes": [
        {"narration": "Long before Halloween had a name, witches hung mugwort over the door to keep the dead outside.",
         "image_prompt": "bundles of dried mugwort hanging over an old wooden cottage door at dusk, candle glow, "
                         "fog, autumn leaves, photographic, intricate detail, moody shadows"},
        {"narration": "They tucked it under pillows for vivid dreams, and brewed it bitter to settle the stomach.",
         "image_prompt": "a clay cup of dark herbal tea on a rustic table beside fresh mugwort sprigs and an "
                         "old leather book, candlelight, photographic, shallow depth of field"},
        {"narration": "Traditional use, not proven. And never drink it if you are pregnant.",
         "image_prompt": "a witch's apothecary shelf with glass jars of dried herbs, handwritten labels, "
                         "a black cat asleep, warm lantern light, photographic, intricate clutter"},
    ],
    "caption": "Mugwort -- the witch's herb. Traditional use; educational, not medical advice.",
    "hashtags": ["#herbalism", "#witchtok", "#halloween"],
}

if __name__ == "__main__":
    print(json.dumps(asyncio.run(reel_builder.build_reel(PACKAGE)), indent=1), flush=True)
