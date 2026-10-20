"""Card guard for a running LTX clip: if dedicated VRAM sits >= 15.3 GB for 90 s, interrupt the render
(so the compositor is never starved into a black screen). Logs every 15 s. Stops when the render ends."""
import sys, time, httpx
sys.path.insert(0, "backend")
import comfy_image  # noqa: E402
B = "http://127.0.0.1:8420"
LIMIT, HOLD = 15.85, 90
over_since = None; peak = 0.0
time.sleep(5)
while True:
    try:
        s = httpx.get(f"{B}/api/generate/status", timeout=20).json()
    except Exception:
        s = {"busy": True}
    gb = comfy_image.gpu_dedicated_gb() or 0.0
    peak = max(peak, gb)
    print(f"{time.strftime('%H:%M:%S')} vram {gb:.1f} GB (peak {peak:.1f}) busy={s.get('busy')}", flush=True)
    if not s.get("busy") and not s.get("video_render_holding_gpu"):
        print("render ended; peak", round(peak, 1), flush=True); break
    if gb >= LIMIT:
        over_since = over_since or time.time()
        if time.time() - over_since >= HOLD:
            print("CARD PINNED -- interrupting the render to protect the display", flush=True)
            print(httpx.post(f"{B}/api/generate/cancel", timeout=30).text, flush=True)
            break
    else:
        over_since = None
    time.sleep(15)
