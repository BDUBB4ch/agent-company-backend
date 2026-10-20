"""Post-generation tone cleanup, currently just for Taliyah.

Four separate prompt rewrites (worked-example, negative "don't say X" list,
positive-only) and one model swap (qwen3.5:9b, reverted -- caused 300s+
hangs on her full prompt) all failed to reliably keep her out of slang,
nicknames, and emoji in real multi-turn conversation, even when short
isolated tests passed. This does not try to talk the model out of it again
-- it deterministically strips the specific, real, recurring offenders
pulled from actual failure transcripts, after generation. Zero risk of
hangs (no extra model call), zero dependence on the model's variable
prompt compliance.

Two layers:
  1. clean_taliyah_reply() -- fast regex pass, catches exact known-bad
     terms pulled from real transcripts. Free, instant, zero model call.
  2. rewrite_taliyah_reply() -- confirmed live that the regex layer alone
     isn't enough: the model drifted into "fam"/"tryna"/"ya"/"tho", none
     of which were in any prior failure transcript. A finite blocklist
     can't cover the space of slang a model might produce. This runs a
     second, narrow, persona-free rewrite call -- the same structural fix
     already proven in this codebase for a different problem (see
     main.py's _force_image_prompt): a dedicated call with nothing else
     competing for the model's attention holds instructions that get
     diluted inside the full persona + tools + thinking prompt.
"""

import re

import llm_router

# Shared with kokoro_tts and piper_tts (consolidated 2026-08-31 -- the same
# regex lived in all three). This module's old local copy listed
# \U0001F900-\U0001F9FF, which sits INSIDE \U0001F300-\U0001FAFF and so added
# nothing; the shared set is a strict superset of it, differing only by also
# dropping the zero-width joiner left behind when a combined emoji is stripped.
from textclean import EMOJI_RE as _EMOJI_RE

# Direct-address nicknames/pet-names actually seen in live failure
# transcripts -- stripped as a whole address term (with a leading comma,
# if any), not replaced, since "Hey, sweetie" -> "Hey," reads fine but a
# forced substitute wouldn't.
# 2026-10-17, Barry: "she should have something more like some slang not gross slang" -- the pet names stay out;
# "homegirl / homie / yo / fam / dude / bro" are how she talks to a friend and are no longer stripped.
_ADDRESS_NICKNAMES = [
    "sweetie", "sweetheart", "boo", "chief", "partner", "boss",
]

# CJK leakage seen once in a real transcript (from the since-reverted
# negative-phrasing prompt). Handled separately from _ADDRESS_NICKNAMES
# because \b relies on a word/non-word transition, and Python's re treats
# CJK characters as \w -- so "the甜心" (no space) has no boundary between
# "e" and "甜" and \b silently fails to match there.
_CJK_LEAKAGE = ["甜心"]

# TEXTING SHORTHAND -> the full word. 2026-10-17 (Barry: proper speech plus some slang, "not gross slang"): the
# slang rows that used to live here ("aight", "no cap", "real talk", "y'all", "gotcha", "ride or die", "no shade",
# "ya dig") are DELETED -- that is her talking. What stays is spelling, not voice: letters standing in for words.
_SLANG_REPLACEMENTS = {
    "respectah mode": "a more respectful tone",
    "esp": "especially",
    "u": "you",
    "ur": "your",
    "r": "are",
    "w/": "with",
    "tryna": "trying to",
    "dat": "that",
}


