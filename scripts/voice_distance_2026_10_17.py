"""VOICE DISTANCE (2026-10-17, Barry: "they all kinda talk the same" / "run the five-prompt before/after measurement").
The same five prompts to every seat on the personal channel (tools off, nothing acts), replies saved, then a
stylometric sameness score across seats. Lower = more distinct. Run once BEFORE a change and once AFTER; compare.
    run:    venv/Scripts/python.exe scripts/voice_distance_2026_10_17.py run <tag>        (50 turns, ~1 h of the card)
    score:  venv/Scripts/python.exe scripts/voice_distance_2026_10_17.py score <tag> [<tag2>]
Replies land in data/voice_measure/<tag>/<agent>.json; the measurement turns are tagged by time so they can be
removed from the threads afterwards (scripts/voice_distance_2026_10_17.py purge <tag>)."""
import datetime
import itertools
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
API = "http://127.0.0.1:8420"
OUT = os.path.join(ROOT, "data", "voice_measure")
SEATS = ["cio", "operations", "business", "legal", "marketing", "creative", "movie", "engineer", "taliyah", "ilnora"]
PROMPTS = [
    "What did you get up to yesterday? A few lines.",
    "Tell me one thing you believe that most people around you don't.",
    "I'm thinking about spending $500 on a new tool for the business. Talk me into it or out of it.",
    "Describe your kitchen to me.",
    "Someone told me you're wrong about something. How do you handle that?",
]
STOP = set("the a an and or but if of to in on at for with by from as is are was were be been being i you he she it we "
           "they me him her us them my your his its our their this that these those there here not no yes do does did "
           "have has had will would can could should may might just so than then too very what which who whom when where "
           "why how all any both each few more most other some such only own same s t ll re ve d m im ive dont cant".split())


def chat(agent_id: str, message: str) -> str:
    body = json.dumps({"agent_id": agent_id, "message": message, "personal": True}).encode("utf-8")
    req = urllib.request.Request(f"{API}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        return (json.loads(r.read().decode("utf-8")).get("reply") or "").strip()


def run(tag: str) -> None:
    d = os.path.join(OUT, tag)
    os.makedirs(d, exist_ok=True)
    started = datetime.datetime.now(datetime.UTC).isoformat()     # conversations.timestamp is UTC isoformat
    for aid in SEATS:
        path = os.path.join(d, f"{aid}.json")
        if os.path.isfile(path):
            print(f"{aid}: already done", flush=True)
            continue
        replies = []
        for p in PROMPTS:
            t0 = time.time()
            try:
                replies.append(chat(aid, p))
            except Exception as exc:  # noqa: BLE001
                replies.append("")
                print(f"{aid}: FAILED on '{p[:30]}' {type(exc).__name__}: {exc}", flush=True)
            print(f"{aid}: {len(replies)}/5 {time.time() - t0:.0f}s", flush=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"agent": aid, "prompts": PROMPTS, "replies": replies, "started": started}, fh, indent=1)
    with open(os.path.join(d, "window.json"), "w", encoding="utf-8") as fh:
        json.dump({"started": started, "ended": datetime.datetime.now(datetime.UTC).isoformat()}, fh)
    print("done", flush=True)


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP and len(w) > 2]


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def features(text: str) -> dict:
    sents = sentences(text)
    toks = re.findall(r"[A-Za-z']+", text)
    n = max(1, len(toks))
    return {
        "avg_sentence_len": round(len(toks) / max(1, len(sents)), 1),
        "contraction_rate": round(sum(1 for t in toks if "'" in t) / n, 3),
        "exclaim_per_100w": round(100 * text.count("!") / n, 2),
        "question_per_100w": round(100 * text.count("?") / n, 2),
        "first_person_rate": round(sum(1 for t in toks if t.lower() in ("i", "i'm", "i'd", "i'll", "i've", "my", "me")) / n, 3),
        "words": len(toks),
    }


def score(tag: str) -> dict:
    d = os.path.join(OUT, tag)
    data = {}
    for aid in SEATS:
        p = os.path.join(d, f"{aid}.json")
        if os.path.isfile(p):
            data[aid] = json.load(open(p, encoding="utf-8"))
    if len(data) < 2:
        return {"error": f"only {len(data)} seats in {tag}"}
    vocab = {a: set(words(" ".join(v["replies"]))) for a, v in data.items()}
    openers = {a: [(" ".join(words(r)[:2])) for r in v["replies"] if r] for a, v in data.items()}
    jacc = []
    for a, b in itertools.combinations(data, 2):
        u = vocab[a] | vocab[b]
        jacc.append(len(vocab[a] & vocab[b]) / len(u) if u else 0)
    all_open = [o for os_ in openers.values() for o in os_]
    opener_repeat = 1 - len(set(all_open)) / max(1, len(all_open))
    # the same 4-grams in more than one seat = shared phrasing
    grams = {}
    for a, v in data.items():
        g = set()
        for r in v["replies"]:
            w = words(r)
            g |= {" ".join(w[i:i + 4]) for i in range(len(w) - 3)}
        grams[a] = g
    shared = set()
    for a, b in itertools.combinations(data, 2):
        shared |= grams[a] & grams[b]
    feats = {a: features(" ".join(v["replies"])) for a, v in data.items()}
    spread = {k: round(max(f[k] for f in feats.values()) - min(f[k] for f in feats.values()), 3)
              for k in ("avg_sentence_len", "contraction_rate", "exclaim_per_100w", "first_person_rate")}
    return {"tag": tag, "seats": len(data),
            "sameness_vocab_jaccard": round(sum(jacc) / len(jacc), 4),      # lower = more distinct
            "opener_repeat_rate": round(opener_repeat, 3),                     # lower = more distinct
            "shared_4grams_across_seats": len(shared),                         # lower = more distinct
            "feature_spread_between_seats": spread,                            # higher = more distinct
            "per_seat": feats}


def purge(tag: str) -> None:
    """Remove the measurement turns from the threads (Barry's rule: test turns pollute threads)."""
    import memory
    w = json.load(open(os.path.join(OUT, tag, "window.json"), encoding="utf-8"))
    with memory.get_db() as conn:
        n = 0
        for aid in SEATS:
            for p in PROMPTS:
                n += conn.execute("DELETE FROM conversations WHERE agent_id = ? AND timestamp BETWEEN ? AND ? "
                                  "AND (content = ? OR role = 'agent')", (aid, w["started"], w["ended"], p)).rowcount
        print(f"purged {n} rows from {w['started']} to {w['ended']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "run":
        run(sys.argv[2])
    elif cmd == "purge":
        purge(sys.argv[2])
    else:
        for t in sys.argv[2:] or ["before"]:
            print(json.dumps(score(t), indent=1))
