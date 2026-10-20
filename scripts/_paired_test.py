import sys; sys.path.insert(0,"scripts")
import kontext_generate as K
K.run("keth_ref_canon.png",
      "Place the small grey-skinned alien man in a dim spacecraft corridor with teal light "
      "strips along the floor, showing him full body standing, while preserving his exact "
      "wrinkled facial features, large dark green eyes with no visible white, small "
      "low-profile ears, grey skin, worn grey facility jumpsuit and bare feet.",
      "pair_keth", reference2="keth_body.png")
K.run("bdubb_ref.png",
      "Place the bearded man in the black star cap and black tactical vest in a sunlit "
      "industrial doorway, showing him full body standing, while preserving his exact facial "
      "features, salt-and-pepper beard, brownish-red skin tone, black cap, black vest over "
      "black hoodie, black cargo pants, black boots and gold number 4 pendant.",
      "pair_bdubb", reference2="bdubb_body.png")
