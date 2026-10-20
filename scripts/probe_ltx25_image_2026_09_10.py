"""Can LTX-2.5 make a single STILL on this card? (2026-09-10, Barry: "images
should be ltx" for MyStudio.)

Same rig launch as the studio's .bat, the studio's own LTX graph with the
duration set so the frame expression yields ONE frame (floor(0*24/8)*8+1 = 1),
audio path left in (the concat node needs it), the terminal swapped from
CreateVideo/SaveVideo to SaveImage on the decoded frame. Measures wall time.
Standalone-render rule: clear the card, own the flag with our token, clear ours.
"""
import asyncio, io, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"ltx-image-probe-{int(time.time())}"
HOST = "http://127.0.0.1:8189"
RIG = r"D:\ComfyUI25"
PROMPT = ("A woman in a grey jumpsuit stands in a dim concrete corridor lit by one "
          "overhead lamp, looking straight at the camera, calm expression, cinematic "
          "still photograph, shallow depth of field.")
W, H = int(sys.argv[1]) if len(sys.argv) > 1 else 1280, int(sys.argv[2]) if len(sys.argv) > 2 else 720


def graph_from_mystudio():
    s = io.open(r"C:\Users\Owner\Desktop\MyStudio.html", encoding="utf-8").read()
    line = [l for l in s.split("\n") if l.startswith("const LTX = {")][0]
    return json.loads(line[len("const LTX = "):].rstrip(";"))


def one_frame_graph():
    wf = graph_from_mystudio()
    wf["266"]["inputs"]["value"] = PROMPT
    wf["247"]["inputs"]["text"] = ("pc game, console game, video game, cartoon, childish, "
                                   "ugly, deformed, watermark, text, subtitles")
    wf["257"]["inputs"]["value"] = W
    wf["258"]["inputs"]["value"] = H
    wf["225"]["inputs"]["value"] = 0          # -> 1 frame
    wf["237"]["inputs"]["noise_seed"] = 777
    wf["216"]["inputs"]["noise_seed"] = 777
    wf["325"] = {"class_type": "EmptyImage", "inputs": {"width": 512, "height": 512, "batch_size": 1, "color": 0}}
    wf["201"]["inputs"]["value"] = True
    for dead in ("220", "242", "900"):
        wf.pop(dead, None)
    wf["901"] = {"class_type": "SaveImage", "inputs": {"images": ["251", 0], "filename_prefix": "mystudio_ltx_img"}}
    return wf


async def main():
    import httpx
    if os.path.exists(FLAG):
        print("another render owns the flag -- refusing"); return 3
    io.open(FLAG, "w").write(TOKEN)
    proc = None
    try:
        import llm_router
        await llm_router.unload_all_models()
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                        "? { $_.CommandLine -like '*ComfyUI*main.py*' } | % { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True)
        await asyncio.sleep(4)
        env = dict(os.environ, PYTORCH_NO_HIP_MEMORY_CACHING="1")
        log = io.open(os.path.join(ROOT, "data", "ltx_image_probe_server.log"), "ab")
        proc = subprocess.Popen([os.path.join(RIG, "venv", "Scripts", "python.exe"), "main.py",
                                 "--listen", "127.0.0.1", "--port", "8189", "--use-pytorch-cross-attention",
                                 "--reserve-vram", "1.5", "--cache-none", "--enable-cors-header"],
                                cwd=RIG, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        print("rig launched pid", proc.pid, flush=True)
        async with httpx.AsyncClient(timeout=5) as c:
            for _ in range(60):
                await asyncio.sleep(5)
                try:
                    if (await c.get(f"{HOST}/queue")).status_code == 200:
                        break
                except Exception:
                    pass
            else:
                print("rig never came up"); return 4
        wf = one_frame_graph()
        t0 = time.time()
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{HOST}/prompt", json={"prompt": wf})
            if r.status_code != 200:
                print("REJECTED:", r.text[:1500]); return 7
            pid = r.json()["prompt_id"]; print("accepted", pid, flush=True)
            entry = None
            while time.time() - t0 < 2400:
                await asyncio.sleep(5)
                try:
                    d = (await c.get(f"{HOST}/history/{pid}")).json()
                except Exception:
                    continue
                if pid in d:
                    entry = d[pid]; break
        if entry is None:
            print("timed out"); return 5
        st = entry.get("status", {})
        print("status", st.get("status_str"), "in %.1f min" % ((time.time() - t0) / 60), flush=True)
        if st.get("status_str") != "success":
            print(json.dumps(st.get("messages", []))[:1200]); return 6
        out = entry["outputs"]["901"]["images"][0]
        path = os.path.join(RIG, "output", out.get("subfolder", ""), out["filename"])
        from PIL import Image
        print("image", path, Image.open(path).size)
        return 0
    finally:
        if proc:
            proc.terminate()
        if os.path.exists(FLAG) and io.open(FLAG).read().strip() == TOKEN:
            os.remove(FLAG); print("flag cleared")


sys.exit(asyncio.run(main()))
