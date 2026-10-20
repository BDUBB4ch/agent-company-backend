"""Put Tazz's gender back into her captions (2026-08-05).

Tazz v2 rendered her as a MAN. Every frame in lora_tazz shows a woman with
twin braids and violet eyes -- but not one caption said "woman". The trigger
learned "person in tactical gear with braids", and combined with Barry's
"Tazz reads better muscular" ruling the base model's prior filled the gap
with a male body.

Same failure class as the Humboldt cap: the caption did not say what the
image showed. Fix is one word, applied honestly to all 29.

Idempotent -- skips captions that already name her a woman.
"""
from pathlib import Path

TAZZ = (Path(__file__).resolve().parent.parent / "tools" / "ComfyUI"
        / "input" / "lora_tazz")

changed = skipped = 0
for txt in sorted(TAZZ.glob("*.txt")):
    caption = txt.read_text(encoding="utf-8").strip()
    low = caption.lower()
    if "woman" in low or "female" in low:
        skipped += 1
        continue
    # "@Tazz, close-up portrait, ..." -> "@Tazz, a woman, close-up portrait, ..."
    if caption.startswith("@Tazz"):
        rest = caption[len("@Tazz"):].lstrip(", ")
        caption = f"@Tazz, a woman, {rest}" if rest else "@Tazz, a woman"
    else:
        caption = f"a woman, {caption}"
    txt.write_text(caption, encoding="utf-8")
    changed += 1

print(f"captions updated: {changed}, already fine: {skipped}")
