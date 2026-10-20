"""LTX-2.5 on the RX 9070 XT -- the measurement that decides whether we move.

Usage:  ltx25_bench_2026_09_03.py gguf|int8 [frames] [width] [height]

WHAT IS BEING TESTED, precisely: not "does it run" -- it will -- but seconds per
step against the LTX-2.3 fp8 baseline of 7-29 min for ~5s. The 2026-08-04 result
that killed LTX-2.3 GGUF on this card was K-quant dequantising EVERY step, making
a resident GGUF 4-6x slower than a streamed fp8. Two things may have changed that:
  * DISTILLED -- few-step schedule at CFG 1.0, so a per-step penalty is paid ~8
    times instead of a full schedule.
  * int8-convrot -- ComfyUI 0.34 reports native HIP kernels for it on gfx1201
    (int8_linear, dequantize_int8_convrot_weight_dtype). It does not dequantise
    per step the way K-quant does, and at 21.5GB it streams like the working
    27GB LTX-2.3 fp8 already does.
So the GGUF is the hypothesis under suspicion and int8 is its control.

SINGLE STAGE ON PURPOSE. The template ships a base+upsample graph; the 16GB
guidance is single-stage only -- the two-stage path came near the wall and hit
host swap. Stage 2 is where an OOM would come from, not stage 1.

The prompt enhancer (TextGenerateLTX2Prompt + its own gemma4_e2b encoder) is
dropped: it is a second LLM on the same card, and the office strips it from the
LTX-2.3 graph for exactly that reason.
"""
import json, os, sys, time, urllib.request, uuid

HOST = "http://127.0.0.1:8190"

WHICH = (sys.argv[1] if len(sys.argv) > 1 else "gguf").lower()
FRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 49
W = int(sys.argv[3]) if len(sys.argv) > 3 else 608
H = int(sys.argv[4]) if len(sys.argv) > 4 else 352
# TEXT ENCODER DEVICE -- the whole ballgame on a 16GB card.
#
# Run 1 (2026-09-03, GPU encoder) died like this, 25 minutes in, without ever
# reaching the video model:
#     HIP out of memory. Tried to allocate 226.00 MiB.
#     GPU has 15.92 GiB, of which 1.16 GiB is free.
#     13.84 GiB is allocated by PyTorch
# LTX-2.5 swapped 2.3's Gemma-3 encoder for a 12B GEMMA-4 one. At 14.3GB it
# fills this card by itself, partially offloads, thrashes, and then cannot find
# 226MB to finish its own encode. The DiT never got a look in.
# Encoding is a ONE-TIME cost per prompt and does not need the GPU, so putting
# it on CPU hands the whole card to the part that actually needs it.
ENC_DEVICE = sys.argv[5] if len(sys.argv) > 5 else "cpu"
FPS = 24.0

GGUF_FILE = "LTX-2.5-Distilled-Q4_K_M.gguf"
INT8_FILE = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"

# ENCODER -- the thing that decides whether this works at all on 16GB.
#   int8  = 14.3GB, fills the card alone, OOMs mid-encode without the
#           no-caching allocator (which itself costs ~2x)
#   gguf  = 9.51GB, fits with ~6GB headroom, encodes on GPU then unloads
# Default is the GGUF. env LTX25_ENC=int8 to compare against the old one.
_ENC = os.environ.get("LTX25_ENC", "gguf").lower()
ENCODER_GGUF = "gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf"
ENCODER_INT8 = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
ENCODER = ENCODER_INT8 if _ENC == "int8" else ENCODER_GGUF
VAE_VIDEO = "ltx-2.5-video-vae-conv-bf16.safetensors"   # conv VAE = the low-VRAM decoder
VAE_AUDIO = "ltx-2.5-audio-vae-bf16.safetensors"        # WITHOUT THIS THE CLIP IS SILENT

# The distilled few-step schedule, copied verbatim from ComfyUI's own LTX-2.5
# template (stage 1). 9 sigmas = 8 steps. Do NOT re-apply CFG on top of this --
# guidance is baked into distilled weights and applying it again degrades output.
SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"

# Written in LTX grammar deliberately: chronological prose with a quoted line and
# a stated tone. That is what made LTX-2.3 actually SPEAK on 2026-08-26 -- the
# historic silent clips were image-fence tag stacks, which this model resists.
PROMPT = ("A weathered man in a black hooded jacket stands alone in a dim workshop, "
          "rain streaking the window behind him. He looks down at his hands, then "
          "lifts his head toward the camera and says in a low, tired voice, "
          "\"We should not be here.\" The overhead lamp flickers once. "
          "Handheld camera, slow push in, shallow depth of field, film grain.")
NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly"

if WHICH == "int8":
    loader = {"class_type": "UNETLoader",
              "inputs": {"unet_name": INT8_FILE, "weight_dtype": "default"}}
else:
    loader = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": GGUF_FILE}}

G = {
    "1":  loader,
    # A GGUF encoder loads through ComfyUI-GGUF's CLIPLoaderGGUF (which needs the
    # gemma4 allowlist patch applied to loader.py); the int8 one is stock comfy_quant.
    "2":  ({"class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": ENCODER, "type": "ltxv"}}
           if ENCODER.endswith(".gguf") else
           {"class_type": "CLIPLoader",
            "inputs": {"clip_name": ENCODER, "type": "ltxv", "device": ENC_DEVICE}}),
    "3":  {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
    "4":  {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
    "5":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": PROMPT}},
    "6":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIVE}},
    "7":  {"class_type": "LTXVConditioning",
           "inputs": {"positive": ["5", 0], "negative": ["6", 0], "frame_rate": FPS}},
    "8":  {"class_type": "EmptyLTXVLatentVideo",
           "inputs": {"width": W, "height": H, "length": FRAMES, "batch_size": 1}},
    "9":  {"class_type": "LTXVEmptyLatentAudio",
           "inputs": {"frames_number": FRAMES, "frame_rate": FPS,
                      "batch_size": 1, "audio_vae": ["4", 0]}},
    "10": {"class_type": "LTXVConcatAVLatent",
           "inputs": {"video_latent": ["8", 0], "audio_latent": ["9", 0]}},
    "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
    "12": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
    "13": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS}},
    "14": {"class_type": "LTXVDualCFGGuider",
           "inputs": {"model": ["1", 0], "positive": ["7", 0], "negative": ["7", 1],
                      "video_cfg": 1.0, "audio_cfg": 1.0}},
    "15": {"class_type": "SamplerCustomAdvanced",
           "inputs": {"noise": ["11", 0], "guider": ["14", 0], "sampler": ["12", 0],
                      "sigmas": ["13", 0], "latent_image": ["10", 0]}},
    "16": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["15", 0]}},
    "17": {"class_type": "VAEDecodeTiled",
           "inputs": {"samples": ["16", 0], "vae": ["3", 0], "tile_size": 512,
                      "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}},
    "18": {"class_type": "LTXVAudioVAEDecode",
           "inputs": {"samples": ["16", 1], "audio_vae": ["4", 0]}},
    "19": {"class_type": "CreateVideo",
           "inputs": {"images": ["17", 0], "fps": FPS, "audio": ["18", 0]}},
    "20": {"class_type": "SaveVideo",
           "inputs": {"video": ["19", 0], "filename_prefix": "ltx25_%s" % WHICH,
                      "format": "auto", "codec": "auto"}},
}


def post(path, payload):
    req = urllib.request.Request(HOST + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


cid = str(uuid.uuid4())
print("LTX-2.5 bench: %s | %dx%d x %d frames @ %.0f fps (~%.1fs of video)"
      % (WHICH.upper(), W, H, FRAMES, FPS, FRAMES / FPS), flush=True)
try:
    r = post("/prompt", {"prompt": G, "client_id": cid})
except urllib.error.HTTPError as e:
    print("REJECTED by ComfyUI:\n" + e.read().decode()[:2000])
    raise SystemExit(1)
pid = r["prompt_id"]
print("queued: %s" % pid, flush=True)

t0 = time.time()
last = ""
while True:
    time.sleep(10)
    try:
        h = json.load(urllib.request.urlopen(HOST + "/history/" + pid, timeout=30))
    except Exception:
        continue
    if pid in h:
        st = h[pid].get("status", {})
        el = time.time() - t0
        ok = st.get("status_str") == "success"
        print("\n%s after %.1f min (%.0f s)" % ("SUCCESS" if ok else "ENDED: %s" % st,
                                                el / 60, el), flush=True)
        if ok:
            steps = SIGMAS.count(",")
            print("  ~%.1f s/step over %d steps" % (el / steps, steps))
            print("  ~%.1f s of wall time per second of video" % (el / (FRAMES / FPS)))
        for nid, out in (h[pid].get("outputs") or {}).items():
            for k, v in out.items():
                print("  output[%s].%s = %s" % (nid, k, str(v)[:200]))
        if not ok:
            print(json.dumps(st, indent=1)[:2500])
        break
    el = time.time() - t0
    msg = "  ... %.1f min elapsed" % (el / 60)
    if msg != last:
        print(msg, flush=True); last = msg
    if el > 3600:
        print("ABANDONED at 60 min -- that is a fail on its own terms.", flush=True)
        break
