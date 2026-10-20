"""FACT NET worker (2026-10-08, Barry: "she needs to know what the fuck shes talking about at all times" -> "do all
three, benchmark the fact net first"). Runs in tools/laya-venv (CPU torch + transformers); the backend venv has no torch.

stdin JSON: {"doc": "<everything she read this turn>", "claims": ["sentence", ...], "model": "<hf id, optional>"}
stdout JSON: {"scores": [0..1 per claim], "model": ..., "seconds": ...}
Score = probability the claim is SUPPORTED by the doc (MiniCheck: label 1 = supported). Long docs are chunked and
the best chunk counts (a claim only needs one passage behind it).
"""
import json
import sys
import time

import torch

MODEL = "lytang/MiniCheck-DeBERTa-v3-Large"
CHUNK_WORDS = 350
STRIDE_WORDS = 250


def chunks(doc: str):
    w = doc.split()
    if not w:
        return [""]
    out = []
    for i in range(0, max(1, len(w) - STRIDE_WORDS + 1), STRIDE_WORDS):
        out.append(" ".join(w[i:i + CHUNK_WORDS]))
        if i + CHUNK_WORDS >= len(w):
            break
    return out


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(max(4, torch.get_num_threads() // 2))
    req = json.load(sys.stdin)
    model_id = req.get("model") or MODEL
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id)
    model.eval()
    load_s = time.time() - t0
    docs = chunks(req.get("doc") or "")
    scores = []
    t1 = time.time()
    # SPEED (bench 2026-10-08: 9.2 s/claim scoring every chunk; a 2,000-word script against 10K words of sources
    # would take an hour on this CPU): score only the TOP_K chunks that share the most words with the claim.
    TOP_K = int(req.get("top_k") or 4)
    import re as _re
    _stop = set("the a an and or of to in on for with by as is are was were be it its this that from at not".split())

    def words(s: str) -> set:
        return {w for w in _re.findall(r"[a-z][a-z\-]{2,}", s.lower()) if w not in _stop}

    doc_words = [words(c) for c in docs]
    with torch.no_grad():
        for claim in req.get("claims") or []:
            cw = words(claim)
            ranked = sorted(range(len(docs)), key=lambda i: -len(cw & doc_words[i]))[:TOP_K]
            picked = [docs[i] for i in ranked] or docs[:1]
            best = 0.0
            for i in range(0, len(picked), 8):
                batch = picked[i:i + 8]
                enc = tok(batch, [claim] * len(batch), truncation="only_first", max_length=512, padding=True,
                          return_tensors="pt")
                probs = torch.softmax(model(**enc).logits, dim=-1)[:, 1]
                best = max(best, float(probs.max()))
            scores.append(round(best, 4))
    json.dump({"scores": scores, "model": model_id, "load_seconds": round(load_s, 1),
               "seconds": round(time.time() - t1, 2), "chunks": len(docs)}, sys.stdout)


if __name__ == "__main__":
    main()
