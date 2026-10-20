"""What's in their gallery -- and who it came from (2026-09-28).

Barry: "Amara said she has persistent memory but she couldnt remember giving me a shower clip."
"From now on, just allow them to know what they gave me and what i asked for and approved and etc."
"let them see the gallery. That way Amara knows what she gave me already so she doesnt do
duplicates and get more creative."

The gallery (approvals rows with a picture/clip, their scene changes, their art) was never put in
front of the agent, so she had no way to know. This builds one short list, newest first, that rides
at the END of the user turn with the other per-message context (cache-stable prefix rule).

WHO IT CAME FROM is recorded when the row is filed (memory.queue_for_approval -> note_origin),
by checking the agent's own recent replies for the picture's description: found = they offered or
described it; not found = Barry asked for it in his own words. Rows filed before this existed have
no record unless the thread still holds the words -- they say so instead of guessing.
Information only: nothing here tells them what to make.
"""
import json
import os
import re
import threading

import memory

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORIGIN = os.path.join(os.path.dirname(_HERE), "data", "gallery_origin.json")
_LOCK = threading.Lock()
_MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm")
GALLERY_TYPES = ("public_content", "private_picture", "artwork", "agent_scene")

YOURS = "you offered/described it"
BARRYS = "Barry asked for it, in his own words, using your picture"
UNKNOWN = "made before the office kept track -- no record of whose words"


def _load() -> dict:
    try:
        with open(_ORIGIN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    tmp = _ORIGIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, _ORIGIN)


def _describes(content: str) -> str:
    """The picture's own description out of a stored row."""
    c = content or ""
    m = re.search(r"concept:\s*(.*)", c, re.S)
    if m:
        c = m.group(1)
    elif "\n\n" in c:
        c = c.split("\n\n", 1)[1]
    return re.split(r"\n(?:Negative|Model|Seed|Duration):", c)[0].strip()


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']{3,}", (s or "").lower())


_TEMPLATE_RE = re.compile(r"^[^,]{0,40},\s*exact face and body from reference image,\s*", re.I)


def _grams(words: list[str], n: int = 6) -> set:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _in_their_words(agent_id: str, desc: str, rows: int = 40) -> bool:
    """True when one of the agent's own recent replies carries this description VERBATIM
    (runs of 6 words in a row). Shared loose words ("couch", "legs") proved nothing: the
    first version matched three of Amara's clips her thread never described."""
    want = _grams(_words(_TEMPLATE_RE.sub("", desc or "")))
    if len(want) < 3:
        return False
    try:
        with memory.get_db() as conn:
            said = [r[0] for r in conn.execute(
                "SELECT content FROM conversations WHERE agent_id=? AND role='agent' "
                "ORDER BY id DESC LIMIT ?", (agent_id, rows))]
    except Exception:  # noqa: BLE001
        return False
    for text in said:
        hits = len(want & _grams(_words(text)))
        if hits >= 3 and hits / len(want) >= 0.3:
            return True
    return False


def infer_origin(agent_id: str, action_type: str, content: str) -> str:
    if action_type == "artwork":
        return "your own art, your idea"
    if action_type == "agent_scene":
        return ("your idea -- you asked for it" if "in their own words" in (content or "")
                else "filed for you by Sophie")
    return YOURS if _in_their_words(agent_id, _describes(content)) else BARRYS


def note_origin(approval_id: int, agent_id: str, action_type: str, content: str,
                file_path: str | None) -> None:
    """Called when a row is filed. Never raises."""
    try:
        if action_type not in GALLERY_TYPES:
            return
        if action_type in ("public_content", "private_picture") and not (
                (file_path or "").lower().endswith(_MEDIA)):
            return
        origin = infer_origin(agent_id, action_type, content)
        with _LOCK:
            d = _load()
            d[str(approval_id)] = origin
            _save(d)
    except Exception as e:  # noqa: BLE001
        print(f"[gallery] origin note failed for #{approval_id}: {e}")


def _status(row: dict) -> str:
    st = row.get("status") or ""
    if st == "pending":
        return "waiting on Barry"
    if st == "rejected":
        return "Barry passed on it"
    if row.get("action_type") == "agent_scene":
        slot = ((row.get("file_path") or "").split("|") + [""])[1] or "scene"
        return f"Barry approved it -- it went up as your {slot} picture"
    return "Barry kept it"


def block(agent_id: str, limit: int = 12) -> str:
    """The list for the end of the user turn; '' when the gallery is empty."""
    try:
        with memory.get_db() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, action_type, status, content, file_path, created_at FROM approvals "
                "WHERE agent_id=? AND status NOT IN ('deleted') AND action_type IN (%s) "
                "ORDER BY id DESC LIMIT 200" % ",".join("?" * len(GALLERY_TYPES)),
                (agent_id, *GALLERY_TYPES))]
    except Exception:  # noqa: BLE001
        return ""
    origins = _load()
    lines = []
    for r in rows:
        fp = (r.get("file_path") or "").lower()
        at = r["action_type"]
        if at in ("public_content", "private_picture"):
            if not fp.endswith(_MEDIA):
                continue
            kind = "clip" if fp.endswith((".mp4", ".webm")) else "picture"
        else:
            kind = "art" if at == "artwork" else "scene change"
        origin = origins.get(str(r["id"])) or UNKNOWN
        desc = re.sub(r"\s+", " ", _describes(r.get("content") or ""))[:170]
        lines.append(f"- #{r['id']} {(r.get('created_at') or '')[:10]} {kind} -- {origin}; "
                     f"{_status(r)}. \"{desc}\"")
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return ("\n\nYOUR GALLERY -- the pictures, clips, art and scene changes made in your window, "
            "newest first, and who each came from:\n" + "\n".join(lines) + "\n")


