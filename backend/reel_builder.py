"""THE REEL BUILDER -- the office's own "FastReel" (2026-09-24, Barry: "i want her to be able to be like a fastreel
type thing ... this is our money maker for this agent").

A reel package (written by the agent) -> a finished vertical video, all local:
  1. every scene's picture rendered by Z-Image Turbo (int8, ~45 s, Apache-2.0 -- commercial use OK), 768x1344
  2. the narration in the agent's LOCKED voice (VoxCPM2 clone, on the card) or Kokoro (CPU) if none is locked,
     one clip per scene -- a scene lasts as long as its line
  3. slow camera motion on each still (zoom in / out, alternating) -- the faceless-reel look
  4. captions timed WORD BY WORD from the voice (faster-whisper word timestamps), burned in, big and bold
  5. background music from data/music/<mood>/ (free, legally usable tracks), ducked under the voice
  -> short: 1080x1920 (max 3:00) / long: 1920x1080; 30 fps, H.264/AAC MP4 + a thumbnail, in data/reels/<id>/.

The GPU is used for the locked voice and the stills, each step owning data/video_rendering.flag with its own token (agents' model
calls stand down meanwhile; nothing reloads Bonsai mid-render), models unloaded first, flag cleared after.
Everything else is CPU. Never posts anything -- the finished reel goes to Barry's Out box (agents draft,
humans send).

Package shape:
  {"title": str, "mood": "spooky|calm|upbeat|mystic" (music folder), "voice_agent": "ilnora",
   "format": "short" | "long",   # HER choice: short = vertical 1-3 min; long = 16:9 YouTube/Facebook video
   "scenes": [{"narration": str, "image_prompt": str}, ...]   # ~6 s each: short 10-30, long up to 200
   "caption": str, "hashtags": [..]}
"""
from __future__ import annotations

import asyncio
import datetime
import glob
import io
import json
import os
import random
import re
import subprocess
import time
import uuid
import wave

import httpx

import config

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REELS_DIR = os.path.join(_ROOT, "data", "reels")
MUSIC_DIR = os.path.join(_ROOT, "data", "music")
FLAG = os.path.join(_ROOT, "data", "video_rendering.flag")
# 24, not 30 (2026-10-11, Barry: "it seems skippy"): every LTX clip is 24 fps (TALK_FPS) and fps=30 repeated every 4th
# frame -- a 6-times-a-second hitch through every video (measured on The Fairy's Bell). Shorts/YouTube take 24.
FPS = 24
PAD_S = 0.35                       # breath after each line
# Barry 2026-09-24: 1-3 minute shorts, 2-3 a day; then "i want her to choose between long and short form based
# on what she wants to talk about" -- the package's "format" is HER choice. ~6 s a scene, ~25 s of GPU a scene.
FORMATS = {
    # vertical: TikTok, YouTube Shorts, Facebook Reels
    "short": {"w": 1080, "h": 1920, "still_w": 768, "still_h": 1344, "max_scenes": 36,
              "font": 92, "margin_v": 560, "words": 3, "chars": 14},
    # widescreen: regular YouTube / Facebook video (8+ minutes lets YouTube place mid-roll ads)
    "long": {"w": 1920, "h": 1080, "still_w": 1344, "still_h": 768, "max_scenes": 200,
             "font": 64, "margin_v": 90, "words": 6, "chars": 32},
}
MAX_SCENES = FORMATS["short"]["max_scenes"]
FONT = "Arial Black"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str]) -> None:
    p = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg: " + (p.stderr or "")[-800:])


# ---------------------------------------------------------------- voice
# A LOCKED voice (data/identity/<agent>/voice: voice_ref.wav + ref_text.txt + voice.json) is cloned with VoxCPM2
# on the card for every line -- Ilnora's is A2 (Barry 2026-09-24: "A2 is the one, lock it in"). An agent without a
# locked voice falls back to Kokoro on the CPU.
IDENTITY_DIR = os.path.join(_ROOT, "data", "identity")
VOXCPM_PY = os.path.join(_ROOT, "tools", "tts", "voxcpm", ".venv", "Scripts", "python.exe")
VOXCPM_LINES = os.path.join(_ROOT, "tools", "tts", "voxcpm_lines.py")


def _locked_voice(agent_id: str) -> str | None:
    d = os.path.join(IDENTITY_DIR, agent_id, "voice")
    need = ("voice_ref.wav", "ref_text.txt", "voice.json")
    return d if all(os.path.isfile(os.path.join(d, f)) for f in need) and os.path.isfile(VOXCPM_PY) else None


# PLANTS (Barry 2026-09-24: "the plants need to be of the plants shes talking about, no other way"; then "so qwen
# for plants and z for the people?"). A scene showing a plant names it: "plant": "<scientific name>". Barry's own
# photos in drop/Plants/<name>/ come first; otherwise Qwen-Image draws it (it knows species; Z-Image drew mugwort
# as the wrong plant). A Z-Image prompt that depicts plants WITHOUT naming the plant is refused -- she fixes it.
_PLANT_WORDS = re.compile(r"\b(herbs?|plants?|leaf|leaves|flowers?|blossoms?|petals?|sprigs?|weeds?|seedlings?|"
                          r"stems?|buds?|shrubs?|bushes|vines?|roots?|bark)\b", re.I)
PLANT_SIZE = {"short": (928, 1664), "long": (1664, 928)}


def _plant(scene: dict) -> str:
    # 2026-10-09: she wrote "*Datura wrightii*" -- markdown stars/quotes are not part of a species name
    return " ".join(str(scene.get("plant") or "").replace("*", " ").replace("_", " ").replace("`", " ")
                    .replace('"', " ").split())


def _plant_portrait(scene: dict) -> bool:
    """True when the picture OPENS on the plant itself (the species or a plant word in its first six words after
    any 'a real photograph of' preamble) -- that scene gets the real photo of the species. A tagged scene that opens
    on something else (a mortar, a fire circle, a night sky, a rattlesnake) is HER picture, painted from her words
    with the species' real look added. 2026-10-09, 'The Flower That Walks Between Worlds': she tagged nine scenes
    with the species and all nine came out as the same three iNaturalist photos -- Barry: "she just showed the plant
    in every scene as a slow moving still... no shaman, no nothing, just the plant. we need to fix that.\""""
    text = _picture_text(scene).strip()
    if not text:
        return True
    text = re.sub(r"^(a|an|the)?\s*(real|true|actual|extreme|tight|wide|close|macro)?\s*"
                  r"(photo|photograph|picture|image|close-?up|shot|macro|view)\s*(of|on)?\s*", "", text, flags=re.I)
    head = " ".join(text.split()[:6]).lower()
    species = _plant(scene).lower()
    return (any(w and w in head for w in species.split()[:1]) or bool(_PLANT_WORDS.search(head))
            or bool(_PORTRAIT_WORDS.search(head)))


# plant PARTS a portrait can open on (kept apart from _PLANT_WORDS, which drives the unnamed-scene send-back)
_PORTRAIT_WORDS = re.compile(r"\b(pods?|seeds?|berry|berries|fruits?|cones?|needles?|fronds?|tubers?|bulbs?|rhizomes?|"
                             r"spines?|thorns?|blooms?|trumpets?|catkins?|husks?|bracts?|tendrils?)\b", re.I)


def _unnamed_plant_scenes(scenes: list[dict]) -> list[int]:
    return [i + 1 for i, s in enumerate(scenes)
            if not _is_self(s) and not _plant(s) and _PLANT_WORDS.search(_picture_text(s))]


SPECIES_LOOKS = os.path.join(_ROOT, "data", "plantdata", "species_looks.json")


