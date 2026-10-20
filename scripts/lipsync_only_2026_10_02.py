"""Step 3 of motion_lipsync_test_2026_10_02.py only: LatentSync on the her_moving.mp4 already rendered
(after the torch.distributed guard fix in tools/latentsync/latentsync/utils/util.py). Frames saved full size."""
import asyncio
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion_lipsync_test_2026_10_02 as T  # noqa: E402
import llm_router  # noqa: E402  (backend on sys.path via T)
import reel_builder  # noqa: E402


async def main() -> None:
    moving, wav = os.path.join(T.D, "her_moving.mp4"), os.path.join(T.D, "v000.wav")
    out = os.path.join(T.D, "her_lipsync.mp4")
    if os.path.exists(T.FLAG):
        print("render flag up -- not touching the card:", open(T.FLAG).read().strip())
        return
    token = f"latentsync-only-{os.getpid()}"
    open(T.FLAG, "w").write(token)
    try:
        await llm_router.unload_all_models()
        t0 = time.time()
        env = dict(os.environ, HF_HOME=os.path.join(T.ROOT, "tools", "latentsync", "hf"))
        env["PATH"] = os.path.join(T.LS_DIR, "bin") + os.pathsep + env.get("PATH", "")  # bin\ffmpeg.exe = office ffmpeg
        r = subprocess.run([T.LS_PY, "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2.yaml",
                            "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", "20",
                            "--guidance_scale", "1.5", "--video_path", moving, "--audio_path", wav,
                            "--video_out_path", out], cwd=T.LS_DIR, env=env, capture_output=True, text=True)
        print(f"latentsync rc={r.returncode} in {time.time() - t0:.0f}s exists={os.path.exists(out)}", flush=True)
        if r.returncode != 0:
            print((r.stderr or r.stdout)[-2500:])
    finally:
        if os.path.exists(T.FLAG) and open(T.FLAG).read().strip() == token:
            os.remove(T.FLAG)
    if os.path.exists(out):
        for k, ss in enumerate((0.5, 2.5, 5.0, 8.0)):
            subprocess.run([reel_builder._ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-i", out,
                            "-frames:v", "1", os.path.join(T.D, f"her_lipsync_full_f{k}.jpg")])
        print("frames saved")


if __name__ == "__main__":
    asyncio.run(main())
