"""Runs tools/tts/voxcpm_natural.py owning the card like any render (flag, LLMs unloaded, ComfyUI stopped), then makes
loudness-matched MP3s (-16 LUFS, so no take wins by being louder) for the test panel: CURRENT (her live voice, the
talking-test line) + N1-N4. -> AgentDashboard/assets/test_panel/ilnora_voice_r5_*.mp3"""
import asyncio
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import reel_builder as R  # noqa: E402

D = os.path.join(ROOT, "data", "voice_round5_2026_10_03")
PANEL = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "assets", "test_panel")
LINE = ("Hi, I'm Ilnora. Tonight I want to tell you about a bitter little herb the Romans poured into their wine, "
        "and why they swore it kept them strong. Soldiers carried it on long marches. Mothers hung it over doorways. "
        "And here's the strange part... they were half right.")


async def main() -> None:
    os.makedirs(D, exist_ok=True)
    script = os.path.join(D, "script.txt")
    open(script, "w", encoding="utf-8").write(R._say("ilnora", LINE))
    if comfy_image.render_in_progress():
        print("render running -- not touching the card")
        return
    token = "voice-round5-claude"
    open(R.FLAG, "w").write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        extra = [os.environ["TAKES"]] if os.getenv("TAKES") else []
        p = subprocess.run([R.VOXCPM_PY, os.path.join(ROOT, "tools", "tts", "voxcpm_natural.py"), D, script, *extra],
                           capture_output=True, text=True)
        print(p.stdout, p.stderr[-1500:] if p.returncode else "")
    finally:
        if os.path.exists(R.FLAG) and open(R.FLAG).read().strip() == token:
            os.remove(R.FLAG)
    pre = os.getenv("TAKE_PREFIX", "N")
    takes = {} if os.getenv("TAKES") else {"CURRENT": os.path.join(ROOT, "data", "reels", "_talk_test", "v000.wav")}
    takes.update({f[:-4]: os.path.join(D, f) for f in sorted(os.listdir(D)) if f.startswith(pre) and f.endswith(".wav")})
    for name, wav in takes.items():
        out = os.path.join(PANEL, f"ilnora_voice_r5_{name}.mp3")
        R._run(["-i", wav, "-af", "loudnorm=I=-16:TP=-1.5", "-ar", "48000", "-b:a", "192k", out])
        print("panel:", os.path.basename(out))


if __name__ == "__main__":
    asyncio.run(main())