async def _species_look(species: str) -> str:
    """One sentence on how the species really looks, for the picture engine -- from data/plantdata/species_looks.json
    ONLY (a curated file: {"sanguinaria canadensis": "white flower with 8-12 petals ..."}). 2026-10-08: asking Bonsai
    was tried and REJECTED the same hour -- it said bloodroot has "bright yellow flowers with four to five petals"
    (real: white, 8-12 petals). A model that does not know the species must not describe it; "" when not curated."""
    try:
        cache = json.load(open(SPECIES_LOOKS, encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return " ".join(str(cache.get(" ".join(species.lower().split())) or "").split())


# THE REAL PLANT IN HER SCENES (2026-10-14, Barry: "have Ilnora use the plants as reference and draw them in some
# scenes herself, so we can get better scenes with action"). A scene she tags with a plant that opens on something
# else (a sick man, a healer at work) -- and her own shots that carry a plant -- are drawn by the picture EDITOR with
# a real photo of the species as a reference (Barry's photo first, then iNaturalist), so the plant in the action is
# the real plant, not the engine's guess. No photo, or the editor fails -> the old path. The photo is credited.
def _plant_ref(species: str, used: dict, log) -> tuple[str, str] | None:
    import plant_photos
    mine = plant_photos.photos(species) or plant_photos.fetch_inaturalist(species, log=log)
    if not mine:
        return None
    k = used.get(species, 0)
    used[species] = k + 1
    ph = mine[k % len(mine)]
    return ph["path"], ph["credit"]


async def _scene_with_plant(species: str, ref: str, words: str, look: str, form: str, log) -> str | None:
    """Her scene, in her words, drawn by the editor with the real plant photo as image 1. Picture path or None."""
    import shutil
    import comfy_image
    import llm_router
    inp = os.path.join(config.COMFY_DIR, "input")
    n = f"plantref_{int(time.time() * 1000)}{os.path.splitext(ref)[1]}"
    shutil.copy2(ref, os.path.join(inp, n))
    ns = comfy_image.small_reference(n)
    W, H = (768, 1376) if form != "long" else (1376, 768)
    instruction = (f"A new photograph: {words}. The {species} in this photograph is exactly the plant in image 1 -- "
                   f"the same leaves, flowers, colours and growth, true to the real species, real-size, part of the "
                   f"scene. {look} Image 1 only shows what the plant looks like: its background, framing and light "
                   f"are not part of this photograph. A real, fully built place with depth and natural light, the "
                   f"scene filling the frame edge to edge. A real photograph taken with a camera: true colours, "
                   f"sharp fine detail. Every surface in the picture is plain and unlettered: no labels, no writing, "
                   f"no captions anywhere.")
    await llm_router.unload_all_models()
    try:
        r = await comfy_image.edit_image([ns], instruction, prefix="reel_plantref", size=(W, H))
    finally:
        for x in {n, ns}:
            try:
                os.remove(os.path.join(inp, x))
            except OSError:
                pass
    if not r.get("path"):
        log(f"plant {species}: drawing with the real plant failed ({r.get('error')}) -- painting from her words")
        return None
    return r["path"]


async def _plant_stills(jobs: list[tuple[str, str, bool]], form: str, log) -> list[tuple[str, str]]:
    """[(species, prompt, portrait)] -> [(image_path, credit)]: a PORTRAIT of the plant = Barry's photo if he dropped
    one, else a real iNaturalist photo, else Qwen-Image; any other tagged scene = Qwen-Image from HER words + the
    species' real look (2026-10-09, see _plant_portrait)."""
    import comfy_image
    import llm_router
    import plant_photos
    out, used = [], {}
    looks = {}
    for species, _p, portrait in jobs:            # all species looks first -- Bonsai leaves the card for the pictures
        if species not in looks and (not portrait or not plant_photos.photos(species)):
            looks[species] = await _species_look(species)
            if looks[species]:
                log(f"plant {species} looks like: {looks[species][:100]}")
    for species, prompt, portrait in jobs:
        mine = (plant_photos.photos(species) or plant_photos.fetch_inaturalist(species, log=log)) if portrait else []
        if not portrait:
            ref = _plant_ref(species, used, log)
            if ref:
                t0 = time.time()
                path = await _scene_with_plant(species, ref[0], prompt, looks.get(species, ""), form, log)
                if path:
                    log(f"plant {species}: her own scene ({prompt[:60]}...) -- drawn with the real plant as "
                        f"reference, {time.time() - t0:.0f}s")
                    out.append((path, ref[1]))
                    continue
            log(f"plant {species}: her own scene ({prompt[:60]}...) -- painted from her words, not the species photo")
        if mine:
            k = used.get(species, 0)
            used[species] = k + 1
            ph = mine[k % len(mine)]
            out.append((ph["path"], ph["credit"]))
            continue
        if species.lower() not in prompt.lower():
            prompt = f"{prompt}. The plant shown is {species}, exactly as the real species looks."
        # Barry 2026-10-06: "i dont want cartoon images of the plants anymore" (Two Witches' Sisters: the belladonna
        # and mugwort came out illustrated). Qwen-Image runs Lightning at cfg 1, so a negative prompt is inert --
        # the photograph is stated positively, after her description (her words are not changed).
        # 2026-10-08 (Bloodroot came out as a pink five-petal flower; Barry: "fix all that"): the species' real look
        # is spelled out for the picture engine, and nothing is written anywhere in the picture (a bottle label
        # came out as garbled text).
        look = looks.get(species, "")
        prompt = (f"{prompt}. {look} A real photograph taken with a camera: the living plant in true colours, real "
                  f"leaf and petal texture, natural light and shadow, sharp fine detail, shallow depth of field -- "
                  f"documentary nature photography. Every surface in the picture is plain and unlettered: no labels, "
                  f"no writing, no captions anywhere.")
        w, h = PLANT_SIZE[form]
        await llm_router.unload_all_models()
        t0 = time.time()
        r = await comfy_image.generate_image(prompt, None, "qwen-image", width=w, height=h)
        if r.get("error"):
            raise RuntimeError(f"plant picture ({species}) failed: {r['error']}")
        log(f"plant {species}: {time.time() - t0:.0f}s (Qwen-Image)")
        out.append((r["path"], ""))
    return out


def _is_self(scene: dict) -> bool:
    return str(scene.get("show") or "").strip().lower() == "self"


def _self_picture(agent_id: str, form: str = "short", take: bool = False) -> str | None:
    """A picture of HER. Her library first (data/identity/<id>/library -- Barry 2026-09-25: "i dont want her just be
    in the same pose in every video"): the least-recently-used picture in the video's shape (tall for shorts, wide
    for long); take=True marks it used. Falls back to her locked full body, then her face."""
    lib = os.path.join(IDENTITY_DIR, agent_id, "library")
    pics = sorted(glob.glob(os.path.join(lib, "*.png")) + glob.glob(os.path.join(lib, "*.jpg")))
    if pics:
        from PIL import Image
        def tall(p):
            with Image.open(p) as im:
                return im.height > im.width
        shaped = [p for p in pics if tall(p) == (form != "long")] or pics
        used_path = os.path.join(lib, "_used.json")
        used = json.load(open(used_path, encoding="utf-8")) if os.path.isfile(used_path) else {}
        pick = min(shaped, key=lambda p: used.get(os.path.basename(p), 0))
        if take:
            used[os.path.basename(pick)] = time.time()
            with open(used_path, "w", encoding="utf-8") as fh:
                json.dump(used, fh, indent=1)
        return pick
    for name in ("body.png", "face.png"):
        p = os.path.join(IDENTITY_DIR, agent_id, name)
        if os.path.isfile(p):
            return p
    return None


def _wav_seconds(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


# PRONUNCIATION (2026-10-02, Barry: "I also need her to say her name correctly. it Il-Nora Ill-Nora"). The voice
# engine reads the SPOKEN form from data/identity/<agent>/voice/pronounce.json ({"Ilnora": "Ill-Nora"}); her script,
# captions and titles keep the written word -- captions map the heard form back.
def _pronounce(agent_id: str) -> dict[str, str]:
    try:
        with open(os.path.join(IDENTITY_DIR, agent_id, "voice", "pronounce.json"), encoding="utf-8") as fh:
            return {k: v for k, v in json.load(fh).items() if k and v}
    except (OSError, ValueError):
        return {}


def _say(agent_id: str, text: str) -> str:
    for written, spoken in _pronounce(agent_id).items():
        text = re.sub(rf"\b{re.escape(written)}\b", spoken, text, flags=re.I)
    return text


def _unsay(agent_id: str, words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Captions: the transcribed spoken form ("Ill-Nora", or "Ill" + "Nora") back to the written word."""
    def bare(w: str) -> str:
        return re.sub(r"[^a-z]", "", w.lower())
    for written, spoken in _pronounce(agent_id).items():
        parts = [bare(p) for p in re.split(r"[-\s]+", spoken) if bare(p)]
        joined, out, i = "".join(parts), [], 0
        while i < len(words):
            s, e, w = words[i]
            tail = re.sub(r"^.*?([^\w]*)$", r"\1", w)
            if bare(w) in (joined, bare(written)):
                out.append((s, e, written + tail))
                i += 1
            elif len(parts) > 1 and [bare(x[2]) for x in words[i:i + len(parts)]] == parts:
                last = words[i + len(parts) - 1]
                out.append((s, last[1], written + re.sub(r"^.*?([^\w]*)$", r"\1", last[2])))
                i += len(parts)
            else:
                out.append(words[i])
                i += 1
        words = out
    return words


async def _voice_locked(voice_dir: str, lines: list[str], d: str, reel_id: str, log) -> list[float]:
    """All lines in one VoxCPM2 run, owning the card like any render (flag, LLMs unloaded, ComfyUI stopped)."""
    import comfy_image
    import llm_router
    if comfy_image.render_in_progress():
        raise RuntimeError("a render already holds the GPU")
    token = f"reel-voice-{reel_id}"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        lines_path = os.path.join(d, "lines.json")
        with open(lines_path, "w", encoding="utf-8") as fh:
            json.dump(lines, fh, ensure_ascii=False)
        t0 = time.time()
        p = await asyncio.to_thread(subprocess.run, [VOXCPM_PY, VOXCPM_LINES, voice_dir, lines_path, d],
                                    capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("locked voice failed: " + (p.stderr or "")[-800:])
        log(f"voice: {len(lines)} lines in {time.time() - t0:.0f}s (locked voice)")
        try:                                   # the pitch guard's report (tools/tts/voxcpm_lines.py)
            rep = json.loads((p.stdout or "").strip().splitlines()[-1])
            with open(os.path.join(d, "voice_pitch.json"), "w", encoding="utf-8") as fh:
                json.dump(rep, fh, indent=1)
            off = [r for r in rep.get("pitch", []) if not r.get("within")]
            if off:
                log(f"voice: {len(off)} line(s) still off her pitch after retries: {off}")
        except (ValueError, IndexError):
            pass
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass
    return [_wav_seconds(os.path.join(d, f"v{i:03d}.wav")) for i in range(len(lines))]


def _tts(agent_id: str, text: str, path: str) -> float:
    import kokoro_tts
    wav = kokoro_tts.synthesize(agent_id, text)
    with open(path, "wb") as fh:
        fh.write(wav)
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / float(w.getframerate())


def _word_times(wav_path: str) -> list[tuple[float, float, str]]:
    import media_understanding as mu
    model = mu._get_whisper()
    segs, _ = model.transcribe(wav_path, beam_size=5, vad_filter=False, word_timestamps=True)
    out = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                out.append((float(w.start), float(w.end), w.word.strip()))
    return out


# ---------------------------------------------------------------- pictures (GPU)
def _zimage_graph(prompt: str, seed: int, prefix: str, still_w: int, still_h: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors",
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": still_w, "height": still_h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": 9, "cfg": 1.0,
                                                   "sampler_name": "res_multistep", "scheduler": "simple",
                                                   "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


async def _render_stills(prompts: list[str], reel_id: str, log, fmt: dict) -> list[str]:
    import comfy_image
    import llm_router
    if comfy_image.render_in_progress():
        raise RuntimeError("a render already holds the GPU")
    token = f"reel-{reel_id}"
    with open(FLAG, "w") as fh:
        fh.write(token)
    paths = []
    try:
        await llm_router.unload_all_models()
        if not await comfy_image.ensure_running(timeout_s=600):
            raise RuntimeError("ComfyUI did not start")
        host = comfy_image.COMFY_HOST
        async with httpx.AsyncClient(timeout=60) as c:
            for i, prompt in enumerate(prompts):
                t0 = time.time()
                prefix = f"reel_{reel_id}_{i:03d}"
                graph = _zimage_graph(prompt, random.randint(1, 2**31), prefix, fmt["still_w"], fmt["still_h"])
                r = await c.post(f"{host}/prompt", json={"prompt": graph,
                                                         "client_id": str(uuid.uuid4())})
                if r.status_code != 200:
                    raise RuntimeError(f"ComfyUI refused scene {i}: {r.text[:300]}")
                pid = r.json()["prompt_id"]
                while True:
                    await asyncio.sleep(2)
                    h = (await c.get(f"{host}/history/{pid}")).json()
                    if pid in h:
                        st = h[pid].get("status", {})
                        if st.get("status_str") == "error":
                            raise RuntimeError(f"scene {i} failed: {json.dumps(st.get('messages', []))[-400:]}")
                        imgs = [im for o in h[pid].get("outputs", {}).values() for im in o.get("images", [])]
                        if imgs:
                            im = imgs[0]
                            paths.append(os.path.join(config.COMFY_DIR, "output", im.get("subfolder", ""), im["filename"]))
                            break
                    if time.time() - t0 > 900:
                        raise RuntimeError(f"scene {i} timed out")
                log(f"still {i + 1}/{len(prompts)} in {time.time() - t0:.0f}s")
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass
    return paths


# ---------------------------------------------------------------- captions
def _ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


# ---------------------------------------------------------------- motion + assembly
def _scene_clip(img: str, seconds: float, idx: int, out: str, fmt: dict, self_shot: bool = False) -> None:
    W, H = fmt["w"], fmt["h"]
    frames = max(1, int(round(seconds * FPS)))
    if self_shot:
        # HER HOOK: open on her whole figure and push in toward her face (upper part of the frame) while she talks
        z = f"min(1.0+0.8*on/{frames},1.8)"
        x, y = "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*0.10"
    else:
        zoom_in = idx % 2 == 0
        z = f"min(1.0+0.12*on/{frames},1.12)" if zoom_in else f"max(1.12-0.12*on/{frames},1.0)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
          f"format=yuv420p")
    _run(["-loop", "1", "-i", img, "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", out])


# ---------------------------------------------------------------- map card (2026-10-17, Barry: plan step 1)
# Hyperframes (tools/hyperframes: HTML + GSAP -> MP4 through headless Edge, CPU only, no GPU, ~7 s per clip) renders
# the one thing diffusion draws badly and ffmpeg draws flatly: a REAL map with legible words. A part she writes with
# "map": "<where the plant grows>" becomes a MAP CARD scene: the world, her named range lighting up, the plant's
# scientific name. Template data/video_queue/cards/map.html; countries from cards/world.svg (scripts/make_world_svg.py;
# without it the card shows the words alone). Never her face, never a plant picture: a card is words and shapes. A
# failed render falls back to a plain ffmpeg text card -- a card never kills her video.
CARDS_DIR = os.path.join(_ROOT, "data", "video_queue", "cards")
HF_DIR = os.path.join(_ROOT, "tools", "hyperframes")
HF_CLI = os.path.join(HF_DIR, "node_modules", "hyperframes", "bin", "hyperframes.mjs")
HF_ENV = {"HYPERFRAMES_OFFLINE": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1",
          "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
          "HYPERFRAMES_BROWSER_PATH": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"}
CARD_RENDER_TIMEOUT_S = 240


CARD_KINDS = ("map", "fact", "grimoire")   # grimoire (2026-10-19): one of her own grimoire pages as a book page     # fact (2026-10-17, step 2): one short line with its number, over the real plant photo


def _card_kind(scene: dict) -> str:
    k = str(scene.get("card") or "").strip().lower()
    return k if k in CARD_KINDS else ""


def _is_card(scene: dict) -> bool:
    return bool(_card_kind(scene))


def _card_tokens(regions: str) -> list[str]:
    """'Mexico, the southwestern United States and the Andes' -> ['mexico', 'southwestern united states', 'andes',
    'united states'] -- her words, lower-cased, split on commas/and/slashes, leading 'the' dropped; a trailing
    direction word is stripped into a second token so 'southern Mexico' still finds Mexico."""
    parts = re.split(r"\s*(?:,|;|/|&|\band\b|\bto\b)\s*", regions, flags=re.I)
    out: list[str] = []
    for p in parts:
        t = re.sub(r"^(the|in|across|throughout|from)\s+", "", " ".join(p.split()).strip(" ."), flags=re.I).lower()
        if not t:
            continue
        out.append(t)
        bare = re.sub(r"^(north|south|east|west|central|northern|southern|eastern|western|southwestern|"
                      r"southeastern|northwestern|northeastern|coastal|tropical|highland|lowland|upper|lower|"
                      r"inland|rural|ancient|old)\s+", "", t, flags=re.I)
        if bare != t:
            out.append(bare)
    return list(dict.fromkeys(out))


def _card_project(scene: dict, seconds: float, fmt: dict, d: str, idx: int) -> str:
    """Write the card's Hyperframes project (index.html + vendor/) under the reel dir; returns its path."""
    import html as _html
    import shutil
    proj = os.path.join(d, f"card{idx:03d}")
    os.makedirs(proj, exist_ok=True)
    vendor = os.path.join(proj, "vendor")
    if not os.path.isdir(vendor):
        shutil.copytree(os.path.join(CARDS_DIR, "vendor"), vendor)
    kind = _card_kind(scene) or "map"
    tall = fmt["h"] > fmt["w"]
    plant = " ".join(str(scene.get("card_plant") or "").replace("*", " ").replace("_", " ").split())
    page = (open(os.path.join(CARDS_DIR, f"{kind}.html"), encoding="utf-8").read()
            .replace("{{W}}", str(fmt["w"])).replace("{{H}}", str(fmt["h"]))
            .replace("{{SECONDS}}", f"{seconds:.2f}")
            .replace("{{PLANT}}", _html.escape(plant)))
    if kind == "map":
        world = os.path.join(CARDS_DIR, "world.svg")
        svg = open(world, encoding="utf-8").read() if os.path.isfile(world) else ""
        regions = " ".join(str(scene.get("map") or "").split())
        page = (page.replace("{{TITLE_PX}}", "88" if tall else "76").replace("{{SUB_PX}}", "48" if tall else "40")
                .replace("{{REGIONS}}", _html.escape(regions))
                .replace("{{TOKENS}}", json.dumps(_card_tokens(regions)))
                .replace("{{WORLD_SVG}}", svg))
    elif kind == "grimoire":                        # 2026-10-19: her grimoire page -- her title, sigil and words
        pg = scene.get("grimoire_page") or {}
        body = str(pg.get("text") or "").strip()
        n = len(body)
        # a pen script has a small x-height: sized up so a phone can read it (Barry: "nicely written in a cursive script")
        bpx = ((58 if n <= 260 else 50 if n <= 520 else 42 if n <= 900 else 35) if tall else
               (46 if n <= 260 else 40 if n <= 520 else 34 if n <= 900 else 28))
        body_html = "<br>".join(_html.escape(" ".join(line.split()))
                                for line in re.split(r"\n+|(?<=[.!?])\s+", body) if line.strip())
        page = (page.replace("{{TITLE_PX}}", "84" if tall else "68").replace("{{BODY_PX}}", str(bpx))
                .replace("{{TITLE}}", _html.escape(str(pg.get("title") or "")))
                .replace("{{TEXT}}", body_html)
                .replace("{{SIGIL_PATHS}}", json.dumps([str(x) for x in (pg.get("sigil") or [])])))
    else:                                           # fact: the line big, the plant photo (if any) behind it
        fact = " ".join(str(scene.get("fact") or "").split())
        bg = ""
        photo = scene.get("_card_photo")
        if photo and os.path.isfile(photo):
            bg = "bg" + (os.path.splitext(photo)[1].lower() or ".jpg")
            shutil.copy2(photo, os.path.join(proj, bg))
        n = len(fact)
        title = (104 if n <= 28 else 88 if n <= 44 else 72) if tall else (92 if n <= 28 else 76 if n <= 44 else 62)
        page = (page.replace("{{TITLE_PX}}", str(title)).replace("{{SUB_PX}}", "46" if tall else "38")
                .replace("{{FACT}}", _html.escape(fact)).replace("{{BG}}", bg))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(proj, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"id": f"card{idx:03d}", "name": plant or "map card"}, fh)
    return proj


def _card_render(proj: str, out_mp4: str, log) -> bool:
    """hyperframes render -> out_mp4. False (logged) on any failure; never raises."""
    if not os.path.isfile(HF_CLI):
        log(f"map card: hyperframes missing at {HF_CLI}")
        return False
    env = dict(os.environ)
    env.update(HF_ENV)
    # 2026-10-19: a process started under the Windows App Health detector carries __COMPAT_LAYER=DetectorsAppHealth;
    # Edge sees it and RELAUNCHES itself (--edge-skip-compat-layer-relaunch), so the process puppeteer started exits 0
    # at once and every card render dies with "Failed to launch the browser process: Code: 0".
    env.pop("__COMPAT_LAYER", None)
    env["PATH"] = os.path.join(HF_DIR, "bin") + os.pathsep + env.get("PATH", "")
    try:
        r = subprocess.run(["node", HF_CLI, "render", proj, "-o", out_mp4, "--fps", str(FPS), "--quality", "looks",
                            "--workers", "2", "--quiet"], env=env, cwd=HF_DIR, capture_output=True, text=True,
                           timeout=CARD_RENDER_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"map card: render failed ({type(exc).__name__}: {exc})")
        return False
    if r.returncode != 0 or not os.path.isfile(out_mp4):
        tail = " | ".join(line.strip() for line in (r.stderr or r.stdout or "").splitlines()[-4:])
        log(f"map card: render exit {r.returncode}: {tail[:400]}")
        return False
    return True


def _card_fallback_still(scene: dict, fmt: dict, png: str) -> None:
    """No renderer: a dark card with the words, drawn by ffmpeg (always works)."""
    plant = " ".join(str(scene.get("card_plant") or "").replace("*", " ").split()).replace("'", "’").replace(":", "\\:")
    if _card_kind(scene) == "fact":
        big = " ".join(str(scene.get("fact") or "").split()).replace("'", "’").replace(":", "\\:")
        small = plant
    else:
        big = plant
        small = "grows in " + " ".join(str(scene.get("map") or "").split()).replace("'", "’").replace(":", "\\:")
    size_a, size_b = (84, 46) if fmt["h"] > fmt["w"] else (72, 40)
    vf = (f"drawtext=fontfile='{PLANT_LABEL_FONT}':text='{big}':fontcolor=#e8e4d8:fontsize={size_a}:"
          f"x=(w-text_w)/2:y=h*0.42,"
          f"drawtext=fontfile='{PLANT_LABEL_FONT}':text='{small}':fontcolor=#b9e4c3:fontsize={size_b}:"
          f"x=(w-text_w)/2:y=h*0.42+{size_a + 30}")
    _run(["-f", "lavfi", "-i", f"color=c=#07090a:s={fmt['w']}x{fmt['h']}", "-vf", vf, "-frames:v", "1", png])


def _card_scene(scene: dict, seconds: float, fmt: dict, d: str, idx: int, log) -> tuple[str, str | None]:
    """Render part idx's map card now (CPU; runs while the GPU is busy elsewhere). Returns (still for the
    storyboard/thumbnail, mp4 or None when the fallback card is all we have)."""
    t0 = time.time()
    mp4 = os.path.join(d, f"card{idx:03d}.mp4")
    png = os.path.join(d, f"card{idx:03d}.png")
    species = " ".join(str(scene.get("card_plant") or "").replace("*", " ").split())
    if _card_kind(scene) == "fact" and species:
        # the real plant behind the words when the office has a photo (Barry's drop or iNaturalist, credited like
        # every other photo in the video); none -> the dark frame. ALWAYS re-picked (2026-10-18): the first build's
        # pick is saved in the job's package, so a requeue reused a photo the OCR gate had since ruled out (the
        # Henbane card came back with the photographer's caption on it a second time).
        scene.pop("_card_photo", None)
        scene.pop("_photo_credit", None)
        try:
            ref = _plant_ref(species, {}, log)
        except Exception as exc:  # noqa: BLE001
            log(f"fact card: no plant photo ({type(exc).__name__}: {exc})")
            ref = None
        if ref:
            scene["_card_photo"], scene["_photo_credit"] = ref[0], ref[1]
    ok = _card_render(_card_project(scene, seconds, fmt, d, idx), mp4, log)
    if ok:
        grab = (max(0.0, seconds * 0.9) if _card_kind(scene) == "grimoire" else min(1.4, max(0.0, seconds - 0.1)))
        _run(["-ss", f"{grab:.2f}", "-i", mp4, "-frames:v", "1", png])
        log(f"map card (part {idx + 1}): {seconds:.1f}s rendered in {time.time() - t0:.0f}s")
        return png, mp4
    _card_fallback_still(scene, fmt, png)
    log(f"map card (part {idx + 1}): fallback text card")
    return png, None


def _card_scene_clip(mp4: str | None, png: str, seconds: float, idx: int, out: str, fmt: dict) -> None:
    """The card as this scene's clip: exactly `seconds` long at FPS (the render is cut or held on its last frame)."""
    if not mp4:
        _scene_clip(png, seconds, idx, out, fmt)
        return
    W, H = fmt["w"], fmt["h"]
    frames = max(1, int(round(seconds * FPS)))
    vf = f"scale={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration={seconds + 1:.2f},format=yuv420p"
    _run(["-i", mp4, "-an", "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", out])


# MOTION (2026-10-02, Barry: "with motion, not stills" / "some of the plant stuff can be images but true to the lines
# that are being said. but ilnora has to have life"). Her own parts ("show": "self") are ALWAYS real video: her
# picture animated by LTX-2.5 image-to-video (comfy_image.generate_video, i2v). Any other part becomes video when it
# carries "motion": true. LTX's own audio is dropped -- her locked voice is the soundtrack. Measured cost: ~13-20 min
# of GPU per 5 s clip at 576p, so a clip is 5 s, slowed up to 2x and then played forward-and-back to fill her line.
MOTION_CLIP_S = 5


def _motion_prompt(scene: dict, self_shot: bool) -> str:
    # HER OWN DIRECTION FIRST (2026-10-02, Barry: "make this good. maybe she neesds some of what elliot has"): a part's
    # "motion_prompt" is what SHE wrote for the clip, in LTX grammar (ltx25-prompting.md) -- used as she wrote it.
    if (scene.get("motion_prompt") or "").strip():
        return scene["motion_prompt"].strip()
    if self_shot:
        # no "hand gestures" (2026-10-02, Barry: "hands not holding the spoon stirring the pot") -- whatever her hands
        # hold in the still, they keep holding; her voice drives the mouth, so the prompt never asks for lip motion
        # static camera (2026-10-02 test: "a slow subtle camera push-in" became a hard dolly into the pot that lost
        # her face). Camera moves only when SHE writes one in her motion_prompt.
        return ("Static locked-off camera, medium shot, the framing does not change. She looks into the camera and "
                "speaks warmly, telling a story: natural small head movements, blinking, relaxed shoulders, her hands "
                "stay on whatever they are holding. Soft light on her face. Photographic, natural lifelike motion.")
    base = (_picture_text(scene) or scene.get("plant") or "").strip().rstrip(".")
    return (f"{base}. Natural real-world motion in the scene -- hands working, liquid pouring, steam rising, leaves "
            f"stirring, flames flickering -- with a slow, smooth cinematic camera move. Photographic, lifelike.")


CLIP_MIN_S, CLIP_MAX_S = 2, 5


def _clip_seconds(scene: dict) -> int:
    """How long this part's moving clip is (2026-10-15, Barry: "random clips length, 3-5 seconds not a fixed number,
    some can be 2 seconds"). Her own "seconds" (2-5) when she set one; otherwise the line decides -- a short line gets
    a short clip, so it is not slowed down and looped under her voice; a long line gets 5 s."""
    try:
        s = int(round(float(scene.get("seconds"))))
        if CLIP_MIN_S <= s <= CLIP_MAX_S:
            return s
    except (TypeError, ValueError):
        pass
    line_s = len(str(scene.get("narration") or "").split()) / 3.1        # her measured pace, pauses included
    return max(CLIP_MIN_S, min(CLIP_MAX_S, int(round(line_s))))


async def _animate(stills: list[str], scenes: list[dict], d: str, form: str, log,
                   talking: set | None = None) -> list[str | None]:
    """Each part that needs life -> a 2-5 s LTX clip from its still (_clip_seconds). None = keep the still (slow zoom).
    Her on-camera parts with a voice line become TALKING clips instead (index added to `talking`)."""
    talking = talking if talking is not None else set()
    import shutil
    import comfy_image
    want = [_is_self(s) or bool(s.get("motion")) for s in scenes]
    if not any(want):
        return [None] * len(stills)
    w, h = (576, 1024) if form == "short" else (1024, 576)
    inp = os.path.join(config.COMFY_DIR, "input")
    out: list[str | None] = []
    n = sum(want)
    k = 0
    for i, (img, s) in enumerate(zip(stills, scenes)):
        if not want[i] or not img:
            out.append(None)
            continue
        k += 1
        name = f"reelmotion_{os.path.basename(d)}_{i:03d}{os.path.splitext(img)[1] or '.png'}"
        shutil.copy2(img, os.path.join(inp, name))
        t0 = time.time()
        wav = os.path.join(d, f"v{i:03d}.wav")
        if _is_self(s) and _talk_on() and os.path.isfile(wav):
            talk = await _talking(img, s, wav, d, i, form, log)
            if talk:
                out.append(talk)
                talking.add(i)
                try:
                    os.remove(os.path.join(inp, name))
                except OSError:
                    pass
                continue
        try:
            r = await comfy_image.generate_video(_motion_prompt(s, _is_self(s)), duration_s=_clip_seconds(s),
                                                 width=w, height=h, start_frame=name)
        except Exception as exc:  # noqa: BLE001 -- a failed clip falls back to the still, never kills the reel
            r = {"error": f"{type(exc).__name__}: {exc}"}
        log(f"motion {k}/{n} (part {i + 1}): {'ok' if r.get('path') else r.get('error')} in {time.time() - t0:.0f}s")
        out.append(r.get("path"))
        try:
            os.remove(os.path.join(inp, name))
        except OSError:
            pass
    return out


# HER OWN SHOT (2026-10-03, Barry: "she has to direct her own video, prompt it right, each scene should be curated",
# "we use her face and body, but prompt a new outfit or color", "she has to describe it then"). A part where she is on
# screen may carry "shot": what she wears, where she is, what she is doing, the framing -- in her words. The office
# draws that still fresh with Qwen-Image-Edit (Apache 2.0) from her locked FACE + BODY (body_neutral.png once Barry
# approves it, else body.png), with his image base line (identity/<agent>/image_prompt.txt) in front. No "shot" =
# her library picture, as before. If her shot names no clothes she wears her usual green dress (Barry's default).
DEFAULT_LOOK = "wearing her emerald-green satin dress with sheer black lace sleeves and a gold sash"
_CLOTHES = ("wear", "dress", "gown", "shirt", "blouse", "top", "sweater", "cardigan", "jacket", "coat", "cloak",
            "robe", "shawl", "skirt", "apron", "outfit", "tunic", "vest", "linen", "silk", "velvet", "knit",
            "jeans", "denim", "pants", "trousers", "leggings", "tights", "tee", "t-shirt", "tank", "clothes", "overalls")


def _her_base(agent_id: str) -> str:
    try:
        txt = open(os.path.join(IDENTITY_DIR, agent_id, "image_prompt.txt"), encoding="utf-8").read()
    except OSError:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", txt) if p.strip()]
    body = [p for p in paras[1:] if not p.lower().startswith("sources")]
    return " ".join(body[0].split()) if body else ""


# HIS PRODUCTS IN HER BACKGROUND (Barry 2026-10-04: "i want to sneak in a bag of Profimix and Microlife from my store in
# her back ground while shes talking and doing gardening" / "soil supermix sometimes too"). When her shot names one,
# the REAL store photo (data/product-images) goes to the editor as a reference, so the container, colours and label
# are the real product, not an invented one. One product per shot; her own parts only.
PRODUCTS = {
    "profimix": ("Bionova Profimix", "bionova-profimix-all-in-one-granular-soil-fertilizer-vegan-n.jpg"),
    "microlife": ("Bionova Microlife", "bionova-microlife-mycorrhiza-soil-enhancer.jpg"),
    "supermix": ("Bionova Soil Supermix", "bionova-soil-supermix-fertilizer.jpg"),
}


def _product_in(shot: str) -> tuple[str, str] | None:
    low = (shot or "").lower()
    hits = sorted((low.find(k), k) for k in PRODUCTS if k in low)
    if not hits:
        return None
    label, fname = PRODUCTS[hits[0][1]]
    path = os.path.join(_ROOT, "data", "product-images", fname)
    return (label, path) if os.path.isfile(path) else None


def _outfit_of(shot: str) -> str:
    """The clothing clause(s) of her shot, in her words ("" if she named none)."""
    segs = [p.strip() for p in re.split(r"[,;]", shot or "") if p.strip()]
    return ", ".join(p for p in segs if any(w in p.lower() for w in _CLOTHES))


async def _her_still(agent_id: str, scene: dict, form: str, d: str, i: int, log,
                     last_outfit: str = "") -> str | None:
    import shutil
    import comfy_image
    shot = " ".join(str(scene.get("shot") or "").split())
    if not shot:
        return None
    idd = os.path.join(IDENTITY_DIR, agent_id)
    body = os.path.join(idd, "body_neutral.png")
    body = body if os.path.isfile(body) else os.path.join(idd, "body.png")
    face = os.path.join(idd, "face.png")
    if not (os.path.isfile(body) and os.path.isfile(face)):
        return None
    # 2026-10-04 fixes (Barry: "go, fix all three"): (1) the OUTPUT SIZE is set directly (wide for a Long) and her
    # body/face are references only -- the old tall-body-on-a-black-wide-canvas kept the bars and the old garden;
    # (2) the face reference is the small copy -- two full-size references ran ~26 min a picture; (3) a shot that
    # names no clothes keeps the outfit of her last shot in this video, the green dress only if she named none yet.
    W, H = (768, 1376) if form != "long" else (1376, 768)
    inp = os.path.join(config.COMFY_DIR, "input")
    n1 = f"reelher_{os.path.basename(d)}_{i:03d}_body.png"
    n2 = f"reelher_{os.path.basename(d)}_{i:03d}_face.png"
    shutil.copy2(body, os.path.join(inp, n1))
    shutil.copy2(face, os.path.join(inp, n2))
    n2s = comfy_image.small_reference(n2)
    if _outfit_of(shot):
        look = shot
    elif last_outfit:
        look = f"{shot}, wearing the same outfit as before: {last_outfit}"
    else:
        look = f"{shot}, {DEFAULT_LOOK}"
    framing = "a wide, horizontal frame" if form == "long" else "a tall, vertical frame"
    # 2026-10-05 MEASURED, not used: "scene first" (Qwen-Image draws the shot, the editor swaps in her face) drew
    # real rooms but the editor would not move her face onto the scene's woman (twice: whole face picture -> it
    # copied the tee; head-only crop -> face unchanged). Body + face below keeps HER face every time.
    t0 = time.time()
    sources, extra, product = [n1, n2s], "", _product_in(shot)
    n3 = n3s = ""
    if product:
        n3 = f"reelher_{os.path.basename(d)}_{i:03d}_product{os.path.splitext(product[1])[1]}"
        shutil.copy2(product[1], os.path.join(inp, n3))
        n3s = comfy_image.small_reference(n3)
        sources.append(n3s)
        extra = (f" The {product[0]} in the scene is exactly the product in image 3 -- the same container, colours "
                 f"and label -- placed in the background as described, real-size, part of the scene.")
    elif _plant(scene):
        # her shot with the real plant (2026-10-14, see _plant_ref): the plant photo is image 3. A product in the
        # same shot keeps image 3 (Barry's own store ask) and the plant is drawn from her words.
        species = _plant(scene)
        ref = _plant_ref(species, {}, log)
        if ref:
            n3 = f"reelher_{os.path.basename(d)}_{i:03d}_plant{os.path.splitext(ref[0])[1]}"
            shutil.copy2(ref[0], os.path.join(inp, n3))
            n3s = comfy_image.small_reference(n3)
            sources.append(n3s)
            extra = (f" The {species} with her is exactly the plant in image 3 -- the same leaves, flowers and "
                     f"colours, true to the real species, real-size, part of the scene as described.")
            scene["_photo_credit"] = ref[1]
    # 2026-10-05: the references are on a plain studio backdrop -- they only say WHO she is, never where or how.
    # Measured: shots that NAME a real place come back in a full room; a "studio" shot comes back blank.
    instruction = (f"A new photograph of the same woman: her body from image 1 and her exact face from image 2. "
                   f"{_her_base(agent_id)} {look}. Keep her face, hair, age and body exactly as in the references; "
                   f"everything else -- clothes, place, light -- is new, as described.{extra} Images 1 and 2 only "
                   f"show who she is: their plain backdrop, pose and framing are not part of this photograph. She "
                   f"stands in a real, fully built place -- walls, furniture, objects, depth and natural light, "
                   f"the place described -- never a blank studio backdrop, posed and framed exactly as described. "
                   f"The scene fills {framing} edge to edge. Photographic, natural light.")
    try:
        r = await comfy_image.edit_image(sources, instruction, prefix="reel_her", size=(W, H))
    finally:
        for n in {n1, n2, n2s, n3, n3s} - {""}:
            try:
                os.remove(os.path.join(inp, n))
            except OSError:
                pass
    if not r.get("path"):
        log(f"her shot for part {i + 1} failed ({r.get('error')}) -- using a library picture")
        return None
    out = os.path.join(d, f"her{i:03d}.png")
    shutil.copy2(r["path"], out)
    made = os.path.join(idd, "library", "made")              # kept: every look she has ever directed
    os.makedirs(made, exist_ok=True)
    shutil.copy2(out, os.path.join(made, f"{os.path.basename(d)}_{i:03d}.png"))
    log(f"her shot for part {i + 1} drawn in {time.time() - t0:.0f}s: {shot[:80]}")
    return out


# TALKING (2026-10-02, Barry: "it looks good ... i think it will do"). Her on-camera parts are LTX-2.5 AUDIO-TO-VIDEO:
# her still + her own voice line -> she talks at real speed, mouth and face driven by the line (comfy_image voice=).
# Replaces the 5 s clip slowed to fill + LatentSync (both looked bad). A line longer than TALK_MAX_S is split into
# chunks; EVERY chunk starts from her original still (2026-10-02 test: chaining from the last frame lost her face and
# changed her dress) -- it plays as jump cuts, the normal talking-head edit. A failed part falls back
# to the plain moving clip, never kills the video. REEL_TALK=0 = off.
TALK_MAX_S = 10.0
TALK_FPS = 24


def _talk_on() -> bool:
    return os.getenv("REEL_TALK", "1") != "0"


async def _talking(still: str, scene: dict, wav: str, d: str, i: int, form: str, log) -> str | None:
    import math
    import shutil
    import comfy_image
    w, h = (576, 1024) if form == "short" else (1024, 576)
    inp = os.path.join(config.COMFY_DIR, "input")
    dur = _wav_seconds(wav)
    n = max(1, math.ceil(dur / TALK_MAX_S))
    seg = dur / n
    start, parts, made = still, [], []
    t0 = time.time()
    try:
        for k in range(n):
            frames = math.ceil(seg * TALK_FPS / 8) * 8 + 1
            img_name = f"reeltalk_{os.path.basename(d)}_{i:03d}_{k}{os.path.splitext(start)[1] or '.png'}"
            wav_name = f"reeltalk_{os.path.basename(d)}_{i:03d}_{k}.wav"
            shutil.copy2(start, os.path.join(inp, img_name))
            _run(["-ss", f"{k * seg:.3f}", "-t", f"{seg:.3f}", "-i", wav, "-af",
                  f"apad=whole_dur={frames / TALK_FPS:.3f}", "-ar", "48000", "-ac", "1", os.path.join(inp, wav_name)])
            made += [os.path.join(inp, img_name), os.path.join(inp, wav_name)]
            r = await comfy_image.generate_video(_motion_prompt(scene, True), width=w, height=h, fps=TALK_FPS,
                                                 start_frame=img_name, voice=wav_name, frames=frames)
            if not r.get("path"):
                log(f"talking part {i + 1} chunk {k + 1}/{n} failed: {r.get('error')}")
                return None
            # LIP SYNC (2026-10-08, Barry: "her lip sync was off too"): the clip is rendered frames/24 s long (frames
            # = 8n+1) but its voice slice is only `seg` s -- joined untrimmed, every chunk pushed the next one later
            # (part 7: 5 chunks, up to ~1.3 s late by the end). Trim each chunk to its exact slice before joining.
            trimmed = os.path.join(d, f"talk{i:03d}_{k}.mp4")
            _run(["-i", r["path"], "-t", f"{seg:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-r", str(TALK_FPS), trimmed])
            parts.append(trimmed)
        out = os.path.join(d, f"talk{i:03d}.mp4")
        if len(parts) == 1:
            shutil.copy2(parts[0], out)
        else:
            lst = os.path.join(d, f"talk{i:03d}.txt")
            with open(lst, "w") as fh:
                fh.writelines("file '" + p.replace(chr(92), "/") + "'\n" for p in parts)
            _run(["-f", "concat", "-safe", "0", "-i", lst, "-an", "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", "18", out])
        log(f"talking part {i + 1}: {n} clip(s), {dur:.1f} s of her voice, in {time.time() - t0:.0f}s")
        return out
    finally:
        for f in made:
            try:
                os.remove(f)
            except OSError:
                pass


def _talk_scene_clip(video: str, seconds: float, out: str, fmt: dict) -> None:
    """Her talking clip at REAL speed: to the reel's frame size and rate, exact length (last frame held through the
    breath), no audio -- her voice track is laid under the whole reel later, starting at the same instant."""
    W, H = fmt["w"], fmt["h"]
    _run(["-i", video, "-an", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration=3,format=yuv420p", "-t", f"{seconds:.3f}", "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "20", out])


def _motion_scene_clip(video: str, seconds: float, out: str, fmt: dict, clip_s: float = MOTION_CLIP_S) -> None:
    """A 2-5 s clip filling a line of any length: slowed up to 2x, then forward-and-back on a loop. No clip audio."""
    W, H = fmt["w"], fmt["h"]
    f = max(1.0, min(2.0, seconds / max(1.0, clip_s)))
    pp = out[:-4] + "_pp.mp4"
    # SLOWED = NEW FRAMES, NOT REPEATS (2026-10-11): setpts alone held each frame up to twice -- ~12 real frames a
    # second, the choppy 0:17-0:35 of The Fairy's Bell. Motion interpolation (CPU, at the clip's own size) fills them.
    interp = (f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1," if f > 1.02 else "")
    fc = (f"[0:v]setpts={f:.4f}*PTS,{interp}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,format=yuv420p[v]")
    _run(["-i", video, "-an", "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", pp])
    _run(["-stream_loop", "-1", "-i", pp, "-t", f"{seconds:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", out])
    try:
        os.remove(pp)
    except OSError:
        pass


def final_mix(d: str, video: str, voice: str, music: str | None, sub: str, total: float, out: str) -> None:
    """Voice + music under the picture -> the finished MP4. Used by the builder and scripts/redo_her_parts.py.

    SOUND FIRST, THEN PICTURE (2026-10-11, Barry: "some words are missing and at the end is a 5 second space of
    nothing"). One pass mixing voice + music while the picture was filtered dropped ~6 s of mixed audio (The Fairy's
    Bell 44.9 s of sound in a 50.8 s file; Wolf's Blood the same) -- the voice skipped ahead and the end ran silent.
    Reproduced exactly; mixing the sound alone (voice split for the ducker) keeps every word. scripts/check_video_audio.py
    measures it."""
    mix = os.path.join(d, "mix.wav")
    if music:
        _run(["-i", voice, "-i", music, "-filter_complex",
              f"[0:a]asplit=2[vs][vm];[1:a]volume=0.35,afade=t=out:st={max(0, total - 2):.2f}:d=2[m];"
              f"[m][vs]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
              f"[vm][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5,aresample=48000[a]",
              "-map", "[a]", "-ac", "2", mix])
    else:
        _run(["-i", voice, "-af", "loudnorm=I=-14:TP=-1.5,aresample=48000", "-ac", "2", mix])
    _run(["-i", video, "-i", mix, "-filter_complex", f"[0:v]{sub}[v]", "-map", "[v]", "-map", "1:a",
          "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
          "-shortest", out])


def _music_for(mood: str) -> str | None:
    tracks = glob.glob(os.path.join(MUSIC_DIR, mood or "", "*.mp3")) or glob.glob(os.path.join(MUSIC_DIR, "**", "*.mp3"),
                                                                                  recursive=True)
    return random.choice(tracks) if tracks else None


def _music_credit(tracks) -> str:
    """The library in data/music is Kevin MacLeod's (incompetech.com, CC BY 4.0 -- free, monetizable on YouTube,
    credit required). Downloaded 2026-09-24 with Barry's OK. One credit line per track used."""
    if isinstance(tracks, str):
        tracks = [tracks]
    return "\n".join(f'Music: "{os.path.splitext(os.path.basename(t))[0]}" Kevin MacLeod (incompetech.com) -- '
                     f"Licensed under Creative Commons: By Attribution 4.0 https://creativecommons.org/licenses/by/4.0/"
                     for t in (tracks or []) if t)


# Long videos change track partway (Barry 2026-09-24: "we can switch part way on long videos, but mix it in in a
# dope way"). The switch lands at a SCENE BREAK: her line ends, an extra breath of silence opens, the voice-duck
# releases so the outgoing track swells up, and a 3 s equal-power crossfade carries it into the next track, which
# is already riding under her first words of the new section. Never mid-sentence.
SECTION_S = 150          # aim for a new track about every 2.5 minutes
SWITCH_BREATH_S = 1.6    # extra silence at a switch point -- the music's moment
XFADE_S = 3.0


def _music_plan(mood: str, durs: list[float], form: str) -> tuple[list[str], list[int]]:
    """-> (tracks, switch_scene_indexes). A switch after scene k means the new track starts in scene k's breath."""
    first = _music_for(mood)
    if not first:
        return [], []
    if form != "long" or sum(durs) < SECTION_S * 1.6:
        return [first], []
    pool = [t for t in glob.glob(os.path.join(MUSIC_DIR, mood or "", "*.mp3")) if t != first]
    random.shuffle(pool)
    switches, t, target = [], 0.0, SECTION_S
    for k, d in enumerate(durs[:-1]):
        t += d
        if t >= target and sum(durs) - t > 45:          # never switch in the last 45 s
            switches.append(k)
            target = t + SECTION_S
    tracks = [first]
    for _ in switches:
        if not pool:                                     # ran out of this mood: reuse, never repeat back-to-back
            pool = [x for x in glob.glob(os.path.join(MUSIC_DIR, mood or "", "*.mp3")) if x != tracks[-1]]
            random.shuffle(pool)
        tracks.append(pool.pop() if pool else tracks[-1])
    return tracks, switches


def _music_bed(tracks: list[str], cut_times: list[float], total: float, out: str) -> None:
    """Chain the tracks into one bed of exactly `total` seconds, crossfading (equal-power) centred on each cut."""
    edges = [0.0] + list(cut_times) + [total]
    args, chain = [], []
    for i, tr in enumerate(tracks):
        seg = edges[i + 1] - edges[i]
        if i < len(tracks) - 1:
            seg += XFADE_S / 2          # outgoing track runs through the crossfade...
        if i > 0:
            seg += XFADE_S / 2          # ...and the incoming one starts inside it
        args += ["-stream_loop", "-1", "-i", tr]
        chain.append(f"[{i}:a]atrim=0:{seg:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[s{i}]")
    prev = "s0"
    for i in range(1, len(tracks)):
        chain.append(f"[{prev}][s{i}]acrossfade=d={XFADE_S}:c1=qsin:c2=qsin[x{i}]")
        prev = f"x{i}"
    chain.append(f"[{prev}]atrim=0:{total:.3f}[bed]")
    _run([*args, "-filter_complex", ";".join(chain), "-map", "[bed]", out])


PLANT_LABEL_S = 2.5
PLANT_LABEL_FONT = "C\\:/Windows/Fonts/georgiai.ttf"


def _plant_labels(scenes: list[dict], durs: list[float], fmt: dict) -> str:
    """Barry 2026-10-06: "I do want her to show the text for the plants she is talking about on the screen for a
    couple of seconds. thats it." -- the plant's name (its "plant" field) fades in for PLANT_LABEL_S the first time
    each plant's picture comes on. Nothing else is written on screen (no captions). ffmpeg filter, "null" if none."""
    out, seen, t = [], set(), 0.0
    for s, sec in zip(scenes, durs):
        name = _plant(s)
        # the name goes on the first PORTRAIT of the plant, not on a mortar or a fire circle she tagged (2026-10-09)
        if name and not _is_self(s) and _plant_portrait(s) and name.lower() not in seen:
            seen.add(name.lower())
            t0, t1 = t + 0.3, t + 0.3 + PLANT_LABEL_S
            txt = re.sub(r"[^A-Za-z0-9 .\-]", "", name)
            fade = (f"if(lt(t,{t0:.2f}+0.4),(t-{t0:.2f})/0.4,if(gt(t,{t1:.2f}-0.4),({t1:.2f}-t)/0.4,1))")
            out.append(f"drawtext=fontfile='{PLANT_LABEL_FONT}':text='{txt}':fontsize={int(fmt['h'] * 0.034)}:"
                       f"fontcolor=white:alpha='{fade}':box=1:boxcolor=black@0.45:boxborderw={int(fmt['h'] * 0.012)}:"
                       f"x=(w-text_w)/2:y=h*0.80:enable='between(t,{t0:.2f},{t1:.2f})'")
        t += sec
    return ",".join(out) or "null"


def _picture_text(scene: dict) -> str:
    """What a picture part is drawn from: her image_prompt -- unless it is a placeholder. MEASURED 2026-10-06: in
    "Two Witches' Sisters" two parts had image_prompt "motion" (her real description was in motion_prompt); Z-Image
    drew the word "motion" as strangers jogging and Barry got 45 s of random people nobody asked for. Then her own
    motion_prompt is the picture -- her words either way."""
    ip = (scene.get("image_prompt") or "").strip()
    mp = (scene.get("motion_prompt") or "").strip()
    if mp and (len(ip.split()) <= 2 or ip.lower().strip(" .") in ("motion", "move", "video", "clip", "animation")):
        return mp
    return ip


STORYBOARD_MAX_REDO = 6          # one round, at most this many parts redrawn (~1-6 min each)


async def _storyboard_pass(storyboard, agent: str, scenes: list[dict], stills: list, kinds: list[str], form: str,
                           d: str, reel_id: str, fmt: dict, log) -> tuple[list, list[str]]:
    """Show her the drawn stills (storyboard(parts) -> [{"part", "picture"}]) and redraw the parts she writes again,
    from HER new words. A failed redraw keeps the old still; a failed check builds the video as drawn.
    Returns (stills, photo credits of any real photos the redraw brought in)."""
    credits: list[str] = []
    parts = [{"part": i + 1, "kind": k, "path": p, "plant": _plant(s),
              "planned": " ".join(str(s.get("shot") if k == "self" else _picture_text(s) or "").split()),
              "says": " ".join(str(s.get("narration") or "").split())}
             for i, (s, p, k) in enumerate(zip(scenes, stills, kinds))]
    try:
        redo = await storyboard(parts) or []
    except Exception as exc:  # noqa: BLE001
        log(f"storyboard check failed ({type(exc).__name__}: {exc}) -- building as drawn")
        return stills, credits
    stills = list(stills)
    first_outfit = next((_outfit_of(s.get("shot") or "") for s in scenes if _is_self(s) and s.get("shot")), "")
    done = 0
    for r in redo:
        try:
            i = int(r.get("part")) - 1
        except (TypeError, ValueError):
            continue
        new = " ".join(str(r.get("picture") or "").split())
        if not (0 <= i < len(scenes)) or not new or kinds[i] in ("photo", "card") or done >= STORYBOARD_MAX_REDO:
            continue
        s, done = scenes[i], done + 1
        try:
            if kinds[i] == "self":
                s["shot"] = new
                path = await _her_still(agent, s, form, d, i, log, last_outfit=first_outfit)
            elif kinds[i] == "plant":
                s["image_prompt"] = new
                (path, credit), = await _plant_stills([(_plant(s), new, _plant_portrait(s))], form, log)
                if credit:
                    credits.append(credit)              # her new words opened on the plant: a real photo, credited
            else:
                s["image_prompt"] = new
                path = (await _render_stills([new], f"{reel_id}_sb{i:03d}", log, fmt))[0]
        except Exception as exc:  # noqa: BLE001
            log(f"storyboard: part {i + 1} redraw failed ({type(exc).__name__}: {exc}) -- keeping the first picture")
            continue
        if path:
            stills[i] = path
            log(f"storyboard: part {i + 1} redrawn ({str(r.get('what') or '')[:80]})")
    return stills, credits


async def build_reel(package: dict, log=print, storyboard=None) -> dict:
    """Render a package into a finished MP4 -- vertical short or widescreen long, per the package's "format"
    (the agent's own choice). Returns {"ok", "video", "thumbnail", "seconds", "format", ...}.
    storyboard: optional async check of the drawn stills before anything is animated (see _storyboard_pass)."""
    form = (package.get("format") or "short").strip().lower()
    if form not in FORMATS:
        return {"ok": False, "why": f'format must be "short" or "long", got "{form}"'}
    fmt = FORMATS[form]
    # 2026-10-06 safety net: a picture part whose description starts "me, ..." is HER (her own words as the shot) --
    # drawn as a picture it would be a stranger instead of her. Its plant stays: her shot is drawn with the real
    # plant (2026-10-14, _plant_ref).
    for s in package.get("scenes") or []:
        ip = str(s.get("image_prompt") or "")
        m = re.match(r"^\s*(me|myself)\b[\s,:;\-–—]+", ip, re.I)
        if not _is_self(s) and m:
            s["show"] = "self"
            s.setdefault("shot", " ".join(ip[m.end():].split()))
            s.pop("image_prompt", None)
    # a scene shows either a new picture ("image_prompt") or the agent HERSELF ("show": "self" -- her locked
    # full-body picture; Barry 2026-09-24: "i need Ilnora in the beginning to hook them")
    scenes = [s for s in (package.get("scenes") or []) if (s.get("narration") or "").strip()
              and (_picture_text(s) or _is_self(s) or _plant(s) or _is_card(s))]
    if not 1 <= len(scenes) <= fmt["max_scenes"]:
        return {"ok": False, "why": f"a {form} video needs 1-{fmt['max_scenes']} scenes with narration and a "
                                    f"picture prompt (or \"show\": \"self\"), got {len(scenes)}"}
    reel_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(REELS_DIR, reel_id)
    os.makedirs(d, exist_ok=True)
    agent = package.get("voice_agent") or "ilnora"
    self_pic = _self_picture(agent, form)          # availability check only; each "self" scene takes its own
    unnamed = _unnamed_plant_scenes(scenes)
    if unnamed:
        return {"ok": False, "why": f"scene(s) {unnamed} show plants without naming them. Every plant on screen "
                                    f"must be the plant you're talking about: add \"plant\": \"<scientific name>\" "
                                    f"to those scenes (Qwen-Image draws the real species), or take the plants out "
                                    f"of the picture."}
    if any(_is_self(s) for s in scenes) and not self_pic:
        return {"ok": False, "why": f"{agent} has no locked picture (data/identity/{agent}/body.png) to show herself"}
    t_all = time.time()

    import comfy_image as _ci
    await _ci.reel_wait_turn(log)                  # Barry / Elliot / MyStudio first
    # 1. voice, one clip per scene (CPU)
    voice_dir = _locked_voice(agent)
    if voice_dir:
        durs = [x + PAD_S for x in await _voice_locked(voice_dir, [_say(agent, s["narration"].strip()) for s in scenes], d,
                                                        reel_id, log)]
    else:
        durs = [_tts(agent, _say(agent, s["narration"].strip()), os.path.join(d, f"v{i:03d}.wav")) + PAD_S
                for i, s in enumerate(scenes)]
    # NO 3:00 CAP (2026-10-11, Barry: "if she has a longer story that 2 minutes, then shen can freely do it"): a
    # vertical video over 3:00 builds; YouTube files it as a regular video instead of a Short.
    # music plan now, because a track switch adds a breath of silence to the scene before it
    tracks, switches = _music_plan(package.get("mood") or "", durs, form)
    for k in switches:
        durs[k] += SWITCH_BREATH_S
    # 2. pictures (GPU, flag-owned)
    drawn = [_picture_text(s) for s in scenes if not _is_self(s) and not _plant(s) and not _is_card(s)]
    made = iter(await _render_stills(drawn, reel_id, log, fmt) if drawn else [])
    plant_jobs = [(_plant(s), (_picture_text(s) or f"Botanical nature photograph of {_plant(s)}").strip(),
                   _plant_portrait(s))
                  for s in scenes if _plant(s) and not _is_self(s) and not _is_card(s)]
    plants = iter(await _plant_stills(plant_jobs, form, log) if plant_jobs else [])
    photo_credits = []
    stills = []
    last_outfit = ""
    # ONE LOOK FOR THE WHOLE VIDEO (2026-10-08, Bloodroot: parts 7 and 13 had no shot, fell to her library picture
    # in the green dress while part 1 wore rust-red linen -- Barry: "her clothes were changing too much"). An
    # on-camera part with no shot of its own is drawn from her FIRST shot in this video (her own words, carried).
    first_shot = next((" ".join(str(s.get("shot") or "").split()) for s in scenes if _is_self(s) and s.get("shot")), "")
    kinds = []                                     # per part: self / photo (real species photo) / plant / drawn / card
    for i, s in enumerate(scenes):
        if _is_card(s):                            # 2026-10-17: map card, rendered on CPU (Hyperframes), no GPU
            still, card_mp4 = await asyncio.to_thread(_card_scene, s, durs[i], fmt, d, i, log)
            s["_card_mp4"] = card_mp4
            stills.append(still)
            kinds.append("card")
        elif _is_self(s):
            if not s.get("shot") and first_shot:
                s["shot"] = first_shot
            mine = (await _her_still(agent, s, form, d, len(stills), log, last_outfit=last_outfit)
                    if s.get("shot") else None)
            last_outfit = _outfit_of(s.get("shot") or "") or last_outfit
            stills.append(mine or _self_picture(agent, form, take=True))   # her directed shot, else her library
            kinds.append("self")
        elif _plant(s):
            path, credit = next(plants)
            stills.append(path)
            painted = os.path.abspath(path).lower().startswith(os.path.abspath(config.COMFY_OUTPUT_DIR).lower())
            kinds.append("plant" if painted else "photo")      # Barry's photos can carry no credit: judged by origin
            if credit and credit not in photo_credits:
                photo_credits.append(credit)
        else:
            stills.append(next(made))
            kinds.append("drawn")
    # 2b. STORYBOARD (2026-10-10, Barry: "do 1"). Wolf's Blood: her proofread failed her own finished video (the wrong
    # flower in her hand, a hat on her shoulder, the wrong plant in 5 of 10 frames) and it shipped anyway -- the check
    # came after the card time. Now she looks at the stills BEFORE anything moves; a part she writes again is drawn
    # once more from her new words. Real species photos stay.
    if storyboard:
        stills, more = await _storyboard_pass(storyboard, agent, scenes, stills, kinds, form, d, reel_id, fmt, log)
        photo_credits += [c for c in more if c not in photo_credits]
    for s in scenes:                               # plant photos used as references in her own shots
        c = s.pop("_photo_credit", "")
        if c and c not in photo_credits:
            photo_credits.append(c)
    # 3. scene clips: real video where the part needs life (her always; others with "motion"), else the still zooms
    talking: set = set()
    vids = (await _animate(stills, scenes, d, form, log, talking=talking) if package.get("motion")
            else [None] * len(stills))
    clips = []
    for i, (img, sec) in enumerate(zip(stills, durs)):
        out = os.path.join(d, f"c{i:03d}.mp4")
        if _is_card(scenes[i]):
            _card_scene_clip(scenes[i].get("_card_mp4"), img, sec, i, out, fmt)
        elif vids[i] and i in talking:
            _talk_scene_clip(vids[i], sec, out, fmt)
        elif vids[i]:
            _motion_scene_clip(vids[i], sec, out, fmt, clip_s=_clip_seconds(scenes[i]))
        else:
            _scene_clip(img, sec, i, out, fmt, self_shot=_is_self(scenes[i]))
        if scenes[i].get("fx"):                    # 2026-10-19: her effects (fx.py, CPU) over the finished clip
            import fx as _fx
            _fx.apply(out, scenes[i]["fx"], sec, fmt, d, i, log, sigil=scenes[i].get("sigil"),
                      sigil_at=scenes[i].get("sigil_at") or "center")
        clips.append(out)
    with open(os.path.join(d, "clips.txt"), "w") as fh:
        fh.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    _run(["-f", "concat", "-safe", "0", "-i", os.path.join(d, "clips.txt"), "-c", "copy", os.path.join(d, "video.mp4")])
    # 4. voice track: each scene's line + its pause, back to back
    parts = []
    for i, sec in enumerate(durs):
        padded = os.path.join(d, f"p{i:03d}.wav")
        _run(["-i", os.path.join(d, f"v{i:03d}.wav"), "-af", f"apad=whole_dur={sec:.3f}", "-ar", "48000", "-ac", "1", padded])
        parts.append(padded)
    with open(os.path.join(d, "voice.txt"), "w") as fh:
        fh.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
    voice = os.path.join(d, "voice.wav")
    _run(["-f", "concat", "-safe", "0", "-i", os.path.join(d, "voice.txt"), "-c", "copy", voice])
    # 5. NO CAPTIONS (Barry 2026-10-06: "no texts" -> "captions"): nothing is burned into the picture.
    # 6. mix music under the voice (ducked), final encode
    total = sum(durs)
    music = None
    if tracks:
        ends = [sum(durs[:k + 1]) for k in switches]
        music = os.path.join(d, "music_bed.wav")
        _music_bed(tracks, [e - 0.6 for e in ends], total, music)   # crossfade centred just after her line ends
    out = os.path.join(d, f"{reel_id}.mp4")
    sub = _plant_labels(scenes, durs, fmt)           # no captions (Barry 2026-10-06); plant names only
    final_mix(d, os.path.join(d, "video.mp4"), voice, music, sub, total, out)
    thumb = os.path.join(d, "thumbnail.jpg")
    _run(["-i", out, "-ss", "0.5", "-frames:v", "1", thumb])
    caption = package.get("caption") or ""
    credit = "\n".join(x for x in [_music_credit(tracks), *photo_credits] if x)
    if credit:                      # CC BY 4.0 requires it where viewers can find it -- the post description
        caption = (caption.rstrip() + "\n\n" + credit).strip()
    meta = {"ok": True, "reel_id": reel_id, "video": out, "thumbnail": thumb, "seconds": round(total, 1),
            "scenes": len(scenes), "format": form, "music": [os.path.basename(t) for t in tracks],
            "music_switch_after_scenes": switches,
            "music_credit": credit, "build_seconds": round(time.time() - t_all), "title": package.get("title"),
            "caption": caption, "hashtags": package.get("hashtags")}
    with open(os.path.join(d, "reel.json"), "w", encoding="utf-8") as fh:
        json.dump({"package": package, "result": meta}, fh, indent=1, ensure_ascii=False)
    for f in (glob.glob(os.path.join(d, "c[0-9][0-9][0-9].mp4")) + glob.glob(os.path.join(d, "[vp][0-9][0-9][0-9].wav"))
              + glob.glob(os.path.join(d, "talk[0-9][0-9][0-9]*"))):
        try:
            os.remove(f)
        except OSError:
            pass
    return meta
