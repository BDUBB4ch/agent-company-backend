"""Probe + transcribe Barry's five character voice samples (2026-08-20).

HONEST SCOPE. probe_media gives duration and levels; transcribe_audio (faster-whisper,
CPU, zero VRAM) gives the WORDS. Neither reports timbre, register, pitch or accent --
Whisper is speech-only and this office has no audio-understanding model installed
(Qwen2-Audio-7B was approved and never installed). So this script establishes what is
measurable and nothing else. Any claim about how a voice SOUNDS has to come from Barry.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import media_understanding as mu

DL = pathlib.Path.home() / "Downloads"
FILES = [
    "B dub Voice sample.mp3",
    "Keth Voice.mp3",
    "Bia Voice.mp3",
    "Tazz Voice.mp3",
    "Yannah Voice.mp3",
]


def main() -> None:
    for name in FILES:
        p = DL / name
        print("=" * 72)
        print(name)
        if not p.exists():
            print("  MISSING at", p)
            continue
        print(f"  {p.stat().st_size:,} bytes")
        try:
            print("  probe:", mu.probe_media(str(p)))
        except Exception as e:
            print("  probe FAILED:", type(e).__name__, e)
        try:
            t = mu.transcribe_audio(str(p))
            print("  transcript:", t if t else "(no speech detected)")
        except Exception as e:
            print("  transcribe FAILED:", type(e).__name__, e)
        print()


if __name__ == "__main__":
    main()
