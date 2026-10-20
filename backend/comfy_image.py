"""
Image generation through local ComfyUI on ROCm (tools/ComfyUI) -- replaced
AmuseBridge/TensorStack as the ONLY image engine on 2026-07-30 (owner's call:
"no send backs"). Same public contract amuse_integration had, so main.py's
/api/generate-image, the dashboard button, Regenerate, and the approval flow
all kept working unchanged through the swap:

    generate_image(prompt, negative_prompt, model) ->
        {"path", "model", "commercial_use", "licence_note", "seed"}  |  {"error"}

Process model mirrors bonsai_llm.py: the server is started on demand (first
generation pays ~25s startup, later ones don't), health-checked via
/system_stats, and its VRAM is released with POST /free before any Ollama
generation (see llm_router's unload chain) -- ComfyUI keeps the checkpoint
resident between generations by design, which is great for back-to-back
renders and fatal for a 16GB card the LLMs also live on.
"""
import asyncio
import json
import os
import random
import re
import subprocess
import time

import httpx

from config import (
    COMFY_CHECKPOINTS_DIR,
    COMFY_DEFAULT_MODEL,
    COMFY_DIR,
    COMFY_HOST,
    COMFY_OUTPUT_DIR,
    COMFY_PYTHON,
    COMFY_I2V_WORKFLOW_PATH,
    COMFY_I2V_SULPHUR_WORKFLOW_PATH,
    COMFY_VIDEO_WORKFLOW_PATH,
    COMFY_VIDEO_SULPHUR_WORKFLOW_PATH,
    COMFY_WORKFLOW_PATH,
    DATA_DIR,
)


# XXX ANATOMY LoRAs (2026-09-16, Barry: "this is not what a vagina looks like.
# i think we need a lora for this" -> "a realistic xxx lora" -> "or for LTX
# 2.5" -> "go on both"). Qwen-Image and LTX both render smooth, featureless
# genitals -- the base models' training data, and negatives are inert at
# cfg 1.0 -- so a LoRA is the only lever. Two files, one per engine, from
# Civitai (login-gated; Barry pulls them or sets CIVITAI_API_KEY in .env):
#   Unchained-XXX (built for Qwen-Image-Edit 2509, our unet; its page says
#   CFG 4, we run Lightning at cfg 1 -- test as-is first) and Excellent Full
#   Nude (native LTXV 2.5, trigger word below).
# GUARDED THREE WAYS: the file must exist on disk (nothing breaks while it is
# not there), the live setting `xxx_loras` must not be "false", and the
# prompt must actually be explicit -- Elliot's film clips and the business
# shots never carry these. Fictional adults only, his standing rule.
XXX_QWEN_LORA = "Unchained-XXX.safetensors"
XXX_LTX_LORA = "E_Full_Nude_LTX2.5_v1.safetensors"   # Civitai's exact filename
XXX_LTX_TRIGGER = "Excellent_Full_Nude"
XXX_QWEN_STRENGTH = 1.0
XXX_LTX_STRENGTH = 1.0
_XXX_PROMPT_RE = re.compile(
    r"(?i)\b(?:naked|nude|nudity|topless|bottomless|vulva|vagina|labia|pussy|"
    r"clit\w*|nipples?|areolae?|breasts?|genitals?|pubic|bare\s+(?:breasts?|"
    r"chest|ass|butt)|spread\s+(?:legs|thighs)|fingers?\s+(?:deep\s+)?inside|"
    r"masturbat\w*|orgasm\w*|sex\b|explicit|uncensored)")


def _xxx_on() -> bool:
    try:
        import memory as _mem
        return str(_mem.get_setting("xxx_loras", "true") or "").strip().lower() != "false"
    except Exception:
        return True


def _xxx_lora_ready(filename: str) -> bool:
    return os.path.isfile(os.path.join(COMFY_DIR, "models", "loras", filename))


def _prompt_is_explicit(text: str) -> bool:
    return bool(_XXX_PROMPT_RE.search(text or ""))


def _sulphur_on() -> bool:
    """Live switch for the Sulphur 2 video graphs (app_settings `video_sulphur`).
    Lazy import: memory is not otherwise a dependency of this module."""
    try:
        import memory as _mem
        return str(_mem.get_setting("video_sulphur", "false") or "").strip().lower() == "true"
    except Exception:
        return False

# LTX-2.5 since 2026-09-04 (int8-convrot distilled transformer + Gemma-4 GGUF
# encoder; see config.COMFY_VIDEO_WORKFLOW_PATH). This is the label stamped on
# approvals/traces -- the 2.3 string sat here for the first verified 2.5 render.
VIDEO_MODEL_NAME = "LTX-2.5-22b-distilled-int8"
# LTX-2 Community License: free commercial use for companies under $10M
# annual revenue -- covers both businesses today. Flagged for Marcus to
# confirm formally before real marketing publication.
_VIDEO_LICENSE_NOTE = (
    "LTX-2 Community License -- commercial use permitted under $10M annual "
    "revenue (covers B Dubb Grows + Gotcho Back; Marcus to confirm formally)."
)

_SERVER_LOG_PATH = os.path.join(DATA_DIR, "comfyui.log")
_server_proc = None

# Cross-process "a video render owns the GPU" flag (original Phase-4 design,
# built 2026-07-31): while a render runs, chat generations must NOT fire the
# VRAM unload chain (it would free ComfyUI's models mid-job). File-based so
# it works across backend restarts and standalone scripts sharing DATA_DIR.
_RENDER_FLAG = os.path.join(DATA_DIR, "video_rendering.flag")


def _set_render_flag():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_RENDER_FLAG, "w") as fh:
            fh.write(str(time.time()))
    except OSError:
        pass


def _clear_render_flag():
    try:
        os.remove(_RENDER_FLAG)
    except OSError:
        pass


# BARRY AND ELLIOT FIRST (2026-10-03, Barry: "leave ltx to me and elliot" -> "your renders and Elliot's always go
# first"). Ilnora's videos build overnight from video_queue; while one runs, data/reel_building.flag is up and her
# own calls carry REEL_ACTIVE. Any OTHER render that finds the card busy with her video does not get refused: it files
# a priority request, her builder stops before its next step (reel_builder._wait_turn), and this render starts the
# moment her current step ends (one step = up to ~15 min of LTX).
import contextvars  # noqa: E402

REEL_ACTIVE = contextvars.ContextVar("reel_active", default=False)
_REEL_MARK = os.path.join(DATA_DIR, "reel_building.flag")
_PRIORITY = os.path.join(DATA_DIR, "render_priority.request")
PRIORITY_TTL_S = 45 * 60


def reel_building() -> bool:
    return os.path.exists(_REEL_MARK)


def priority_pending() -> bool:
    try:
        return time.time() - os.path.getmtime(_PRIORITY) < PRIORITY_TTL_S
    except OSError:
        return False


def _clear_priority() -> None:
    try:
        os.remove(_PRIORITY)
    except OSError:
        pass


async def _wait_out_reel_step(kind: str, max_wait_s: int = 40 * 60) -> bool:
    """True = the card came free (her step ended); False = gave up."""
    if REEL_ACTIVE.get() or not reel_building():
        return False
    with open(_PRIORITY, "w") as fh:
        fh.write(f"{kind} {time.time()}")
    print(f"[render] {kind} waits for Ilnora's current video step to finish (priority filed)")
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        await asyncio.sleep(10)
        if not render_in_progress():
            return True
    return False


async def _mystudio_busy() -> bool:
    """Barry's MyStudio ComfyUI (port 8189) has a job running or queued -- it shares this card."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as cx:
            q = (await cx.get("http://127.0.0.1:8189/queue")).json()
        return bool(q.get("queue_running") or q.get("queue_pending"))
    except (httpx.HTTPError, ValueError):
        return False


async def reel_wait_turn(log=print) -> None:
    """Ilnora's builder, before every GPU step: wait while anyone else uses the card or has asked for it."""
    said = False
    while render_in_progress() or priority_pending() or await _mystudio_busy():
        if not said:
            log("waiting for the card -- Barry / Elliot / MyStudio go first")
            said = True
        await asyncio.sleep(30)


def _owned_start() -> None:
    """Raise the flag; a non-reel render that starts has been served, so its priority request is done."""
    _set_render_flag()
    if not REEL_ACTIVE.get():
        _clear_priority()


def _keep_awake(on: bool) -> None:
    """Hold Windows out of standby while a render runs (2026-09-04, Barry:
    "i went to bed and left you running and woke up to my pc on standby...
    it happens every time i leave you over night"). A GPU render is not
    "activity" to the sleep timer, so an overnight job died with the
    machine. This is the same app-scoped request a video player makes --
    ES_SYSTEM_REQUIRED | ES_CONTINUOUS -- released the moment the render
    ends, so his own sleep settings apply the rest of the time. Not a system
    setting; nothing outside this process changes. Visible in
    `powercfg -requests` under SYSTEM while a render is up. Must be set and
    cleared on the SAME thread (ES_CONTINUOUS is per-thread): both wrappers
    call it from the event-loop thread."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED if on else ES_CONTINUOUS)
    except Exception as e:  # never let power plumbing break a render
        print(f"[render] keep-awake {'on' if on else 'off'} failed: {e}")


def render_in_progress() -> bool:
    """True while ANY render holds the GPU. Stale-flag safe: a crash that
    never cleared the flag stops blocking after 2 hours.

    2026-09-04: judged by the FILE'S MTIME, not by parsing its content. The
    old version did float(content) and returned False on ValueError -- and
    every standalone GPU script since 08-29 (qwen_t2i, the Task Scheduler
    LTX runner, the MyStudio test, the training probe) writes an OWNERSHIP
    TOKEN, not a timestamp. So their flags were invisible to this guard: the
    office's idle Bonsai calls evicted ComfyUI under a live training probe at
    14:38 (log stops mid-step, no error, fresh Bonsai start the same minute).
    A non-empty flag file younger than 2h is a render, whatever it says."""
    try:
        st = os.stat(_RENDER_FLAG)
        if st.st_size == 0:
            return False
        return (time.time() - st.st_mtime) < 7200
    except OSError:
        return False


# WHAT IS RENDERING RIGHT NOW (2026-08-16, Barry: "i want something that
# shows me its generating"). Set at submit, cleared when the job ends.
# In-memory on purpose: it describes THIS process's live job, and a stale
# entry after a restart would be a lie -- ComfyUI's own queue is the
# authority (see current_render), this only adds the human-readable
# context the queue can't give (which agent, which kind, the prompt text).
_CURRENT: dict | None = None


def _begin_render(kind: str, prompt: str, agent_id: str = "", prompt_id: str = ""):
    global _CURRENT
    _CURRENT = {
        "kind": kind,               # "image" | "video"
        "prompt": prompt,
        "agent_id": agent_id,
        "prompt_id": prompt_id,
        "started_at": time.time(),
    }


def _end_render():
    global _CURRENT
    _CURRENT = None


def current_render() -> dict | None:
    """The live job, or None. Cross-checked against ComfyUI's real queue by
    the caller (main.py's status endpoint) so a crashed render can't leave
    the dashboard claiming work is happening."""
    if not _CURRENT:
        return None
    out = dict(_CURRENT)
    out["elapsed_s"] = int(time.time() - _CURRENT["started_at"])
    return out


async def queue_state() -> dict:
    """ComfyUI's own view: how many jobs running/pending right now."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{COMFY_HOST}/queue")
            resp.raise_for_status()
            data = resp.json()
        return {
            "reachable": True,
            "running": len(data.get("queue_running") or []),
            "pending": len(data.get("queue_pending") or []),
        }
    except (httpx.HTTPError, ValueError):
        return {"reachable": False, "running": 0, "pending": 0}


async def cancel_render() -> dict:
    """Stop whatever is generating (2026-08-16, Barry: "i want a cancell
    generation button" -- after a 22-minute render of the wrong shot).

    Two calls, both needed: /interrupt kills the job actually executing,
    /queue {clear:true} drops anything waiting behind it. The render flag
    is cleared unconditionally so the GPU is released for chat even if
    ComfyUI is already gone."""
    result = {"interrupted": False, "queue_cleared": False, "error": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r1 = await client.post(f"{COMFY_HOST}/interrupt")
            result["interrupted"] = r1.status_code < 400
            r2 = await client.post(f"{COMFY_HOST}/queue", json={"clear": True})
            result["queue_cleared"] = r2.status_code < 400
    except httpx.HTTPError as e:
        result["error"] = str(e)
    finally:
        _clear_render_flag()
        _end_render()
        # Free the checkpoint too -- measured on the first live cancel: the
        # interrupted job left ~GBs resident, so the very next chat message
        # loaded Bonsai into a squeezed card, spilled to shared memory, and
        # took 596s. Cancelling must hand the GPU back, not just stop the
        # job. Same reason generate_video unloads in its own finally.
        try:
            await unload()
        except Exception:
            pass
    return result

# Per-checkpoint licence facts, surfaced on every generation so the owner
# sees at approval time whether a render is safe for real marketing use.
# Add an entry when a new checkpoint lands; unknown checkpoints get the
# conservative default below.
# --- Qwen-Image: the plain-prompt engine (2026-09-04) -----------------------
# Barry: "sdxl has too many flaws. too many extra limbs and ugly faces even with
# neg. prompts." That is the model, not the negatives. Qwen-Image was pulled and
# A/B'd against SDXL on the identical prompt 2026-08-28 and won on exactly this
# (whole figure, sane hands, it counted the objects); it sat unwired waiting on
# his call. Files live in models/unet + models/loras, shared encoder/VAE.
QWEN_UNET = "Qwen_Image-Q4_K_S.gguf"
QWEN_WORKFLOW_PATH = os.path.join(os.path.dirname(COMFY_WORKFLOW_PATH),
                                  "comfy_qwen_t2i_gguf_api.json")
# names an agent can put in a ```model``` fence to pick the engine explicitly
_QWEN_ALIASES = {"qwen", "qwen-image", "qwen_image", "qwenimage"}
_SDXL_ALIASES = {"sdxl", "realvis", "realvisxl"}

# --- Qwen-Image 2.1: the FILM-ONLY 2K engine (2026-09-22, Barry: "Try it") ---
# 7B MMDiT, native 2K, generation + editing in one checkpoint. Comfy-Org's
# int8-convrot build (the format that beat GGUF 2x on LTX-2.5), Qwen3-VL 8B
# int8-convrot encoder, its own VAE (64-channel latent at /16). Files live on
# D:\LTX25\models via extra_model_paths. Sampler contract taken from the
# detailer-LoRA author's own workflow: 25 steps, cfg 1.0, euler/simple.
# NEVER the default engine: the Qwen Research licence is NON-COMMERCIAL, so it
# is picked ONLY by an explicit ```model``` fence -- like Kontext, film only;
# B Dubb / Gotcho Back work stays on Qwen-Image (Apache) above.
QWEN21_UNET = "qwen_image_2.1_int8_convrot.safetensors"
QWEN21_DETAILER_LORA = "elusarcas-qwen2-1-detailer-v1.safetensors"
QWEN21_WORKFLOW_PATH = os.path.join(os.path.dirname(COMFY_WORKFLOW_PATH),
                                    "comfy_qwen21_t2i_api.json")
# "qwen21" = plain; "qwen21-detail" = the detailer LoRA at 0.8
_QWEN21_ALIASES = {"qwen21", "qwen2.1", "qwen-2.1", "qwen-image-2.1", "qwen_image_2.1",
                   "qwen-image-21", "qwen_image_21", "qwenimage21"}
_QWEN21_DETAIL_ALIASES = {a + "-detail" for a in _QWEN21_ALIASES} | {a + "-detailer" for a in _QWEN21_ALIASES}

# --- Qwen-Image-Edit: the REFERENCE engine for people (2026-09-10) ----------
# Barry: "Amara is still generating herself as the old version, not my new
# images of her." Measured cause: every picture WITH an agent in it (a [SELF]
# show, change_my_picture's home/self/out/office slots) ran SDXL + IP-Adapter,
# which averages a face embed and cannot hold a body -- the August finding, and
# exactly what her rejected render looked like (lean, short straight hair). The
# editor takes his actual picture as the source and restages it, so identity,
# hair and figure come from HIS pixels. Apache-2.0, unfiltered (the reason it
# replaced Kontext 2026-08-28). Cost: ~8 min a pass on a clean card.
QWEN_EDIT_UNET = "Qwen-Image-Edit-2509-Q4_K_S.gguf"
QWEN_EDIT_WORKFLOW_PATH = os.path.join(os.path.dirname(COMFY_WORKFLOW_PATH),
                                       "comfy_qwen_edit_gguf_api.json")

_MODEL_LICENSES = {
    QWEN21_UNET: (
        False,
        "Qwen-Image 2.1 (Qwen Research licence, NON-COMMERCIAL) -- film / "
        "personal work only, never B Dubb or Gotcho Back marketing.",
    ),
    QWEN_EDIT_UNET: (
        True,
        "Qwen-Image-Edit (Apache-2.0) -- edited images OK for commercial use.",
    ),
    "RealVisXL_V5.0_fp16.safetensors": (
        True,
        "SDXL fine-tune (CreativeML OpenRAIL++) -- generated images OK for "
        "commercial use.",
    ),
    # Qwen-Image base, Apache-2.0: commercial-safe for B Dubb / Gotcho Back,
    # unlike Kontext (non-commercial, film only). Wired 2026-09-04.
    QWEN_UNET: (
        True,
        "Qwen-Image (Apache-2.0) -- generated images OK for commercial use.",
    ),
}
_UNKNOWN_LICENSE = (
    False,
    "Licence not on file for this checkpoint -- treat as personal-use only "
    "until Marcus confirms.",
)


def files_present() -> bool:
    """Is the ComfyUI install actually on disk? Used by the capability
    status block so agents describe a missing install as missing, not as a
    temporary outage."""
    return os.path.isfile(COMFY_PYTHON) and os.path.isfile(
        os.path.join(COMFY_DIR, "main.py")
    )


async def _is_up(client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.get(f"{COMFY_HOST}/system_stats")
        return resp.is_success
    except httpx.HTTPError:
        return False


async def is_available() -> bool:
    """Cheap check for the capability-status injection: the engine counts as
    available if the server answers OR the install exists (we can start it
    on demand) -- unlike AmuseBridge, which had to be running already."""
    if not files_present():
        return False
    return True


# Which mode the running ComfyUI was launched in. The two modes differ in ENV,
# which a process cannot change after launch, so a request for the other mode
# stops the server and relaunches it (~30-50s). See the env block below for why.
_server_mode: str | None = None


async def ensure_running(timeout_s: float = 120.0, mode: str = "image") -> bool:
    """Start the ComfyUI server if it isn't answering, and wait until it is.
    First start on a cold machine measured ~25s (2026-07-30); the generous
    timeout covers a slow disk day, not an expected wait."""
    global _server_proc, _server_mode
    async with httpx.AsyncClient(timeout=3.0) as client:
        if await _is_up(client):
            # A server we did not launch (MyStudio, a previous backend life) has
            # an unknown env; assume the historical default, image mode -- no
            # flag. So an IMAGE request keeps it and a VIDEO request replaces it.
            if (_server_mode or "image") == mode:
                return True
            # Wrong mode for this job. ENV cannot change on a live process, and
            # running LTX-2.5 without the flag is the measured 576p crawl / 720p
            # OOM, so pay the ~30-50s relaunch instead of a 15-minute encode.
            await stop_server()
            await asyncio.sleep(2.0)
    if not files_present():
        return False
    _server_mode = mode

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        log_handle = open(_SERVER_LOG_PATH, "a", encoding="utf-8", errors="replace")
        log_handle.write(f"\n--- ComfyUI start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_handle.flush()
        _server_proc = subprocess.Popen(
            [
                COMFY_PYTHON,
                "main.py",
                "--listen", "127.0.0.1",
                "--port", COMFY_HOST.rsplit(":", 1)[-1],
                # AMD's recommended attention path for ROCm on Windows.
                "--use-pytorch-cross-attention",
                # Keep 1.5GB of VRAM for the desktop -- without this, video
                # renders starve the display and the owner's screen goes
                # black (observed live 2026-07-31). The heavier safety
                # flags (--cache-none/--disable-pinned-memory) are OFF on
                # purpose: measured ~2x slower, and a clean machine doesn't
                # need them (owner's own run: 5s clip in ~7 min).
                # BOTH MODES. This was briefly made image-only (2026-09-04) on
                # the theory that the reserve starved LTX-2.5's encoder -- and
                # within the hour Barry's monitor was going black mid-render,
                # exactly the 2026-07-31 failure above. The 576p crawl that
                # motivated dropping it was the MISSING no-caching flag, not the
                # reserve (that run had neither the flag nor a working
                # allocator). Flag + reserve together is the video config.
                "--reserve-vram", "1.5",
                # VIDEO MODE ALSO GETS --cache-none (2026-09-04, measured under Task
                # Scheduler so nothing could kill it): at reserve 1.5 the LTX-2.5
                # stage-1 sampler ran 40.5 s/step; with --cache-none, 11.5 s/step --
                # better than the no-reserve run that blacked the screen (12.9). It
                # evicts the text encoder fully before the video model loads, which
                # is the room the reserve takes. Encode also fell ~12 min -> ~4.
                # NOT for image mode: the 2026-07-30 measurement had cache-none ~2x
                # slower on SDXL, and images do not have a 10.9GB encoder to evict.
                *(["--cache-none"] if _server_mode == "video" else []),
            ],
            cwd=COMFY_DIR,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            # ROCm fragmentation fix (2026-07-31): a render died with "HIP
            # out of memory: tried to allocate 288MB, 15.28GiB free" --
            # allocation failure with the card nearly EMPTY. Torch's own
            # error message prescribes exactly this allocator mode.
            env={**os.environ,
                 # LTX-2.5 NEEDS THIS, IMAGES MUST NOT HAVE IT (2026-09-04, measured):
                 # without it the 720p refine dies "Tried to allocate 16 MiB ...
                 # 4.80 GiB is free" (fragmentation) and even a 576p encode crawls
                 # >15 min; with it, SDXL sampling drops 3.20 -> 1.98 it/s (1.6x) and
                 # Qwen's 8 steps at 43-100 s/step would pay that in minutes. So the
                 # flag rides on VIDEO launches only -- see ensure_running(mode).
                 **({"PYTORCH_NO_HIP_MEMORY_CACHING": "1"} if _server_mode == "video" else {}),
                 # `expandable_segments` was here since 2026-07-31; it is documented
                 # unsupported on HIP (torch says so in its own OOM text) and has
                 # been a no-op the whole time. Removed rather than carried.
                 # TunableOp -- TRIED AND SHELVED 2026-08-29. On gfx1201 the
                 # tuning pass never finished step 1 of a Qwen-Image render
                 # in 25 minutes (baseline step time: 43s) and wrote no CSV.
                 # Left as OPT-IN: set COMFY_TUNABLEOP=1 to retry, ideally
                 # with PYTORCH_TUNABLEOP_MAX_TUNING_DURATION_MS /
                 # _MAX_TUNING_ITERATIONS bounds added first.
                 **({} if os.environ.get("COMFY_TUNABLEOP") != "1" else {
                     "PYTORCH_TUNABLEOP_ENABLED": "1",
                     "PYTORCH_TUNABLEOP_TUNING": "1",
                     "PYTORCH_TUNABLEOP_FILENAME":
                         os.path.join(DATA_DIR, "tunableop_comfy.csv"),
                 })},
        )
    except (OSError, subprocess.SubprocessError):
        return False

    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.monotonic() < deadline:
            await asyncio.sleep(2.0)
            if await _is_up(client):
                return True
    return False


async def unload() -> None:
    """Release ComfyUI's VRAM (checkpoint + cached tensors) without killing
    the server -- called from llm_router's unload chain before any Ollama
    generation, exactly where amuse_integration.unload() used to be. The
    idle server itself holds almost nothing; the loaded checkpoint holds
    ~7GB+. Best-effort: not running means nothing to release."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{COMFY_HOST}/free",
                json={"unload_models": True, "free_memory": True},
            )
    except httpx.HTTPError:
        pass


async def stop_server() -> None:
    """Fully release ComfyUI's GPU footprint by ENDING the process, not just
    freeing its models. Measured 2026-08-28 (per-process GPU counters):
    after unload()'s /free, the ComfyUI process still held ~2.6GB of
    dedicated VRAM -- torch's HIP context plus the allocator arena, which
    only process exit returns. That residue squeezed Bonsai's ~11GB load
    into shared system memory and dropped the whole office to 3-5 tok/s
    (the documented spill signature), and the spilled server persists until
    killed. Called on the PRE-BONSAI eviction path only -- the tight fit;
    the Ollama path keeps the cheaper unload(), since those models fit
    alongside the residue. ComfyUI auto-starts on demand (~25s), so the
    only cost is a cold start on the next render. MyStudio's twin on 8189
    is untouched -- this only handles OUR port."""
    global _server_proc
    await unload()                      # graceful: checkpoint out first
    if _server_proc is not None and _server_proc.poll() is None:
        try:
            _server_proc.kill()
            _server_proc.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    _server_proc = None
    # Any OTHER instance holding our port -- e.g. started by a previous
    # backend life or a build script -- still holds its arena; find it by
    # port ownership (never by image name -- the AMD-bundle lesson).
    port = COMFY_HOST.rsplit(":", 1)[-1]

    def _kill_port_owner():
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
                 "-ErrorAction SilentlyContinue).OwningProcess"],
                capture_output=True, text=True, timeout=15).stdout.split()
            for pid in {int(x) for x in out if x.strip().isdigit()}:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

    await asyncio.to_thread(_kill_port_owner)


def _resolve_model(requested: str | None) -> str:
    """Map an agent's ```model``` fence to a real checkpoint file. Accepts
    the exact filename or a loose name (case-insensitive, extension
    optional). Anything unrecognized quietly becomes the default -- same
    typo/hallucination resilience the Amuse path had."""
    if not requested:
        return COMFY_DEFAULT_MODEL
    try:
        available = [
            f for f in os.listdir(COMFY_CHECKPOINTS_DIR)
            if f.lower().endswith((".safetensors", ".ckpt", ".gguf"))
        ]
    except OSError:
        return COMFY_DEFAULT_MODEL
    want = requested.strip().lower()
    for f in available:
        if f.lower() == want or os.path.splitext(f)[0].lower() == want:
            return f
    return COMFY_DEFAULT_MODEL



# --- Character LoRAs via @mentions (2026-07-31) -----------------------
# Owner's rule: @Bia / @BDUBB is THE name everywhere -- in his script, in
# prompts, in the trained models themselves. Each LoRA is trained on its
# own @Name token, so the mention passes straight through to the model
# untouched; all this layer does is load the right LoRA file.
# ALL CHARACTERS MOVED TO THEIR LATEST VERSION 2026-08-21 (Barry: "they all
# should be on the latest version" -- this is the approval the v2/v3/v5 flips
# had been waiting on since the overnight training runs). Previous map (for
# rollback): bdubb/bia/yannah/tazz/keth all base-v1, vorshara v4.
# THE ONE EXCEPTION: keth stays on v5, NOT v7 -- v7 is the fried run
# (documented 2026-08-09: noise at strength 1.0, human at 0.4, UNet corrupt).
CHARACTER_LORAS = {
    # REVERTED to the PROVEN set 2026-08-21. The "all on latest" flip earlier
    # that day was tested immediately and bia_character_v3 rendered PURE
    # NOISE -- the fried-run signature documented for keth v7 (UNet corrupt).
    # The vN files from the overnight runs were NEVER eyeballed, so newest is
    # not working. Restore a vN only after it renders correctly by eye.
    "bdubb":    "bdubb_character.safetensors",
    "bia":      "bia_character.safetensors",
    "yannah":   "yannah_character.safetensors",
    "tazz":     "tazz_character.safetensors",
    # v5 = the working Keth (v3 and v7 both fried -- see the gradient-clip
    # post-mortem, data/backup_nodes_train_before_clip_2026-08-09.py).
    "keth":     "keth_character_v5.safetensors",
    # v4 verified 2026-08-04 at native resolution: four icy-blue slit-pupil
    # eyes in full-body frames where v3 collapses to two.
    "vorshara": "vorshara_character_v4.safetensors",
}

# Solo strength per character, where the shared default is wrong for that one.
# Vor'Shara measured 2026-08-04: at 0.9 the prompt overpowers her and she
# renders as a generic member of her species (Barry: "it would no problem
# creating her sister"). 1.0 is what produced the approved face; anything the
# other characters use is deliberately left alone -- Bia is already good.
CHARACTER_SOLO_STRENGTH = {
    "vorshara": 1.0,
}
CHARACTER_ALIASES = {
    # 2026-08-14 rename. Barry renamed his trained assets: @Bia -> @Bia-2 and
    # @BDUBB -> @B-DUBB-new ("the characters we trained needs a name change
    # too"). Before this they resolved BY ACCIDENT, not by design: the old
    # regex stopped at the hyphen, so "@Bia-2" matched "@Bia" and "@B-DUBB-new"
    # matched "@B" (already an alias for bdubb), leaving "-2" and "-DUBB-new"
    # in the prompt as junk tokens. Now they are real entries and the regex
    # takes the whole handle.
    "bia2": "bia", "bdubbnew": "bdubb",
    "bdubbgrows": "bdubb", "barry": "bdubb", "b": "bdubb",
    "vor": "vorshara", "vorsharavel": "vorshara", "shara": "vorshara",
    "ladyvorshara": "vorshara", "ladyvor": "vorshara",
    # Barry writes her full title in prompts; the regex strips ' and _ before
    # lookup, so @LadyVor'SharaVel arrives here as "ladyvorsharavel".
    "ladyvorsharavel": "vorshara", "sharavel": "vorshara",
    "ladyshara": "vorshara", "vorshar": "vorshara",
}
# Hyphens and a trailing * are part of the 2026-08-14 handles (@Bia-2,
# @B-DUBB-new, @Bia's-Pistol*), so the pattern has to take the WHOLE handle --
# otherwise it silently matches a prefix and leaves the rest as loose text.
_MENTION_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_'\-]*)\*?")

# The trained token each LoRA actually learned. THE RENAME DID NOT RETRAIN
# ANYTHING -- it renamed Barry's asset library. So a new handle is accepted on
# the way in and rewritten to the token the weights were trained on before the
# text reaches the model; otherwise the model sees tokens the LoRA never saw.
CHARACTER_TRAINED_TOKEN = {
    "bdubb": "@BDUBB", "bia": "@Bia", "yannah": "@Yannah",
    "tazz": "@Tazz", "keth": "@Keth", "vorshara": "@Vorshara",
}

# --- CHARACTER RESTAGE: the Amara door for the Bia crew (2026-09-14) --------
# Barry: "looking at how well its rendering amara with only an image, thats
# how i want my characters from the Bia show to be done with Elliot." The
# agent pictures are Qwen-Image-Edit RESTAGING his reference pixels; the
# character LoRAs were measured 2026-09-04 as carrying ~no identity on bare
# text (Keth v5 -> a human woman at every strength). So an @handle in a
# local fence now restages the character's staged whole-figure reference
# through the editor instead of loading the LoRA. One character per frame
# for now: multi-image edits BLEND their references (2026-08-28), so a
# two-character shot keeps the SDXL+LoRA path until a stitch pass exists.
# References live in ComfyUI's INPUT ROOT (LoadImage reads no subfolders)
# and must be ONE whole figure -- a turnaround sheet reads as a collage.
# Revert = COMFY_CHARACTER_RESTAGE=0 (routing falls back to SDXL+LoRA).
CHARACTER_REFS = {
    # Picked by OPENING the frames (2026-09-14), all from the 09-04 training
    # sets = his August Higgsfield batches of the CURRENT looks, 1328 long edge:
    # keth 007 (the one whole-figure single frame; the rest are close-ups),
    # tazz 004 (front, sleeveless black one-piece), yannah 015 (front, black
    # suit + teal piping), bdubb 011 (real photo, full canon gear: cap, hoodie,
    # vest, pendant), vorshara 009 (three-quarter length so the four eyes stay
    # readable -- her full-body frames have ~120px heads), bia = the Aug-22
    # whole-figure front (char_bia_body.png).
    "keth": "char_ref_keth.png",
    "bia": "char_ref_bia.png",
    "tazz": "char_ref_tazz.png",
    "yannah": "char_ref_yannah.png",
    "bdubb": "char_ref_bdubb.png",
    "vorshara": "char_ref_vorshara.png",
}
CHARACTER_RESTAGE_ENABLED = os.environ.get("COMFY_CHARACTER_RESTAGE", "1") != "0"
# Qwen-Edit's output takes the ASPECT of image 1 (VAEEncode of the source is
# the latent). His references are portrait; his shots are cinematic. So the
# restage feeds a 16:9 CANVAS with the figure centred on it, and the
# instruction already says to drop the reference's background/framing. The
# fill is the reference's own border colour so the pads read as backdrop,
# not as panels. A portrait ask (height > width) uses the raw reference.
RESTAGE_WIDE = (1344, 768)


def character_reference(key: str) -> str | None:
    """Staged whole-figure reference for a character key, if it exists."""
    cand = CHARACTER_REFS.get(key)
    if cand and os.path.isfile(os.path.join(COMFY_DIR, "input", cand)):
        return cand
    return None


# THE REFERENCE SETS THE CANVAS (2026-09-19, measured the hard way).
# Qwen-Image-Edit takes the OUTPUT SIZE from image 1. Staging a tight face
# crop as someone's reference -- 322x430, all the pixels a 1024x1024 source
# holds around a head -- therefore rendered their whole picture at 320x424,
# where a face is about 60 pixels tall and cannot look like anyone. The room
# was fixed and the resolution was broken in the same edit.
# Upscaling adds no detail, and it does not need to: the crop already carries
# the identity, and what was missing was somewhere to draw. 1024 on the long
# edge matches the renders that worked and keeps the upscale modest.
WORKING_REF_LONG_EDGE = 1024


def working_reference(ref: str, min_long_edge: int = WORKING_REF_LONG_EDGE) -> str:
    """A reference big enough to render from, cached as <stem>_work.png.

    Returns the original name when it is already large enough, or when
    anything goes wrong -- a soft reference is better than no picture.
    """
    src = os.path.join(COMFY_DIR, "input", ref)
    try:
        from PIL import Image
        with Image.open(src) as probe:
            if max(probe.size) >= min_long_edge:
                return ref
        stem, _ = os.path.splitext(ref)
        work_name = f"{stem}_work.png"
        dst = os.path.join(COMFY_DIR, "input", work_name)
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return work_name
        with Image.open(src) as im:
            im = im.convert("RGB")
            scale = min_long_edge / float(max(im.size))
            big = im.resize((max(1, round(im.width * scale)),
                             max(1, round(im.height * scale))), Image.LANCZOS)
            big.save(dst)
        print(f"[ref] {ref} upscaled to {big.size} for rendering", flush=True)
        return work_name
    except Exception as e:  # noqa: BLE001
        print(f"[ref] working copy failed for {ref}: {e}", flush=True)
        return ref


# EXTRA REFERENCES RIDE SMALL (2026-09-22, the second black screen of the day:
# the PC hard-hung during the text encode of an 8-picture group still). The
# Qwen 2.1 encode node scales EVERY picture to the output resolution (~1024²),
# so each extra reference cost the Qwen3-VL encoder the same vision tokens as
# the picture being made. Extras only need to show identity, not become the
# canvas, so they are staged at this long edge and the node is run with
# resolution=0 (keep each picture's own size). ~1/2.5 the tokens per extra.
EXTRA_REF_LONG_EDGE = int(os.environ.get("COMFY_EXTRA_REF_EDGE", "640"))


VRAM_GUARD_GB = float(os.environ.get("COMFY_VRAM_GUARD_GB", "15.3"))
VRAM_GUARD_SECONDS = int(os.environ.get("COMFY_VRAM_GUARD_SECONDS", "120"))


def gpu_dedicated_gb() -> float | None:
    """Dedicated VRAM in use on the busiest adapter, in GB (Windows perf
    counter). None if it cannot be read -- the guard then simply does nothing."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             r"((Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples"
             " | Measure-Object CookedValue -Maximum).Maximum"],
            capture_output=True, text=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return float(out.stdout.strip()) / (1024 ** 3)
    except Exception:  # noqa: BLE001
        return None


def small_reference(ref: str, long_edge: int = EXTRA_REF_LONG_EDGE) -> str:
    """A down-scaled copy of a staged reference, cached as <stem>_small.png
    (rebuilt when the source is newer). Returns the original on any failure."""
    src = os.path.join(COMFY_DIR, "input", os.path.basename(ref))
    try:
        from PIL import Image
        with Image.open(src) as probe:
            if max(probe.size) <= long_edge:
                return os.path.basename(ref)
        stem, _ = os.path.splitext(os.path.basename(ref))
        name = f"{stem}_s{long_edge}.png"
        dst = os.path.join(COMFY_DIR, "input", name)
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return name
        with Image.open(src) as im:
            im = im.convert("RGB")
            s = long_edge / float(max(im.size))
            im.resize((max(32, round(im.width * s)), max(32, round(im.height * s))),
                      Image.LANCZOS).save(dst)
        return name
    except Exception as e:  # noqa: BLE001
        print(f"[ref] small copy failed for {ref}: {e}", flush=True)
        return os.path.basename(ref)


def _wide_reference(ref: str) -> str:
    """The 16:9 canvas version of a staged reference, built once and cached
    in the input root as <stem>_wide.png (rebuilt if the source is newer)."""
    src = os.path.join(COMFY_DIR, "input", ref)
    stem, _ = os.path.splitext(ref)
    wide_name = f"{stem}_wide.png"
    dst = os.path.join(COMFY_DIR, "input", wide_name)
    if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return wide_name
    try:
        from PIL import Image, ImageStat
        im = Image.open(src).convert("RGB")
        w, h = RESTAGE_WIDE
        # border colour = median of a 4px frame around the source
        px = list(im.crop((0, 0, im.width, 4)).getdata()) + \
             list(im.crop((0, im.height - 4, im.width, im.height)).getdata()) + \
             list(im.crop((0, 0, 4, im.height)).getdata()) + \
             list(im.crop((im.width - 4, 0, im.width, im.height)).getdata())
        fill = tuple(int(sorted(c[i] for c in px)[len(px) // 2]) for i in range(3))
        fig = im.copy()
        fig.thumbnail((w, h))
        canvas = Image.new("RGB", (w, h), fill)
        canvas.paste(fig, ((w - fig.width) // 2, (h - fig.height) // 2))
        canvas.save(dst)
        return wide_name
    except Exception as e:  # PIL missing or a bad file: fall back to portrait
        print(f"[restage] wide canvas failed for {ref}: {e}", flush=True)
        return ref


# Weapon + location REFERENCES for the restage (2026-09-14, Barry: "all of
# it"). The first six stills showed the two things words cannot carry
# locally: Bia's purple revolver came back a black pistol, Tazz's blaster an
# olive rifle, and "the Talia's bridge" a city skyline. So a weapon handle in
# the fence attaches its hero render as the next image, and a place word
# attaches Barry's own Higgsfield plate of that location (the Talia deck's
# art, assets/locs/_full). Three sources max (the editor takes three; more
# blends). Weapons come from tools/ComfyUI/input/*_ref.png (08-14/08-25),
# locations from AgentDashboard/assets/locs/_full -- both re-staged at 1344.
WEAPON_REFS = {
    "biaspistol": "weapon_ref_bia_pistol.png",
    "yannahsmachinepistol": "weapon_ref_yannah_pistol.png",
    "tazzsweapon": "weapon_ref_tazz_weapon.png",
    "misslelauncher": "weapon_ref_tazz_weapon.png",  # Barry 2026-09-24
    "missilelauncher": "weapon_ref_tazz_weapon.png",
    "bdubbsbanger": "weapon_ref_bdubb_banger.png",
}
# FIRING PLATES (2026-09-25, Barry: "i gave images of her weapon and it should be pistol style, one hand shooter.
# and how it looks when fired"). #464 fired GREEN LASER LINES because the engine only ever saw the at-rest plate.
# When the shot has the weapon firing, the firing plate goes in instead, with its canon look in words.
WEAPON_FIRE_REFS = {
    "yannahsmachinepistol": "weapon_fire_yannah_pistol.png",   # data/props/yannah-machine-pistol/..._043500
    # Barry, same day: "Bia's is also a revolver style pistol"
    "biaspistol": "weapon_fire_bia_pistol.png",                # data/props/bia-pistol/..._035649
}
WEAPON_FIRE_LOOK = {
    "biaspistol": ("firing: ONE glowing purple plasma ball with a white-hot core leaves the revolver's muzzle with "
                   "gold sparks and a curl of smoke, exactly as in that image -- one ball per shot, never a beam, "
                   "never a stream"),
    "yannahsmachinepistol": ("firing: raindrop-shaped glowing forest-green liquid-metal rounds with pointed tails "
                             "fly from a near-invisible muzzle with a thin puff of smoke, exactly as in that image -- "
                             "never laser beams, never tracer lines"),
}
_FIRING_RE = re.compile(r"\b(fir(e|es|ed|ing)|shoot(s|ing)?|shots? fired|burst|opens? fire|rounds|tracers?|muzzle "
                        r"flash|pulls? the trigger)\b", re.I)


def _weapon_plate(wkey: str, prompt: str) -> str:
    """The firing plate when the shot has this weapon firing (and one is staged), else the at-rest plate."""
    fire = WEAPON_FIRE_REFS.get(wkey)
    if fire and _FIRING_RE.search(prompt or "") and _staged(fire):
        return fire
    return WEAPON_REFS[wkey]


# REAL SIZE OF EACH WEAPON (2026-09-23, Barry: "Elliot has her pistol too big.
# its a pistol should be held in one hand"). A weapon reference is a studio plate
# with no hand or body in it, so the engine has no scale cue and blows the gun up
# to carbine size. The office states the canon size next to the plate.
WEAPON_SCALE = {
    "biaspistol": "a revolver-sized pistol held in ONE hand",
    # 2026-09-25, Barry: "the gun is off and its too big" -- "the length of her forearm" drew a carbine-sized gun
    "yannahsmachinepistol": ("a small HANDGUN-SIZED machine pistol, no longer than her hand from wrist to fingertips, "
                             "gripped in ONE hand like an ordinary pistol, the exact shape and white-and-green design "
                             "of that image"),
    "tazzsweapon": "a compact two-handed carbine with a folding stock",
    "misslelauncher": "a compact two-handed carbine with a folding stock",
    "missilelauncher": "a compact two-handed carbine with a folding stock",
    "bdubbsbanger": "an ordinary handgun held in ONE hand",
}


# Barry, same day: "her zip shows her with it holstered, thats the size." Each
# carrier's MAIN reference shows the weapon holstered at its real size, so when
# the carrier is in the shot the note points at that picture as the ruler.
WEAPON_OWNER = {"biaspistol": "bia", "yannahsmachinepistol": "yannah",
                "tazzsweapon": "tazz", "bdubbsbanger": "bdubb",
                "misslelauncher": "tazz", "missilelauncher": "tazz"}


def _weapon_scale_note(weapon_idx: dict, carrier_img: dict | None = None, prompt: str = "") -> str:
    carrier_img = carrier_img or {}
    parts = []
    for k, i in weapon_idx.items():
        if k not in WEAPON_SCALE:
            continue
        line = f"the weapon from image {i} is {WEAPON_SCALE[k]}"
        if k in WEAPON_FIRE_LOOK and _weapon_plate(k, prompt) != WEAPON_REFS[k]:
            line += f", {WEAPON_FIRE_LOOK[k]}"
        own = carrier_img.get(WEAPON_OWNER.get(k, ""))
        if own:
            line += (f" -- it is the SAME weapon holstered on the character in image {own}, "
                     "and that holster is its true size")
        parts.append(line)
    return (" TRUE SIZE: " + "; ".join(parts) + " -- the weapon images have no scale, so "
            "size each weapon to a real hand and body, never larger.") if parts else ""


# (regex over the prompt, staged plate). Order = priority; first hit wins.
LOCATION_REFS = [
    (re.compile(r"black[\s-]?site", re.I), "loc_ref_blacksite.png"),
    (re.compile(r"\bbridge\b", re.I), "loc_ref_bridge.png"),
    (re.compile(r"common\s+area", re.I), "loc_ref_common.png"),
    (re.compile(r"sanctum|garden\s+atrium|reflecting\s+pool", re.I), "loc_ref_sanctum.png"),
    (re.compile(r"rai'?lin|\bmarket\b", re.I), "loc_ref_market.png"),
    (re.compile(r"araxys", re.I), "loc_ref_araxys.png"),
    (re.compile(r"ext\.?\s*@?talia|@?talia\b[^.]{0,40}\b(deep space|hull|cruis)", re.I),
     "loc_ref_talia_ship.png"),
]


def video_prompt_text(prompt: str) -> str:
    """The LTX prompt for a character clip made FROM a restaged still: the
    still carries the identity, so every character handle becomes 'the
    character' and weapon handles become plain words. LTX SPEAKS its prompt
    -- an '@Keth' left in would be read aloud."""
    def sub(m: "re.Match") -> str:
        base, possessive = _split_possessive(m.group(1))
        raw = _mention_key(base)
        k = raw if raw in CHARACTER_LORAS else CHARACTER_ALIASES.get(raw)
        if k:
            return "the character" + ("'s" if possessive else "")
        return WEAPON_HANDLE_WORDS.get(_mention_key(m.group(1)), m.group(0))
    return _MENTION_RE.sub(sub, prompt or "")


def _staged(name: str) -> str | None:
    return name if os.path.isfile(os.path.join(COMFY_DIR, "input", name)) else None


def character_face_reference(key: str) -> str | None:
    """The staged FRONT-FACE close-up for a character (char_<key>_face.png), or
    None. 2026-09-22, Barry: "keths front facing face in the video is wrong, i
    think its because you didnt use his front face image" -- he was right. The
    whole-figure ref for Keth is a side profile, so the moment he turned to the
    camera the engine (and then LTX) invented a front it had never been shown."""
    name = f"char_{key}_face.png"
    return name if _staged(name) else None


# Every other view of a character Barry supplied, in the order they are
# handed to the engine (2026-09-22, Barry: "I want headshots, full front
# facing 3/4 and rear of each ... i need complete accuracy"). Files live in the
# input ROOT as char_<key>_angle_<view>.png; a missing view is skipped.
_ANGLE_VIEWS = [
    ("threequarter", "from a three-quarter angle"),
    ("side", "in side profile"),
    ("rear_threequarter", "from behind at three-quarters"),
    ("back", "from directly behind"),
    ("front_nude", "from the front, undressed (her body as it is under the gown)"),
    ("back_nude", "from behind, undressed"),
]


_FRAMING_RE = re.compile(
    r"waist[- ]?up|chest[- ]?up|close[- ]?up|close on|extreme close|head and shoulders|"
    r"head[- ]?shot|medium (?:close|shot)|\bmcu\b|\becu\b|over[- ]the[- ]shoulder|"
    r"portrait|knees? up|full[- ]?(?:body|figure|length)|wide shot|long shot", re.I)


def character_angle_references(key: str) -> list[tuple[str, str]]:
    """[(filename, description)] -- the face close-up first, then every staged
    angle. Used on the Qwen 2.1 restage path only (it takes 16 images)."""
    refs: list[tuple[str, str]] = []
    # FACE AND BODY ONLY (2026-09-23, Barry: "we should do face and body and
    # let the script do the rest"). The stills he loved were made from ONE
    # body picture (+ the face); the sheets and angle files pulled the look
    # off (a heavier B Dubb, duplicated figures) and cost the encode step.
    # Env QWEN21_REFS=sheets restores the sheet/angle behaviour below.
    if QWEN21_FACE_AND_BODY_ONLY:
        face = character_face_reference(key)
        return [(face, "a close-up of the face, seen from the front")] if face else []
    # ONE SHEET PER CHARACTER (2026-09-22, Barry: "all the angles for 1
    # character on 1 sheet"). char_<key>_sheet.png = every angle side by side;
    # a sheet reads as ONE person, which is what keeps two people apart in a
    # group still. When it exists it replaces the separate files.
    if _staged(f"char_{key}_sheet.png"):
        return [(f"char_{key}_sheet.png",
                 "on a reference sheet -- the same character from every angle side by "
                 "side: a close-up of the face, the front, the other views, and close-ups "
                 "of anything they always WEAR (put those on them, not in the scene)")]
    face = character_face_reference(key)
    if face:
        refs.append((face, "a close-up of the face, seen from the front"))
    for view, words in _ANGLE_VIEWS:
        name = f"char_{key}_angle_{view}.png"
        if _staged(name):
            refs.append((name, words))
    return refs


def _restage_instruction(prompt: str, key: str,
                         angle_refs: list[tuple[str, str]] | None = None) -> tuple[str, list[str]]:
    """Rewrite Elliot's fence into editor grammar and pick the extra sources.
    Every @mention of the character (any alias, possessive or not) becomes
    'the character from image 1'; a weapon handle with a staged reference
    becomes 'the weapon from image N' (else plain words); a place word with a
    staged plate adds 'the setting is the place in image N'. A preservation
    clause is carried and the reference's background/framing is dropped.
    Wardrobe is NOT dropped -- for these characters it is canon, and the
    Elliot tail spells it out in every prompt anyway.
    Returns (instruction, extra_sources) -- extras are images 2..3 in order."""
    # With a face close-up the face takes image 2 and plates follow it, so the
    # cap on extras rises by one (only the 2.1 engine is handed a face_ref --
    # it takes up to 16 images; Qwen-Edit's path stays at 3 sources).
    angle_refs = list(angle_refs or [])
    extras: list[str] = [f for f, _ in angle_refs]
    cap = len(extras) + 2
    weapon_idx: dict[str, int] = {}

    def sub(m: "re.Match") -> str:
        base, possessive = _split_possessive(m.group(1))
        raw = _mention_key(base)
        k = raw if raw in CHARACTER_LORAS else CHARACTER_ALIASES.get(raw)
        if k == key:
            return "the character from image 1" + ("'s" if possessive else "")
        if k:
            return CHARACTER_TRAINED_TOKEN.get(k, base) + possessive
        wkey = _mention_key(m.group(1))
        if wkey in WEAPON_REFS:
            if wkey not in weapon_idx and len(extras) < cap and _staged(_weapon_plate(wkey, prompt)):
                extras.append(_weapon_plate(wkey, prompt))
                weapon_idx[wkey] = len(extras) + 1
            if wkey in weapon_idx:
                return f"the weapon from image {weapon_idx[wkey]}"
        return WEAPON_HANDLE_WORDS.get(wkey, m.group(0))

    scene = _MENTION_RE.sub(sub, prompt or "").strip().rstrip(".")
    setting = ""
    if len(extras) < cap:
        for rx, plate in LOCATION_REFS:
            if rx.search(prompt or "") and _staged(plate):
                extras.append(plate)
                setting = (f" The setting is the place shown in image {len(extras) + 1}: "
                           f"keep its architecture, materials, colours and lighting, and "
                           f"place the character inside it.")
                break
    weapon_note = ""
    if weapon_idx:
        weapon_note = (" Keep each weapon's exact shape, colours and materials as shown in "
                       "its image; do not keep the white studio background of any weapon image.")
        weapon_note += _weapon_scale_note(weapon_idx, {key: 1}, prompt)
    # 2026-09-22: this used to END with a fixed "the whole figure framed in the
    # scene", which overrode the shot's own framing -- a waist-up Keth came back
    # as a small full figure. The shot's framing words win when present.
    framing = ("framed exactly as described." if _FRAMING_RE.search(prompt or "")
               else "the whole figure framed in the scene.")
    face_note = ""
    if angle_refs:
        views = "; ".join(f"image {i + 2} shows them {words}" for i, (_, words) in enumerate(angle_refs))
        last = len(angle_refs) + 1
        face_note = (f" Images 2 to {last} are the SAME character from other views -- {views}. "
                     "Whatever angle this shot needs, match the character to the image that "
                     "shows that angle: face, eyes, eye colour, skin texture and wrinkles, ears, "
                     "build and clothing exactly. Keep the clothing described for this shot, "
                     "not an undressed view unless the shot asks for it. Do not keep the "
                     "backgrounds of those images.")
    instruction = (
        "Make a new cinematic photograph of the exact same character from "
        "image 1, keeping the character's face, head shape, eyes, skin, "
        "build, height and body proportions identical to image 1. Do not keep "
        "the background, lighting or framing from image 1 -- stage the "
        f"character only as described here: {scene}.{face_note}{setting}{weapon_note} "
        "Photorealistic, film still, " + framing
    )
    return instruction, extras


# THE GROUP DOOR (2026-09-22, Barry: "build the 2 character door, if there is a
# three that would be crazy cool"). Two or three characters in one Qwen 2.1
# still. Each person gets their OWN labelled block of reference pictures and a
# letter (Character A/B/C); the instruction names which images belong to whom
# and forbids mixing features -- the known risk is the engine blending two
# faces together. Budget per person shrinks with the count so the encode stays
# sane (2 people: main + face + one view; 3 people: main + face).
GROUP_MAX = 3
_BACK_VIEW_RE = re.compile(r"from behind|\bback to (?:the )?camera|\bhis back\b|\bher back\b|"
                           r"\btheir back\b|rear view|over[- ]the[- ]shoulder", re.I)


def _group_refs(key: str, count: int, prompt: str) -> list[tuple[str, str]]:
    """This person's pictures for a group still: [(filename, words)], main first."""
    main = character_reference(key)
    refs = [(main, "the whole figure, from the front")]
    if QWEN21_FACE_AND_BODY_ONLY:  # 2026-09-23, see character_angle_references
        face = character_face_reference(key)
        if face:
            refs.append((face, "a close-up of the face"))
        return refs
    if _staged(f"char_{key}_sheet.png"):
        refs.append((f"char_{key}_sheet.png",
                     "a reference sheet of them from every angle, face close-up first, then "
                     "close-ups of anything they always WEAR (put those on them)"))
        return refs
    face = character_face_reference(key)
    if face:
        refs.append((face, "a close-up of the face"))
    if count == 2:
        want = ["back", "rear_threequarter", "threequarter"] if _BACK_VIEW_RE.search(prompt or "") \
            else ["threequarter", "side", "back"]
        words = dict(_ANGLE_VIEWS)
        for view in want:
            name = f"char_{key}_angle_{view}.png"
            if _staged(name):
                refs.append((name, words[view]))
                break
    return refs


def _restage_group_instruction(prompt: str, keys: list[str]) -> tuple[str, list[str]]:
    """Group version of _restage_instruction. Returns (instruction, sources):
    sources[0] is image 1 (the first person's main picture, widened by the
    caller) and the rest follow in order -- every person's block, then weapon
    plates, then one location plate."""
    letters = "ABC"
    sources: list[str] = []
    blocks: list[str] = []
    main_img: dict[str, int] = {}
    for i, key in enumerate(keys):
        refs = _group_refs(key, len(keys), prompt)
        first = len(sources) + 1
        main_img[key] = first
        sources.extend(f for f, _ in refs)
        last = len(sources)
        views = ", ".join(f"image {first + j} shows {w}" for j, (_, w) in enumerate(refs))
        span = f"image {first}" if first == last else f"images {first} to {last}"
        blocks.append(f"Character {letters[i]} is the person in {span} ({views}).")
    label = {k: f"Character {letters[i]}" for i, k in enumerate(keys)}
    weapon_idx: dict[str, int] = {}

    def sub(m: "re.Match") -> str:
        base, possessive = _split_possessive(m.group(1))
        raw = _mention_key(base)
        k = raw if raw in CHARACTER_LORAS else CHARACTER_ALIASES.get(raw)
        if k in label:
            return label[k] + ("'s" if possessive else "")
        if k:
            return CHARACTER_TRAINED_TOKEN.get(k, base) + possessive
        wkey = _mention_key(m.group(1))
        if wkey in WEAPON_REFS:
            if wkey not in weapon_idx and len(sources) < 14 and _staged(_weapon_plate(wkey, prompt)):
                sources.append(_weapon_plate(wkey, prompt))
                weapon_idx[wkey] = len(sources)
            if wkey in weapon_idx:
                return f"the weapon from image {weapon_idx[wkey]}"
        return WEAPON_HANDLE_WORDS.get(wkey, m.group(0))

    scene = _MENTION_RE.sub(sub, prompt or "").strip().rstrip(".")
    setting = ""
    for rx, plate in LOCATION_REFS:
        if rx.search(prompt or "") and _staged(plate) and len(sources) < 16:
            sources.append(plate)
            setting = (f" The setting is the place shown in image {len(sources)}: keep its "
                       "architecture, materials, colours and lighting, and place everyone inside it.")
            break
    weapon_note = (" Keep each weapon's exact shape, colours and materials as shown in its "
                   "image; do not keep the white studio background of any weapon image."
                   if weapon_idx else "")
    weapon_note += _weapon_scale_note(weapon_idx, main_img, prompt) if weapon_idx else ""
    who = " and ".join(f"Character {letters[i]}" for i in range(len(keys)))
    framing = ("framed exactly as described." if _FRAMING_RE.search(prompt or "")
               else "everyone fully in frame.")
    instruction = (
        f"Make a new cinematic photograph with {len(keys)} different people in it. "
        + " ".join(blocks)
        + f" These are {len(keys)} separate individuals: keep each person's face, head shape, "
        "eyes, eye colour, skin, hair, ears, build, height and clothing exactly as in THEIR OWN "
        "images, and never mix features between them. Do not keep the backgrounds, lighting or "
        f"framing of any reference image. Stage {who} only as described here: {scene}."
        f"{setting}{weapon_note} Photorealistic, film still, {framing}"
    )
    return instruction, sources


# Weapon handles resolve to trained assets on HIGGSFIELD only -- there are no
# weapon LoRAs here. Locally they are meaningless tokens, so they become the
# plain words instead of riding into the prompt as noise.
WEAPON_HANDLE_WORDS = {
    "biaspistol": "her energy revolver",
    "yannahsmachinepistol": "her liquid-metal machine pistol",
    "tazzsweapon": "her two-handed missile blaster",
    # Barry 2026-09-24: her weapon handle is @missle-launcher (his spelling).
    # The "missile" spelling is caught too so a corrected typo still renders.
    "misslelauncher": "her two-handed missile blaster",
    "missilelauncher": "her two-handed missile blaster",
    # 2026-08-25: B Dubb's gun got a handle so a real manufacturer's trademark
    # stops riding into every prompt. Still an ordinary Earth handgun locally.
    "bdubbsbanger": "his black pistol with chrome accents",
}


def _split_possessive(raw: str) -> tuple[str, str]:
    """Barry's rule 2026-08-14: EVERY mention of a character carries the @, and
    most sentences mention them possessively -- "@Bia-2's emitter". Before this
    split, a possessive handle matched nothing: "@Tazz's" normalised to "tazzs",
    which is in no map, so the LoRA silently did not load and the raw text rode
    into the prompt. Weapon handles are unaffected -- "@Bia's-Pistol*" does not
    END in 's, so it never enters this path."""
    for suffix in ("'s", "’s"):
        if len(raw) > len(suffix) and raw.lower().endswith(suffix):
            return raw[: -len(suffix)], suffix
    return raw, ""


def _mention_key(raw: str) -> str:
    return raw.lower().replace("'", "").replace("_", "").replace("-", "")


def mentioned_characters(prompt: str) -> list[str]:
    """Character keys named with @mentions, in order of appearance."""
    found = []
    for m in _MENTION_RE.finditer(prompt or ""):
        raw = _mention_key(_split_possessive(m.group(1))[0])
        key = raw if raw in CHARACTER_LORAS else CHARACTER_ALIASES.get(raw)
        if key and key not in found:
            found.append(key)
    return found


def normalize_mentions(prompt: str) -> str:
    """Rewrite handles to what the local pipeline can actually use: characters
    to their trained token, weapons to plain words. An @name that is neither is
    left exactly as written -- this layer never guesses."""
    def sub(m: "re.Match") -> str:
        base, possessive = _split_possessive(m.group(1))
        raw = _mention_key(base)
        key = raw if raw in CHARACTER_LORAS else CHARACTER_ALIASES.get(raw)
        if key:
            return CHARACTER_TRAINED_TOKEN.get(key, base) + possessive
        return WEAPON_HANDLE_WORDS.get(_mention_key(m.group(1)), m.group(0))

    return _MENTION_RE.sub(sub, prompt or "")


def _inject_character_lora(workflow: dict, prompt: str) -> str | None:
    """Chain a LoraLoader per @mentioned character (max 3). Stacked
    likenesses fight each other, so strength steps down as more join:
    solo 0.9, duo 0.8 each, trio 0.7 each."""
    found = [k for k in mentioned_characters(prompt)
             if os.path.isfile(os.path.join(COMFY_DIR, "models", "loras",
                                            CHARACTER_LORAS[k]))][:3]
    if not found:
        return None
    strength = {1: 0.9, 2: 0.8, 3: 0.7}[len(found)]
    if len(found) == 1:
        # Only solo is overridable -- the step-down for 2/3 exists because
        # stacked likenesses fight each other, which is a separate problem.
        strength = CHARACTER_SOLO_STRENGTH.get(found[0], strength)
    prev = "4"
    for i, key in enumerate(found):
        nid = str(90 + i)
        workflow[nid] = {
            "class_type": "LoraLoader",
            "inputs": {"model": [prev, 0], "clip": [prev, 1],
                       "lora_name": CHARACTER_LORAS[key],
                       "strength_model": strength, "strength_clip": strength},
        }
        prev = nid
    for nid, node in workflow.items():
        if int(nid) >= 90:
            continue
        for k2, v in list(node.get("inputs", {}).items()):
            if isinstance(v, list) and len(v) == 2 and v[0] == "4" and v[1] in (0, 1):
                node["inputs"][k2] = [prev, v[1]]
    return ", ".join(CHARACTER_LORAS[k] for k in found)


FP16_VAE = "sdxl.vae.safetensors"
DETAIL_LORA = "add-detail-xl.safetensors"
CONTROLNET_UNION = "controlnet-union-promax-sdxl-1.0.safetensors"
# Real-ESRGAN is BSD-3 = safe for B Dubb / Gotcho Back product work.
# 4x-UltraSharp is CC BY-NC-SA -- its author states the NC terms cover the model
# AND its outputs, so it is MOVIE ONLY and must never touch a commercial shot.
UPSCALERS = {
    "commercial": ("RealESRGAN_x4plus.pth", True, "Real-ESRGAN (BSD-3) - commercial OK"),
    "movie": ("4x-UltraSharp.pth", False, "4x-UltraSharp (CC BY-NC-SA) - NON-COMMERCIAL, film only"),
}


def _lora_file(path):
    return os.path.isfile(os.path.join(COMFY_DIR, "models", path))


def _set_latent_size(workflow, width, height):
    """Override the workflow's output size (Barry 2026-08-28: home renders
    were 1024x1024 squares, and the chamber displays them full-screen with
    background cover -- a square in a 16:9 window loses ~44% off top and
    bottom, so full-body frames read as 'too close'). Both image workflows
    hardcode EmptyLatentImage at 1024x1024; this finds that node by
    class_type rather than by id, so it works for the plain SDXL graph
    (node 5) and the IP-Adapter graph (node 7) alike. SDXL wants dimensions
    that are multiples of 64 and near its 1024x1024 training area."""
    if not width or not height:
        return
    for node in workflow.values():
        if node.get("class_type") == "EmptyLatentImage":
            node["inputs"]["width"] = int(width)
            node["inputs"]["height"] = int(height)


def _inject_extras(workflow, *, detail, pose_image, pose_strength, upscale,
                   reference_image=None, reference_weight=0.85,
                   reference_preset="PLUS (high strength)",
                   extra_lora=None, extra_lora_strength=0.8, vae_name=None):
    """Chain the optional tools onto an already-built workflow.

    Runs AFTER _inject_character_lora, and deliberately uses node ids 200+ so it
    is never touched by that function's rewiring loop (which only rewrites ids
    below 90). Whatever the character chain ended on is read back off nodes 3
    and 6 rather than recomputed, so the two stay in step.

    Returns a note dict describing what was actually applied.
    """
    note = {}
    model_src = workflow["3"]["inputs"]["model"]
    clip_src = workflow["6"]["inputs"]["clip"]

    # --- detail dial (-3..+3), 0 = off -------------------------------------
    if detail and _lora_file(os.path.join("loras", DETAIL_LORA)):
        workflow["200"] = {"class_type": "LoraLoader", "inputs": {
            "model": model_src, "clip": clip_src, "lora_name": DETAIL_LORA,
            "strength_model": float(detail), "strength_clip": float(detail)}}
        model_src, clip_src = ["200", 0], ["200", 1]
        workflow["3"]["inputs"]["model"] = model_src
        workflow["6"]["inputs"]["clip"] = clip_src
        workflow["7"]["inputs"]["clip"] = clip_src
        note["detail"] = float(detail)

    # --- drop-in LoRA (2026-08-05, owner's ask) ----------------------------
    # Any .safetensors dropped into models/loras shows up in the Studio's
    # LoRA dropdown (via /api/studio/options) and loads here -- no code edit,
    # no restart of anything but the render. Chained after the detail dial so
    # it stacks with character LoRAs the same way everything else does.
    if extra_lora and _lora_file(os.path.join("loras", os.path.basename(extra_lora))):
        workflow["202"] = {"class_type": "LoraLoader", "inputs": {
            "model": model_src, "clip": clip_src,
            "lora_name": os.path.basename(extra_lora),
            "strength_model": float(extra_lora_strength),
            "strength_clip": float(extra_lora_strength)}}
        model_src, clip_src = ["202", 0], ["202", 1]
        workflow["3"]["inputs"]["model"] = model_src
        workflow["6"]["inputs"]["clip"] = clip_src
        workflow["7"]["inputs"]["clip"] = clip_src
        note["extra_lora"] = os.path.basename(extra_lora)
        note["extra_lora_strength"] = float(extra_lora_strength)

    # --- IP-Adapter reference: the IDENTITY lane ---------------------------
    # The character-consistency skill ranks this ABOVE LoRA training for making
    # a face actually be that person. The LoRA gives species and anatomy; a
    # reference image gives the face. Chained after the LoRAs so both apply.
    if reference_image:
        # 3-5 references, not one (owner's correction 2026-08-04): a single
        # crop makes the adapter copy that crop's angle/lighting/expression;
        # 3-5 varied crops average into an embedding that captures the FACE
        # and leaves pose free. More than 5 dilutes it again -- hard cap.
        # Accepts "a.png" or "a.png,b.png,c.png"; batched embeds are averaged
        # by the IPAdapter node.
        refs = [r.strip() for r in str(reference_image).split(",") if r.strip()][:5]
        image_src = None
        for i, ref in enumerate(refs):
            load_id = str(230 + (0 if i == 0 else 2 + i))  # 230, 233, 234, ...
            workflow[load_id] = {"class_type": "LoadImage",
                                 "inputs": {"image": ref}}
            if image_src is None:
                image_src = [load_id, 0]
            else:
                batch_id = str(240 + i)
                workflow[batch_id] = {"class_type": "ImageBatch", "inputs": {
                    "image1": image_src, "image2": [load_id, 0]}}
                image_src = [batch_id, 0]
        # PLUS FACE is tuned for HUMAN facial structure and fights a face that
        # isn't one -- same reason FaceID/insightface can't see the aliens.
        # Plain PLUS preserves overall appearance instead of fitting a template,
        # so it is the default for the Talia Crew.
        workflow["231"] = {"class_type": "IPAdapterUnifiedLoader", "inputs": {
            "model": model_src, "preset": reference_preset}}
        workflow["232"] = {"class_type": "IPAdapter", "inputs": {
            "model": ["231", 0], "ipadapter": ["231", 1], "image": image_src,
            "weight": float(reference_weight), "start_at": 0.0, "end_at": 1.0,
            "weight_type": "standard"}}
        model_src = ["232", 0]
        workflow["3"]["inputs"]["model"] = model_src
        note["reference"] = ",".join(refs)
        note["reference_count"] = len(refs)
        note["reference_weight"] = float(reference_weight)
        note["reference_preset"] = reference_preset

    # --- VAE: drop-in override, else the fp16 fix --------------------------
    # Any .safetensors dropped into models/vae shows up in the Studio's VAE
    # dropdown; picking one wins over the automatic fp16-fix default.
    pick_vae = None
    if vae_name and _lora_file(os.path.join("vae", os.path.basename(vae_name))):
        pick_vae = os.path.basename(vae_name)
    elif _lora_file(os.path.join("vae", FP16_VAE)):
        pick_vae = FP16_VAE
    if pick_vae:
        workflow["201"] = {"class_type": "VAELoader", "inputs": {"vae_name": pick_vae}}
        workflow["8"]["inputs"]["vae"] = ["201", 0]
        note["vae"] = pick_vae

    # --- ControlNet pose: the only thing that controls HEIGHT/BUILD --------
    if pose_image and _lora_file(os.path.join("controlnet", CONTROLNET_UNION)):
        workflow["210"] = {"class_type": "LoadImage", "inputs": {"image": pose_image}}
        workflow["211"] = {"class_type": "ControlNetLoader",
                           "inputs": {"control_net_name": CONTROLNET_UNION}}
        # union is one file covering many control types -- declare which
        workflow["212"] = {"class_type": "SetUnionControlNetType",
                           "inputs": {"control_net": ["211", 0], "type": "openpose"}}
        workflow["213"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": workflow["3"]["inputs"]["positive"],
            "negative": workflow["3"]["inputs"]["negative"],
            "control_net": ["212", 0], "image": ["210", 0],
            "strength": float(pose_strength), "start_percent": 0.0,
            "end_percent": 0.85}}
        workflow["3"]["inputs"]["positive"] = ["213", 0]
        workflow["3"]["inputs"]["negative"] = ["213", 1]
        note["pose"] = pose_image
        note["pose_strength"] = float(pose_strength)

    # --- upscale pass, licence-aware ---------------------------------------
    if upscale:
        pick = UPSCALERS.get(upscale)
        if pick and _lora_file(os.path.join("upscale_models", pick[0])):
            workflow["220"] = {"class_type": "UpscaleModelLoader",
                               "inputs": {"model_name": pick[0]}}
            workflow["221"] = {"class_type": "ImageUpscaleWithModel", "inputs": {
                "upscale_model": ["220", 0], "image": workflow["9"]["inputs"]["images"]}}
            workflow["9"]["inputs"]["images"] = ["221", 0]
            note["upscale"] = pick[0]
            note["upscale_commercial"] = pick[1]
            note["upscale_licence"] = pick[2]
    return note


def _names_a_checkpoint(stem: str) -> bool:
    """True if `stem` (lowercase, no extension) is an SDXL checkpoint file that
    actually exists in COMFY_CHECKPOINTS_DIR. Used by the engine router so an
    explicit checkpoint name always means SDXL, default or not."""
    if not stem:
        return False
    try:
        for f in os.listdir(COMFY_CHECKPOINTS_DIR):
            if f.lower().endswith((".safetensors", ".ckpt")) and \
               os.path.splitext(f)[0].lower() == stem:
                return True
    except OSError:
        pass
    return False


async def _generate_qwen(prompt, negative_prompt, seed, width, height,
                         upscale=None) -> dict:
    """Qwen-Image text-to-image through workflows/comfy_qwen_t2i_gguf_api.json.

    Its own node ids (5 positive, 6 negative, 7 EmptySD3LatentImage, 8 KSampler,
    10 SaveImage) -- none of the SDXL helpers (_inject_character_lora,
    _inject_extras, _set_latent_size) apply, and they are deliberately not
    called: every one of them assumes SDXL's node layout and would corrupt this
    graph. Same return shape as the SDXL path so callers cannot tell them apart.

    Honest costs: ~6 min/image on a clean card (43.5 s/step x 8, measured
    2026-08-29) vs SDXL's ~15s. The negative prompt is passed through but is
    INERT -- the Lightning 8-step LoRA runs at cfg 1.0.
    """
    try:
        with open(QWEN_WORKFLOW_PATH, encoding="utf-8") as fh:
            workflow = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": f"Could not load Qwen workflow ({QWEN_WORKFLOW_PATH}): {e}"}

    used_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    # Handles have no LoRA here, so normalize them to plain words rather than
    # leaving "@Bia-2" in a diffusion prompt as junk.
    workflow["5"]["inputs"]["text"] = normalize_mentions(prompt)
    workflow["6"]["inputs"]["text"] = negative_prompt or ""
    workflow["8"]["inputs"]["seed"] = used_seed
    # Qwen-Image's own sizes are 16-multiples near ~1.4MP (1328x1328, 1140x1472,
    # 928x1664, 1664x928). Honour a caller's size, snapped to 16; default 1024^2
    # is what the A/B used and what the office's SDXL path produces today.
    if width and height:
        workflow["7"]["inputs"]["width"] = max(256, int(width) // 16 * 16)
        workflow["7"]["inputs"]["height"] = max(256, int(height) // 16 * 16)
    workflow["10"]["inputs"]["filename_prefix"] = "qwen_agent"

    # PRINT SIZE (2026-09-18, Barry: "300 dpi or better is how they should draw
    # or output it"). The SDXL upscale pass in _inject_extras cannot be reused
    # -- it rewires node "9", which is SaveImage there and VAEDecode here, so
    # calling it would corrupt this graph. Same two nodes, this graph's ids:
    # SaveImage is "10". Real-ESRGAN x4 takes 1328px to 5312px, which is ~17.7
    # inches at 300dpi -- an actual wall print rather than a word in a prompt.
    if upscale:
        pick = UPSCALERS.get(upscale)
        if pick and _lora_file(os.path.join("upscale_models", pick[0])):
            workflow["220"] = {"class_type": "UpscaleModelLoader",
                               "inputs": {"model_name": pick[0]}}
            workflow["221"] = {"class_type": "ImageUpscaleWithModel", "inputs": {
                "upscale_model": ["220", 0],
                "image": workflow["10"]["inputs"]["images"]}}
            workflow["10"]["inputs"]["images"] = ["221", 0]

    # (the one-render-at-a-time refusal + the render flag live in the public
    # generate_image wrapper now -- raised BEFORE ensure_running, 2026-09-04)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"error": f"ComfyUI rejected the Qwen workflow: {e}"}
    _begin_render("image", prompt, prompt_id=prompt_id)
    try:
        # 8 steps at 43-100 s/step depending on GPU state, plus a cold ~12GB
        # load: 1200s is a real ceiling here, not a formality like SDXL's 600.
        deadline = time.monotonic() + 1200
        entry = None
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(3.0)
                try:
                    resp = await client.get(f"{COMFY_HOST}/history/{prompt_id}")
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if prompt_id in data:
                    entry = data[prompt_id]
                    break
        if entry is None:
            return {"error": "Qwen-Image generation timed out after 1200s."}
        status = entry.get("status", {})
        if status.get("status_str") != "success":
            msgs = json.dumps(status.get("messages", []))[:400]
            if "interrupt" in msgs.lower():
                return {"error": "Generation was cancelled."}
            return {"error": f"Qwen-Image generation failed: {msgs}"}
        try:
            filename = entry["outputs"]["10"]["images"][0]["filename"]
        except (KeyError, IndexError):
            return {"error": "ComfyUI reported success but no output image was found."}
        commercial_use, licence_note = _MODEL_LICENSES.get(QWEN_UNET, _UNKNOWN_LICENSE)
        return {
            "path": os.path.join(COMFY_OUTPUT_DIR, filename),
            "model": QWEN_UNET,
            "commercial_use": commercial_use,
            "licence_note": licence_note,
            "seed": used_seed,
            "character_lora": None,
            "extras": {"engine": "qwen"},
        }
    finally:
        _end_render()


QWEN21_REF_WORKFLOW_PATH = os.path.join(os.path.dirname(COMFY_WORKFLOW_PATH),
                                        "comfy_qwen21_ref_api.json")


# 35 as of 2026-09-23 (Barry: "try 35 steps ... if this is bad, we go to 25"); was 27.
QWEN21_STEPS = int(os.environ.get("QWEN21_STEPS", "35"))
STEPS_OVERRIDE: int | None = None   # set by main.generate_image for ONE call (req.steps)
# the detailer LoRA rides every character still (Barry, 2026-09-23: "dont forget to
# use the detailer too"); 0 = off
QWEN21_CHARACTER_DETAILER = float(os.environ.get("QWEN21_CHARACTER_DETAILER", "0.8"))
# references per character: face + body only (default) or "sheets" (the 09-22 sheets/angles)
QWEN21_FACE_AND_BODY_ONLY = os.environ.get("QWEN21_REFS", "facebody").lower() != "sheets"
# CPU encoder for multi-character stills -- TESTED 2026-09-23 AND OFF: the CPU
# was still reading the prompt after 18 min where the whole GPU render took
# 8.5 (Barry: "waaaay too slow"). Kept as an opt-in (env "1") only.
QWEN21_CPU_ENCODER_FOR_GROUPS = os.environ.get("QWEN21_CPU_ENCODER_FOR_GROUPS", "0") == "1"
# vision budget per reference picture on multi-character stills (see _generate_qwen21)
QWEN21_GROUP_RESOLUTION = int(os.environ.get("QWEN21_GROUP_RESOLUTION", "768"))


async def _generate_qwen21(prompt, negative_prompt, seed, width, height,
                           detailer: float = 0.0, steps: int = None,
                           reference_image: str | None = None,
                           extra_refs: list[str] | None = None,
                           prefix: str = "qwen21_agent",
                           cpu_encoder: bool = False) -> dict:
    """Qwen-Image 2.1 text-to-image through workflows/comfy_qwen21_t2i_api.json.

    Own node ids (5 TextEncodeQwenImage21 -> positive AND negative, 7
    EmptyLatentImage, 8 KSampler, 10 SaveImage, 12 the detailer LoRA); none of
    the SDXL helpers apply. A plain EmptyLatentImage is correct here -- ComfyUI
    reshapes an empty latent to the model's own 64-channel /16 format, which is
    exactly what the LoRA author's workflow does. cfg 1.0 is the model's
    contract (guidance-free), so the negative is passed through but INERT.
    `detailer` = strength of the elusarcas detailer LoRA (0 = bypass).
    """
    # REFERENCE PATH: a filename in ComfyUI's input ROOT goes into the 2.1
    # text-encode node as image_1 (seen by the Qwen3-VL encoder AND spliced in
    # as a VAE latent) and the output latent takes the reference's size.
    # HEAVY-MODE SERVER, NOT THE IMAGE ONE (2026-09-22, Barry's monitor went
    # black mid-render and he rebooted). 2.1 is two models (8.9 GB encoder +
    # 6.9 GB DiT) that cannot both sit on the card, so ComfyUI partially unloads
    # one to load the other on EVERY prompt. On the image-mode server (HIP
    # caching allocator, no --cache-none) each swap left residue -- the log
    # showed 2.7 GB of DiT still resident when the encoder reloaded -- and the
    # fourth 2.1 job in a row died "HIP out of memory: 18 MiB, 3.58 GiB free"
    # with PyTorch's arena at a 15.1 GB peak (17.9 GB reserved, i.e. spilled).
    # That peak is what starved the desktop compositor. The video launcher
    # (PYTORCH_NO_HIP_MEMORY_CACHING=1 + --cache-none + the 1.5 GB reserve) was
    # built for exactly this two-model juggle for LTX-2.5: the encoder is
    # evicted fully before the DiT loads and the allocator never grows past
    # what is live. Same mode for the still and the LTX clip also means the
    # character video door no longer relaunches the rig between the two.
    if not await ensure_running(timeout_s=180.0, mode="video"):
        return {"error": "ComfyUI could not be started for Qwen 2.1 -- see "
                         f"{_SERVER_LOG_PATH} for startup errors."}
    wf_path = QWEN21_REF_WORKFLOW_PATH if reference_image else QWEN21_WORKFLOW_PATH
    try:
        with open(wf_path, encoding="utf-8") as fh:
            workflow = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": f"Could not load Qwen 2.1 workflow ({wf_path}): {e}"}

    used_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    workflow["5"]["inputs"]["prompt"] = normalize_mentions(prompt)
    workflow["5"]["inputs"]["negative_prompt"] = negative_prompt or ""
    workflow["8"]["inputs"]["seed"] = used_seed
    # 27 steps (2026-09-23, Barry: "i want 27 steps for him"). Every Qwen 2.1
    # render is film work (non-commercial licence), i.e. Elliot's. Env
    # QWEN21_STEPS overrides; the LoRA author's workflow used 25.
    # per-call override (the IMAGE endpoint's `steps` field, 2026-09-23) beats the default
    workflow["8"]["inputs"]["steps"] = max(4, min(60, int(steps or STEPS_OVERRIDE or QWEN21_STEPS)))
    if reference_image:
        workflow["20"]["inputs"]["image"] = os.path.basename(reference_image)
        # weapon / location plates ride as image 2 / image 3 -- the 2.1 encode
        # node's image slots autogrow, so they are just more LoadImage nodes
        extras = list(extra_refs or [])[:15]
        for i, extra in enumerate(extras):
            nid = str(21 + i)
            workflow[nid] = {"class_type": "LoadImage",
                             "inputs": {"image": os.path.basename(extra)}}
            workflow["5"]["inputs"][f"images.image_{i + 2}"] = [nid, 0]
        # 2026-09-22: the resolution=0 / shrunken-extras experiment filled the
        # card on its first run (15.8/16 GB, stopped by hand) -- reverted to
        # the PROVEN path: the node scales every picture to its ~1024 budget,
        # which is what Keth's 5-picture run finished on. Load is capped by
        # COUNT instead (one sheet per character, see character_angle_references).
        # VISION BUDGET (2026-09-23, research pass). Qwen3-VL spends one token
        # per 32x32 patch, so `resolution` is the load knob: 1024 -> ~1024
        # tokens per picture, 768 -> ~576, 512 -> ~256. resolution=0 (native)
        # was the 09-22 thrash: 1328-1600px pictures cost 1.7-2.5x MORE. And
        # exactly 1024 is a documented noise knife-edge with the VAE attached
        # (Comfy-Org/ComfyUI #16435) -- 992 is clean. Groups (the stills that
        # froze the PC) run at QWEN21_GROUP_RESOLUTION; singles at 992.
        res = QWEN21_GROUP_RESOLUTION if extras else 992
        if width and height:
            # a caller's size scales the budget too, never above the group cap
            res = min(res, max(256, int(max(width, height)) // 32 * 32))
        workflow["5"]["inputs"]["resolution"] = res if res != 1024 else 992
    elif width and height:
        workflow["7"]["inputs"]["width"] = max(256, int(width) // 16 * 16)
        workflow["7"]["inputs"]["height"] = max(256, int(height) // 16 * 16)
    strength = max(0.0, min(1.5, float(detailer or 0.0)))
    # (2026-09-23: this checked models/<file> instead of models/loras/<file>, so
    # the detailer was silently bypassed on every render that asked for it)
    if strength > 0 and _lora_file(os.path.join("loras", QWEN21_DETAILER_LORA)):
        workflow["12"]["inputs"]["strength_model"] = strength
    else:
        # bypass the LoRA node entirely so a missing file cannot fail the graph
        workflow["8"]["inputs"]["model"] = ["1", 0]
        del workflow["12"]
        strength = 0.0
    workflow["10"]["inputs"]["filename_prefix"] = prefix
    # CPU ENCODER (2026-09-23, Barry: "allocate something to cpu"). Three hard
    # PC freezes, all during the TEXT ENCODE of a multi-character still -- the
    # 8.9 GB Qwen3-VL encoder plus several reference pictures on the card. On
    # the CPU that step cannot touch the GPU at all; the card only ever holds
    # the 6.9 GB DiT. Slower encode, trades a crash for minutes.
    if cpu_encoder and QWEN21_CPU_ENCODER_FOR_GROUPS:
        workflow["2"]["inputs"]["device"] = "cpu"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"error": f"ComfyUI rejected the Qwen 2.1 workflow: {e}"}
    _begin_render("image", prompt, prompt_id=prompt_id)
    try:
        # unmeasured until the gate test: 25 steps + a cold ~17GB two-model load
        deadline = time.monotonic() + 1800
        entry = None
        full_since = None
        next_vram = time.monotonic() + 20
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(3.0)
                # CARD GUARD (2026-09-22, two hard freezes in one day): a 2.1
                # job that pins the card full for VRAM_GUARD_SECONDS is thrashing,
                # not working -- that is the state that froze the PC. Stop it.
                if time.monotonic() >= next_vram:
                    next_vram = time.monotonic() + 15
                    used = await asyncio.to_thread(gpu_dedicated_gb)
                    if used is not None and used >= VRAM_GUARD_GB:
                        full_since = full_since or time.monotonic()
                        if time.monotonic() - full_since >= VRAM_GUARD_SECONDS:
                            try:
                                await client.post(f"{COMFY_HOST}/interrupt")
                            except httpx.HTTPError:
                                pass
                            print(f"[guard] Qwen 2.1 job stopped: card at {used:.1f} GB "
                                  f"for {VRAM_GUARD_SECONDS}s", flush=True)
                            return {"error": f"Stopped to protect the PC: the card sat full "
                                    f"({used:.1f} of 16 GB) for {VRAM_GUARD_SECONDS // 60} "
                                    "minutes, which is what froze it earlier. Try fewer "
                                    "characters or references in this shot."}
                    else:
                        full_since = None
                try:
                    resp = await client.get(f"{COMFY_HOST}/history/{prompt_id}")
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if prompt_id in data:
                    entry = data[prompt_id]
                    break
        if entry is None:
            return {"error": "Qwen-Image 2.1 generation timed out after 1800s."}
        status = entry.get("status", {})
        if status.get("status_str") != "success":
            msgs = json.dumps(status.get("messages", []))[:400]
            if "interrupt" in msgs.lower():
                return {"error": "Generation was cancelled."}
            return {"error": f"Qwen-Image 2.1 generation failed: {msgs}"}
        try:
            filename = entry["outputs"]["10"]["images"][0]["filename"]
        except (KeyError, IndexError):
            return {"error": "ComfyUI reported success but no output image was found."}
        commercial_use, licence_note = _MODEL_LICENSES.get(QWEN21_UNET, _UNKNOWN_LICENSE)
        return {
            "path": os.path.join(COMFY_OUTPUT_DIR, filename),
            "model": QWEN21_UNET,
            "commercial_use": commercial_use,
            "licence_note": licence_note,
            "seed": used_seed,
            "character_lora": None,
            "extras": {"engine": "qwen21", "detailer": strength, "steps": workflow["8"]["inputs"]["steps"]},
        }
    finally:
        _end_render()


async def edit_image(sources, instruction: str, seed: int | None = None,
                     prefix: str = "qwen_edit_agent", size: tuple[int, int] | None = None) -> dict:
    """Restage or change an EXISTING picture through Qwen-Image-Edit.

    `sources`: one to three filenames already in ComfyUI's INPUT ROOT (LoadImage
    does not read subfolders). Image 1 drives identity AND the output aspect
    ratio; extra sources are addressable as "image 2" / "image 3" in the
    instruction. Same return shape as generate_image so callers cannot tell the
    engines apart. Owns the card exactly like the other two public entry points
    (refusal + flag + keep-awake, before ensure_running -- the 2026-09-04 rule).

    Prompting rules that decide whether it works (qwen-image-edit skill): say
    what to DO, never what to avoid; always carry a preservation clause; one
    change per pass. A multi-image edit BLENDS everything in the references
    (measured 2026-08-28), so a person + a scene is two sources at most.
    """
    if REEL_ACTIVE.get():
        await reel_wait_turn()
    if render_in_progress() and not await _wait_out_reel_step("edit"):
        return {"error": "A render is using the whole GPU right now. "
                         "Try again when it finishes, or hit Cancel first."}
    _owned_start()
    _keep_awake(True)
    try:
        return await _edit_image_impl(sources, instruction, seed, prefix, size)
    finally:
        _keep_awake(False)
        _clear_render_flag()


async def _edit_image_impl(sources, instruction, seed, prefix, size=None) -> dict:
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split(",") if s.strip()]
    sources = list(sources or [])[:3]
    if not sources:
        return {"error": "edit_image needs at least one source image."}
    for s in sources:
        if not os.path.isfile(os.path.join(COMFY_DIR, "input", s)):
            return {"error": f"Source '{s}' is not in ComfyUI's input folder "
                             f"({os.path.join(COMFY_DIR, 'input')})."}
    if not await ensure_running():
        return {"error": "ComfyUI could not be started -- check tools/ComfyUI exists "
                         f"and {_SERVER_LOG_PATH} for startup errors."}
    try:
        with open(QWEN_EDIT_WORKFLOW_PATH, encoding="utf-8") as fh:
            workflow = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": f"Could not load Qwen-Edit workflow ({QWEN_EDIT_WORKFLOW_PATH}): {e}"}

    used_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    workflow["4"]["inputs"]["image"] = sources[0]
    workflow["5"]["inputs"]["prompt"] = normalize_mentions(instruction)
    workflow["8"]["inputs"]["seed"] = used_seed
    workflow["10"]["inputs"]["filename_prefix"] = prefix
    if size:
        # OUTPUT SIZE (2026-10-04): an empty canvas of the size asked for instead of image 1's pixels -- image 1
        # stays a reference (TextEncodeQwenImageEditPlus), so a new scene can be drawn at a new shape. Feeding a
        # tall body pasted on a wide black canvas kept the black bars and the old background (Ilnora's first Long).
        workflow["7"] = {"class_type": "EmptySD3LatentImage",
                         "inputs": {"width": int(size[0]) // 16 * 16, "height": int(size[1]) // 16 * 16, "batch_size": 1}}
    # XXX anatomy LoRA on the editor (2026-09-16): chained AFTER the Lightning
    # LoRA (node 11) exactly the way node 11 chains off the GGUF unet, and
    # the sampler (8) repointed to it. Only when the file is on disk, the
    # switch is on, and the instruction is explicit.
    if (_xxx_on() and _prompt_is_explicit(instruction)
            and _xxx_lora_ready(XXX_QWEN_LORA)):
        workflow["12"] = {"class_type": "LoraLoaderModelOnly",
                          "inputs": {"model": ["11", 0],
                                     "lora_name": XXX_QWEN_LORA,
                                     "strength_model": XXX_QWEN_STRENGTH}}
        workflow["8"]["inputs"]["model"] = ["12", 0]
        print(f"[comfy] qwen-edit: XXX LoRA chained ({XXX_QWEN_LORA} @ {XXX_QWEN_STRENGTH})")
    # extra references -> their own LoadImage nodes, wired into image2/image3
    # of BOTH encoders so positive and negative see the same set (the shape
    # scripts/qwen_edit.py proved 2026-08-28).
    for i, src in enumerate(sources[1:3], start=2):
        node = str(20 + i)
        workflow[node] = {"class_type": "LoadImage", "inputs": {"image": src}}
        workflow["5"]["inputs"][f"image{i}"] = [node, 0]
        workflow["6"]["inputs"][f"image{i}"] = [node, 0]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"error": f"ComfyUI rejected the Qwen-Edit workflow: {e}"}
    _begin_render("image", instruction, prompt_id=prompt_id)
    try:
        # 8 steps at ~58 s/step measured (the source also goes through the VL
        # encoder), plus a cold ~11GB load: 1500s is a real ceiling for ONE
        # source. Every extra source is another VL encode and a longer
        # sequence -- measured 2026-09-14: three sources ran 277 s/step on a
        # tired card, ~40 min, and the 1500s ceiling gave up at step 6 while
        # ComfyUI kept rendering unguarded. Scale the ceiling per source.
        deadline = time.monotonic() + 1500 + 1500 * (len(sources) - 1)
        entry = None
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(3.0)
                try:
                    resp = await client.get(f"{COMFY_HOST}/history/{prompt_id}")
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if prompt_id in data:
                    entry = data[prompt_id]
                    break
        if entry is None:
            # A timed-out job must not keep running with the render flag
            # already dropped (the wrapper's finally clears it) -- an idle
            # Bonsai call would stop_server() under it. Cancel it.
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(f"{COMFY_HOST}/interrupt")
            except httpx.HTTPError:
                pass
            return {"error": f"Qwen-Image-Edit timed out after "
                             f"{1500 + 1500 * (len(sources) - 1)}s (cancelled)."}
        status = entry.get("status", {})
        if status.get("status_str") != "success":
            msgs = json.dumps(status.get("messages", []))[:400]
            if "interrupt" in msgs.lower():
                return {"error": "Generation was cancelled."}
            return {"error": f"Qwen-Image-Edit failed: {msgs}"}
        try:
            filename = entry["outputs"]["10"]["images"][0]["filename"]
        except (KeyError, IndexError):
            return {"error": "ComfyUI reported success but no output image was found."}
        commercial_use, licence_note = _MODEL_LICENSES.get(QWEN_EDIT_UNET, _UNKNOWN_LICENSE)
        return {
            "path": os.path.join(COMFY_OUTPUT_DIR, filename),
            "model": QWEN_EDIT_UNET,
            "commercial_use": commercial_use,
            "licence_note": licence_note,
            "seed": used_seed,
            "character_lora": None,
            "extras": {"engine": "qwen-edit", "sources": sources},
        }
    finally:
        _end_render()


async def generate_image(*args, **kwargs) -> dict:
    """ONE RENDER AT A TIME, and the render flag goes up BEFORE ComfyUI is
    even started (2026-09-04). Why the flag lives here and not deeper: until
    tonight only video raised it, so llm_router's render-wins guard never saw
    an image render -- an idle loop's Bonsai call ran stop_server() under a
    9-minute Qwen job and it died at step 7/8 with no error logged (SDXL's
    15s never exposed that). Then the flag was raised at submit time, and the
    post-render prewarm slipped into the ~40s gap between a request arriving
    and its submit (ensure_running's cold boot), parking Bonsai beside the
    loading model. So: refuse if a render owns the card, otherwise own it
    from the first instruction to the last, whatever path the request takes."""
    if REEL_ACTIVE.get():
        await reel_wait_turn()
    if render_in_progress() and not await _wait_out_reel_step("image"):
        return {"error": "A render is using the whole GPU right now. "
                         "Try again when it finishes, or hit Cancel first."}
    _owned_start()
    # EVICT BONSAI HERE, NOT IN EVERY CALLER (2026-10-02). The flag only stops Bonsai from STARTING; a Bonsai already on
    # the card stayed there. A backend restart's boot prewarm loaded Bonsai (9.4 GB) at 15:22 while an LTX i2v clip was
    # loading -> LTX starved and hung for 60 min. Now every render clears the card itself once its flag is up.
    try:
        import llm_router as _lr
        await _lr.unload_all_models()
    except Exception as _exc:  # noqa: BLE001 -- eviction is best-effort; the render still runs
        print(f"[render] could not unload models first: {_exc}")
    _keep_awake(True)
    try:
        return await _generate_image_impl(*args, **kwargs)
    finally:
        _keep_awake(False)
        _clear_render_flag()


def _character_engine() -> str:
    try:
        import memory as _mem
        return (_mem.get_setting("character_engine", "qwen21") or "qwen21").strip().lower()
    except Exception:
        return "qwen21"


def _routes_to_qwen21(prompt, model, reference_image, pose_image, extra_lora, detail) -> bool:
    """Cheap mirror of the 2.1 branches of _generate_image_impl, used only to
    pick the launcher mode before the server comes up. Must stay in step with
    the routing below; a miss costs one relaunch, not a wrong engine."""
    want = (model or "").strip().lower()
    for ext in (".safetensors", ".ckpt", ".gguf"):
        if want.endswith(ext):
            want = want[:-len(ext)]
            break
    if want in _QWEN21_ALIASES or want in _QWEN21_DETAIL_ALIASES:
        return True
    if not CHARACTER_RESTAGE_ENABLED or reference_image or pose_image or extra_lora or detail:
        return False
    if want in _SDXL_ALIASES or _names_a_checkpoint(want):
        return False
    chars = mentioned_characters(prompt)
    if not (1 <= len(chars) <= GROUP_MAX) or not all(character_reference(k) for k in chars):
        return False
    try:
        import memory as _mem
        return (_mem.get_setting("character_engine", "qwen21") or "qwen21").strip().lower() == "qwen21"
    except Exception:
        return True


async def _generate_image_impl(
    prompt: str,
    negative_prompt: str | None = None,
    model: str | None = None,
    seed: int | None = None,
    detail: float = 0.0,
    pose_image: str | None = None,
    pose_strength: float = 0.6,
    upscale: str | None = None,
    reference_image: str | None = None,
    reference_weight: float = 0.85,
    reference_preset: str = "PLUS (high strength)",
    extra_lora: str | None = None,
    extra_lora_strength: float = 0.8,
    vae_name: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    """Run the project's text-to-image workflow with the given parameters.
    No word cap here: the old 40-word truncation guarded a TensorStack
    chunking crash that doesn't exist in ComfyUI -- longer, richer prompts
    are now allowed and encouraged."""
    # A job that will route to Qwen-Image 2.1 (explicit fence, or a one-character
    # restage with the qwen21 engine) wants the HEAVY server config from the
    # start -- launching image mode here and relaunching inside _generate_qwen21
    # would cost a wasted ~30-50 s cold boot. Mismatch is only a relaunch, never
    # a wrong render, so this predicate only has to be right most of the time.
    _mode = "video" if _routes_to_qwen21(prompt, model, reference_image, pose_image,
                                          extra_lora, detail) else "image"
    if not await ensure_running(timeout_s=180.0 if _mode == "video" else 120.0, mode=_mode):
        return {
            "error": "ComfyUI could not be started -- check tools/ComfyUI exists "
            f"and {_SERVER_LOG_PATH} for startup errors."
        }

    # ENGINE ROUTING (2026-09-04): Qwen-Image by default, SDXL only when something
    # SDXL-ONLY is in play. The character LoRAs, IP-Adapter references, ControlNet
    # pose, the detail dial and drop-in LoRAs are all SDXL machinery -- Qwen cannot
    # load any of them, so a prompt that needs them keeps the engine that has them.
    # An explicit ```model``` fence wins in both directions.
    want = (model or "").strip().lower()
    # strip only a REAL model extension -- os.path.splitext would read the ".0"
    # in "RealVisXL_V5.0_fp16" as an extension and route the default checkpoint
    # to Qwen (caught by the routing unit test, 2026-09-04)
    want_key = want
    for ext in (".safetensors", ".ckpt", ".gguf"):
        if want.endswith(ext):
            want_key = want[:-len(ext)]
            break
    # Qwen-Image 2.1 ONLY by explicit fence (non-commercial, film only) -- it
    # wins over everything, including the character restage below.
    if want_key in _QWEN21_ALIASES or want_key in _QWEN21_DETAIL_ALIASES:
        return await _generate_qwen21(
            prompt, negative_prompt, seed, width, height,
            detailer=0.8 if want_key in _QWEN21_DETAIL_ALIASES else 0.0,
            reference_image=reference_image)
    forced_qwen = want_key in _QWEN_ALIASES
    # An explicit checkpoint NAME forces SDXL. Checked against the files on disk,
    # not against "did _resolve_model change its answer" -- RealVisXL is the
    # default, so naming it explicitly used to look like naming nothing and fell
    # through to Qwen (caught by the routing unit test, 2026-09-04).
    forced_sdxl = want_key in _SDXL_ALIASES or _names_a_checkpoint(want_key)
    chars = mentioned_characters(prompt)
    # CHARACTER RESTAGE (2026-09-14): exactly one character named, nothing
    # else SDXL-only in play, a whole-figure reference staged for them, and
    # no explicit SDXL fence -> restage the reference through Qwen-Edit.
    # The render flag is already held by the generate_image wrapper, so this
    # calls the impl directly (edit_image's own wrapper would refuse).
    # GROUP DOOR: 2-3 characters, every one with a staged reference, on the
    # qwen21 engine -> one still with each person's own labelled pictures.
    if (CHARACTER_RESTAGE_ENABLED and 2 <= len(chars) <= GROUP_MAX and not forced_sdxl
            and not (reference_image or pose_image or extra_lora or detail)
            and all(character_reference(k) for k in chars)
            and _character_engine() == "qwen21"):
        instruction, sources = _restage_group_instruction(prompt, chars)
        portrait_ask = bool(width and height and height > width)
        first = sources[0] if portrait_ask else _wide_reference(sources[0])
        result = await _generate_qwen21(
            instruction, negative_prompt, seed, width, height,
            reference_image=first, extra_refs=sources[1:], prefix=f"char_{'_'.join(chars)}",
            cpu_encoder=True, detailer=QWEN21_CHARACTER_DETAILER)
        if "error" not in result:
            result["extras"] = dict(result.get("extras") or {}, engine="qwen21-group",
                                    characters=list(chars), references=len(sources))
        return result
    if (CHARACTER_RESTAGE_ENABLED and len(chars) == 1 and not forced_sdxl
            and not (reference_image or pose_image or extra_lora or detail)):
        ref = character_reference(chars[0])
        if ref:
            portrait_ask = bool(width and height and height > width)
            src = ref if portrait_ask else _wide_reference(ref)
            # CHARACTER ENGINE (2026-09-22, Barry: "the images look great, so
            # we need to teach Elliot the settings so he can generate great
            # videos as well with this accuracy of my characters"). Qwen-Image
            # 2.1's reference path held Vor'Shara's four eyes and Keth's whole
            # look from the same char_ref_* files at ~20 s of sampling, so it
            # is the character engine now -- for the still button AND for the
            # start frame the video door renders. Live setting, no restart:
            #   memory.set_setting("character_engine", "qwen-edit")  # revert
            # Film-only by construction: these characters are the film.
            try:
                import memory as _mem
                engine = (_mem.get_setting("character_engine", "qwen21") or "qwen21").strip().lower()
            except Exception:
                engine = "qwen21"
            # Front-face close-up rides as image 2 on the 2.1 engine only.
            angles = character_angle_references(chars[0]) if engine == "qwen21" else None
            instruction, extras = _restage_instruction(prompt, chars[0], angle_refs=angles)
            if engine == "qwen21":
                result = await _generate_qwen21(
                    instruction, negative_prompt, seed, width, height,
                    reference_image=src, extra_refs=extras, prefix=f"char_{chars[0]}",
                    detailer=QWEN21_CHARACTER_DETAILER)
                if "error" not in result:
                    result["extras"] = dict(result.get("extras") or {},
                                            engine="qwen21-restage",
                                            character=chars[0])
                return result
            result = await _edit_image_impl(
                [src] + extras, instruction, seed, f"char_{chars[0]}")
            if "error" not in result:
                result["extras"] = dict(result.get("extras") or {},
                                        engine="qwen-edit-restage",
                                        character=chars[0])
            return result
    needs_sdxl = bool(reference_image or pose_image or extra_lora or detail
                      or chars)
    if forced_qwen or (not forced_sdxl and not needs_sdxl):
        return await _generate_qwen(prompt, negative_prompt, seed, width, height,
                                    upscale=upscale)

    try:
        with open(COMFY_WORKFLOW_PATH, encoding="utf-8") as fh:
            workflow = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": f"Could not load workflow JSON ({COMFY_WORKFLOW_PATH}): {e}"}

    used_model = _resolve_model(model)
    used_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    workflow["4"]["inputs"]["ckpt_name"] = used_model
    used_lora = _inject_character_lora(workflow, prompt)
    # Handles in, trained tokens out (see normalize_mentions). The LoRA lookup
    # above runs on the original text so both spellings find the same file.
    workflow["6"]["inputs"]["text"] = normalize_mentions(prompt)
    if negative_prompt:
        workflow["7"]["inputs"]["text"] = negative_prompt
    workflow["3"]["inputs"]["seed"] = used_seed
    _set_latent_size(workflow, width, height)
    extras = _inject_extras(workflow, detail=detail, pose_image=pose_image,
                            pose_strength=pose_strength, upscale=upscale,
                            reference_image=reference_image,
                            reference_weight=reference_weight,
                            reference_preset=reference_preset,
                            extra_lora=extra_lora,
                            extra_lora_strength=extra_lora_strength,
                            vae_name=vae_name)

    # (one-at-a-time refusal + render flag: see the generate_image wrapper)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"error": f"ComfyUI rejected the workflow: {e}"}
    _begin_render("image", prompt, prompt_id=prompt_id)
    try:
        # Measured 12-20s per SDXL image on this card; the long deadline is for
        # a future heavyweight model, not an expected wait.
        deadline = time.monotonic() + 600
        entry = None
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(2.0)
                try:
                    resp = await client.get(f"{COMFY_HOST}/history/{prompt_id}")
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if prompt_id in data:
                    entry = data[prompt_id]
                    break
        if entry is None:
            return {"error": "ComfyUI generation timed out after 600s."}

        status = entry.get("status", {})
        if status.get("status_str") != "success":
            # A cancel lands here: ComfyUI reports the interrupted job as not
            # successful. Say so plainly instead of "failed", which reads
            # like a bug.
            msgs = json.dumps(status.get("messages", []))[:400]
            if "interrupt" in msgs.lower():
                return {"error": "Generation was cancelled."}
            return {"error": f"ComfyUI generation failed: {msgs}"}

        try:
            images = entry["outputs"]["9"]["images"]
            filename = images[0]["filename"]
        except (KeyError, IndexError):
            return {"error": "ComfyUI reported success but no output image was found."}

        commercial_use, licence_note = _MODEL_LICENSES.get(used_model, _UNKNOWN_LICENSE)
        # An NC upscaler taints the whole output, so it downgrades the commercial
        # flag no matter how permissive the checkpoint was.
        if extras.get("upscale") and not extras.get("upscale_commercial", True):
            commercial_use = False
            licence_note = f"{licence_note} | {extras['upscale_licence']}"
        return {
            "path": os.path.join(COMFY_OUTPUT_DIR, filename),
            "model": used_model,
            "commercial_use": commercial_use,
            "licence_note": licence_note,
            "seed": used_seed,
            "character_lora": used_lora,
            "extras": extras,
        }
    finally:
        _end_render()


async def generate_video(*args, **kwargs) -> dict:
    """Same wrapper as generate_image (2026-09-04): refuse if a render owns
    the card, else raise the flag BEFORE ensure_running's mode switch / cold
    boot, so nothing idle can slip Bonsai onto the card in that window."""
    if REEL_ACTIVE.get():
        await reel_wait_turn()
    if render_in_progress() and not await _wait_out_reel_step("video"):
        cur = current_render()
        mins = f" (running {cur['elapsed_s'] // 60}m {cur['elapsed_s'] % 60}s)" if cur else ""
        return {"error": f"A render is already running{mins}. Wait for it "
                         f"to finish, or hit Cancel first -- two renders at once "
                         f"will run this card out of memory and lose both."}
    _owned_start()
    # EVICT BONSAI HERE, NOT IN EVERY CALLER (2026-10-02). The flag only stops Bonsai from STARTING; a Bonsai already on
    # the card stayed there. A backend restart's boot prewarm loaded Bonsai (9.4 GB) at 15:22 while an LTX i2v clip was
    # loading -> LTX starved and hung for 60 min. Now every render clears the card itself once its flag is up.
    try:
        import llm_router as _lr
        await _lr.unload_all_models()
    except Exception as _exc:  # noqa: BLE001 -- eviction is best-effort; the render still runs
        print(f"[render] could not unload models first: {_exc}")
    _keep_awake(True)
    try:
        return await _generate_video_impl(*args, **kwargs)
    finally:
        _keep_awake(False)
        _clear_render_flag()


async def _generate_video_impl(
    prompt: str,
    negative_prompt: str | None = None,
    duration_s: int = 5,
    # 1024x576, not 1280x720 (2026-09-04, Barry: "figure out resolution and
    # audio"). Measured under the exact office launcher (flag + reserve 1.5 +
    # cache-none): 576p 5s = 19.5 min with correct audio; 720p 5s = ~30 min, no
    # faster than LTX-2.3 ever was, because the display-safe reserve is what
    # costs 720p its headroom. The dashboard sends no size, so THIS is the
    # everyday resolution; 720p stays one explicit arg away.
    width: int = 1024,
    height: int = 576,
    # 24, not 25 (2026-09-04): LTX-2.5's native rate. The 25 inherited from 2.3
    # made 5s = 126 frames, which breaks the 8n+1 rule and silenced the audio.
    # The 2.5 workflow now snaps frames itself, so any fps is SAFE -- this just
    # stops the default from being the one value that needed snapping.
    fps: int = 24,
    seed: int | None = None,
    start_frame: str | None = None,
    voice: str | None = None,
    frames: int | None = None,
) -> dict:
    """voice / frames (2026-10-02, Ilnora's talking parts): `voice` = a WAV filename in ComfyUI's input root. With a
    start_frame it switches the i2v graph to Lightricks' official LTX-2.5 audio-to-video wiring
    (LTX-2.5_A2V_Two_Stage_Distilled): the voice is VAE-encoded, frozen with a zero noise mask in BOTH passes, and the
    original waveform is muxed into the output -- the mouth and face follow her real line at real speed. `frames`
    (8n+1) sets the exact clip length to match the voice; the caller pads the WAV to frames/fps. Omit both and
    nothing changes.

    Text-to-video WITH synchronized audio in one pass (LTX-2.3). Same
    contract shape as generate_image. Renders take minutes, not seconds --
    the poll deadline is sized for a cold first run (model streaming +
    kernel warm-up), and strictly one job runs at a time because ComfyUI
    queues internally and the whole 16GB card belongs to this.

    start_frame: filename of an image in ComfyUI's INPUT ROOT (LoadImage does
    not list subfolders). Passing one switches to the i2v workflow, where LTX
    is conditioned on that actual frame instead of inferring the character from
    words. This is the second half of the character chain -- SDXL + IP-Adapter
    produces a canon-correct still, and LTX inherits the character from it.
    Omit it and behaviour is byte-for-byte what it always was."""
    if not await ensure_running(timeout_s=180.0, mode="video"):
        return {
            "error": "ComfyUI could not be started -- check tools/ComfyUI exists "
            f"and {_SERVER_LOG_PATH} for startup errors."
        }

    # SULPHUR 2 (2026-09-15): the live `video_sulphur` setting swaps in the
    # same graphs with the Sulphur LoRA on the transformer. Read fresh per
    # render, no restart; a missing/garbled setting means plain 2.5.
    if _sulphur_on():
        workflow_path = COMFY_I2V_SULPHUR_WORKFLOW_PATH if start_frame else COMFY_VIDEO_SULPHUR_WORKFLOW_PATH
        print(f"[comfy] video: Sulphur 2 LoRA graph ({os.path.basename(workflow_path)})")
    else:
        workflow_path = COMFY_I2V_WORKFLOW_PATH if start_frame else COMFY_VIDEO_WORKFLOW_PATH
    try:
        with open(workflow_path, encoding="utf-8") as fh:
            workflow = json.load(fh)
    except (OSError, ValueError) as e:
        return {"error": f"Could not load video workflow ({workflow_path}): {e}"}

    # XXX anatomy LoRA on the LTX-2.5 transformer (2026-09-16). Node ids are
    # identical across all four 2.5 graphs: UNETLoader 236 feeds the two
    # LTXVDualCFGGuiders (231, 213) directly, or via the Sulphur LoRA at 400.
    # A new node 401 chains off whatever currently feeds the guiders, and the
    # guiders are repointed to it; the trigger word is prepended so the LoRA
    # actually fires. Same three guards as the editor.
    if (_xxx_on() and _prompt_is_explicit(prompt)
            and _xxx_lora_ready(XXX_LTX_LORA)
            and all(k in workflow for k in ("236", "231", "213"))):
        _feed = workflow["231"]["inputs"].get("model") or ["236", 0]
        workflow["401"] = {"class_type": "LoraLoaderModelOnly",
                           "inputs": {"model": _feed,
                                      "lora_name": XXX_LTX_LORA,
                                      "strength_model": XXX_LTX_STRENGTH}}
        for _g in ("231", "213"):
            workflow[_g]["inputs"]["model"] = ["401", 0]
        if XXX_LTX_TRIGGER.lower() not in (prompt or "").lower():
            prompt = f"{XXX_LTX_TRIGGER}. {prompt}"
        print(f"[comfy] video: XXX LoRA chained ({XXX_LTX_LORA} @ {XXX_LTX_STRENGTH}, trigger added)")

    if start_frame:
        # LoadImage resolves against ComfyUI's input ROOT only -- a path with
        # directories in it will not resolve, so fail loudly here rather than
        # letting ComfyUI reject the whole graph with a less obvious error.
        frame_path = os.path.join(COMFY_DIR, "input", start_frame)
        if not os.path.isfile(frame_path):
            return {
                "error": f"start_frame '{start_frame}' not found in ComfyUI's input "
                f"folder ({os.path.join(COMFY_DIR, 'input')}). Copy the still there "
                "first -- LoadImage does not read subfolders."
            }
        workflow["325"]["inputs"]["image"] = start_frame

    used_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    workflow["266"]["inputs"]["value"] = prompt
    if negative_prompt:
        workflow["247"]["inputs"]["text"] = negative_prompt
    workflow["257"]["inputs"]["value"] = int(width)
    workflow["258"]["inputs"]["value"] = int(height)
    # Owner's target (2026-07-31): up to 15-second clips -- the slim model
    # exists for exactly this. Frame count scales memory hard; the 15s
    # ceiling is his stated max.
    workflow["225"]["inputs"]["value"] = max(1, min(int(duration_s), 15))
    workflow["260"]["inputs"]["value"] = int(fps)
    workflow["237"]["inputs"]["noise_seed"] = used_seed

    if voice and start_frame:
        if not os.path.isfile(os.path.join(COMFY_DIR, "input", voice)):
            return {"error": f"voice '{voice}' not found in ComfyUI's input folder"}
        # Official A2V wiring (node ids 600+ are new; 214/220 = the generated-audio path it replaces)
        workflow["600"] = {"class_type": "LoadAudio", "inputs": {"audio": voice}}
        workflow["601"] = {"class_type": "LTXVAudioVAEEncode", "inputs": {"audio": ["600", 0], "audio_vae": ["221", 0]}}
        workflow["602"] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": 1024, "height": 1024}}
        workflow["603"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["601", 0], "mask": ["602", 0]}}
        workflow["222"]["inputs"]["audio_latent"] = ["603", 0]      # stage 1
        workflow["229"]["inputs"]["audio_latent"] = ["603", 0]      # refine: the ORIGINAL audio, never stage 1's output
        workflow["242"]["inputs"]["audio"] = ["600", 0]             # her real voice on the file
        workflow.pop("214", None)
        workflow.pop("220", None)
    if frames:
        n = max(9, (int(frames) - 1) // 8 * 8 + 1)                  # 8n+1
        workflow["225"]["inputs"]["value"] = n
        workflow["277"]["inputs"] = {"values.a": ["225", 0], "expression": "a"}

    # ONE RENDER AT A TIME -- the guard that was missing (2026-08-16).
    # Diagnosed from ComfyUI's own history: three jobs errored, two of them
    # overlapping, and the failure was
    #   "HIP out of memory. Tried to allocate 288.00 MiB... 14.98 GiB is free"
    # -- an allocation failure on a nearly EMPTY card, which is what a second
    # LTX job looks like when it lands while the first still owns the model.
    # ComfyUI queues jobs, but LTX-2.3 fp8 is ~27GB streaming through a 16GB
    # card: two in flight is not a queue, it is a crash. Refusing here is
    # kinder than a 7-minute wait that ends in an out-of-memory trace, and it
    # protects the render already in progress, which would otherwise die too.
    # (refusal + render flag: see the generate_video wrapper above)
    try:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": workflow})
                resp.raise_for_status()
                prompt_id = resp.json()["prompt_id"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            return {"error": f"ComfyUI rejected the video workflow: {e}"}
        _begin_render("video", prompt, prompt_id=prompt_id)

        deadline = time.monotonic() + 3600
        entry = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(5.0)
                try:
                    resp = await client.get(f"{COMFY_HOST}/history/{prompt_id}")
                    data = resp.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if prompt_id in data:
                    entry = data[prompt_id]
                    break
        if entry is None:
            return {"error": "Video generation timed out after 60 minutes."}
    finally:
        _end_render()
        # Free the GPU the moment the render ends (2026-07-31): the 27GB
        # model staying resident caused a full system freeze when the owner
        # simply tried to PLAY the finished clip -- playback needed the
        # same card the engine was still hogging. Cost: the next render
        # reloads the model; worth it, the machine is instantly normal
        # after every render.
        await unload()

    status = entry.get("status", {})
    if status.get("status_str") != "success":
        msgs = json.dumps(status.get("messages", []))[:400]
        if "interrupt" in msgs.lower():
            return {"error": "Video generation was cancelled."}
        return {"error": f"Video generation failed: {msgs}"}

    # SaveVideo's history shape differs from images -- find whatever file
    # any output node reported rather than hardcoding one key.
    out_file = None
    for node_out in entry.get("outputs", {}).values():
        for key in ("video", "videos", "images", "gifs"):
            items = node_out.get(key)
            if isinstance(items, list) and items and items[0].get("filename"):
                item = items[0]
                out_file = os.path.join(
                    COMFY_OUTPUT_DIR, item.get("subfolder", ""), item["filename"]
                )
                break
        if out_file:
            break
    if not out_file:
        return {"error": "Video reported success but no output file was found."}

    return {
        "path": out_file,
        "model": VIDEO_MODEL_NAME,
        "commercial_use": True,
        "licence_note": _VIDEO_LICENSE_NOTE,
        "seed": used_seed,
    }
