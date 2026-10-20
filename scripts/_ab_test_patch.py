"""A/B the gradient-clipping patch. Trains keth 150 steps FROM SCRATCH on the
stock (unpatched) trainer and renders it, so it can be compared directly with
v8_keth_seg1 (150 steps, same folder, same everything, WITH the patch).
If this one is not noise, my patch was the cause."""
import json, sys, time, urllib.request, uuid
sys.path.insert(0, "scripts")
import train_character_loras as T
import compare_keth_loras as C
import shutil, pathlib

wf = json.loads(T.WORKFLOW.read_text(encoding="utf-8"))
wf["2"]["inputs"]["folder"] = "lora_keth_v5"
wf["4"]["inputs"].update({"steps": 150, "rank": 16, "learning_rate": 1e-4,
                          "seed": 0, "grad_accumulation_steps": 1})
wf["5"]["inputs"]["prefix"] = "loras/_noclip150"
wf["5"]["inputs"]["steps"] = 150

req = urllib.request.Request(T.COMFY + "/prompt",
    data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
    headers={"Content-Type": "application/json"})
pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
print("queued", pid, flush=True)
t0 = time.time()
while time.time() - t0 < 5400:
    h = json.loads(urllib.request.urlopen(T.COMFY + "/history/" + pid, timeout=60).read())
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print("FAILED:", str(st.get("messages", [])[-3:])[:800]); sys.exit(1)
        print(f"trained in {(time.time()-t0)/60:.1f} min", flush=True)
        break
    time.sleep(10)
else:
    print("TIMEOUT"); sys.exit(1)

out = sorted((T.ROOT/"tools/ComfyUI/output/loras").glob("_noclip150*.safetensors"),
             key=lambda p: p.stat().st_mtime)[-1]
dest = T.ROOT/"tools/ComfyUI/models/loras"/out.name
shutil.copyfile(out, dest)
print("installed", dest.name, flush=True)
C.run("ab_noclip_150", dest.name)
