"""Does a finished MP4 hold all of its sound? (2026-10-11, Barry: "some words are missing and at the end is a 5 second
space of nothing"). AAC frames are always 1024 samples, so frames x 1024 / rate = the sound actually in the file;
the container's timestamps can stretch it to the full length, which is exactly how 6 s of voice went missing
unnoticed. Usage: python scripts/check_video_audio.py <mp4> [<mp4> ...]"""
import os
import re
import subprocess
import sys

FF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv", "Lib", "site-packages",
                  "imageio_ffmpeg", "binaries", "ffmpeg-win-x86_64-v7.1.exe")


def check(mp4: str) -> dict:
    info = subprocess.run([FF, "-hide_banner", "-i", mp4], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    rate = int((re.search(r"Audio: .*?(\d+) Hz", info) or [0, 48000])[1])
    md5 = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", mp4, "-map", "0:a:0", "-c", "copy", "-f",
                          "framemd5", "-"], capture_output=True, text=True).stdout
    frames = sum(1 for ln in md5.splitlines() if ln.strip() and not ln.startswith("#"))
    sound = frames * 1024 / rate
    return {"file": os.path.basename(mp4), "length_s": round(dur, 2), "sound_s": round(sound, 2),
            "missing_s": round(max(0.0, dur - sound), 2), "ok": dur - sound < 0.5}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(check(p))
