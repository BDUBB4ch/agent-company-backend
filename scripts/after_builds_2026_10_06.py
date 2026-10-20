"""After today's two builds (The Dragon's Weed, Halloween's Real Garden) -- Barry 2026-10-06: "captions" / "the words
she says are written, i dont want that". Those two builds loaded the old code, so:
1. wait until both jobs are done and the card is quiet 5 minutes
2. re-mix each one WITHOUT captions from its own reel folder (video.mp4 + voice.wav + music_bed.wav, the same mix as
   reel_builder step 6) and replace the copy in Desktop\\Ilnora's Videos, on the DESK, and in the reel folder (CPU only)
3. preflight + restart the backend so the no-caption code is live (never during a render)
4. relay Barry's words to her office window: "let the scenes also tell the story, and no texts. tell her that"
Log: data/video_queue/after_builds_2026-10-06.log"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import reel_builder as R  # noqa: E402

LOG = os.path.join(ROOT, "data", "video_queue", "after_builds_2026-10-06.log")
QDIR = os.path.join(ROOT, "data", "video_queue")
TITLES = ("The Dragon's Weed", "Halloween's Real Garden")
FLAG = os.path.join(ROOT, "data", "reel_building.flag")
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
MSG = 'From Barry (relayed by Claude, his exact words): "let the scenes also tell the story, and no texts. tell her that"'


def log(m: str) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}\n")


def jobs() -> list[dict]:
    out = []
    for f in glob.glob(os.path.join(QDIR, "job_*.json")):
        try:
            out.append(json.load(open(f, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out


def busy() -> bool:
    return os.path.exists(FLAG) or any(j.get("status") == "building" for j in jobs())


def remix(title: str, job: dict) -> None:
    dirs = []
    for d in glob.glob(os.path.join(ROOT, "data", "reels", "2026100*")):
        try:
            if json.load(open(os.path.join(d, "reel.json"), encoding="utf-8"))["package"].get("title") == title:
                dirs.append(d)
        except (OSError, ValueError, KeyError):
            pass
    if not dirs:
        log(f"{title}: no reel folder found -- left as is")
        return
    d = max(dirs)
    rid = os.path.basename(d)
    video, voice, music = (os.path.join(d, x) for x in ("video.mp4", "voice.wav", "music_bed.wav"))
    p = subprocess.run([R._ffmpeg(), "-hide_banner", "-i", voice], capture_output=True, text=True)
    hh, mm, ss = p.stderr.split("Duration: ")[1].split(",")[0].split(":")
    total = int(hh) * 3600 + int(mm) * 60 + float(ss)
    out = os.path.join(d, f"{rid}_nocaptions.mp4")
    if os.path.isfile(music):
        fc = (f"[2:a]volume=0.35,afade=t=out:st={max(0, total - 2):.2f}:d=2[m];"
              f"[m][1:a]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
              f"[1:a][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
        args = ["-i", video, "-i", voice, "-i", music, "-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
    else:
        args = ["-i", video, "-i", voice, "-filter_complex", "[1:a]loudnorm=I=-14:TP=-1.5[a]", "-map", "0:v",
                "-map", "[a]"]
    R._run(args + ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                   "-b:a", "192k", "-movflags", "+faststart", "-shortest", out])
    targets = [os.path.join(d, f"{rid}.mp4"), job.get("folder_copy") or ""]
    targets += glob.glob(os.path.join(ROOT, "data", "agent_files", "ilnora", f"*_{rid}.mp4"))
    for t in [t for t in targets if t and os.path.isfile(t)]:
        shutil.copy2(out, t)
        log(f"{title}: no-caption copy -> {t}")


def main() -> None:
    time.sleep(120)
    quiet = 0
    while quiet < 5:
        quiet = 0 if busy() else quiet + 1
        time.sleep(60)
    for title in TITLES:
        job = next((j for j in jobs() if j["pkg"].get("title") == title and j.get("status") == "done"), None)
        if job:
            try:
                remix(title, job)
            except Exception as exc:  # noqa: BLE001
                log(f"{title}: remix failed: {exc}")
        else:
            log(f"{title}: not done -- nothing to re-mix")
    pf = subprocess.run([PY, os.path.join(ROOT, "scripts", "preflight_check.py")], cwd=ROOT,
                        capture_output=True, text=True)
    if pf.returncode == 0 and not busy():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$procId=(Get-NetTCPConnection -LocalPort 8420 -State Listen).OwningProcess; "
                        "Stop-Process -Id $procId -Force"])
        log("backend restarted (watchdog revives it) -- no-caption code live")
        time.sleep(240)
    else:
        log(f"backend NOT restarted (preflight exit {pf.returncode}, busy {busy()})")
    try:
        req = urllib.request.Request("http://127.0.0.1:8420/api/chat",
                                     data=json.dumps({"agent_id": "ilnora", "message": MSG, "personal": False}).encode(),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=2400).read()).get("reply", "")
        log("relayed to her; she said: " + " ".join(r.split())[:400])
    except Exception as exc:  # noqa: BLE001
        log(f"relay failed: {exc}")


if __name__ == "__main__":
    main()
