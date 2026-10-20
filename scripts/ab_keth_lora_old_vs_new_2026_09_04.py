r"""A/B: the same @Keth SDXL render (same seed, same prompt) on the OLD office
ComfyUI (tools/ComfyUI, 0.29.0, port 8189) vs the NEW one (D:\ComfyUI25, 0.34.0,
port 8188), through the office's own comfy_image.generate_image.

Why (2026-09-04): the first @Keth render after the migration came back as a
blonde human woman with `character_lora: keth_character_v5` reported loaded.
The record says bare text+LoRA never held Keth's identity (IP-Adapter/Kontext
do), so this is probably pre-existing -- but "probably" is not a measurement.
This settles regression-or-not with one render per install.

Run ONLY when the office is idle (no render, no chat). It raises the render
flag itself through generate_image, and stops whatever ComfyUI holds the card
first, because the two installs cannot share the GPU.

Usage:  venv/Scripts/python.exe scripts/ab_keth_lora_old_vs_new_2026_09_04.py old|new
Outputs land in each install's own output/ folder as phase1_sanity_*.png.
"""
import asyncio, os, sys, importlib

WHICH = sys.argv[1] if len(sys.argv) > 1 else "old"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WHICH == "old":
    os.environ["COMFY_DIR"] = os.path.join(ROOT, "tools", "ComfyUI")
    os.environ["COMFY_HOST"] = "http://127.0.0.1:8189"
# "new" = config defaults (D:\ComfyUI25 on 8188)

sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402  (reads the env above)
import comfy_image  # noqa: E402

PROMPT = "@Keth standing in a dim facility corridor, gray facility jumpsuit, barefoot, cinematic still"
NEG = "text, logo"
SEED = 1322780258  # the seed of the migrated-office render (approval 187)


async def main():
    print(f"[{WHICH}] COMFY_DIR={config.COMFY_DIR}  COMFY_HOST={config.COMFY_HOST}")
    # Standalone-render rule (2026-08-29): clear the card FIRST -- every LLM
    # (Bonsai parks itself 60s after any office render) and any ComfyUI on
    # either port, because the two installs cannot share the GPU.
    import llm_router, subprocess
    await llm_router.unload_all_models()
    subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True)
    await asyncio.sleep(4)
    if WHICH == "old":
        # comfy_image's launcher passes --port from COMFY_HOST? It does not: it
        # launches on the default 8188. So for the OLD install we launch it
        # ourselves on 8189, exactly like Start My Studio.bat does.
        import subprocess
        py = os.path.join(config.COMFY_DIR, "venv", "Scripts", "python.exe")
        proc = subprocess.Popen(
            [py, "main.py", "--listen", "127.0.0.1", "--port", "8189",
             "--use-pytorch-cross-attention", "--reserve-vram", "1.5"],
            cwd=config.COMFY_DIR, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=open(os.path.join(ROOT, "data", "ab_old_comfy.log"), "ab"),
            stderr=subprocess.STDOUT)
        print(f"[old] launched tools/ComfyUI pid {proc.pid} on 8189")
        import httpx
        for _ in range(60):
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    if (await c.get(f"{config.COMFY_HOST}/queue")).status_code == 200:
                        break
            except Exception:
                pass
        else:
            print("[old] never came up"); return
    res = await comfy_image.generate_image(PROMPT, NEG, seed=SEED)
    print(res)
    if WHICH == "old":
        proc.terminate()


asyncio.run(main())
