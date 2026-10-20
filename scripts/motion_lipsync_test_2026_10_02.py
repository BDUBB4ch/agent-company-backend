"""Ilnora alive, end to end (2026-10-02): LTX motion clip -> her locked voice -> LatentSync 1.5 lip-sync.
Retry of motion_test_2026_10_02.py, which hung 60 min because ITS backend restart let the boot prewarm load Bonsai
onto the card mid-render. No restart here; renders now evict Bonsai themselves (comfy_image wrappers). Waits for
Derek's redraft to finish first. Outputs: data/reels/_motion_test/. Log: data/reels/_motion_test/test.log"""
import asyncio
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
D = os.path.join(ROOT, "data", "reels", "_motion_test")
os.makedirs(D, exist_ok=True)
LOG = os.path.join(D, "test.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
LS_DIR = os.path.join(ROOT, "tools", "latentsync")
LS_PY = os.path.join(ROOT, "tools", "latentsync-venv", "Scripts", "python.exe")
LINE = ("Hi, I'm Ilnora. Tonight I want to tell you about a bitter little herb the Romans poured into their wine, "
        "and why they swore it kept them strong.")


def log(m: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def running(pattern: str) -> bool:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {{ $_.CommandLine "
                        f"-match '{pattern}' }}).Count"], capture_output=True, text=True)
    return (r.stdout.strip() or "0") != "0"


async def main() -> None:
    while running("derek_redraft") or running("derek_after_motion"):
        time.sleep(30)
    while os.path.exists(FLAG):          # Derek's picture render, if still going
        time.sleep(20)
    log("start (Derek done, card free)")
    import reel_builder
    import llm_router
    # 1. her voice for the line (locked voice)
    t0 = time.time()
    durs = await reel_builder._voice_locked(reel_builder._locked_voice("ilnora"), [LINE], D, "lstest", log)
    wav = os.path.join(D, "v000.wav")
    log(f"voice: {durs[0]:.1f} s in {time.time() - t0:.0f}s -> {wav} exists={os.path.exists(wav)}")
    # 2. motion clip of her (render wrapper evicts Bonsai itself)
    pic = reel_builder._self_picture("ilnora", "short", take=False)
    t0 = time.time()
    vids = await reel_builder._animate([pic], [{"show": "self", "narration": LINE}], D, "short", log)
    log(f"i2v: {vids[0]} in {time.time() - t0:.0f}s")
    if not vids[0]:
        log("STOP: no motion clip")
        return
    moving = os.path.join(D, "her_moving.mp4")
    reel_builder._motion_scene_clip(vids[0], max(durs[0], 1.0), moving, reel_builder.FORMATS["short"])
    log(f"moving clip filled to {durs[0]:.1f}s -> {moving}")
    # 3. lip-sync to her voice (LatentSync owns the card like any render)
    token = f"latentsync-test-{os.getpid()}"
    open(FLAG, "w").write(token)
    try:
        await llm_router.unload_all_models()
        out = os.path.join(D, "her_lipsync.mp4")
        t0 = time.time()
        env = dict(os.environ, HF_HOME=os.path.join(ROOT, "tools", "latentsync", "hf"))
        r = subprocess.run([LS_PY, "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2.yaml",
                            "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", "20",
                            "--guidance_scale", "1.5", "--video_path", moving, "--audio_path", wav,
                            "--video_out_path", out], cwd=LS_DIR, env=env, capture_output=True, text=True)
        log(f"latentsync rc={r.returncode} in {time.time() - t0:.0f}s exists={os.path.exists(out)}")
        if r.returncode != 0:
            log("latentsync stderr tail: " + (r.stderr or r.stdout)[-1500:].replace("\n", " | "))
    finally:
        if open(FLAG).read().strip() == token:
            os.remove(FLAG)
    for name in ("her_moving.mp4", "her_lipsync.mp4"):
        p = os.path.join(D, name)
        if os.path.exists(p):
            for k, ss in enumerate((0.5, 2.5, 5.0)):
                subprocess.run([reel_builder._ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-i", p,
                                "-frames:v", "1", "-vf", "scale=270:480", os.path.join(D, f"{name[:-4]}_f{k}.jpg")])
    log("frames saved; done")


if __name__ == "__main__":
    asyncio.run(main())
