"""
Central configuration for the agent company.

Nothing in here costs money by default. Claude is only called when an
agent's `backend` is explicitly set to "claude" AND you've supplied an
API key. Everything else runs on your local Ollama instance for free.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads a local .env file if present (never commit this file)

# --- Claude (optional, pay-per-use) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# --- Ollama (local, free) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# huihui_ai/qwen3-abliterated:8b-v2 -- uncensored via abliteration (removes
# the refusal direction via activation editing, not RLHF retraining), same
# Qwen3 architecture/chat template as the prior qwen3.5:9b default so
# nothing else needed rewiring. Chosen after two other candidates failed
# real testing: hermes3:8b fixed refusals but broke image-fence following
# and flattened personality; huihui_ai/gemma-4-abliterated:12b was
# confirmed via direct timing test to take 120s+ just to load and then
# hard-timeout (300s) on a real request -- unusable regardless of content
# permissiveness. This one is 5GB (vs Gemma's 7.6GB) and loads in ~9s,
# confirmed via a raw timed API call.
# Real bug found while testing update_checker.py: this was still pointing
# at "huihui_ai/qwen3-abliterated:8b-v2", the model that got deliberately
# deleted from disk during the later "final model decision" cleanup (see
# memory) -- this default was never updated when that swap happened, so
# every update check (and any code path relying on this as a fallback
# default rather than an explicit resolved model) was silently checking a
# model that no longer exists locally.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "huihui_ai/qwen3.5-abliterated:9b")

# --- SearXNG (local, free, optional -- see AgentCompanyBackend/searxng/) ---
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")

# --- Bonsai (local, free -- the office's main model) ---
# Ternary Bonsai 27B (PrismML) served by the PrismML llama.cpp fork's
# llama-server -- a 27B-class model in ~7.5GB of VRAM thanks to ternary
# 2-bit quantization. Runs OUTSIDE Ollama (stock llama.cpp can't load
# ternary Q2_0; only the PrismML fork can), so it's managed as its own
# provider: bonsai_llm.py starts/stops the server process on demand and
# speaks llama-server's OpenAI-compatible API. Port 8811 deliberately --
# llama-server's default 8080 is already claimed by SEARXNG_URL above
# (dormant but configured), and AmuseBridge owns 8757.
BONSAI_HOST = os.getenv("BONSAI_HOST", "http://127.0.0.1:8811")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
# ===========================================================================
# ⚠️ CORRECTION 2026-09-28: THIS BANNER IS STALE. LIVE IS BONSAI 2 since
# 2026-09-24 (BONSAI_MODEL_NAME "Ternary-Bonsai-2-27B", HIP server, q8_0 KV,
# 98304) -- read the actual values below, and CLAUDE.md "Models (live)". The
# banner is kept as written because it records the 09-21 -> 09-24 period.
# ===========================================================================
# LIVE TODAY: BONSAI 1 (back since 2026-09-21, Barry: "Bonsai 1 is the 27b.
# switch it."). All four values below are Bonsai 1's and MUST MOVE TOGETHER:
#   weights  models/bonsai/Ternary-Bonsai-27B-Abliterated-LowDeg-Q2_0.gguf
#   mmproj   models/bonsai/Ternary-Bonsai-27B-mmproj-BF16.gguf
#   server   tools/llama-prism/vulkan/llama-server.exe
#   window   98304 WITH a q8_0 KV cache (BONSAI_KV_TYPE) -- f16 at 98304 spills
# plus BONSAI_MODEL_NAME, plus the DB setting (memory.set_active_generation),
# plus killing llama-server so it relaunches on the new files. Sophie's first
# attempt on 09-21 changed only the weights line and left Bonsai 2's HIP
# server, projector and 81920 window behind -- a mismatched build. Full
# procedure: knowledge/engineering/swapping-the-bonsai-model.md.
# EVERYTHING BELOW ABOUT BONSAI 2 IS HISTORY -- kept for the measurements.
# Bonsai 2 files are still on disk in models/bonsai2 + tools/llama-prism/hip.
# ===========================================================================
# (history) BONSAI 2 FROM 2026-09-18 TO 09-21 (Barry: "i need elliot to have the room he
# needs"). Qwen3.8-27B backbone, ~75% LINEAR attention, abliterated PQ2_0 from
# Hikari07jp -- the same publisher as the Bonsai 1 build this replaces, and
# byte-exact against the official PQ2_0 (7,206,168,928), which proves the
# abliteration edits ternary digits in place and never requantises.
#
# WHY IT WON, measured on this card (data/elliot_window_bonsai2_2026-09-18.json
# and data/bench_bonsai2_2026-09-18.json, replies spot-checked):
#   * Elliot's real seat prompt is 44,456 tokens. At the old 49152 he came back
#     EMPTY -- ~4,700 tokens left for reasoning, tool results and the answer.
#     At 98304 he writes a full correct block, on canon, with the fence.
#   * At 98304 this model generates 39.2 tok/s where BONSAI 1 managed 3.7 --
#     more than 10x, and the whole reason the 98304 window was abandoned in
#     September. Linear attention is what makes the long KV cheap.
#   * Hard logic 5/5 in 42.8s (Bonsai 1: 5/5 in 120.7s), explicit vocab 4/4
#     through the real call path, 0 refusals, AOV trap passed on a human read.
# ⚠️ It REASONS FAR MORE than Bonsai 1 (21-26K chars on creative work vs
# 2-14K), so creative turns are slower. Barry's ruling: that is a dial, tune it
# via --reasoning-budget / think_budget_override rather than reverting.
#
# ⚠️ PQ2_0 (7.21GB), NOT the 5.95GB PTQ1_0 everyone quotes -- PTQ1_0's kernels
# are NVIDIA-only and fall back to dequantise+BLAS on this card.
#
# ROLLBACK is doing nothing: Bonsai 1's weights, its mmproj and the Vulkan
# binary are all still on disk. Put the three "models/bonsai/..." +
# "vulkan" paths back (see data/backup_config_before_bonsai2_2026-09-18.py)
# and set BONSAI_NUM_CTX back to 49152.
BONSAI_MODEL_PATH = os.getenv(
    "BONSAI_MODEL_PATH",
    os.path.join(_PROJECT_ROOT, "models", "bonsai2",
                 "Ternary-Bonsai-2-27B-Abliterated-PQ2_0.gguf"),
)
# Vision tower for image input -- loaded by llama-server alongside the main
# model so Bonsai can accept images through the same OpenAI-style API.
# ⚠️ THE PROJECTOR IS PER-MODEL. Bonsai 1's mmproj on Bonsai 2 is a mismatched
# tower: a load failure at best, silent garbage on image input at worst.
BONSAI_MMPROJ_PATH = os.getenv(
    "BONSAI_MMPROJ_PATH",
    os.path.join(_PROJECT_ROOT, "models", "bonsai2",
                 "Ternary-Bonsai-2-27B-mmproj-BF16.gguf"),
)
# (history -- Bonsai 1 runs on VULKAN, the path below) HIP was for Bonsai 2: its packed tensors have no fast Vulkan path (they
# fall back to CPU), and the Vulkan build predates the format entirely. The
# HIP build reports `ROCm0: AMD Radeon RX 9070 XT`, needs no extra runtime
# (it ships hipBLAS/hipBLASLt; amdhip64 comes from the driver in System32),
# and its CI compiles gfx1201 -- this exact card. Every launch flag
# bonsai_llm.py passes was verified present in this build before the swap.
BONSAI_SERVER_EXE = os.getenv(
    "BONSAI_SERVER_EXE",
    os.path.join(_PROJECT_ROOT, "tools", "llama-prism", "hip", "llama-server.exe"),
)
# 65536 as of 2026-08-16 (was 32768), so Elliot is genuinely switchable to
# Bonsai from the dashboard (Barry: "elliot can be switchable too").
# MEASURED, not assumed (scripts/probe_bonsai_elliot_64k.py): the model's
# n_ctx_train is 262,144, and at 65,536 Elliot's real full prompt (35,337
# tokens after the same-day grammar unpin) loaded and answered a canon
# question correctly on this 16GB card -- llama-server's fit-params pass
# accepted it, prefill 883 tok/s, generation 45.2 tok/s, ~66s for the
# first (uncached) full-prompt message. The old 32K reasoning ("context
# VRAM starves everything") predates the fit-params behaviour and the
# probe; if VRAM trouble ever shows up, drop back via the env var and
# re-run the probe before theorising.
# 65536 -> 98304 (2026-08-21). Measured that day: an Elliot production pass
# hit 69,651 tokens -- his baseline sits ~64K, i.e. ~98% of the old window,
# and any injection or long history tipped it into a context error + silent
# 9b-truncation garbage. n_ctx_train is 262,144, so the cap is VRAM caution,
# not the model. If generation collapses to ~6 tok/s (the spill signature,
# see the 2026-08-16 prewarm note) or fit fails: revert via env var or this
# default and re-measure.
# 98304 -> 49152 on 2026-08-21, paired with -np 2 in bonsai_llm.py: two
# cache slots of 49152 each = the same total KV memory as the old single
# 98304 slot (the proven 16GB fit). Elliot's canon diet (anchors card
# instead of the 100K pin) brought his worst-case prompt to ~36K tokens, so
# 49152 per slot holds him with margin -- and the second slot means
# switching agents no longer wipes the cache (the server routes each
# request to the slot with the longest matching prefix).
#
# BACK TO 98304 (2026-09-11, Barry: "fix elliot, get him back on bonsai").
# The 49152 figure above assumed TWO slots; -np went back to 1 the same day
# (see bonsai_llm), so the server has been running ONE 49152 slot -- half the
# proven KV budget. Elliot's seat crept back to 146K always-on chars (~37K
# tokens) + ~12K of tool schemas, and llama-server refused his board turns:
# "request (50842 tokens) exceeds the available context size (49152)" -- every
# one fell back to the 9b silently. One slot at 98304 is exactly the config
# measured 2026-08-21 (69,646-token prompt loads, prefill 760 tok/s, 38.4
# tok/s, fits the 16GB card). Env var still overrides.
# ⚡ 49152 -> 98304 ON 2026-09-18, AND THIS TIME IT HOLDS -- because the model
# changed, not the caution. Every reversal above was Bonsai 1 spilling its KV
# cache at 98304 (3.7 tok/s). Bonsai 2's ~75% linear-attention backbone makes
# that cache cheap: measured on this card at 98304, 14,163 MB dedicated with
# only 675 MB shared, prefill 257 tok/s, generation 39.2 tok/s on Elliot's
# real 44,456-token prompt -- which is the ONLY window where he answers at all
# (at 49152 he returns an empty reply; see the model-path note above).
# 131072 also loads and answers but spills 2,787 MB and halves generation to
# 17.1 tok/s -- that is the reserve, not the default.
# If generation ever collapses toward ~6 tok/s, that is the spill signature:
# check the server log FIRST, then drop this via the env var.
#
# ⚡ 98304 -> 65536 ON 2026-09-20 (Barry: "it was better befor the bonsai 2...
# you over compensated"). HE WAS RIGHT, AND THE 98304 NUMBER ABOVE WAS
# MEASURED ON A CLEAN CARD, WHICH IS NOT HOW HE WORKS.
#   gate bench, nothing else on the GPU : 14,163 MB dedicated,   675 MB shared -> 39.2 tok/s
#   his actual desktop, 2026-09-20      : 13,049 MB dedicated, 1,998 MB shared -> 15.6 tok/s
# Bonsai 2 needs 14.1 GB at 98304, which leaves ~1.9 GB on a 16 GB card -- and
# chrome (743 MB) + dwm (647) + AMDChat (259) + AMDRSSrcExt (233) = 1,882 MB
# were already holding it, so ~2 GB of the model lived in shared system RAM.
# Measured flat 14.5-16.4 tok/s at EVERY prompt size (8-token replies too), so
# this was never context length or prompt bloat -- it was the spill. The
# 131072 line above is the same curve one step further out (2,787 MB shared,
# 17.1 tok/s) and corroborates it.
# Bonsai 1 was ~8 GB and had 6+ GB of headroom, which is why nothing on his
# desktop ever pushed it out and why the office felt faster before the swap.
# 65536 gives back ~1,765 MB of KV (from the 49152/98304 pair above, ~2,648 MB
# per 49,152 tokens of window) -- about exactly what was spilling.
# ⚡ 65536 -> 81920 LATER THE SAME NIGHT, and 65536 was measured against the
# wrong number. The floor is ELLIOT, and his prompt is not fixed -- it grows
# with the conversation and resets every 20 messages. 65536 was chosen against
# a 53,683-token sample; hours later, working a real scene, he hit 62,293:
#   prompt 51,956 -> 13,580 tokens left for the reply   (cap 6,144, fine)
#   prompt 62,293 ->  3,243 tokens left for the reply   (cap 6,144, NOT fine)
# Nothing errors in that state -- the server just generates until the window is
# full and stops, so the reply ends mid-sentence. The {} dialogue lines sit at
# the END of the fence, so dialogue is the first thing lost, which is exactly
# what Barry reported twice ("some dialog got cut", "i think dialog got lost").
# 81920 needs ~13.3 GB (from the 49152/98304 pair above, ~2,648 MB per 49,152
# tokens of window), so it still fits without spilling now that AMDChat and
# AMDRSSrcExt are off the card -- and gives him ~19.6K of reply room at that
# same 62,293-token prompt, three times what 65536 allowed.
# ⚠️ Watch the server log for a FULL-count prefill on a follow-up (cache miss)
# or generation falling toward ~15 tok/s (the spill signature). Either means
# this is too high for whatever else is on the GPU that day.
# ↑ the 65536/81920/98304 notes above were BONSAI 2's windows. Bonsai 1 spilled
# at 98304 with a FULL-SIZE (f16) KV cache (3.7 tok/s, 2026-09-11).
# ⚡ 98304 AGAIN ON 2026-09-22, WITH A COMPRESSED KV CACHE (Barry: "switch on the
# compressed memory for elliot"). bonsai_llm now launches with -fa on -ctk q8_0
# -ctv q8_0 (BONSAI_KV_TYPE), which halves the cache. Measured on his desktop
# (data/bench_bonsai1_kvquant_2026-09-22.json): 14.1 GB dedicated / 0.6 shared --
# no more spill than f16 at 49152 -- Elliot's 47.7K shot prompt prefill 668 tok/s
# (829 before), generation 43.0 tok/s (42.9 before), and a 66,112-token prompt
# answered at 42.5 tok/s. The window and the KV type MOVE TOGETHER: f16 at 98304
# is the spill. Revert = BONSAI_NUM_CTX=49152 + BONSAI_KV_TYPE=f16.
BONSAI_NUM_CTX = int(os.getenv("BONSAI_NUM_CTX", "98304"))
BONSAI_KV_TYPE = os.getenv("BONSAI_KV_TYPE", "q8_0")
# ⚡ BONSAI 2 AGAIN, 2026-09-24 (Barry: "yea switch it"). Every earlier Bonsai 2 run used an f16 KV
# cache -- that was the 09-20 spill. Measured on his real desktop at 98304
# (scripts/bench_bonsai2_kv_2026_09_24.py, data/bench_bonsai2_kv_2026-09-24.json):
#   f16                         16.0 GB, spilled, 45K prompt 211 s
#   q8_0/q8_0                   14.3 GB, no spill, 84 s
#   q8_0/q8_0 + mmproj on CPU   12.7 GB, no spill, ~3.6 GB room, 83 s   <- live
# buried-fact retrieval passed in all three. Rollback = data/backup_config_before_bonsai2_kvq8_2026-09-24.py
# (Bonsai 1 files untouched) + memory.set_active_generation + kill llama-server.
# Vision projector on the CPU (--no-mmproj-offload) frees ~0.9 GB of VRAM; image encoding runs on
# the CPU instead. "1" = keep it on the GPU.
BONSAI_MMPROJ_GPU = os.getenv("BONSAI_MMPROJ_GPU", "0") == "1"
# Draft-free speculative decoding (2026-09-22, Barry: "i need all my agents
# faster"). The engine drafts text the model has already seen and confirms
# several tokens per pass -- it cannot change WHAT is written, only speed.
# Measured on 3 real asks (data/bench_bonsai_ngram_2026-09-22.json):
# generation 46.4 tok/s none / 51.0 ngram-mod / 58.5 ngram-simple. Small
# samples; "none" reverts. Reading the prompt, not writing, is most of each turn.
BONSAI_SPEC_TYPE = os.getenv("BONSAI_SPEC_TYPE", "ngram-simple")
# The display name used anywhere a "model" string is shown/stored for
# Bonsai replies (tracing, the dashboard dropdown, reply stamps).
# 2026-10-17: env-overridable so a .env model block (the Swift trial) names the model it loads -- the
# hard-coded name kept saying Bonsai 2 while Swift ran, and Sophie read that as the live model.
BONSAI_MODEL_NAME = os.getenv("BONSAI_MODEL_NAME", "Ternary-Bonsai-2-27B")

# --- ComfyUI (image generation engine since 2026-07-30, replaced AmuseBridge) ---
# Local ComfyUI on ROCm (tools/ComfyUI, own py3.12 venv with torch+rocm7.2.1).
# comfy_image.py starts/stops the server on demand and drives it through its
# HTTP API. Port 8188 is ComfyUI's default and was free on this machine.
COMFY_HOST = os.getenv("COMFY_HOST", "http://127.0.0.1:8188")
# MIGRATED 2026-09-04: the office runs on the ComfyUI 0.34 install on D: (LTX-2.5
# needs 0.32+; tools/ComfyUI is 0.29.0 and stays on disk untouched as the rollback --
# revert this one line). D:\ComfyUI25\models and \input are JUNCTIONS to the C: tree
# (scripts/junction_comfyui25_to_office_models.ps1), so every direct filesystem check
# below (input/, models/loras, models/<path>) resolves to the same files as before.
# Verified before the swap: 34 LoRAs, 156 staged refs, RealVisXL, both Qwen GGUFs all
# resolve via D:; the rig lists each model exactly once; a 1024x576x5s LTX-2.5 render
# under the exact launcher config finished in 19.5 min with dialogue transcribed.
COMFY_DIR = os.getenv("COMFY_DIR", r"D:\ComfyUI25")
COMFY_PYTHON = os.getenv("COMFY_PYTHON", os.path.join(COMFY_DIR, "venv", "Scripts", "python.exe"))
COMFY_WORKFLOW_PATH = os.getenv(
    "COMFY_WORKFLOW_PATH",
    os.path.join(_PROJECT_ROOT, "workflows", "comfy_t2i_sdxl_api.json"),
)
# Checkpoints can live anywhere big (weights are 7-25GB each); default is
# inside the ComfyUI tree, override COMFY_CHECKPOINTS_DIR to move them to D:.
COMFY_CHECKPOINTS_DIR = os.getenv(
    "COMFY_CHECKPOINTS_DIR", os.path.join(COMFY_DIR, "models", "checkpoints")
)
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", os.path.join(COMFY_DIR, "output"))
COMFY_DEFAULT_MODEL = os.getenv("COMFY_DEFAULT_MODEL", "RealVisXL_V5.0_fp16.safetensors")
# Text-to-video with synchronized audio -- LTX-2.5 since 2026-09-04 (int8-convrot
# distilled transformer + Q5_K_M Gemma-4 GGUF encoder, two-stage, frames snapped
# to 8n+1). Built by scripts/build_ltx25_office_workflow_2026_09_04.py, which
# asserts the node-ID contract generate_video() substitutes into. The 2.3 graph
# (comfy_t2v_ltx_api.json) stays on disk; point this back at it to roll back.
COMFY_VIDEO_WORKFLOW_PATH = os.getenv(
    "COMFY_VIDEO_WORKFLOW_PATH",
    os.path.join(_PROJECT_ROOT, "workflows", "comfy_t2v_ltx25_api.json"),
)

# Image-to-video: same graph, but the start frame is a REAL image instead of the
# 512x512 black EmptyImage, and LTXVImgToVideoInplace is no longer bypassed.
# Kept as a SEPARATE file on purpose (owner: "i want accuracy and stability") --
# the t2v workflow above is the one that currently produces finished work and is
# left byte-for-byte untouched.
#
# Why this matters: the character stack chains IMAGE -> VIDEO. SDXL + IP-Adapter
# makes a still where the character is actually canon (Vor'Shara's four eyes,
# Keth's cranium), and that still conditions LTX -- so the video INHERITS the
# character instead of LTX being asked to infer it from words, which it cannot do.
# Until now the img2video path existed in the graph but sat bypassed with a black
# frame, i.e. every local video has been blind text-to-video.
# LTX-2.5 i2v since 2026-09-04: the 2.5 t2v graph + resize -> LTXVPreprocess ->
# two LTXVImgToVideoInplace (0.7 on stage 1, 1.0 on the upsampled latent) behind
# one bypass boolean -- the same shape as the 2.3 i2v and ComfyUI's own 2.5 i2v
# template, so node 325 (LoadImage) / 201 (bypass) keep their contract here.
COMFY_I2V_WORKFLOW_PATH = os.getenv(
    "COMFY_I2V_WORKFLOW_PATH",
    os.path.join(_PROJECT_ROOT, "workflows", "comfy_i2v_ltx25_api.json"),
)

# SULPHUR 2 ON LTX-2.5 (2026-09-15, Barry: "we need sulphur running as well").
# Same two graphs with one LoraLoaderModelOnly (node 400, sulphur_lora_rank_768
# @1.0) between the transformer and both guiders. Sulphur 2 is a 2.3-era
# finetune; Lightricks says most 2.3 LoRAs carry to 2.5, some do not -- so the
# live setting `video_sulphur` (app_settings, no restart) picks these files
# only when it reads "true". Barry flips it after judging one test clip.
COMFY_VIDEO_SULPHUR_WORKFLOW_PATH = os.getenv(
    "COMFY_VIDEO_SULPHUR_WORKFLOW_PATH",
    os.path.join(_PROJECT_ROOT, "workflows", "comfy_t2v_ltx25_sulphur_api.json"),
)
COMFY_I2V_SULPHUR_WORKFLOW_PATH = os.getenv(
    "COMFY_I2V_SULPHUR_WORKFLOW_PATH",
    os.path.join(_PROJECT_ROOT, "workflows", "comfy_i2v_ltx25_sulphur_api.json"),
)

# --- Storage ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "brain.db")

# --- Server ---
HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8420"))
