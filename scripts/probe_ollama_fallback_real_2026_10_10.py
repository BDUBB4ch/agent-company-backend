"""2026-10-10: reproduce the 9b fallback's 400 for Elliot with HIS real request, OFF the GPU.
Captures the exact /api/chat body llm_router builds (the unload / stop-Bonsai / ComfyUI steps are no-ops here, so the
live office is untouched), then sends it to the real 9b with num_gpu 0 (CPU only) and num_predict 1, and prints
Ollama's answer. Then bisects: which field makes it 400."""
import asyncio
import copy
import json
import os
import sys

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import bonsai_llm  # noqa: E402
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import main  # noqa: E402
import memory  # noqa: E402

captured = {}


async def _noop(*a, **k):
    return None


llm_router._unload_models = _noop
bonsai_llm.stop_server = _noop
comfy_image.unload = _noop
_real_post = httpx.AsyncClient.post


async def _capture(self, url, *a, **k):
    if str(url).endswith("/api/chat") and "body" not in captured:
        captured["body"] = copy.deepcopy(k.get("json"))
        raise RuntimeError("captured")
    return await _real_post(self, url, *a, **k)


httpx.AsyncClient.post = _capture

cache = json.load(open(os.path.join(ROOT, "data", "bonsai_prompt_cache", "movie.json"), encoding="utf-8"))
hist = memory.get_recent_history("movie", 12)
msgs = [{"role": "user" if r["role"] == "user" else "assistant", "content": r["content"]} for r in hist]
if not msgs or msgs[-1]["role"] != "user":
    msgs.append({"role": "user", "content": "hi Elliot"})
extra = [t for t in (main._tools_for_seat("movie", False) or [])
         if (t.get("function") or {}).get("name") not in llm_router._FALLBACK_WRITE_TOOLS]
try:
    asyncio.run(llm_router.call_ollama(cache["system_prompt"] + llm_router._FALLBACK_NOTE, msgs,
                                       model=llm_router.OLLAMA_MODEL, use_tools=True, extra_tools=extra,
                                       office_name="MovieDirector", allow_web_search=True, use_thinking=True))
except Exception as e:  # noqa: BLE001
    print("call_ollama stopped:", type(e).__name__, str(e)[:120])
body = captured.get("body")
if not body:
    sys.exit("no body captured")
print("captured: keys", list(body), "| msgs", len(body["messages"]), "| tools", len(body.get("tools") or []),
      "| options", body.get("options"), "| think", body.get("think"),
      "| prompt chars", sum(len(m.get("content") or "") for m in body["messages"]))
json.dump(body, open(os.path.join(ROOT, "data", "probe_fallback_body_movie.json"), "w", encoding="utf-8"))


def send(b):
    b = copy.deepcopy(b)
    b["options"] = dict(b.get("options") or {}, num_gpu=0, num_predict=1)
    b["keep_alive"] = 0
    r = httpx.post("http://127.0.0.1:11434/api/chat", json=b, timeout=900)
    return r.status_code, r.text[:300]


print("REAL BODY ->", send(body))
