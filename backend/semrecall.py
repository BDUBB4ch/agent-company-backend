"""Meaning-based recall -- the second door into an agent's shelf (2026-09-15).

Barry: "ok keep bonsai, now do my agents." The keyword scorer in recall.py
does no stemming and no synonyms, and the record is full of the cost:
"looks" is not "look", "venting" is not "vent", "hurt" never finds the scene
that says "wounds". Embeddings were declined in August because they cost
VRAM. They do not any more: BAAI/bge-small-en-v1.5 runs on the CPU through
onnxruntime (already in the venv, no torch), 384 dims, ~0.5 ms per embed,
65 MB on disk under models/embeddings, offline after the one download.

What this module does and does NOT do:
  * It scores cosine similarity between the message and each on-demand doc's
    ROUTING TEXT (title + USE WHEN line + the opening of the body). It never
    decides on its own what to inject -- recall.py owns eligibility, floors,
    budgets and every explicit door. Here a strong similarity may make a doc
    eligible and lifts its rank; that is all.
  * Vectors live in one SQLite table (fact_vectors) keyed by fact id and a
    hash of the embedded text, so a doc is re-embedded only when it changes.
  * Everything is local. local_files_only=True: the backend never reaches
    the network for this, ever. A missing model = the door stays closed.
  * OFF by default: app_settings `semantic_recall` = "true" turns it on,
    live, no restart. scripts/test_semantic_recall_2026_09_15.py measures it.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

import numpy as np

import memory

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "models", "embeddings")
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Calibrated in scripts/test_semantic_recall_2026_09_15.py against the real
# shelves: greetings and small talk must stay under it on every doc, and the
# paraphrases the keyword door misses must clear it on the right doc.
SEM_MIN = 0.62
# Added to the keyword score for a doc above SEM_MIN: int(sim * SEM_WEIGHT).
# 30 puts a 0.65 match at +19 -- past MIN_SCORE on its own, which is the point.
SEM_WEIGHT = 30
# How much of a doc's body rides into the embedded text after the routing
# line. bge-small's window is 512 tokens; ~1500 chars of opening keeps the
# routing declaration dominant while giving unrouted docs a fair signature.
BODY_CHARS = 1500

_model = None
_model_lock = threading.Lock()
_model_failed: str | None = None


def is_enabled() -> bool:
    try:
        return str(memory.get_setting("semantic_recall", "false") or "").strip().lower() == "true"
    except Exception:
        return False


def _embedder():
    """Lazy, one per process, never touches the network."""
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        raise RuntimeError(_model_failed)
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextEmbedding
            t0 = time.monotonic()
            _model = TextEmbedding(MODEL_NAME, cache_dir=CACHE_DIR, local_files_only=True)
            print(f"[semrecall] {MODEL_NAME} loaded on CPU in {time.monotonic()-t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            _model_failed = f"embedding model unavailable ({exc})"
            raise RuntimeError(_model_failed)
    return _model


# Docs the meaning door never opens. They are not knowledge to route on:
# summaries of old chats, the agent's own home/appearance notes, their
# journals. The keyword door treats them as before. Measured 2026-09-15 pass
# 1: with these included, "how much runway" pulled in a conversation summary
# and "ok cool" nearly cleared the floor on me-at-home.
EXCLUDE_PREFIXES = ("conversation-history", "me-at-home", "me-in-my-office", "my-home",
                    "my-appearance", "my-reference-pictures", "mind-", "worknote-",
                    "note-", "prompt-exemplars", "style-exemplars", "my-code-fixes",
                    "team-loops", "my-lessons")
# Chunking (pass 2). Pass 1 embedded title + routing line + a 1500-char
# opening, and the meaning door found nothing the keyword door had missed:
# the routing lines are keyword lists, not sentences, so their vectors are
# mush. Now each doc is title+routing PLUS its body in ~1200-char chunks,
# and the doc's similarity is the best chunk -- a paraphrase lands on the
# paragraph that actually discusses it.
CHUNK_CHARS = 1200
MAX_CHUNKS = 14          # ~17K chars covered; larger docs are judged by their head


def routable(fact: dict) -> bool:
    sn = (fact.get("source_name") or "").lower()
    return not sn.startswith(EXCLUDE_PREFIXES)


def doc_chunks(fact: dict) -> list[str]:
    """Chunk 0 = what the doc is FOR (title + routing line); 1..n = the body."""
    title = memory._skill_title(fact).replace("-", " ").replace("_", " ")
    use_when = memory._skill_use_when(fact, max_len=1200) or ""
    body = (fact.get("content") or "")
    lines = [ln for ln in body.splitlines()
             if ln.strip() and not ln.strip().upper().startswith("USE WHEN:")]
    text = "\n".join(lines[1:] if lines and lines[0].strip().lower() == title.lower() else lines)
    chunks = [f"{title}\n{use_when}".strip()]
    # Split on paragraph breaks first so a chunk is a coherent passage.
    buf = ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > CHUNK_CHARS and buf:
            chunks.append(f"{title}\n{buf.strip()}")
            buf = ""
        buf += para + "\n\n"
        if len(chunks) >= MAX_CHUNKS:
            break
    if buf.strip() and len(chunks) < MAX_CHUNKS:
        chunks.append(f"{title}\n{buf.strip()}")
    return chunks


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _ensure_table(conn) -> None:
    # v2 (chunked): one row per (fact, chunk). The pass-1 table (one row per
    # fact, PRIMARY KEY fact_id) is dropped -- it was a cache, nothing else.
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name='fact_vectors'").fetchone()
    if row and "chunk_idx" not in (row["sql"] or ""):
        conn.execute("DROP TABLE fact_vectors")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fact_vectors ("
        "fact_id INTEGER NOT NULL, chunk_idx INTEGER NOT NULL, model TEXT NOT NULL, "
        "text_hash TEXT NOT NULL, vec BLOB NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (fact_id, chunk_idx))")


def vectors_for(facts: list[dict]) -> dict[int, np.ndarray]:
    """fact id -> (n_chunks x dims) matrix, embedding only what is new or changed."""
    if not facts:
        return {}
    chunks = {int(f["id"]): doc_chunks(f) for f in facts}
    hashes = {fid: _hash("\n<<chunk>>\n".join(c)) for fid, c in chunks.items()}
    out: dict[int, np.ndarray] = {}
    with memory.get_db() as conn:
        _ensure_table(conn)
        ids = list(chunks)
        q = ("SELECT fact_id, chunk_idx, text_hash, vec FROM fact_vectors "
             "WHERE model = ? AND fact_id IN (%s) ORDER BY fact_id, chunk_idx"
             % ",".join("?" * len(ids)))
        rows: dict[int, list] = {}
        for row in conn.execute(q, [MODEL_NAME, *ids]):
            fid = int(row["fact_id"])
            if row["text_hash"] == hashes[fid]:
                rows.setdefault(fid, []).append(np.frombuffer(row["vec"], dtype=np.float32))
        for fid, vs in rows.items():
            if len(vs) == len(chunks[fid]):
                out[fid] = np.vstack(vs)
    missing = [fid for fid in ids if fid not in out]
    if missing:
        model = _embedder()
        t0 = time.monotonic()
        flat = [(fid, i, txt) for fid in missing for i, txt in enumerate(chunks[fid])]
        vecs = list(model.embed([t for _, _, t in flat], batch_size=32))
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with memory.get_db() as conn:
            _ensure_table(conn)
            for fid in missing:
                conn.execute("DELETE FROM fact_vectors WHERE fact_id = ? AND model = ?", (fid, MODEL_NAME))
            per: dict[int, list] = {}
            for (fid, i, _), v in zip(flat, vecs):
                v = np.asarray(v, dtype=np.float32)
                per.setdefault(fid, []).append(v)
                conn.execute(
                    "INSERT OR REPLACE INTO fact_vectors (fact_id, chunk_idx, model, text_hash, vec, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (fid, i, MODEL_NAME, hashes[fid], v.tobytes(), now))
            conn.commit()
        for fid, vs in per.items():
            out[fid] = np.vstack(vs)
        print(f"[semrecall] embedded {len(flat)} chunk(s) of {len(missing)} doc(s) "
              f"in {1000*(time.monotonic()-t0):.0f}ms")
    return out


def query_vector(message: str) -> np.ndarray:
    model = _embedder()
    # query_embed applies bge's retrieval instruction to the short side.
    return np.asarray(list(model.query_embed([message]))[0], dtype=np.float32)


def similarities(message: str, facts: list[dict]) -> dict[int, float]:
    """fact id -> cosine similarity to the message (bge vectors are unit
    length, so a dot product is the cosine). Empty dict if the model is
    unavailable -- recall then behaves exactly as before."""
    facts = [f for f in facts if routable(f)]
    if not facts or not (message or "").strip():
        return {}
    q = query_vector(message)
    vecs = vectors_for(facts)
    qn = q / (np.linalg.norm(q) or 1.0)
    out = {}
    for fid, m in vecs.items():
        norms = np.linalg.norm(m, axis=1)
        norms[norms == 0] = 1.0
        sims = (m / norms[:, None]) @ qn
        out[fid] = float(sims.max())      # a doc is as relevant as its best passage
    return out
