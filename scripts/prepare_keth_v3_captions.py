"""Honest style captions for Keth's drawn sheet panels (2026-08-05).

Keth v2 rendered with heavy posterized artifacting: 34 of his 41 frames are
DRAWN character-sheet panels (the *_p* splits), and nothing in their captions
said so -- so the LoRA bound the illustration style itself to @Keth. Same
failure class as the Humboldt-cap mis-caption: the image showed one thing,
the caption said another. Fix: say what the image actually is, so the style
stays promptable and only the character binds to the trigger.

Idempotent -- appends only if the words aren't already there. Photoreal
singles (000-010) are untouched.
"""
from pathlib import Path

KETH = (Path(__file__).resolve().parent.parent / "tools" / "ComfyUI"
        / "input" / "lora_keth")
STYLE = ", illustrated character sheet artwork, drawn concept art style"

changed = 0
for txt in sorted(KETH.glob("*_p*.txt")):
    caption = txt.read_text(encoding="utf-8").rstrip()
    if "illustrat" not in caption.lower() and "drawn" not in caption.lower():
        txt.write_text(caption + STYLE, encoding="utf-8")
        changed += 1
print(f"updated {changed} panel captions in {KETH}")
