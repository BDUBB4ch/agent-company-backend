"""Redo ONLY her on-camera parts of a finished video; everything else stays frame for frame (Barry 2026-10-04: "i do
want the herb history and science Video redid. i really like it, its just the images of her thats wrong" / "is there
a way to redo just the parts with her ?").

    python scripts/redo_her_parts.py data/reels/<reel_id>

1. She re-directs ONLY her on-camera shots (one outfit, her style, never a doctor -- her playbook); her words stay.
   Saved to <reel>/redo_shots.json (reused if present).
2. Part boundaries come from the existing silent video (hard cuts between parts), snapped to the word-count estimate.
3. Each of her parts: a new still from her new shot (reel_builder._her_still) -> LTX talking from the EXACT slice of the
   existing voice track -> same length. Every other part is cut from the existing video untouched.
4. Same captions, voice and music mixed exactly as the original build. -> Desktop\\Ilnora's Videos\\... (redo).mp4
Owns the card like her queue builds (REEL_ACTIVE + reel_building.flag: Barry's and Elliot's renders go first)."""
import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import httpx  # noqa: E402
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import reel_builder as R  # noqa: E402
import video_tool  # noqa: E402
import video_queue  # noqa: E402

D = os.path.abspath(os.path.join(ROOT, sys.argv[1])) if len(sys.argv) > 1 else ""
# 2026-10-15 (Barry: "is it possible to just change that part?"): --parts=1,3 redoes only those parts (1-based, her
# on-camera parts only); --why="..." is Barry's reason, told to her in place of the old lab-coat message.
_ARGS = dict(a[2:].split("=", 1) for a in sys.argv[2:] if a.startswith("--") and "=" in a)
PARTS = {int(x) for x in _ARGS.get("parts", "").split(",") if x.strip().isdigit()}
WHY = _ARGS.get("why", "").strip()
W = os.path.join(D, "redo")
LOG = os.path.join(D, "redo.log")


def log(m: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def dur(path: str) -> float:
    p = subprocess.run([R._ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def shot_problems(shots: list[str]) -> str:
    for n, sh in enumerate(shots, 1):
        if len(sh.split()) < 4:                          # 2026-10-05: a fallback answer passed with two empty shots
            return f"shot {n} is empty"
        if video_tool._MEDICAL.search(sh):
            return f"shot {n} puts you in doctor/medical clothes"
    named = {frozenset(w for w in video_tool._GARMENTS if re.search(rf"\b{w}", R._outfit_of(sh).lower())) for sh in shots}
    named.discard(frozenset())
    if len(named) > 1:
        return "your shots name more than one outfit"
    if not R._outfit_of(shots[0]):
        return "your first shot doesn't name your outfit"
    return ""


async def ask_shots(scenes: list[dict], mine: list[int], title: str, outfit: str = "") -> list[str]:
    parts = "\n".join(f"{k}. (part {i + 1}) you say: \"{scenes[i]['narration']}\"\n   old shot: {scenes[i].get('shot', '')}"
                      for k, i in enumerate(mine, 1))
    if WHY:
        msg = (f"Barry likes your video \"{title}\" -- everything stays exactly as it is except "
               f"{'this shot' if len(mine) == 1 else 'these shots'} of you. Barry: \"{WHY}\" Re-direct "
               f"{'it' if len(mine) == 1 else 'them'}: keep the same outfit ({outfit or 'the one in your first shot'}) "
               "and name it in each shot, a real place with things around you, and what your hands are doing. Your "
               "words don't change.\n\n" + parts +
               f"\n\nReply with ONLY a JSON list of {len(mine)} shot{'s' if len(mine) != 1 else ''}, in this order.")
    else:
        msg = None
    msg = msg or (f"Barry loves your video \"{title}\" -- the information and the plant and tea pictures stay exactly as they "
           "are. Only the shots of YOU are being redone: the old ones put you in a lab coat and your clothes kept "
           "changing. Re-direct your on-camera shots for this widescreen video, following your playbook: one outfit "
           "for the whole video, named in your first shot (the others leave clothes out); dressed as yourself, never "
           "as a doctor. Every shot says WHERE you are -- a real place with things around you; the picture builder "
           "draws a bare wall when a shot names no place or says \"studio\". Your words don't change.\n\n" + parts +
           f"\n\nReply with ONLY a JSON list of {len(mine)} shots, in this order.")
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=2400) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": "ilnora", "message": msg,
                                                                        "task": True, "personal": False,
                                                                        "activity": "re-directing her shots"})
        reply = (r.json() or {}).get("reply") or ""
        m = re.search(r"\[.*\]", reply, re.S)
        try:
            # she may answer [{"part": 1, "shot": "..."}] -- take the shot text, never the dict's repr
            shots = [" ".join(str(s.get("shot", "") if isinstance(s, dict) else s).split())
                     for s in json.loads(m.group(0))] if m else []
        except json.JSONDecodeError:
            shots = []
        why = "not a JSON list" if not shots else (f"{len(shots)} shots, need {len(mine)}" if len(shots) != len(mine)
                                                    else shot_problems(shots))
        if not why:
            return shots
        log(f"her shots came back wrong ({why}); asking once more")
        msg = f"That came back wrong: {why}. Send ONLY the JSON list of {len(mine)} shots, in order."
    raise SystemExit("no usable shots from her")


