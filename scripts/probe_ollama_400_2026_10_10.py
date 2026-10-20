"""2026-10-10: why does the 9b fallback answer 400? Sends each seat's real tool list to Ollama with a model name that
does not exist: a malformed body is rejected (400) BEFORE any model lookup, a well-formed one gets 404 "not found".
Nothing loads on the GPU. Bisects to the offending tool."""
import json
import os
import sys

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import llm_router  # noqa: E402
import main  # noqa: E402

FAKE = "probe-does-not-exist:latest"


def probe(tools, messages=None):
    body = {"model": FAKE, "stream": False, "keep_alive": 0,
            "messages": messages or [{"role": "system", "content": "x"}, {"role": "user", "content": "hi"}],
            "options": {"num_ctx": 4096}, "think": True}
    if tools:
        body["tools"] = tools
    r = httpx.post("http://127.0.0.1:11434/api/chat", json=body, timeout=30)
    return r.status_code, r.text[:300]


print("no tools:", probe(None))
for aid in ["movie", "ilnora", "creative", "engineer"]:
    extra = main._tools_for_seat(aid, False) or []
    base = [llm_router.WEB_SEARCH_TOOL, llm_router.READ_SKILL_TOOL, llm_router.INSPECT_BRAIN_TOOL,
            llm_router.LOOK_AT_MY_PICTURES_TOOL]
    tools = base + extra
    code, text = probe(tools)
    print(f"{aid}: {len(tools)} tools -> {code} {text[:160]}")
    if code == 400:
        bad = []
        for t in tools:
            c, tx = probe([t])
            if c == 400:
                bad.append((t.get("function", {}).get("name"), tx[:200]))
        print("   offending tools:", json.dumps(bad, indent=1)[:1500])
