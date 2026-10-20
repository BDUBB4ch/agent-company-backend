"""
Gives the agents eyes and ears.

Until this module existed, nothing in the backend could hand a picture to a
model -- document_extract.py covered pdf/docx/xlsx/pptx and stopped there, and
llm_router.py never populated Ollama's `images` array. So an uploaded PNG was
either decoded as garbled UTF-8 or never ingested at all, and Elliot's entire
knowledge of what the Talia Crew look like was a prose description someone
typed for him. He could not check a render against canon because he had never
seen a render. That is exactly how a Vor'Shara with two eyes and flowing hair
(canon: FOUR eyes, tendrils instead of hair) sat on disk for months.

Three separate capabilities live here, deliberately layered cheapest-first so
the expensive ones stay optional:

  1. probe_media()      -- ffmpeg only, no AI. Does an audio stream exist, how
                           long is it, how loud. Deterministic and instant.
                           This alone answers "did the audio actually land".
  2. transcribe_audio() -- faster-whisper on CPU. Speech only.
  3. describe_image()   -- the vision-capable Ollama model. Costs VRAM.

The split matters because they fail independently: ffmpeg reporting healthy
levels while Whisper returns nothing is not a bug, it means the audio is real
but contains no speech -- which is what every LTX clip measured so far does
(ambient sound, no dialogue, mean levels 10-20dB under broadcast).

WHAT THIS CANNOT DO: Whisper transcribes speech and nothing else. It will
never report "door creak at 3.2s" or notice a missing engine hum. Identifying
non-speech sound needs an audio-language model (Qwen2-Audio-7B, ~8GB GPU) --
approved by the owner but not installed. probe_media() covers the "is anything
there at all" half of that gap for free.

Everything fails soft and returns a readable "[...]" string rather than
raising, matching document_extract.py's contract -- a failed extraction still
gets recorded, it just has no useful content.
"""
import base64
import json
import os
import re
import subprocess
import tempfile

import httpx

import config

# Whisper's model size is deliberately an env var, not a constant: 'small' is
# already cached on disk (0.49GB, no download) and measured 2.7x realtime on
# the i9-12900K, while 'large-v3' is a ~3GB pull that runs near 1x realtime.
# Swapping is a one-line change with no rework, so the build proves itself on
# 'small' and upgrades when the owner's bandwidth is free.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "12"))

# Every LTX clip measured so far sits at mean -28 to -38 dBFS. Broadcast
# dialogue sits nearer -18. That is a systematic pipeline issue rather than a
# per-clip accident, so it is worth flagging on every probe instead of making
# the owner notice it himself five clips later.
QUIET_MEAN_DBFS = -24.0

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
VIDEO_EXTS = {"mp4", "mov", "mkv", "webm", "avi", "m4v"}
AUDIO_EXTS = {"wav", "mp3", "m4a", "flac", "ogg", "aac"}

# Each frame is a separate vision call (~2-5s warm), so an uncapped sample on a
# 15s clip would quietly cost a minute. Four frames covers a short LTX shot;
# raise deliberately, not by accident.
DEFAULT_FRAME_SAMPLES = 4

_whisper_model = None


def _ffmpeg() -> str:
    """The ffmpeg binary bundled into the venv by imageio-ffmpeg. Deliberately
    not a PATH lookup -- there is no system ffmpeg on this machine, and the
    project folder has to stay portable (see CLAUDE.md's hard constraints)."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run_ffmpeg(args: list[str]) -> str:
    """ffmpeg writes its stream/filter reports to stderr, including when the
    command 'fails' because no output file was requested (-f null). stderr is
    the payload here, not an error channel."""
    proc = subprocess.run([_ffmpeg(), *args], capture_output=True, text=True)
    return proc.stderr or ""


# --------------------------------------------------------------------------
# Layer 1: ffmpeg only. No AI, no VRAM, no model load.
# --------------------------------------------------------------------------

def probe_media(path: str) -> dict:
    """Streams, duration and loudness. This is the cheap half of "how will they
    know the sound is there" -- it answers existence and level deterministically,
    with no model involved and no possibility of hallucination."""
    if not os.path.isfile(path):
        return {"ok": False, "error": f"No such file: {path}"}

    info = _run_ffmpeg(["-i", path])
    duration = None
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

    has_video = bool(re.search(r"Stream #\d+:\d+.*: Video:", info))
    has_audio = bool(re.search(r"Stream #\d+:\d+.*: Audio:", info))

    result = {
        "ok": True,
        "duration_s": duration,
        "has_video": has_video,
        "has_audio": has_audio,
        "mean_dbfs": None,
        "peak_dbfs": None,
        "notes": [],
    }

    if not has_audio:
        result["notes"].append("NO AUDIO STREAM -- this file is silent.")
        return result

    levels = _run_ffmpeg(["-i", path, "-af", "volumedetect", "-f", "null", "-"])
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", levels)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", levels)
    if mean:
        result["mean_dbfs"] = float(mean.group(1))
    if peak:
        result["peak_dbfs"] = float(peak.group(1))

    if result["mean_dbfs"] is not None and result["mean_dbfs"] < QUIET_MEAN_DBFS:
        result["notes"].append(
            f"QUIET: mean {result['mean_dbfs']:.1f} dBFS is well under the "
            f"~-18 dBFS of normal dialogue. Audio is present but faint -- it "
            f"likely needs a normalisation pass before it is usable."
        )
    return result


def extract_frames(path: str, count: int = DEFAULT_FRAME_SAMPLES) -> list[tuple[float, bytes]]:
    """Evenly-spaced JPEG stills as (timestamp_seconds, bytes). Even spacing
    rather than scene-change detection on purpose: an LTX clip is a single
    continuous shot, so scene detection would return exactly one frame and
    miss the motion that the whole sample is meant to cover."""
    meta = probe_media(path)
    duration = meta.get("duration_s") or 0
    if not meta.get("ok") or not meta.get("has_video") or duration <= 0:
        return []

    frames = []
    for i in range(count):
        # Sample inside the clip rather than at its edges -- the first and last
        # frames of a generated clip are frequently the weakest.
        ts = duration * (i + 0.5) / count
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "f.jpg")
            subprocess.run(
                [_ffmpeg(), "-y", "-ss", f"{ts:.3f}", "-i", path,
                 "-frames:v", "1", "-q:v", "3", out],
                capture_output=True,
            )
            if os.path.isfile(out):
                with open(out, "rb") as fh:
                    frames.append((ts, fh.read()))
    return frames


# --------------------------------------------------------------------------
# Layer 2: Whisper on CPU. Speech only. Zero VRAM -- never contends with the
# GPU, which is the whole reason it is allowed to be the biggest model that
# fits rather than a compromise pick.
# --------------------------------------------------------------------------

def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE, device="cpu", compute_type="int8",
            cpu_threads=WHISPER_THREADS,
        )
    return _whisper_model


def transcribe_audio(path: str) -> dict:
    """Speech with word-level timing, so an agent can say "the line lands at
    00:03.4" rather than just quoting it.

    vad_filter is ON deliberately. Without it Whisper hallucinates filler on
    silent or non-speech audio -- every LTX clip tested returned a spurious
    "You" at 48% language confidence, which is a well-known artefact and would
    read as real dialogue to an agent that trusted it."""
    try:
        model = _get_whisper()
        segments, info = model.transcribe(path, beam_size=5, vad_filter=True)
        segments = list(segments)
    except Exception as e:
        return {"ok": False, "error": f"[Transcription failed: {e}]", "segments": []}

    return {
        "ok": True,
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "duration_s": info.duration,
        "segments": [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments
        ],
        "text": " ".join(s.text.strip() for s in segments),
    }


def _audio_track(path: str) -> str | None:
    """16kHz mono WAV in a temp file -- what Whisper wants. Returns None when
    the file has no audio at all, so callers can tell "silent" apart from
    "transcription broke"."""
    if not probe_media(path).get("has_audio"):
        return None
    fd, wav = tempfile.mkstemp(suffix=".wav", dir=config.DATA_DIR)
    os.close(fd)
    subprocess.run(
        [_ffmpeg(), "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav],
        capture_output=True,
    )
    return wav if os.path.getsize(wav) > 0 else None


# --------------------------------------------------------------------------
# Layer 3: vision. Costs VRAM, so it goes last.
# --------------------------------------------------------------------------

def vision_model_available(model: str | None = None) -> bool:
    """Whether the model actually declares vision. Checked live rather than
    assumed from the name: qwen3.5-abliterated:9b reports vision, but the two
    14b models (Marcus/Amara's reasoning model and Sophie's coder) do not, and
    abliteration can strip capabilities the name still implies."""
    model = model or config.OLLAMA_MODEL
    try:
        r = httpx.post(f"{config.OLLAMA_HOST}/api/show", json={"model": model}, timeout=30)
        r.raise_for_status()
        return "vision" in set(r.json().get("capabilities", []))
    except Exception:
        return False


def describe_image(data: bytes, question: str | None = None,
                   model: str | None = None, timeout: float = 300.0) -> str:
    """Hand raw image bytes to the vision model and get back what is actually
    in the picture.

    think is forced off: a reasoning pass on a description task roughly triples
    latency and the reasoning is not used for anything here."""
    model = model or config.OLLAMA_MODEL
    prompt = question or (
        "Describe exactly what you see in this image. Be literal and specific "
        "about people, count, anatomy, clothing, colours, setting and framing. "
        "Do not interpret, flatter, or invent -- report only what is visibly there."
    )
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [base64.b64encode(data).decode()],
        }],
        "stream": False,
        "think": False,
        # THE 9b MUST NOT SIT ON THE CARD AFTERWARDS (Barry, 2026-09-18: "9b
        # should not even be stil here" / "bonsai only, unless she fell back
        # to 9b").
        #
        # Measured live during a social post: Vivian called
        # look_at_product_photo, Ollama loaded the vision model with its
        # DEFAULT 5-minute keep_alive, and Bonsai -- already running -- went
        # from 44.45 tok/s to 7.78 for the rest of her turn and everyone
        # else's. Two models on a 16GB card is the documented spill, and the
        # existing eviction chain never fires here because it runs BEFORE a
        # generation, not after a tool call, and Bonsai was already up.
        #
        # keep_alive 0 makes the vision model unload the moment it answers.
        # The cost is a ~6s cold load per describe; the alternative is the
        # whole office at a sixth speed for five minutes. Vision is a one-shot
        # description, so there is no warm-cache benefit to trade away.
        "keep_alive": 0,
        "options": {"num_ctx": 8192},
    }
    try:
        r = httpx.post(f"{config.OLLAMA_HOST}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()
    except Exception as e:
        return f"[Could not describe image: {e}]"


# --------------------------------------------------------------------------
# An agent looking at its OWN reference pictures.
# --------------------------------------------------------------------------
#
# Barry, 2026-08-31: "Amara needs to be able to look at the pictures to see
# herself."
#
# Until now an agent's knowledge of its own face and body was a caption
# somebody else wrote and stored as a fact -- and captions drift. Amara's said
# "tall and slender" and "light brown eyebrows" when the actual picture shows
# a curvy athletic figure and thick dark brows, so she described herself wrong
# and rendered herself wrong. This lets her open the real pixels instead.
#
# Two rules this deliberately keeps:
#   * NEUTRAL CAPTION RELAY. The vision model is only ever asked to describe
#     faithfully; the agent then reasons over the description. Handing an image
#     to the chat model alongside a leading question was measured making it
#     suggestible (it answered "four eyes" for a two-eyed render). So no
#     question from the agent is ever forwarded to the vision pass.
#   * FULL RESOLUTION. Raw file bytes, no resize -- judging a visual detail
#     from a downscaled view is the documented way to get it wrong.
#
# Purely local (Ollama vision), so offline mode does not strip it.

# Where each agent's staged reference frames live, and what each one is FOR.
_REF_SLOTS = (
    ("agent_face_{aid}.png", "your face, close up"),
    ("agent_body_{aid}.png", "your body"),
    ("agent_body_{aid}_clothed.png", "your body, dressed"),
)


def own_picture_paths(agent_id: str) -> list[tuple[str, str]]:
    """(path, what-it-is) for every reference frame staged for this agent."""
    import config
    base = os.path.join(config.COMFY_DIR, "input")
    out = []
    for pattern, label in _REF_SLOTS:
        p = os.path.join(base, pattern.format(aid=agent_id))
        if os.path.isfile(p):
            out.append((p, label))
    # FALL BACK TO THE MAIN REFERENCE (2026-09-19). The slots above are the
    # hand-cut frames the nine were given; a seat whose picture arrived through
    # `set as main` has `agent_ref_<id>.png` and may have nothing else --
    # measured on Ilnora, for whom this returned an EMPTY LIST, so she could
    # not open a single picture of herself while all nine could, and nothing
    # said so. Only when nothing else is staged: for the nine `agent_ref` is
    # the same pixels as a slot above (Amara's is byte-identical to her nude
    # body frame), and every extra frame here costs a real vision pass.
    if not out:
        p = os.path.join(base, "agent_ref_%s.png" % agent_id)
        if os.path.isfile(p):
            out.append((p, "you, the whole figure"))
    return out


# Barry, 2026-08-31: "she should not be saying slender" / "she should not be
# having them to pull anymore."
#
# Measured the same day: with look_at_my_pictures working, Amara opened her
# real files and still answered "slender but soft" -- because the local vision
# model captions her body as "lean and toned" and "slender" when the same
# frames plainly show wide full hips, a full bust and a full backside. The
# caption is the lossy link, not her.
#
# A note asking her not to use those words was the first attempt and it is not
# enough: a word sitting in front of the model is a word it will reach for.
# So the words are corrected out of the caption BEFORE she ever sees it --
# fixed where it fires, which is this build's standing rule after two prompt-
# level failures. His sanctioned wording goes in their place.
#
# The guard list matters: "thin straps" is a real and correct detail of her
# bra, so `thin` is only rewritten when it is describing a body.
_FIGURE_WORD_RE = re.compile(
    r"\b(slender|slim|skinny|petite|waifish|willowy|lean|thin)\b"
    r"(?!\s+(?:strap|straps|strip|strips|line|lines|layer|layers|"
    r"chain|chains|band|bands|fabric|heel|heels|frame\s+of))",
    re.I)
_FIGURE_WORD_OK_BEFORE = re.compile(r"(?i)\b(leaning|leaned|leans)\b")


def _correct_figure_words(text: str) -> str:
    """Replace under-reporting body adjectives with Barry's own ruling."""
    if not text:
        return text
    # "lean forward / leaning against" are postures, not builds -- leave them.
    def _sub(m):
        word = m.group(1)
        tail = text[m.end():m.end() + 12].lower()
        if word.lower() == "lean" and tail.strip().startswith(("forward", "against", "over", "in ", "back")):
            return word
        return "athletic but soft"
    out = _FIGURE_WORD_RE.sub(_sub, text)
    # Two offenders side by side ("slim, petite figure") would otherwise read
    # "athletic but soft, athletic but soft figure".
    out = re.sub(r"athletic but soft(?:\s*(?:,|and)?\s*athletic but soft)+",
                 "athletic but soft", out, flags=re.I)
    return re.sub(r"\ba(?= athletic but soft)", "an", out)


def look_at_own_pictures(agent_id: str, model: str | None = None) -> dict:
    """Open this agent's own reference pictures and report what is in them."""
    paths = own_picture_paths(agent_id)
    if not paths:
        return {"looked": False,
                "error": "There are no reference pictures staged for you yet."}
    if not vision_model_available(model):
        return {"looked": False,
                "error": ("The active model cannot see images, so the pictures "
                          "could not be opened.")}
    seen = []
    for path, label in paths:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except Exception as exc:            # unreadable file must not kill the turn
            seen.append({"picture": label, "error": str(exc)})
            continue
        seen.append({"picture": label,
                     "what_is_in_it": _correct_figure_words(
                         describe_image(data, model=model))})
    return {
        "looked": True,
        "_pixels": [p for p, _ in paths],
        "pictures": seen,
        "note": (
            "This is what is actually in your reference pictures, read off the "
            "real files at full size. For FEATURES -- your face, brows, "
            "freckles, hair, skin, eyes, what you have on -- the pictures are "
            "right, and if a written description of you disagrees, say so "
            "instead of repeating the written one.\n\n"
            "ON BODY SHAPE the authority is Barry's own ruling: athletic but "
            "soft, nice sized breasts, and the plump part is the butt -- only "
            "the butt. Never describe yourself as slender, slim, lean or thin; "
            "those words are wrong about you and he has said so directly."),
    }


# --------------------------------------------------------------------------
# VIVIAN'S EYES (2026-09-10, "now do Vivian, everything she needs").
#
# She art-directs product shots for a catalogue whose 119 real product photos
# have been on disk since 2026-08-21 and which she could not open. So she was
# writing prompts for products she had never seen, and grading her own renders
# from the prompt she had written rather than from the pixels -- the exact
# thumbnail/caption failure this build has paid for three times.
#
# Two read-only lookups, both local Ollama vision calls, so NOT stripped by
# offline mode. Same neutral caption relay as look_at_my_pictures: her question
# is never forwarded to the vision pass (a leading question makes the 9b
# suggestible -- measured 2026-08-03).
# --------------------------------------------------------------------------

_PRODUCT_IMAGE_DIR = os.path.join(config.DATA_DIR, "product-images")
_PRODUCT_INDEX = os.path.join(_PRODUCT_IMAGE_DIR, "_index.json")


def _product_index() -> list[dict]:
    try:
        with open(_PRODUCT_INDEX, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:      # missing/corrupt index must degrade, never raise
        return []


def _match_products(query: str, index: list[dict]) -> list[dict]:
    """Name/SKU match, best first. Deliberately dumb and predictable: exact
    substring, then all-words, then any-word -- an agent that gets a surprising
    product back cannot tell that it got the wrong one."""
    q = (query or "").strip().lower()
    if not q:
        return []
    words = [w for w in re.split(r"\W+", q) if len(w) > 2]
    exact, allw, anyw = [], [], []
    for row in index:
        hay = f"{row.get('name', '')} {row.get('sku', '')}".lower()
        if q in hay:
            exact.append(row)
        elif words and all(w in hay for w in words):
            allw.append(row)
        elif any(w in hay for w in words):
            anyw.append(row)
    return exact + allw + anyw


def look_at_product_photo(query: str, model: str | None = None) -> dict:
    """Open the REAL photo of a real store product and report what is in it."""
    index = _product_index()
    if not index:
        return {"looked": False,
                "error": ("The product photo library is not on disk. Use "
                          "read_product for the words, and tell Barry the "
                          "photos are missing.")}
    hits = _match_products(query, index)
    if not hits:
        return {"looked": False,
                "error": f"No product photo matches {query!r}.",
                "hint": "Try the product name as it reads on the store, or its SKU."}
    if not vision_model_available(model):
        return {"looked": False,
                "error": "The active model cannot see images, so the photo could not be opened."}
    row = hits[0]
    path = os.path.join(_PRODUCT_IMAGE_DIR, row.get("file", ""))
    if not os.path.isfile(path):
        return {"looked": False,
                "error": f"The index lists {row.get('file')!r} but that file is not on disk."}
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except Exception as exc:                       # noqa: BLE001
        return {"looked": False, "error": f"Could not open the photo: {exc}"}
    out = {
        "looked": True,
        "product": row.get("name"),
        "sku": row.get("sku") or None,
        "price": row.get("price") or None,
        "link": row.get("permalink"),
        "photo_file": row.get("file"),
        "_pixels": [path],
        "what_is_in_it": describe_image(data, model=model),
        "label_text_read_exactly": __import__("ocr").read_image(data) or None,
        "note": ("This is the REAL product photo off the live store, read at "
                 "full size. It is the truth about what this product looks "
                 "like -- shape, cap, colour, label layout. Build the shot "
                 "from this, never from memory, and never invent packaging, "
                 "label text or a logo that is not described here. A render "
                 "makes a product-LIKE object, so anything a customer will "
                 "read as THE product comes from this photo or is composited "
                 "onto the render afterwards."),
    }
    if len(hits) > 1:
        out["other_matches"] = [h.get("name") for h in hits[1:6]]
    return out


def _recent_renders(agent_id: str, limit: int = 12) -> list[dict]:
    """The agent's own finished renders, newest first, straight from the
    approval rows -- the only place a render's file path is recorded."""
    import memory
    rows = []
    with memory.get_db() as conn:
        for r in conn.execute(
                "SELECT id, action_type, file_path, status, created_at "
                "FROM approvals WHERE agent_id=? AND file_path IS NOT NULL "
                "AND file_path != '' ORDER BY id DESC LIMIT ?", (agent_id, limit * 3)):
            path = r["file_path"] or ""
            if path.rsplit(".", 1)[-1].lower() in IMAGE_EXTS and os.path.isfile(path):
                rows.append({"id": r["id"], "path": path, "status": r["status"],
                             "when": r["created_at"]})
            if len(rows) >= limit:
                break
    return rows


def look_at_render(agent_id: str, which: str | None = None,
                   model: str | None = None) -> dict:
    """Open one of this agent's own renders and report what is actually in it."""
    renders = _recent_renders(agent_id)
    if not renders:
        return {"looked": False,
                "error": "You have no rendered images on disk yet."}
    pick = renders[0]
    want = (which or "").strip()
    if want:
        digits = re.findall(r"\d+", want)
        if digits:
            wanted_id = int(digits[-1])
            match = next((r for r in renders if r["id"] == wanted_id), None)
            if not match:
                return {"looked": False,
                        "error": f"No render of yours has approval id {wanted_id}.",
                        "your_recent_renders": [
                            {"id": r["id"], "when": r["when"]} for r in renders]}
            pick = match
    if not vision_model_available(model):
        return {"looked": False,
                "error": "The active model cannot see images, so the render could not be opened."}
    try:
        with open(pick["path"], "rb") as fh:
            data = fh.read()
    except Exception as exc:                       # noqa: BLE001
        return {"looked": False, "error": f"Could not open the render: {exc}"}
    return {
        "looked": True,
        "render_id": pick["id"],
        "_pixels": [pick["path"]],
        "made": pick["when"],
        "status": pick["status"],
        "file": os.path.basename(pick["path"]),
        "what_is_in_it": describe_image(data, model=model),
        "text_in_it_read_exactly": __import__("ocr").read_image(data) or None,
        "note": ("This is what is really in the render, read off the file at "
                 "full size -- not what the prompt asked for. Check it against "
                 "the brief and the real product photo: count hands and "
                 "fingers, look for text or gibberish lettering, check the "
                 "product shape and label colours, check the crop for where it "
                 "is going. The caption misses small things, so if something "
                 "matters and the caption is silent, say it was not verified "
                 "rather than calling the render clean."),
        "your_recent_renders": [{"id": r["id"], "when": r["when"]} for r in renders[:6]],
    }


# --------------------------------------------------------------------------
# Orchestration -- what upload/chat paths actually call.
# --------------------------------------------------------------------------

def _text_block(data: bytes) -> str:
    """The exact text in an image (ocr.py, CPU), as a section to append -- or "" when there is none."""
    import ocr
    txt = ocr.read_image(data)
    return f"\nText in the image (read exactly, line by line):\n{txt}" if txt else ""


def understand_image(data: bytes, filename: str = "image") -> str:
    """One image -> text a brain fact can hold: what it SHOWS (vision model) + the exact TEXT in it
    (ocr.py, 2026-09-24). Seeing and reading fail independently -- one missing never hides the other."""
    text = _text_block(data)
    if not vision_model_available():
        return (f"--- Image: {filename} ---\n[The active model cannot see images, so what it shows "
                f"was not described.]{text}")
    desc = describe_image(data)
    return f"--- Image: {filename} ---\n{desc}{text}"


def understand_video(path: str, filename: str | None = None,
                     frame_count: int = DEFAULT_FRAME_SAMPLES) -> str:
    """A video -> a timeline document: what is on screen at which timestamp,
    whether audio exists and at what level, and any speech with timings.

    Assembled as text on purpose. It flows into exactly the same brain fact
    that a dropped .docx does, so nothing downstream needs to learn a new
    shape -- and an agent can read a timeline the same way it reads a script."""
    filename = filename or os.path.basename(path)
    meta = probe_media(path)
    if not meta.get("ok"):
        return f"[Could not read video '{filename}': {meta.get('error')}]"

    lines = [f"--- Video: {filename} ---"]
    dur = meta.get("duration_s")
    lines.append(f"Duration: {dur:.2f}s" if dur else "Duration: unknown")

    # Audio report first: it is free, deterministic, and the most common
    # failure (silent or far-too-quiet output) shows up here without any model.
    if meta["has_audio"]:
        lines.append(
            f"Audio: present, mean {meta['mean_dbfs']} dBFS, peak {meta['peak_dbfs']} dBFS"
        )
    else:
        lines.append("Audio: NONE -- this clip is silent.")
    for note in meta["notes"]:
        lines.append(f"  ! {note}")

    if meta["has_audio"]:
        wav = _audio_track(path)
        if wav:
            try:
                tr = transcribe_audio(wav)
                if tr["ok"] and tr["segments"]:
                    lines.append("Speech:")
                    for s in tr["segments"]:
                        lines.append(f"  [{s['start']:.2f} -> {s['end']:.2f}] {s['text']}")
                elif tr["ok"]:
                    lines.append(
                        "Speech: none detected. The audio is real but contains no "
                        "dialogue -- ambience or effects only. Identifying WHICH "
                        "sounds are present needs an audio model, which is not "
                        "installed; this layer can only confirm the audio exists."
                    )
                else:
                    lines.append(f"Speech: {tr.get('error')}")
            finally:
                try:
                    os.remove(wav)
                except OSError:
                    pass

    if meta["has_video"]:
        if not vision_model_available():
            lines.append("Frames: not described -- the active model has no vision capability.")
        else:
            lines.append(f"Frames ({frame_count} sampled):")
            import ocr
            _last_txt = ""
            for ts, jpg in extract_frames(path, frame_count):
                desc = describe_image(jpg)
                lines.append(f"  [{ts:.2f}s] {desc}")
                _txt = " / ".join(ocr.read_image(jpg).splitlines())
                if _txt and _txt != _last_txt:            # on-screen text, only when it changes
                    lines.append(f"  [{ts:.2f}s] on-screen text: {_txt}")
                _last_txt = _txt or _last_txt

    return "\n".join(lines)


def understand_media_bytes(filename: str, data: bytes) -> str | None:
    """Entry point for the upload path. Returns None when this is not media,
    so document_extract can fall through to its existing handling unchanged."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in IMAGE_EXTS:
        return understand_image(data, filename)
    if ext in VIDEO_EXTS or ext in AUDIO_EXTS:
        # ffmpeg and Whisper both want a real path, not a buffer.
        fd, tmp = tempfile.mkstemp(suffix=f".{ext}", dir=config.DATA_DIR)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            return understand_video(tmp, filename)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return None
