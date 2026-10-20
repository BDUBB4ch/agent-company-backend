import sys; sys.path.insert(0,"scripts")
import kontext_generate as K

JOBS = [
 ("yannah_face.png","yannah_body.png",
  "Place the young alien woman in a dim ship corridor with teal lighting, showing her full "
  "body standing, while preserving her exact facial features, green and brown double-ringed "
  "irises, pointed ears, gold freckle spots on her upper cheeks, her short asymmetrical wavy "
  "hair shaved on one side, and her black tactical jumpsuit with teal piping and black boots.",
  "pair_yannah"),
 ("tazz_face.png","tazz_body.png",
  "Place the muscular alien woman in a dark cargo hold with hard overhead light, showing her "
  "full body standing, while preserving her exact facial features, pink and blue double-ringed "
  "irises, pointed ears, light skin, her two long dark braids, and her all-black sleeveless "
  "one-piece tactical outfit with harness, thigh rig and black boots.",
  "pair_tazz"),
 ("bia_face.png","bia_body.png",
  "Place the athletic alien woman in a dark ship interior with cool blue light, showing her "
  "full body standing, while preserving her exact facial features, deep-purple and gold "
  "double-ringed irises, pointed ears, gold spots on her skin, her sleek faded pixie shaved "
  "on one side, and her black form-fitting tactical suit with the multi-tool on her right hip.",
  "pair_bia"),
 ("ref_shara_face.png","vorshara_ref.png",
  "Place the elegant alien woman in an interior garden atrium with a shallow reflecting pool, "
  "dark green marble columns and warm golden light, showing her full body standing, while "
  "preserving her exact facial features, all four electric-blue eyes stacked in two pairs, her "
  "greyish-white skin, her long organic tendrils with gold rings, and her sheer pale-purple gown.",
  "pair_vorshara"),
]
for face, body, prompt, prefix in JOBS:
    K.run(face, prompt, prefix, reference2=body)
