"""Generate one Kontext scene per character, from each character's master
reference. No training involved.

Barry, 2026-08-09: "do all the characters, stop asking questions and do whats
needed to be done to get this finished."

Each prompt follows the rules that actually work with Kontext (see
kontext_generate.py's header): action verb first, subject named concretely,
explicit preservation clause, ONE change, same scale/pose/framing.

Canon notes baked into the preservation clauses, from the CHARACTER CANON bible:
  KETH     dark green eyes, no sclera; small barely-pointed ears; smooth grey
           weathered-stone skin; grey facility jumpsuit; barefoot; ~4ft
  BIA      deep-purple and gold double-ring irises; gold spots; grey/black suit
  YANNAH   green and brown double-ring irises; gold freckle spots; asymmetrical
           wavy hair shaved one side; teal piping
  TAZZ     pink and blue double-ring irises; two long dark braids; all-black
           one-piece sleeveless tactical jumpsuit; muscular
  VORSHARA four electric-blue eyes stacked in two pairs; tendrils NOT hair;
           greyish-white skin
  B DUBB   black star cap, gold #4 pendant, black vest over hoodie
           -- NO watch, NO phone, NO trackers on jobs (Kontext added a wristwatch
           on the first test; the negative is called out explicitly now)
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kontext_generate as K

JOBS = [
    ("keth_ref_canon.png",
     "Place the small grey-skinned alien man in a dim spacecraft corridor with teal light "
     "strips along the floor, showing him full body standing, while preserving his exact "
     "facial features, large dark green eyes with no visible white, small low-profile "
     "barely-pointed ears, smooth grey skin, worn grey facility jumpsuit and bare feet.",
     "final_keth"),

    ("bia_ref.png",
     "Place the athletic alien woman in a dark ship interior with cool blue light, showing "
     "her full body standing, while preserving her exact facial features, deep-purple and "
     "gold double-ringed irises, pointed ears, subtle gold spots on her skin and her grey "
     "and black form-fitting tactical suit.",
     "final_bia"),

    ("yannah_ref.png",
     "Place the young alien woman in a dim ship corridor with teal lighting, showing her "
     "full body standing, while preserving her exact facial features, green and brown "
     "double-ringed irises, pointed ears, gold freckle spots on her upper cheeks, short "
     "asymmetrical wavy hair shaved on one side and her tactical jumpsuit with teal piping.",
     "final_yannah"),

    ("tazz_ref.png",
     "Place the muscular alien woman in a dark cargo hold with hard overhead light, showing "
     "her full body standing, while preserving her exact facial features, pink and blue "
     "double-ringed irises, pointed ears, light skin, two long dark braids and her all-black "
     "form-fitting sleeveless one-piece tactical jumpsuit.",
     "final_tazz"),

    ("vorshara_ref.png",
     "Place the elegant alien woman in an interior garden atrium with a shallow reflecting "
     "pool, dark green marble columns and warm golden light, showing her full body standing, "
     "while preserving her exact facial features, all four electric-blue eyes stacked in two "
     "pairs, her greyish-white skin, her long organic tendrils with gold rings, and her sheer "
     "pale-purple gown.",
     "final_vorshara"),

    ("bdubb_ref.png",
     "Place the bearded man in the black star cap and black tactical vest in a sunlit "
     "industrial doorway, showing him full body standing, while preserving his exact facial "
     "features, salt-and-pepper beard, brownish-red skin tone, black cap, black vest over "
     "black hoodie, black cargo pants, black boots and gold number 4 pendant. He wears no "
     "watch and no wristwear of any kind.",
     "final_bdubb"),
]

if __name__ == "__main__":
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for ref, prompt, prefix in JOBS:
        if only and not any(o in prefix for o in only):
            continue
        K.run(ref, prompt, prefix)
