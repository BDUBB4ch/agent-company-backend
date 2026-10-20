"""Time one SDXL render on the D: rig, with or without PYTORCH_NO_HIP_MEMORY_CACHING.
Two questions in one probe: (1) is the GPU in the documented decayed state
(baseline for this render is ~12-15s)? (2) what does the flag cost IMAGE renders,
since the LTX-2.5 720p path needs it and the office launcher is shared?"""
import json, os, sys, time, subprocess, urllib.request
HOST="http://127.0.0.1:8190"; label=sys.argv[1]; use_flag=sys.argv[2]=="1"
env=dict(os.environ); env.pop("PYTORCH_NO_HIP_MEMORY_CACHING",None)
if use_flag: env["PYTORCH_NO_HIP_MEMORY_CACHING"]="1"
log=open(r"D:\ComfyUI25\probe_%s.log"%label,"w")
p=subprocess.Popen([r"D:\ComfyUI25\venv\Scripts\python.exe","main.py","--port","8190","--use-pytorch-cross-attention"],
                   cwd=r"D:\ComfyUI25",env=env,stdout=log,stderr=subprocess.STDOUT)
t=time.time()
while time.time()-t<240:
    try: urllib.request.urlopen(HOST+"/queue",timeout=3); break
    except Exception: time.sleep(3)
else: print(label,"server never came up"); p.kill(); sys.exit(1)
w=json.load(open(r"C:\Users\Owner\Desktop\AgentCompanyBackend\workflows\comfy_t2i_sdxl_api.json",encoding="utf-8"))
w["6"]["inputs"]["text"]="photo of a weathered man in a black hooded jacket in a dim workshop, rain on the window, film grain"
w["3"]["inputs"]["seed"]=42; w["9"]["inputs"]["filename_prefix"]="probe_"+label
req=urllib.request.Request(HOST+"/prompt",data=json.dumps({"prompt":w}).encode(),headers={"Content-Type":"application/json"})
t0=time.time(); pid=json.load(urllib.request.urlopen(req,timeout=60))["prompt_id"]
while time.time()-t0<900:
    time.sleep(2)
    try: h=json.load(urllib.request.urlopen(HOST+"/history/"+pid,timeout=20))
    except Exception: continue
    if pid in h:
        st=h[pid]["status"].get("status_str"); el=time.time()-t0
        its=[l for l in open(r"D:\ComfyUI25\probe_%s.log"%label,encoding="utf-8",errors="replace").read().splitlines() if "it/s" in l or "s/it" in l]
        print("%-8s flag=%s  %s in %.1fs  (incl. cold model load)  last-progress: %s" % (label, use_flag, st, el, (its[-1][-40:] if its else "?")))
        break
p.kill(); p.wait(timeout=30)
