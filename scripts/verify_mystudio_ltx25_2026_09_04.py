r"""Functional test of the MyStudio LTX-2.5 clone (2026-09-04, Barry: "just
finish this one first and then clone it to my studio").

Does exactly what `Start My Studio.bat` + MyStudio.html do, minus the browser
pop-up: launches D:\ComfyUI25 on port 8189 with the .bat's own env + flags,
takes the `const LTX = {...}` graph OUT OF MyStudio.html (so the test runs the
bytes he will run), applies the same substitutions `videoWorkflow()` applies,
submits, polls, verifies the clip (duration / level / transcript), stops the rig.

Standalone-render rule: clear the card first, own the render flag with our own
token, clear only our own flag. Run only when the office is idle.
"""
import asyncio, json, os, re, subprocess, sys, time, io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"mystudio-verify-{int(time.time())}"
HOST = "http://127.0.0.1:8189"
RIG = r"D:\ComfyUI25"
PROMPT = ('A woman in a grey jumpsuit stands in a dim corridor, looks straight at the camera and says '
          'in a calm, clear voice, "We should not be here." She turns and walks away. Camera holds steady.')


def graph_from_mystudio():
    s = io.open(r"C:\Users\Owner\Desktop\MyStudio.html", encoding="utf-8").read()
    line = [l for l in s.split("\n") if l.startswith("const LTX = {")][0]
    return json.loads(line[len("const LTX = "):].rstrip(";"))


async def main():
    import httpx, llm_router, media_understanding as mu
    if os.path.exists(FLAG):
        print("another render owns the flag -- refusing"); return 3
    io.open(FLAG, "w").write(TOKEN)
    proc = None
    try:
        await llm_router.unload_all_models()
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                        "? { $_.CommandLine -like '*ComfyUI*main.py*' } | % { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True)
        await asyncio.sleep(4)
        env = dict(os.environ, PYTORCH_NO_HIP_MEMORY_CACHING="1")
        log = io.open(os.path.join(ROOT, "data", "mystudio_verify_server.log"), "ab")
        proc = subprocess.Popen([os.path.join(RIG, "venv", "Scripts", "python.exe"), "main.py",
                                 "--listen", "127.0.0.1", "--port", "8189", "--use-pytorch-cross-attention",
                                 "--reserve-vram", "1.5", "--cache-none", "--enable-cors-header"],
                                cwd=RIG, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        print("rig launched pid", proc.pid, "(the .bat's exact line)")
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
        wf = graph_from_mystudio()
        # what videoWorkflow() does, with the UI defaults (1024x576, 5s, t2v)
        wf["266"]["inputs"]["value"] = PROMPT
        wf["247"]["inputs"]["text"] = "pc game, console game, video game, cartoon, childish, ugly, deformed, watermark, text, subtitles"
        wf["257"]["inputs"]["value"] = 1024
        wf["258"]["inputs"]["value"] = 576
        wf["225"]["inputs"]["value"] = 5
        wf["237"]["inputs"]["noise_seed"] = 4242
        wf["216"]["inputs"]["noise_seed"] = 4242
        wf["325"] = {"class_type": "EmptyImage", "inputs": {"width": 512, "height": 512, "batch_size": 1, "color": 0}}
        wf["201"]["inputs"]["value"] = True
        t0 = time.time()
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{HOST}/prompt", json={"prompt": wf}); r.raise_for_status()
            pid = r.json()["prompt_id"]; print("accepted", pid)
            entry = None
            while time.time() - t0 < 3600:
                await asyncio.sleep(10)
                try:
                    d = (await c.get(f"{HOST}/history/{pid}")).json()
                except Exception:
                    continue
                if pid in d:
                    entry = d[pid]; break
        if entry is None:
            print("timed out"); return 5
        st = entry.get("status", {})
        print("status", st.get("status_str"), "in %.1f min" % ((time.time() - t0) / 60))
        if st.get("status_str") != "success":
            print(json.dumps(st.get("messages", []))[:600]); return 6
        out = entry["outputs"]["900"]["images"][0]
        clip = os.path.join(RIG, "output", out.get("subfolder", ""), out["filename"])
        d = mu.probe_media(clip); t = mu.transcribe_audio(clip).get("text")
        print("clip %s: %.2fs mean %.1f dBFS peak %.1f transcript=%r" % (clip, d["duration_s"], d["mean_dbfs"], d["peak_dbfs"], t))
        return 0
    finally:
        if proc:
            proc.terminate()
        if os.path.exists(FLAG) and io.open(FLAG).read().strip() == TOKEN:
            os.remove(FLAG); print("flag cleared")


sys.exit(asyncio.run(main()))
