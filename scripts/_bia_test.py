"""Test the new Bia references through Kontext. Prompt written to his 2026-08-10
spec and guardrails: documentary realism, no pin-up posing, no text/logos, natural
proportions, hazel-green eyes with the violet ring, non-glowing gold spots.
Bright environment on purpose -- 'dim'/'dark' scene words underexposed the whole
frame on Yannah and Tazz."""
import sys; sys.path.insert(0, "scripts")
import kontext_generate as K

K.run("bia_face.png",
  "Place the athletic woman standing full body in a bright ship corridor with pale walls and "
  "strong even daylight, a natural documentary-style standing pose, fully lit and well exposed, "
  "while preserving her exact facial features, her hazel-green double-ringed irises with the "
  "faint violet ring, her subtly pointed ears, the subtle gold spots on her skin, her short "
  "faded pixie shaved at the sides, and her black form-fitting tactical bodysuit with the "
  "utility belt, shoulder rig and black boots.",
  "test_bia_new", reference2="bia_body.png")
