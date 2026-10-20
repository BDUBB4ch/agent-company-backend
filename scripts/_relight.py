"""Re-run Yannah and Tazz with proper key light. The characters were correct in
the previous pass -- only the exposure was wrong, because 'dim corridor' and
'dark cargo hold' are instructions the model followed literally. Lighting is
stated explicitly here instead of being left to the environment."""
import sys; sys.path.insert(0,"scripts")
import kontext_generate as K

K.run("yannah_face.png",
  "Place the young alien woman standing full body in a ship corridor with teal light strips, "
  "brightly lit by a soft key light on her face and body so she is clearly visible and well "
  "exposed, while preserving her exact facial features, green and gold double-ringed irises, "
  "pointed ears, the shaved side of her short asymmetrical wavy hair, and her black "
  "form-fitting tactical jumpsuit with teal piping and black boots.",
  "lit_yannah", reference2="yannah_body.png")

K.run("tazz_face.png",
  "Place the muscular alien woman standing full body in a cargo hold, brightly lit by a soft "
  "key light on her face and body so she is clearly visible and well exposed, while preserving "
  "her exact facial features, pink and blue double-ringed irises, pointed ears, light skin, her "
  "two long dark braids, and her all-black sleeveless one-piece tactical outfit with harness, "
  "thigh rig and black boots.",
  "lit_tazz", reference2="tazz_body.png")
