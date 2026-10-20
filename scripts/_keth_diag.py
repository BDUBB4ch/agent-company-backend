import sys
sys.path.insert(0, "scripts")
import json, time, urllib.request, uuid, pathlib
import compare_keth_loras as C

def run2(prefix, lora, sm, sc):
    wf = C.build(lora, prefix)
    wf["10"]["inputs"]["strength_model"] = sm
    wf["10"]["inputs"]["strength_clip"] = sc
    req = urllib.request.Request(C.COMFY + "/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    print(f"{prefix}: model={sm} clip={sc} queued", flush=True)
    t0 = time.time()
    while time.time() - t0 < 600:
        h = json.loads(urllib.request.urlopen(C.COMFY + "/history/" + pid, timeout=60).read())
        if pid in h:
            outs = [i["filename"] for n in h[pid].get("outputs", {}).values() for i in n.get("images", [])]
            print(f"   {time.time()-t0:.0f}s -> {outs}", flush=True)
            return
        time.sleep(3)

run2("keth_v7_modelonly", "keth_character_v7.safetensors", 1.0, 0.0)
run2("keth_v7_cliponly", "keth_character_v7.safetensors", 0.0, 1.0)
