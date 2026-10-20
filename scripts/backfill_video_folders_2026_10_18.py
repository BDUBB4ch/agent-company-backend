"""Backfill ONE FOLDER PER VIDEO (Barry 2026-10-18) for a video built before video_queue.video_folder existed
(or built by a backend still running the old code). For each done job whose folder_copy is a flat MP4 in his
folder, the build's own MP4 in data/reels/<id>/ is matched by title and the folder is built exactly as a fresh
build would. Usage: venv/Scripts/python.exe scripts/backfill_video_folders_2026_10_18.py [--apply] [--out DIR]"""
import glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import reel_builder, video_queue  # noqa: E402

apply = "--apply" in sys.argv
HIS = video_queue.FOLDER                                               # his real folder, before any --out
if "--out" in sys.argv:
    video_queue.FOLDER = sys.argv[sys.argv.index("--out") + 1]

reels = {}
for rj in glob.glob(os.path.join(reel_builder.REELS_DIR, "*", "reel.json")):
    try:
        r = json.load(open(rj, encoding="utf-8")).get("result") or {}
    except (OSError, ValueError):
        continue
    if r.get("ok") and r.get("video") and os.path.isfile(r["video"]):
        reels.setdefault(video_queue._norm_title(r.get("title")), []).append(r["video"])

for jf in sorted(glob.glob(os.path.join(video_queue.QDIR, "job_*.json"))):
    job = json.load(open(jf, encoding="utf-8"))
    fc = job.get("folder_copy") or ""
    if job.get("status") != "done" or not fc:
        continue
    if os.path.basename(os.path.dirname(fc)) != os.path.basename(HIS) or not os.path.isfile(fc):
        continue                      # already in its own folder, or the flat copy is gone (archived/deleted by Barry)
    job["_file"] = jf                                                # _write pops it
    stem = os.path.splitext(os.path.basename(fc))[0]
    src = sorted(reels.get(video_queue._norm_title(job["pkg"].get("title")), []))
    src = src[-1] if src else None                                   # the newest build of that title
    print(f"{job['pkg'].get('title')!r}\n  stem: {stem}\n  reel mp4: {src}")
    if src and apply:
        out = video_queue.video_folder(job, src, stem)
        if video_queue.FOLDER == HIS:
            job["folder_copy"] = out
            video_queue._write(job)
            if os.path.isfile(fc) and os.path.abspath(fc) != os.path.abspath(out):
                os.remove(fc)                                            # the flat copy, now inside its folder
        print("  ->", out)