def clean_taliyah_reply(text: str) -> str:
    if not text:
        return text
    cleaned = text

    cleaned = _EMOJI_RE.sub("", cleaned)

    for term in _ADDRESS_NICKNAMES:
        cleaned = re.sub(rf"[,'’]?\s*\b{re.escape(term)}\b[,'’]?", "", cleaned, flags=re.IGNORECASE)

    for term in _CJK_LEAKAGE:
        cleaned = cleaned.replace(term, "")

    for slang, plain in _SLANG_REPLACEMENTS.items():
        # (?<!\w)...(?!\w) instead of \b...\b: \b only fires on a
        # word/non-word transition, so it silently fails to match at the
        # END of a term like "w/" -- both "/" and the space after it are
        # non-word characters, so there's no transition there for \b to
        # find. Confirmed live: "w/" never got replaced under \b\b.
        cleaned = re.sub(rf"(?<!\w){re.escape(slang)}(?!\w)", plain, cleaned, flags=re.IGNORECASE)

    # 2026-10-17: g-dropping ("chillin'", "sayin'") and "'bout" are no longer restored -- Barry wants some slang
    # back. The old _restore_g pass and the wit'/'bout/ta rewrites are deleted, not disabled (his rule).

    # Clean up whitespace/punctuation artifacts left behind by removals.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,.!?]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"^[\s,]+", "", cleaned)
    cleaned = cleaned.strip()

    # The dictionary replacements above are all lowercase ("aight" ->
    # "alright"), which reads wrong when that word opens the reply or a
    # sentence -- re-capitalize after the fact rather than special-casing
    # every replacement's capitalization up front.
    cleaned = re.sub(
        r"(^\s*|[.!?]\s+)([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        cleaned,
    )

    return cleaned


# PROPER FOR THE VOICE (2026-10-17, Barry: "for the voice, her texts need to be proper"). Her written reply keeps her
# slang; the copy a voice engine READS gets the spelled-out words, because "chillin'", "'bout", "aight" trip TTS.
# These are the rows deleted from the display pass above, kept here for sound only.
_VOICE_REPLACEMENTS = {
    "aight": "alright", "ya dig": "you know", "yessir": "yes sir", "no cap": "for real", "y'all": "you all",
    "yall": "you all", "ya": "you", "til": "until", "gonna": "going to", "wanna": "want to", "gotta": "got to",
    "kinda": "kind of", "lemme": "let me", "gimme": "give me", "lowkey": "low key", "imma": "I'm going to",
    "finna": "about to", "ain't": "isn't",
}


def proper_for_voice(text: str) -> str:
    """The spoken form of a reply: every word spelled out so the voice reads it cleanly. Display text is untouched."""
    if not text:
        return text
    spoken = clean_taliyah_reply(text)
    for slang, plain in _VOICE_REPLACEMENTS.items():
        spoken = re.sub(rf"(?<!\w){re.escape(slang)}(?!\w)", plain, spoken, flags=re.IGNORECASE)
    spoken = re.sub(r"\b(\w+)in['’](?!t\b)", lambda m: m.group(1) + "ing", spoken)   # chillin' -> chilling
    spoken = re.sub(r"\bwit['’]", "with", spoken, flags=re.IGNORECASE)
    spoken = re.sub(r"['’]bout\b", "about", spoken, flags=re.IGNORECASE)
    spoken = re.sub(r"\bta\b", "to", spoken, flags=re.IGNORECASE)
    return spoken


_REWRITE_SYSTEM_PROMPT = (
    "You rewrite a short passage into normal American English -- the "
    "way a plainspoken, ordinary adult writes a genuine reply to a "
    "friend, warm and direct, nothing added on top of that. Every word "
    "is spelled out in full and standard: 'you' not 'u', 'with' not "
    "'w/', 'especially' not 'esp', 'going to' not 'gonna'. This holds "
    "no matter how casual or slang-heavy the original passage is -- "
    "match its warmth and its meaning, just in full, standard, normal "
    "American English words throughout, not the original's specific "
    "phrasing or spelling. Keep the same length and the same paragraph "
    "breaks as the original. Output ONLY the rewritten text and nothing "
    "else -- no preamble, no quotation marks, no explanation."
)


async def rewrite_taliyah_reply(reply: str, model: str) -> str:
    """Run AFTER clean_taliyah_reply(). Never let a failure here take down
    Taliyah's actual reply -- falls back to the regex-cleaned text."""
    if not reply or not reply.strip():
        return reply
    try:
        rewritten = await llm_router.generate(
            "ollama",
            _REWRITE_SYSTEM_PROMPT,
            [{"role": "user", "content": reply}],
            model=model,
            use_tools=False,
            use_thinking=False,
        )
        rewritten = rewritten.strip()
        return rewritten or reply
    except Exception:
        return reply
