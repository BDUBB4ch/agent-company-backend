"""One talking part of Ilnora through the shipped code (reel_builder._say -> _voice_locked -> _talking ->
_talk_scene_clip): her locked voice with the name fix, LTX-2.5 audio-to-video from one of her pictures.
-> data/reels/_talk_test/ (talk_with_voice.mp4, frames, test.log)."""
import asyncio
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import reel_builder as R  # noqa: E402

D = os.path.join(ROOT, "data", "reels", "_talk_test")
os.makedirs(D, exist_ok=True)
LOG = os.path.join(D, "test.log")
LINE = ("Hi, I'm Ilnora. Tonight I want to tell you about a bitter little herb the Romans poured into their wine, "
        "and why they swore it kept them strong.")


def log(m: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


async def main() -> None:
    log("start")
    spoken = R._say("ilnora", LINE)
    log(f"spoken text: {spoken}")
    wav = os.path.join(D, "v000.wav")
    if os.getenv("REUSE_VOICE") == "1" and os.path.isfile(wav):
        durs = [R._wav_seconds(wav)]
        log("voice: reusing the line already made")
    else:
        durs = await R._voice_locked(R._locked_voice("ilnora"), [spoken], D, "talktest", log)
    heard = R._word_times(wav)
    log("whisper heard: " + " ".join(w for _, _, w in heard))
    log("captions show: " + " ".join(w for _, _, w in R._unsay("ilnora", heard)))
    pic = os.getenv("TALK_PIC") or R._self_picture("ilnora", "short")   # no take= : the test uses up nothing
    log(f"still: {os.path.basename(pic)}")
    talk = await R._talking(pic, {"show": "self"}, wav, D, 0, "short", log)
    if not talk:
        log("STOP: talking failed")
        return
    sec = durs[0] + R.PAD_S
    clip = os.path.join(D, "c000.mp4")
    R._talk_scene_clip(talk, sec, clip, R.FORMATS["short"])
    out = os.path.join(D, "talk_with_voice.mp4")
    R._run(["-i", clip, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
    for k, ss in enumerate((0.5, 3.0, 5.5, 8.5)):
        R._run(["-ss", str(ss), "-i", out, "-frames:v", "1", os.path.join(D, f"talk_f{k}.jpg")])
    p = subprocess.run([R._ffmpeg(), "-hide_banner", "-i", out], capture_output=True, text=True)
    log("output: " + " | ".join(x.strip() for x in p.stderr.splitlines() if "Duration" in x or "Stream" in x))
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
