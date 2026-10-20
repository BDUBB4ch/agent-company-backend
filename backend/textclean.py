"""Shared text cleanup used by more than one subsystem.

WHY IT EXISTS: the same emoji regex + strip function was copy-pasted into
THREE modules -- kokoro_tts.py, piper_tts.py and tone_guard.py -- so a fix in
one never reached the other two. Consolidated 2026-08-31.

The three sets were already equivalent in practice: tone_guard's extra
\\U0001F900-\\U0001F9FF range sits INSIDE \\U0001F300-\\U0001FAFF, so it added
nothing, and the only genuine difference was that tone_guard did not strip the
zero-width joiner. The union below is a strict superset of all three, so
nothing that used to be stripped stops being stripped -- tone_guard simply also
drops orphaned joiners now, which is invisible garbage either way.

Deliberately imports nothing from this project: it must stay safe for any
module to import without creating a cycle.
"""

from __future__ import annotations

import re

# Both TTS engines read emoji ALOUD as their literal description ("waving
# hand"), and Taliyah's tone guard strips them from chat text. Same job, one
# definition.
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # symbols, pictographs, emoticons, transport
    "\U00002600-\U000027BF"  # misc symbols & dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicator letters (flag emoji)
    "\U0000FE0F"             # variation selector-16 (emoji presentation)
    "\U0000200D"             # zero-width joiner (combined emoji)
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str, collapse_spaces: bool = True) -> str:
    """Remove emoji. `collapse_spaces` closes the gaps they leave behind.

    The TTS callers want the collapse (a double space becomes an audible
    pause); tone_guard runs its own whitespace pass afterwards and passes
    False so this one does not fight it.
    """
    cleaned = EMOJI_RE.sub("", text)
    if collapse_spaces:
        cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned
