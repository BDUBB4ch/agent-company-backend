"""Vivian's product spots (2026-10-17, Barry: plan step 3 -- "make sure my agents have the skills and the tools to use
these"). A 10-30 s product video for the store: the REAL product photo (from the store's own listing), the name, three
bullets Vivian writes from read_product, the live price, the site -- on the v5 look (black + green). Rendered by
Hyperframes on the CPU (reel_builder._card_render: headless Edge, offline env), lands on his DESK; he posts.
Nothing publishes. Crop-neutral copy is Vivian's job (her skill making-product-videos.md); the price is the store's.
"""
from __future__ import annotations

import asyncio
import datetime
import html as _html
import json
import os
import re
import shutil

import httpx

import agent_files
import reel_builder
import store

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "data", "product_videos")
SITE = "bdubbgrowsllc.com"
FORMATS = {"vertical": (1080, 1920), "square": (1080, 1080), "wide": (1920, 1080)}

PRODUCT_VIDEO_TOOL = {
    "type": "function",
    "function": {
        "name": "product_video",
        "description": (
            "Make a 10-30 second PRODUCT SPOT for the store: the real product photo, its name, your three bullets, "
            "the live price and the site, on the brand look (black + green). Rendered locally in about a minute; the "
            "MP4 (phone-safe) plus a silent email GIF and a poster frame land on Barry's DESK for him to post. Read the "
            "product first (read_product / look_at_product_photo) so every bullet is true to the listing. Crop-neutral "
            "wording: it may run as an ad. In an email use the GIF linked to the video -- mail apps do not play MP4."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product name or SKU, as in the store."},
                "headline": {"type": "string", "description": "One short line under the name (3-8 words). Optional."},
                "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                            "description": "Three benefits, 3-9 words each, true to the listing."},
                "format": {"type": "string", "enum": ["vertical", "square", "wide"],
                           "description": "vertical = TikTok/Shorts/Reels (default), square = Facebook feed, wide = YouTube."},
                "seconds": {"type": "integer", "minimum": 10, "maximum": 30, "description": "Length. Default 15; grows to fit your voice line."},
                "mood": {"type": "string", "enum": ["upbeat", "calm", "mystic", "spooky"],
                         "description": "The music bed. Default upbeat."},
                "voice": {"type": "boolean", "description": "You read the name, headline, bullets and price over it (default true)."},
            },
            "required": ["product", "bullets"],
        },
    },
}


def _clean(s, n: int = 120) -> str:
    return " ".join(str(s or "").split())[:n]


def _price_text(p: dict) -> str:
    price = p.get("price") or p.get("regular_price") or ""
    return f"${float(price):,.2f}" if re.fullmatch(r"\d+(\.\d+)?", str(price)) else _clean(price, 20)


MOODS = ("upbeat", "calm", "mystic", "spooky")


def _sound(d: str, silent_mp4: str, out_mp4: str, seconds: float, voice_wav: str | None, music: str | None) -> bool:
    """Voice (Vivian, Kokoro on the CPU) + a music bed from the office library under the picture, the same mix the
    reels use (reel_builder.final_mix: ducked music, loudnorm -14). Returns False (and leaves no file) on failure."""
    try:
        src = voice_wav
        if not src:                                   # music only: a silent voice track to mix under
            src = os.path.join(d, "silence.wav")
            reel_builder._run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{seconds:.2f}", src])
        padded = os.path.join(d, "voice_padded.wav")
        reel_builder._run(["-i", src, "-af", f"apad=whole_dur={seconds:.3f}", "-ar", "48000", "-ac", "1", padded])
        reel_builder.final_mix(d, silent_mp4, padded, music, "null", float(seconds), out_mp4)
        return os.path.isfile(out_mp4)
    except Exception:  # noqa: BLE001
        return False


def _fetch_image(url: str, dest_dir: str) -> str | None:
    """The product photo from the store's own listing (his site). None when offline or not a picture."""
    if not url or not url.lower().startswith("http"):
        return None
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            return None
        ext = ".png" if "png" in r.headers["content-type"] else ".webp" if "webp" in r.headers["content-type"] else ".jpg"
        path = os.path.join(dest_dir, "product" + ext)
        with open(path, "wb") as fh:
            fh.write(r.content)
        return path
    except Exception:  # noqa: BLE001
        return None


def _project(d: str, p: dict, a: dict, w: int, h: int, seconds: float, img: str | None) -> str:
    proj = os.path.join(d, "spot")
    os.makedirs(proj, exist_ok=True)
    shutil.copytree(os.path.join(reel_builder.CARDS_DIR, "vendor"), os.path.join(proj, "vendor"), dirs_exist_ok=True)
    rel = ""
    if img:
        rel = "product" + os.path.splitext(img)[1]
        shutil.copy2(img, os.path.join(proj, rel))
    price_txt = _price_text(p)
    tall = h > w
    name = _clean(p.get("name"), 80)
    name_px = (84 if len(name) <= 24 else 68 if len(name) <= 40 else 54) if tall else (72 if len(name) <= 24 else 58 if len(name) <= 40 else 46)
    bullets = [_clean(b, 70) for b in (a.get("bullets") or [])][:3] + ["", "", ""]
    page = (open(os.path.join(reel_builder.CARDS_DIR, "product_hero.html"), encoding="utf-8").read()
            .replace("{{W}}", str(w)).replace("{{H}}", str(h)).replace("{{SECONDS}}", f"{seconds:.2f}")
            .replace("{{NAME_PX}}", str(name_px)).replace("{{BULLET_PX}}", "44" if tall else "36")
            # phone safe zones on a vertical canvas: right 16% and bottom 28% stay clear of the app's buttons/captions
            .replace("{{SAFE_RIGHT}}", "16" if tall else "7").replace("{{SAFE_BOTTOM_BULLETS}}", "37" if tall else "22")
            .replace("{{SAFE_BOTTOM_PRICE}}", "31" if tall else "11")
            # tall: name 6-20 %, photo 23-51 %, bullets ~53-63 %, price 65-69 %, site 69-72 %, bottom 28 % empty
            .replace("{{SHOT_TOP}}", "37" if tall else "44").replace("{{SHOT_H}}", "28" if tall else "52")
            .replace("{{NAME}}", _html.escape(name)).replace("{{HEADLINE}}", _html.escape(_clean(a.get("headline"), 60)))
            .replace("{{B1}}", _html.escape(bullets[0])).replace("{{B2}}", _html.escape(bullets[1]))
            .replace("{{B3}}", _html.escape(bullets[2])).replace("{{PRICE}}", _html.escape(price_txt))
            .replace("{{SITE}}", SITE).replace("{{IMG}}", rel))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(proj, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"id": "spot", "name": name}, fh)
    return proj


def _ffmpeg() -> str:
    return os.path.join(_ROOT, "tools", "hyperframes", "bin", "ffmpeg.exe")


def _email_assets(mp4: str, d: str, seconds: float, tall: bool) -> tuple[str | None, str | None]:
    """A silent GIF of the first ~6 s (phone-light: 480 px wide, 12 fps, 128 colours, under ~2.5 MB) and a poster PNG.
    Never raises; None for whatever did not get made."""
    import subprocess
    base = os.path.splitext(mp4)[0]
    gif, poster = base + "-email.gif", base + "-poster.png"
    out_gif, out_poster = None, None
    try:
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{min(9.0, max(0.0, seconds - 1)):.1f}", "-i", mp4,
                        "-frames:v", "1", poster], check=True, timeout=60, capture_output=True)
        out_poster = poster if os.path.isfile(poster) else None
    except Exception:  # noqa: BLE001
        pass
    for width, fps in ((480, 12), (400, 10), (320, 8)):
        try:
            vf = (f"fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];"
                  f"[b][p]paletteuse=dither=bayer:bayer_scale=3")
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-t", f"{min(6.0, seconds):.1f}", "-i", mp4,
                            "-filter_complex", vf, "-loop", "0", gif], check=True, timeout=180, capture_output=True)
            if os.path.isfile(gif) and os.path.getsize(gif) <= 2_600_000:
                out_gif = gif
                break
        except Exception:  # noqa: BLE001
            continue
    if out_gif is None and os.path.isfile(gif):
        out_gif = gif                                 # bigger than we like, still better than nothing; she is told
    return out_gif, out_poster


def _plan(a: dict) -> dict:
    """Everything before the voice: the product, the bullets, the folder, the words she will say. {"error"} or a plan."""
    bullets = [b for b in (a.get("bullets") or []) if _clean(b)]
    if len(bullets) < 3:
        return {"error": "Give three bullets (3-9 words each), true to the listing."}
    query = _clean(a.get("product"), 80)
    if not query:
        return {"error": "Which product? Give its name or SKU as in the store."}
    try:
        hits = store._search_products(query)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"The store did not answer ({type(exc).__name__}: {exc}). Try again, or tell Barry."}
    if not hits:
        return {"error": f"No published product matches '{query}'. Use lookup_product to find the exact name."}
    p = hits[0]
    fmt = a.get("format") if a.get("format") in FORMATS else "vertical"
    try:
        seconds = max(10, min(30, int(a.get("seconds") or 15)))
    except (TypeError, ValueError):
        seconds = 15
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(OUT_DIR, stamp)
    os.makedirs(d, exist_ok=True)
    spoken = ". ".join(x for x in [_clean(p.get("name"), 80), _clean(a.get("headline"), 60),
                                   *[_clean(b, 70) for b in bullets[:3]], f"{_price_text(p)} at B Dubb Grows"] if x) + "."
    return {"p": p, "bullets": bullets, "fmt": fmt, "seconds": seconds, "d": d, "stamp": stamp,
            "spoken": reel_builder._say("creative", spoken), "voice_on": a.get("voice") is not False}


def _kokoro_voice(plan: dict, log_lines: list[str]) -> tuple[str | None, float]:
    """The CPU fallback voice (Kokoro, bf_isabella) -- used when the card is busy or the locked voice fails."""
    try:
        wav = os.path.join(plan["d"], "voice.wav")
        return wav, reel_builder._tts("creative", plan["spoken"], wav)
    except Exception as exc:  # noqa: BLE001
        log_lines.append(f"voice skipped ({type(exc).__name__}: {exc})")
        return None, 0.0


def _make(office_name: str, a: dict, plan: dict, voice_wav: str | None, vo_s: float, log_lines: list[str],
          voice_how: str) -> dict:
    p, bullets, fmt, seconds, d = plan["p"], plan["bullets"], plan["fmt"], plan["seconds"], plan["d"]
    w, h = FORMATS[fmt]
    imgs = p.get("images") or []
    img = _fetch_image((imgs[0] or {}).get("src", "") if imgs else "", d)
    # SOUND (Barry 2026-10-17: "with sound if possible whenever possible"): Vivian reads the name, headline, bullets
    # and price -- her LOCKED voice (VoxCPM2, V1, Barry's pick 2026-10-17) on the card when it is free, Kokoro on the
    # CPU otherwise -- over a music bed from data/music (Kevin MacLeod, CC BY -- credit returned). A GIF has no sound
    # by nature; the MP4 carries it. The spot grows to fit the voice (cap 30 s).
    mood = a.get("mood") if a.get("mood") in MOODS else "upbeat"
    if voice_wav and vo_s + 1.5 > seconds:
        seconds = int(min(30, -(-(vo_s + 1.5) // 1)))
    music = reel_builder._music_for(mood)
    stem = re.sub(r'[^A-Za-z0-9]+', '-', _clean(p.get('name'), 40)).strip('-') or 'product'
    silent = os.path.join(d, f"{stem}-{fmt}-silent.mp4")
    mp4 = os.path.join(d, f"{stem}-{fmt}.mp4")
    ok = reel_builder._card_render(_project(d, p, a, w, h, float(seconds), img), silent, log_lines.append)
    if not ok:
        return {"error": "The spot did not render: " + " | ".join(log_lines)[-400:],
                "tell_barry": "Say the render failed and that Sophie should run hyperframes doctor; do not describe a video."}
    has_sound = _sound(d, silent, mp4, float(seconds), voice_wav, music)
    if not has_sound:
        shutil.copy2(silent, mp4)
        log_lines.append("sound mix failed; the spot is silent")
    reg = agent_files.register_file(office_name, mp4,
                                    f"Product spot ({fmt}, {seconds}s): {_clean(p.get('name'), 80)} -- "
                                    f"bullets: {' / '.join(_clean(b, 70) for b in bullets[:3])}")
    # FOR EMAILS (Barry 2026-10-17: "make sure it plays in emails"): mail apps do not play MP4. What plays everywhere,
    # phones included, is a silent GIF of the first seconds, linking to the full video; and a poster frame for a
    # video block / a play-button image. Both made here and put on the DESK next to the MP4.
    gif, poster = _email_assets(mp4, d, float(seconds), tall=h > w)
    if gif:
        agent_files.register_file(office_name, gif, f"Email GIF of the spot (silent, first seconds): {_clean(p.get('name'), 80)}")
    if poster:
        agent_files.register_file(office_name, poster, f"Poster frame of the spot: {_clean(p.get('name'), 80)}")
    return {
        "saved": True, "video": mp4, "format": fmt, "seconds": seconds,
        "sound": {"voice": bool(voice_wav) and has_sound, "voice_seconds": round(vo_s, 1), "voice_engine": voice_how,
                  "music": os.path.basename(music) if (music and has_sound) else None,
                  "music_credit": reel_builder._music_credit(music) if (music and has_sound) else "",
                  "note": "Put the music credit in the post description (CC BY). The GIF is silent by nature."},
        "email_gif": gif, "poster": poster,
        "email_note": ("Mail apps do not play MP4: put the GIF in an image block (it autoplays, silent) and link it to the "
                       "full video on the site or YouTube; the poster is the thumbnail for a video block."
                       if gif else "GIF not made; use the poster with a link to the video."),
        "product": {"name": p.get("name"), "price": p.get("price"), "photo_used": bool(img),
                    "permalink": p.get("permalink")},
        "approval_id": reg.get("approval_id"), "download_url": reg.get("download_url"),
        "tell_barry": reg.get("tell_barry", f"The spot is on disk at {mp4}") +
                      (" The listing had no photo, so the spot shows the words on the brand look." if not img else ""),
        "not_done": "Nothing is posted. Barry downloads it from the DESK and posts it himself.",
    }


async def run(office_name: str, a: dict) -> dict:
    a = a if isinstance(a, dict) else {}
    plan = await asyncio.to_thread(_plan, a)
    if plan.get("error"):
        return plan
    log_lines: list[str] = []
    voice_wav, vo_s, how = None, 0.0, "none"
    if plan["voice_on"]:
        # HER LOCKED VOICE (2026-10-17, Barry: "V1 is Vivian. Lock it and switch her spots to it."): VoxCPM2 on the
        # card -- owns the render flag, unloads the LLMs like a reel (reel_builder._voice_locked). When a render or
        # build already holds the card, Kokoro on the CPU speaks instead and the result says so.
        import comfy_image
        voice_dir = reel_builder._locked_voice("creative")
        if voice_dir and not comfy_image.render_in_progress():
            try:
                durs = await reel_builder._voice_locked(voice_dir, [plan["spoken"]], plan["d"], "spot-" + plan["stamp"],
                                                        log_lines.append)
                wav = os.path.join(plan["d"], "v000.wav")
                if durs and os.path.isfile(wav):
                    voice_wav, vo_s, how = wav, float(durs[0]), "locked (VoxCPM2 V1)"
            except Exception as exc:  # noqa: BLE001
                log_lines.append(f"locked voice failed ({type(exc).__name__}: {exc}); Kokoro instead")
        if not voice_wav:
            voice_wav, vo_s = await asyncio.to_thread(_kokoro_voice, plan, log_lines)
            how = "kokoro (CPU fallback)" if voice_wav else "none"
    return await asyncio.to_thread(_make, office_name, a, plan, voice_wav, vo_s, log_lines, how)
