"""Where are we in the script -- Elliot's bookmark.

Barry, 2026-09-16: "when i say next shot, he needs to know where we are at,
because i may forget."

Until now nothing tracked position. "next shot" named no shot, so it routed to
plain chat and Elliot guessed. This is a mechanical bookmark, no model in it:

  * every time a shot is served or written for Elliot, `mark()` records its label
  * "next shot" / "keep going" / "the one after" resolves to the block AFTER the
    bookmark in script order and is rewritten into a named-shot ask, so every
    existing shot mechanism (grounding, motion, handles, voices, the fence)
    fires exactly as if Barry had typed the label
  * "where are we" / "what shot are we on" is answered straight from the
    bookmark and the script order -- no model call, no GPU

The bookmark lives in app_settings (`script_pos:<office>`), read fresh per call,
so it survives restarts and needs none.
"""
import re

import memory
import script_index

_KEY = "script_pos:{office}"

# "next shot", "next one", "next block", "keep going", "continue", "carry on",
# "the one after that", "what's next", "next". Deliberately NOT "shot 05" --
# a named shot is handled by the existing parser and should win.
NEXT_RE = re.compile(
    r"(?i)\b(?:next\s+(?:shot|one|block|scene|b-?roll)|keep\s+going|"
    r"carry\s+on|continue|the\s+(?:one|shot)\s+after(?:\s+that)?|"
    r"what'?s\s+next|moving\s+on|on\s+to\s+the\s+next|^\s*next\s*[.!?]?\s*$)")

# "where are we", "where were we", "what shot are we on", "where did we leave
# off", "what did we do last", "which shot".
WHERE_RE = re.compile(
    r"(?i)\b(?:where\s+(?:are|were)\s+we|where\s+did\s+we\s+(?:leave|stop)|"
    r"what\s+shot\s+(?:are\s+we\s+on|was\s+that|did\s+we)|which\s+shot\s+(?:are\s+we|was)|"
    r"what\s+did\s+we\s+do\s+last|where\s+we\s+at|what\s+(?:shot|block)\s+is\s+next)\b")

# "go back", "previous shot", "the one before"
PREV_RE = re.compile(
    r"(?i)\b(?:previous\s+(?:shot|one|block)|(?:the\s+)?(?:one|shot)\s+before(?:\s+that)?|"
    r"go\s+back\s+(?:one|a\s+shot))\b")


def _labels(office_name: str) -> list[str]:
    """Ordered shot/B-ROLL/SCENE labels of the office's default script."""
    name = script_index.default_script(office_name)
    if not name:
        return []
    # get_skill_content returns {"found": bool, "skills": [{"title", "content"}]}
    d = memory.get_skill_content(office_name, name) or {}
    text = ""
    for s in d.get("skills") or []:
        if (s.get("title") or "") == name:
            text = s.get("content") or ""
            break
    if not text and d.get("skills"):
        text = d["skills"][0].get("content") or ""
    if not text:
        return []
    return [b["label"] for b in script_index.parse_blocks(text)
            if b.get("kind") == "shot" and b.get("label")]


def get(office_name: str) -> str:
    return (memory.get_setting(_KEY.format(office=office_name)) or "").strip()


def mark(office_name: str, label: str) -> None:
    """Record the block Barry and Elliot are on. Called after a shot is served."""
    label = (label or "").strip()
    if not label:
        return
    memory.set_setting(_KEY.format(office=office_name), label)
    print(f"[script-pos] {office_name}: now at {label}")


def _index_of(labels: list[str], label: str) -> int:
    norm = lambda s: re.sub(r"\s+", " ", s.strip().upper())
    target = norm(label)
    for i, l in enumerate(labels):
        if norm(l) == target:
            return i
    return -1


def resolve(office_name: str, message: str) -> dict:
    """Turn a relative ask into a concrete one.

    Returns {} when the message is not a relative ask, else:
      {"kind": "next"|"prev"|"where", "label": <resolved or None>,
       "current": <bookmark or None>, "reply": <text for 'where' asks>}
    """
    msg = message or ""
    kind = None
    if WHERE_RE.search(msg):
        kind = "where"
    elif PREV_RE.search(msg):
        kind = "prev"
    elif NEXT_RE.search(msg):
        kind = "next"
    if not kind:
        return {}

    labels = _labels(office_name)
    current = get(office_name)
    idx = _index_of(labels, current) if current else -1

    if kind == "where":
        if not labels:
            reply = "I don't have a script loaded, so I can't tell you where we are."
        elif idx < 0:
            reply = ("We haven't started working through the script this round -- no bookmark yet. "
                     f"The first block is {labels[0]}. Say 'next shot' and I'll start there, "
                     "or name any shot.")
        else:
            nxt = labels[idx + 1] if idx + 1 < len(labels) else None
            reply = f"We're on {labels[idx]} ({idx + 1} of {len(labels)})."
            reply += f" Next up is {nxt}." if nxt else " That was the last block in the script."
        return {"kind": kind, "label": None, "current": current or None, "reply": reply}

    if not labels:
        return {"kind": kind, "label": None, "current": current or None,
                "reply": "I don't have a script loaded to move through."}

    if kind == "next":
        if idx < 0:
            target = labels[0]
        elif idx + 1 < len(labels):
            target = labels[idx + 1]
        else:
            return {"kind": kind, "label": None, "current": current,
                    "reply": f"{labels[idx]} was the last block -- there is no next shot in the script."}
    else:  # prev
        if idx <= 0:
            return {"kind": kind, "label": None, "current": current or None,
                    "reply": "We're at the start -- there's nothing before this."}
        target = labels[idx - 1]

    return {"kind": kind, "label": target, "current": current or None, "reply": None}
