"""FACT NET (2026-10-08, Barry: "she needs to know what the fuck shes talking about at all times" / "do all three,
benchmark the fact net first" / "A, redo it with the true story").

Every sentence of a video script is checked against WHAT SHE READ THIS TURN (the exact tool text -- library sections,
PubMed abstracts, web pages -- returned by /api/chat as "sources"). A sentence nothing she read supports goes back
to her by number; she fixes or cuts it. Her words are never rewritten here.

Checker: MiniCheck (lytang/MiniCheck-DeBERTa-v3-Large) -- a model trained to answer "is this claim supported by
this document?" -- run on the CPU in tools/laya-venv by scripts/fact_check_worker.py (the backend venv has no
torch). Bench on the bloodroot script: see data/bench_fact_net_2026-10-08.txt. No card time.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(_ROOT, "tools", "laya-venv", "Scripts", "python.exe")
WORKER = os.path.join(_ROOT, "scripts", "fact_check_worker.py")
THRESHOLD = 0.35          # below = "nothing you read says this" (bench 2026-10-08)
MIN_WORDS = 6
# Her own framing -- greetings, promises of what is coming, sign-offs, questions to the viewer -- is not a claim.
_FRAMING_RE = re.compile(r"^(hi|hello|hey|i'?m |i am |today|tonight|in (ten|five|\d+) minutes|let'?s|follow|"
                         r"by the end|here'?s what|we'?re going|you'?ll|you will|stay|welcome|thanks|thank you|"
                         r"so |now,? |and that|that'?s (why|the|it)|imagine|picture this|remember)", re.I)


def sentences(text: str) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        s = s.strip()
        if len(s.split()) >= MIN_WORDS and not s.endswith("?") and not _FRAMING_RE.match(s):
            out.append(s)
    return out


def score(doc: str, claims: list[str], timeout: int = 900) -> list[float] | None:
    """Support scores 0..1 per claim, or None when the checker could not run (never blocks a build)."""
    if not claims or not doc.strip() or not os.path.isfile(PY):
        return None
    try:
        r = subprocess.run([PY, WORKER], input=json.dumps({"doc": doc, "claims": claims}), capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout)
        if r.returncode:
            return None
        return json.loads(r.stdout).get("scores")
    except Exception:  # noqa: BLE001
        return None


def check_video(video: dict, sources: list[str]) -> dict:
    """{"flags": [{"part": n, "sentence": s, "score": x}], "checked": k, "ok": bool}. ok=True when nothing is flagged
    or the checker could not run (reported, not blocking)."""
    doc = "\n\n".join(s for s in (sources or []) if s)
    items = []
    for n, p in enumerate(video.get("parts") or [], 1):
        for s in sentences(str(p.get("say") or "")):
            items.append((n, s))
    if not items:
        return {"flags": [], "checked": 0, "ok": True}
    sc = score(doc, [s for _n, s in items])
    if sc is None:
        return {"flags": [], "checked": 0, "ok": True, "note": "checker did not run"}
    flags = [{"part": n, "sentence": s, "score": round(v, 2)} for (n, s), v in zip(items, sc) if v < THRESHOLD]
    return {"flags": flags, "checked": len(items), "ok": not flags}


def send_back_text(flags: list[dict]) -> str:
    by_part: dict[int, list[str]] = {}
    for f in flags:
        by_part.setdefault(f["part"], []).append(f["sentence"])
    lines = [f"part {n}:\n" + "\n".join(f"  - {s}" for s in ss) for n, ss in sorted(by_part.items())]
    return ("The office checked your script against what you read this turn. These sentences are not backed by "
            "anything you read -- nothing in your sources says this:\n" + "\n".join(lines)
            + "\n\nFor each one: say what your sources actually say instead, or cut it. Keep every other sentence as "
              "it is. Facts only from your notes.")
