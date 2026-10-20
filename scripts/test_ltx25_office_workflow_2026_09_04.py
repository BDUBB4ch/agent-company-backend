"""Submit the office's LTX-2.5 workflow the exact way comfy_image.generate_video
does -- same node-ID substitutions -- so a pass here means the real code path
will work, not just that the JSON parses."""
import json, os, sys, time, urllib.request

HOST = "http://127.0.0.1:8190"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, "workflows", "comfy_t2v_ltx25_api.json")

prompt = ("A weathered man in a black hooded jacket stands in a dim workshop, rain "
          "on the window behind him. He looks up and says in a low, tired voice, "
          "\"We should not be here.\" Handheld camera, slow push in, film grain.")
dur   = int(sys.argv[1]) if len(sys.argv) > 1 else 1
w     = int(sys.argv[2]) if len(sys.argv) > 2 else 512
h     = int(sys.argv[3]) if len(sys.argv) > 3 else 320
fps   = int(sys.argv[4]) if len(sys.argv) > 4 else 24

wf = json.load(open(WF, encoding="utf-8"))
# --- byte-for-byte the substitutions comfy_image.generate_video performs ---
wf["266"]["inputs"]["value"] = prompt
wf["257"]["inputs"]["value"] = w
wf["258"]["inputs"]["value"] = h
wf["225"]["inputs"]["value"] = max(1, min(dur, 15))
wf["260"]["inputs"]["value"] = fps
wf["237"]["inputs"]["noise_seed"] = 42

print("submitting: %dx%d, %ds @ %dfps  (stage1 samples %dx%d, %d frames)"
      % (w, h, dur, fps, w // 2, h // 2, dur * fps + 1), flush=True)
req = urllib.request.Request(HOST + "/prompt",
                             data=json.dumps({"prompt": wf}).encode(),
                             headers={"Content-Type": "application/json"})
try:
    pid = json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]
except urllib.error.HTTPError as e:
    print("GRAPH REJECTED:\n" + e.read().decode()[:2500]); raise SystemExit(1)
print("accepted:", pid, flush=True)

t0 = time.time()
while time.time() - t0 < 3000:
    time.sleep(10)
    try:
        hist = json.load(urllib.request.urlopen(HOST + "/history/" + pid, timeout=30))
    except Exception:
        continue
    if pid in hist:
        st = hist[pid].get("status", {})
        el = time.time() - t0
        print("\n%s after %.1f min" % (st.get("status_str"), el / 60))
        for nid, out in (hist[pid].get("outputs") or {}).items():
            print("  output[%s] = %s" % (nid, str(out)[:220]))
        if st.get("status_str") != "success":
            print(json.dumps(st, indent=1)[:2500])
        break
else:
    print("timed out")
