"""
Local, offline text-to-speech via Piper (OHF-Voice/piper1-gpl) -- genuinely
natural neural voices with zero API key, zero cost, and zero cloud
dependency. This is a deliberate alternative to Windows' own "Online
(Natural)" voices, which enumerate fine via the browser's Web Speech API but
are locked to Microsoft's own first-party apps (Narrator, Edge Read Aloud)
and silently fail to actually synthesize from a regular web page -- Piper
runs the whole model locally, so there's no such restriction.

Voice models were downloaded once via:
    python -m piper.download_voices --download-dir piper_voices <name> ...
(see piper_voices/ at the project root, sibling to backend/)
"""
import io
import re
import wave
from pathlib import Path

from piper import PiperVoice

# Piper reads emoji out as their literal description ("waving hand" etc)
# instead of skipping them -- strip them here so it happens regardless of
# whether a given reply actually followed the no-emoji prompt instruction.
# One definition, shared with kokoro_tts and tone_guard (consolidated
# 2026-08-31 -- it had been copy-pasted into all three).
from textclean import strip_emoji as _strip_emoji

VOICE_DIR = Path(__file__).resolve().parent.parent / "piper_voices"

# One distinct voice per agent -- mixes US/UK accents and genders so no two
# agents sound alike. "high" quality tier used where available (ryan, cori),
# "medium" elsewhere (still natural, just a smaller/faster model).
AGENT_VOICE_FILE = {
    "cio": "en_US-ryan-high.onnx",                        # Victor
    "operations": "en_US-amy-medium.onnx",                 # Priya
    "business": "en_GB-cori-high.onnx",                    # Amara
    "legal": "en_US-joe-medium.onnx",                      # Marcus
    "marketing": "en_GB-alan-medium.onnx",                 # Derek
    "creative": "en_GB-jenny_dioco-medium.onnx",           # Vivian
    "movie": "en_GB-northern_english_male-medium.onnx",    # Elliot
    "engineer": "en_GB-alba-medium.onnx",                  # Sophie
    "taliyah": "en_US-hfc_female-medium.onnx",             # Taliyah
}
DEFAULT_VOICE_FILE = "en_US-ryan-high.onnx"

# Loading an .onnx model takes real time -- cache per voice file so only the
# first request for a given agent pays that cost, not every request.
_voice_cache: dict[str, PiperVoice] = {}


def _get_voice(agent_id: str) -> PiperVoice:
    filename = AGENT_VOICE_FILE.get(agent_id, DEFAULT_VOICE_FILE)
    if filename not in _voice_cache:
        _voice_cache[filename] = PiperVoice.load(str(VOICE_DIR / filename))
    return _voice_cache[filename]


def synthesize(agent_id: str, text: str) -> bytes:
    """Real neural speech, synthesized entirely locally. Returns WAV bytes."""
    voice = _get_voice(agent_id)
    clean_text = _strip_emoji(text)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(clean_text, wav_file)
    return buf.getvalue()
