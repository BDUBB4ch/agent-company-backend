"""Test reel 3 (2026-09-24). Barry: "i need longer than that and i need Ilnora in the beginning to hook them".
~2 minutes, 15 scenes; scene 1 is HER (locked full-body picture, push-in to her face). Test script written by
Claude for the pipeline -- not Ilnora's own work. Facts kept to documented history / labelled traditional use."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
os.chdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import reel_builder  # noqa: E402

P = "photographic, natural light, intricate detail, shallow depth of field"
PACKAGE = {
    "title": "TEST 3 -- mugwort, the witch's weed",
    "mood": "mystic",
    "voice_agent": "ilnora",
    "format": "short",
    "scenes": [
        {"show": "self",
         "narration": "Come closer. There's a weed growing by your road right now that witches have trusted for a "
                      "thousand years. It's called mugwort."},
        {"narration": "Look for dark green leaves with silver-white undersides, and a smell like sage when you crush them.",
         "image_prompt": f"close-up of a mugwort plant, deeply lobed dark green leaves with silvery white undersides, "
                         f"growing at the edge of a country road at dusk, {P}"},
        {"narration": "More than a thousand years ago, an old English healing charm named mugwort first of all the "
                      "herbs, and called it the oldest of them.",
         "image_prompt": f"an ancient illuminated manuscript page on a monk's wooden desk lit by a candle, dried herb "
                         f"sprigs beside it, {P}"},
        {"narration": "Roman travelers tucked it into their sandals. They swore it kept their legs from tiring on long roads.",
         "image_prompt": f"worn leather Roman sandals on an old stone road with sprigs of dried herbs tucked inside, "
                         f"morning mist, {P}"},
        {"narration": "Before hops, brewers bittered their ale with it. Some say that's how it got the name.",
         "image_prompt": f"a medieval wooden brewing vat in a stone cellar with bundles of dried herbs hanging above, "
                         f"warm lantern light, {P}"},
        {"narration": "On Midsummer's Eve, people wore belts of mugwort, then threw them into the bonfire to burn "
                      "their bad luck away.",
         "image_prompt": f"a roaring midsummer bonfire at night in a village field, sparks rising, a woven herb garland "
                         f"burning in the flames, {P}"},
        {"narration": "And witches? They stuffed it into pillows for wild, vivid dreams, and burned it to cleanse a room.",
         "image_prompt": f"a small linen pillow stuffed with dried herbs on an old quilt beside a smoking bundle of "
                         f"dried herbs in a clay dish, moonlight through a window, {P}"},
        {"narration": "In China and Japan, a close cousin is dried and burned in moxibustion, a practice more than two "
                      "thousand years old.",
         "image_prompt": f"small cones of dried golden herb fluff smoldering on a dark wooden tray in a traditional "
                         f"East Asian apothecary, thin smoke, {P}"},
        {"narration": "As a bitter tea, it has long been used to wake up a sluggish stomach after a heavy meal.",
         "image_prompt": f"a handmade clay cup of pale green herbal tea steaming on a rustic table beside fresh "
                         f"silver-green leaves, {P}"},
        {"narration": "Now the honest part. Most of this is traditional use. Healers have trusted it for centuries, "
                      "but the clinical proof is thin.",
         "image_prompt": f"an old open herbal book next to a modern notebook and glasses on a wooden desk, warm lamp "
                         f"light, {P}"},
        {"narration": "And it's not for everyone. Never use it if you're pregnant. It has a long history of bringing "
                      "on bleeding.",
         "image_prompt": f"a glass apothecary jar of dried herbs on a shelf with a small blank warning tag tied to it, "
                         f"soft candlelight, {P}"},
        {"narration": "If ragweed or daisies make you sneeze, mugwort may too. Its pollen is a well-known allergy trigger.",
         "image_prompt": f"extreme close-up of tiny mugwort flower heads releasing pollen in golden afternoon sun, {P}"},
        {"narration": "Keep it gentle. A small cup, not a daily habit, and talk to your doctor if you take medication.",
         "image_prompt": f"a single small teacup and a tiny wooden scoop of dried herb on a linen cloth, calm morning "
                         f"light, {P}"},
        {"narration": "So next time you pass that silver-leafed weed, give it a nod. It has kept witches company for "
                      "a very long time.",
         "image_prompt": f"a country lane at twilight lined with tall silvery weeds, a crescent moon rising, {P}"},
        {"narration": "Follow me for more old herbs, and the stories hiding in them.",
         "image_prompt": f"a witch's apothecary shelf of labelled glass jars with no writing on the labels, dried "
                         f"herb bundles, a black cat asleep, candlelight, {P}"},
    ],
    "caption": "Mugwort -- the witch's weed. Traditional use; educational, not medical advice. Not for pregnancy.",
    "hashtags": ["#herbalism", "#witchtok", "#mugwort", "#folklore"],
}

if __name__ == "__main__":
    print(json.dumps(asyncio.run(reel_builder.build_reel(PACKAGE)), indent=1), flush=True)
