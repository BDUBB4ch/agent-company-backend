"""30-step smoke test of the gradient-clipping patch. Proves the patched
trainer still trains and still saves, before committing 4h+ per character."""
import json, sys, time, urllib.request, uuid, pathlib
sys.path.insert(0, "scripts")
import train_character_loras as T

wf = json.loads(T.WORKFLOW.read_text(encoding="utf-8"))
wf["2"]["inputs"]["folder"] = "lora_keth_v5"
n = wf["4"]["inputs"]
n.update({"steps": 30, "rank": 16, "learning_rate": 1e-4, "seed": 0,
          "grad_accumulation_steps": 1})
wf["5"]["inputs"]["prefix"] = "loras/_cliptest"
wf["5"]["inputs"]["steps"] = 30

req = urllib.request.Request(T.COMFY + "/prompt",
    data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
    headers={"Content-Type": "application/json"})
pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
print("queued", pid, flush=True)
t0 = time.time()
while time.time() - t0 < 1800:
    h = json.loads(urllib.request.urlopen(T.COMFY + "/history/" + pid, timeout=60).read())
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print("FAILED:", str(st.get("messages", [])[-3:])[:900])
            sys.exit(1)
        print(f"trained 30 steps in {time.time()-t0:.0f}s")
        break
    time.sleep(5)
else:
    print("TIMEOUT"); sys.exit(1)

out = sorted((T.ROOT/"tools/ComfyUI/output/loras").glob("_cliptest*.safetensors"),
             key=lambda p: p.stat().st_mtime)
print("saved:", out[-1].name if out else "NOTHING SAVED")
