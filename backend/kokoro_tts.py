"""
Local, offline text-to-speech via Kokoro (hexgrad/Kokoro-82M, Apache 2.0),
served through kokoro-onnx -- the 2026 upgrade over Piper after the owner's
verdict on Piper's output: "i just hate the robotic voices." Kokoro is a
different generation of model: natural pacing and intonation instead of
read-out-loud flatness, while still being a perfect fit for this machine:

- Runs on CPU via ONNX Runtime -- ZERO VRAM, so it never fights the LLMs or
  AmuseBridge for the 16GB card (the binding constraint on everything).
- Fully offline after a one-time model download (~310MB + 27MB voices).
- Same contract as piper_tts.synthesize(): (agent_id, text) -> WAV bytes,
  so /api/tts and the dashboard needed no changes.

Piper stays installed as the automatic fallback (see main.py's /api/tts):
if Kokoro's model files are missing or it fails for any reason, voices
degrade to Piper instead of dying.

Model files live in kokoro/ at the project root (sibling to backend/,
same pattern as piper_voices/):
    kokoro/kokoro-v1.0.onnx   kokoro/voices-v1.0.bin
Re-download from github.com/thewh1teagle/kokoro-onnx releases if lost.
"""
import io
import re
import threading
import wave
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent.parent / "kokoro"
MODEL_PATH = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

# Kokoro reads emoji out as words, same as Piper did -- strip regardless of
# whether the reply followed the no-emoji prompt instruction.
# One definition, shared with piper_tts and tone_guard (consolidated
# 2026-08-31 -- it had been copy-pasted into all three).
from textclean import strip_emoji as _strip_emoji


# One distinct voice per agent -- prefix key: a=American/b=British,
# f=female/m=male. Picked to keep every agent recognizably different and to
# roughly preserve each agent's old Piper accent/gender identity.
AGENT_VOICE = {
    "cio": "am_michael",      # Victor -- composed, authoritative US male
    "operations": "hf_alpha", # Priya -- Indian-accented female (owner's call
                              # 2026-07-30: "Priya should be indian american");
                              # hf_beta is the alternate if this one reads
                              # English oddly -- these voices were trained on
                              # Hindi, accent quality on English varies.
    "business": "bf_emma",    # Amara -- warm UK female (was UK on Piper too)
    "legal": "bm_george",     # Marcus -- measured UK male
    "marketing": "am_adam",   # Derek -- energetic US male
    "creative": "bf_isabella", # Vivian -- deeper, richer British female
                               # (owner imagines her as a British Black
                               # woman, 2026-07-30; was af_aoede)
    "movie": "bm_fable",      # Elliot -- British storyteller, fits a director
    "engineer": "bf_lily",    # Sophie -- lighter UK female
    "taliyah": "af_bella",    # Taliyah -- rich, expressive, grounded US
                              # female (owner imagines her as a natural
                              # Black American woman, 2026-07-30; was
                              # af_heart -- swap back if he prefers it)
    "ilnora": "af_heart",     # Ilnora -- 2026-09-24, her reels need a voice (she fell back to Victor's
                              # male voice). af_heart = one of Kokoro's top-rated voices, free since
                              # Taliyah moved to af_bella. Barry's call if he wants her different.
}
DEFAULT_VOICE = "am_michael"

_kokoro = None
_lock = threading.Lock()


def files_present() -> bool:
    return MODEL_PATH.is_file() and VOICES_PATH.is_file()


def _get_kokoro():
    """Lazy singleton -- the ONNX session load takes a few seconds, paid
    once on the first voice request, never per call."""
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _kokoro


def synthesize(agent_id: str, text: str) -> bytes:
    """Natural neural speech, synthesized entirely locally on CPU.
    Returns WAV bytes (16-bit PCM). Raises on any failure -- the caller
    (main.py's /api/tts) is responsible for falling back to Piper."""
    if not files_present():
        raise FileNotFoundError(f"Kokoro model files missing in {MODEL_DIR}")
    clean = _strip_emoji(text).strip()
    if not clean:
        raise ValueError("Nothing speakable after cleanup")
    voice = AGENT_VOICE.get(agent_id, DEFAULT_VOICE)
    # kokoro-onnx's create() isn't documented thread-safe; /api/tts runs in
    # FastAPI's threadpool, so serialize access to the shared session.
    with _lock:
        samples, sample_rate = _get_kokoro().create(clean, voice=voice, speed=1.0, lang="en-us")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buf.getvalue()