def _norm_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower().replace("’", "'").replace("'", ""))]


def boundaries(video: str, scenes: list[dict]) -> list[float]:
    """Each part starts where its first words are SPOKEN in the voice track (Whisper word times), snapped to a hard
    cut in the video when one is within 0.6 s. Raises if any part's opening words can't be found -- never guesses."""
    total = dur(video)
    voice = os.path.join(os.path.dirname(video), "voice.wav")
    heard = [(s, _norm_words(w)) for s, _e, w in R._word_times(voice)]
    flat = [(s, w) for s, ws in heard for w in ws]
    p = subprocess.run([R._ffmpeg(), "-hide_banner", "-i", video, "-vf", "select='gt(scene,0.2)',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True)
    cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]
    out, pos = [0.0], 0
    for k, sc in enumerate(scenes):
        first = _norm_words(R._say("ilnora", sc["narration"]))[:3]
        if k == 0:
            pos = len(_norm_words(R._say("ilnora", sc["narration"]))) // 2
            continue
        hit = next((j for j in range(pos, len(flat) - 2) if [w for _, w in flat[j:j + 3]] == first), None)
        if hit is None:                                  # a misheard word ("Valyrian's"): 2 of the first 3 agree
            hit = next((j for j in range(pos, len(flat) - 2)
                        if sum(a == b for a, (_, b) in zip(first, flat[j:j + 3])) >= 2), None)
        if hit is None:
            raise SystemExit(f"part {k + 1}: its opening words {first} weren't found in the voice track")
        t = flat[hit][0]
        near = min(cuts, key=lambda c: abs(c - t)) if cuts else t
        # a hard cut IS the true boundary (video and voice were assembled to the same part lengths); without one
        # (two shots of her that look alike), the part starts ~0.28 s before its first word, as measured on the cuts
        out.append(near if abs(near - t) <= 0.6 else max(out[-1] + 0.5, t - 0.28))
        pos = hit + len(_norm_words(R._say("ilnora", sc["narration"]))) // 2
    return out + [total]


async def main() -> None:
    os.makedirs(W, exist_ok=True)
    rj = json.load(open(os.path.join(D, "reel.json"), encoding="utf-8"))
    pkg, scenes = rj["package"], rj["package"]["scenes"]
    mine = [i for i, s in enumerate(scenes) if s.get("show") == "self"]
    outfit = next((R._outfit_of(scenes[i].get("shot") or "") for i in mine if R._outfit_of(scenes[i].get("shot") or "")), "")
    if PARTS:
        mine = [i for i in mine if i + 1 in PARTS]
        if not mine:
            raise SystemExit(f"--parts {sorted(PARTS)}: none of those is one of her on-camera parts")
    shots_path = os.path.join(D, "redo_shots.json" if not PARTS else
                              f"redo_shots_parts_{'-'.join(str(i + 1) for i in mine)}.json")
    if os.path.isfile(shots_path):
        shots = json.load(open(shots_path, encoding="utf-8"))
    else:
        shots = await ask_shots(scenes, mine, pkg.get("title", ""), outfit)
        json.dump(shots, open(shots_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log("her new shots:\n  " + "\n  ".join(shots))
    b = boundaries(os.path.join(D, "video.mp4"), scenes)
    log("part boundaries: " + ", ".join(f"{x:.2f}" for x in b))
    form, fmt = pkg.get("format", "long"), R.FORMATS[pkg.get("format", "long")]
    token = comfy_image.REEL_ACTIVE.set(True)
    open(comfy_image._REEL_MARK, "w").write(f"redo {pkg.get('title')}")
    try:
        await comfy_image.reel_wait_turn(log)
        await llm_router.unload_all_models()
        clips, last_outfit, t0 = [], "", time.time()
        for i, s in enumerate(scenes):
            a, z = b[i], b[i + 1]
            out = os.path.join(W, f"c{i:03d}.mp4")
            if i in mine:
                shot = shots[mine.index(i)]
                seg = os.path.join(W, f"v{i:03d}.wav")
                R._run(["-ss", f"{a:.3f}", "-t", f"{z - a:.3f}", "-i", os.path.join(D, "voice.wav"), "-ar", "48000",
                        "-ac", "1", seg])
                still = await R._her_still("ilnora", {"show": "self", "shot": shot}, form, W, i, log,
                                           last_outfit=last_outfit)
                last_outfit = R._outfit_of(shot) or last_outfit
                if not still:
                    raise SystemExit(f"part {i + 1}: no still")
                talk = await R._talking(still, {"show": "self", "shot": shot}, seg, W, i, form, log)
                if not talk:
                    raise SystemExit(f"part {i + 1}: talking failed")
                R._talk_scene_clip(talk, z - a, out, fmt)
            else:
                R._run(["-ss", f"{a:.3f}", "-t", f"{z - a:.3f}", "-i", os.path.join(D, "video.mp4"), "-an",
                        "-vf", f"fps={R.FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])
            clips.append(out)
        log(f"her {len(mine)} parts rebuilt in {(time.time() - t0) / 60:.0f} min")
    finally:
        comfy_image.REEL_ACTIVE.reset(token)
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass
    with open(os.path.join(W, "clips.txt"), "w") as fh:
        fh.writelines("file '" + c.replace(chr(92), "/") + "'\n" for c in clips)
    video = os.path.join(W, "video.mp4")
    R._run(["-f", "concat", "-safe", "0", "-i", os.path.join(W, "clips.txt"), "-c", "copy", video])
    # the original build's final mix (reel_builder.build_reel step 6), same inputs
    voice, music, total = os.path.join(D, "voice.wav"), os.path.join(D, "music_bed.wav"), dur(os.path.join(D, "voice.wav"))
    out = os.path.join(W, "final.mp4")
    sub = "null"                                     # no captions (Barry 2026-10-06)
    R.final_mix(os.path.dirname(out), video, voice, music if os.path.isfile(music) else None, sub, total, out)
    title = re.sub(r'[<>:"/\\|?*]+', "", pkg.get("title") or "video").strip()
    dest = os.path.join(video_queue.FOLDER, f"{datetime.date.today():%Y-%m-%d} {form.title()} - {title} (redo).mp4")
    os.makedirs(video_queue.FOLDER, exist_ok=True)
    shutil.copy2(out, dest)
    log(f"DONE {dur(out):.1f}s -> {dest}")


if __name__ == "__main__":
    asyncio.run(main())
