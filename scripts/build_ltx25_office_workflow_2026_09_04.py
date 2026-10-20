"""Build the office's LTX-2.5 video workflow as a DROP-IN for the 2.3 one.

`comfy_image.generate_video()` substitutes into hardcoded node IDs, so the 2.5
graph has to keep exactly the same contract or the swap is not a swap:
    266 prompt (PrimitiveStringMultiline.value)   247 negative (CLIPTextEncode.text)
    257 width   258 height  (PrimitiveInt.value)  225 duration SECONDS
    260 fps                                        237 RandomNoise.noise_seed
and 277 must still compute frames as `a*b + 1` from (duration, fps).

TOPOLOGY MIRRORS 2.3 ON PURPOSE -- two stage. The 2.3 graph samples at HALF the
requested size (256/259 = a/2) and then upsamples x2, so a 1280x720 request
really samples 640x360. Building 2.5 single-stage at the full requested size
would quietly make every existing office call 2-3x heavier than it is today.
Same request in, same resolution out, is the only honest migration.

WHAT CHANGES vs 2.3, and why each one:
  * transformer: UNETLoader + the int8-convrot distilled 2.5 file, replacing
    CheckpointLoaderSimple + the 2.3 distill LoRA. Measured 2026-09-03:
    int8-convrot is ~2x faster than the GGUF on this card (58.8 vs 111.4 s/step)
    because K-quant dequantises every step and int8-convrot has native HIP
    kernels on gfx1201.
  * text encoder: CLIPLoaderGGUF (type ltxv) + the 9.51GB Q5_K_M gemma4. The
    official 14.3GB int8 encoder fills a 16GB card by itself and OOMs DURING
    ENCODE before the video model ever loads.
  * VAEs: two explicit VAELoaders. 2.5 splits them; the AUDIO one is not
    optional -- missing it is the single most common cause of a silent clip.
  * guider: LTXVDualCFGGuider at 1.0/1.0. The distilled weights have guidance
    baked in; re-applying CFG degrades output.
Sigmas are copied verbatim from ComfyUI 0.34's own LTX-2.5 template.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "workflows", "comfy_t2v_ltx25_api.json")

TRANSFORMER = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
ENCODER = "gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf"
VAE_VIDEO = "ltx-2.5-video-vae-conv-bf16.safetensors"
VAE_AUDIO = "ltx-2.5-audio-vae-bf16.safetensors"
UPSCALER = "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"

SIGMAS_BASE = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
SIGMAS_REFINE = "0.85, 0.7250, 0.4219, 0.0"
NEG = ("pc game, console game, video game, cartoon, childish, ugly, "
       "deformed, watermark, text")

W = {
    # ---- loaders -------------------------------------------------------
    "236": {"class_type": "UNETLoader",
            "inputs": {"unet_name": TRANSFORMER, "weight_dtype": "default"}},
    "243": {"class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": ENCODER, "type": "ltxv"}},
    "244": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
    "221": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
    "233": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": UPSCALER}},

    # ---- the office's substitution points (IDs are a contract) ---------
    "266": {"class_type": "PrimitiveStringMultiline",
            "inputs": {"value": "placeholder prompt"}},
    "257": {"class_type": "PrimitiveInt", "inputs": {"value": 1280}},
    "258": {"class_type": "PrimitiveInt", "inputs": {"value": 720}},
    "225": {"class_type": "PrimitiveInt", "inputs": {"value": 5}},
    "260": {"class_type": "PrimitiveInt", "inputs": {"value": 25}},
    "237": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},

    # ---- derived sizes (same expressions as the 2.3 graph) -------------
    "256": {"class_type": "ComfyMathExpression",
            "inputs": {"values.a": ["257", 0], "expression": "a/2"}},
    "259": {"class_type": "ComfyMathExpression",
            "inputs": {"values.a": ["258", 0], "expression": "a/2"}},
    "261": {"class_type": "ComfyMathExpression",
            "inputs": {"values.a": ["260", 0], "expression": "a"}},
    # FRAMES SNAP TO 8n+1 -- THE AUDIO ROOT CAUSE (2026-09-04). LTX-2.5's temporal
    # compression is 8x, so frame counts must satisfy frames % 8 == 1 (documented
    # constraint, not an inference). The 2.3 graph's `a*b+1` at the office default
    # of 25 fps gives 5*25+1 = 126, which is NOT 8n+1: the video latent got rounded
    # to 121 while the audio latent was built for 126, and the mismatch through the
    # joint sampler produced clips at -46 dBFS with an EMPTY transcript. At 24 fps
    # (121 frames) the same graph came back -25.1 dBFS, dialogue transcribed. This
    # expression makes the graph correct for ANY fps the caller passes.
    "277": {"class_type": "ComfyMathExpression",
            "inputs": {"values.a": ["225", 0], "values.b": ["260", 0],
                       "expression": "floor(a * b / 8) * 8 + 1"}},

    # ---- conditioning --------------------------------------------------
    "240": {"class_type": "CLIPTextEncode",
            "inputs": {"clip": ["243", 0], "text": ["266", 0]}},
    "247": {"class_type": "CLIPTextEncode",
            "inputs": {"clip": ["243", 0], "text": NEG}},
    "239": {"class_type": "LTXVConditioning",
            "inputs": {"positive": ["240", 0], "negative": ["247", 0],
                       "frame_rate": ["261", 0]}},

    # ---- stage 1: sample at half size ----------------------------------
    "228": {"class_type": "EmptyLTXVLatentVideo",
            "inputs": {"width": ["256", 1], "height": ["259", 1],
                       "length": ["277", 1], "batch_size": 1}},
    # frame_rate here is the INT output (index 1) -- byte-for-byte what ComfyUI's
    # own LTX-2.5 template wires (node 366 <- 359.out1). The video conditioning
    # and CreateVideo take the FLOAT (index 0), also as the template does.
    "214": {"class_type": "LTXVEmptyLatentAudio",
            "inputs": {"frames_number": ["277", 1], "frame_rate": ["261", 1],
                       "batch_size": 1, "audio_vae": ["221", 0]}},
    "222": {"class_type": "LTXVConcatAVLatent",
            "inputs": {"video_latent": ["228", 0], "audio_latent": ["214", 0]}},
    "231": {"class_type": "LTXVDualCFGGuider",
            "inputs": {"model": ["236", 0], "positive": ["239", 0],
                       "negative": ["239", 1], "video_cfg": 1.0, "audio_cfg": 1.0}},
    "209": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
    "252": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS_BASE}},
    "215": {"class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["237", 0], "guider": ["231", 0],
                       "sampler": ["209", 0], "sigmas": ["252", 0],
                       "latent_image": ["222", 0]}},
    "217": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["215", 0]}},

    # ---- stage 2: upsample x2 and refine --------------------------------
    "253": {"class_type": "LTXVLatentUpsampler",
            "inputs": {"samples": ["217", 0], "upscale_model": ["233", 0],
                       "vae": ["244", 0]}},
    "229": {"class_type": "LTXVConcatAVLatent",
            "inputs": {"video_latent": ["253", 0], "audio_latent": ["217", 1]}},
    "213": {"class_type": "LTXVDualCFGGuider",
            "inputs": {"model": ["236", 0], "positive": ["239", 0],
                       "negative": ["239", 1], "video_cfg": 1.0, "audio_cfg": 1.0}},
    "246": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
    "211": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS_REFINE}},
    "216": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
    "219": {"class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["216", 0], "guider": ["213", 0],
                       "sampler": ["246", 0], "sigmas": ["211", 0],
                       "latent_image": ["229", 0]}},
    "218": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["219", 0]}},

    # ---- decode + save --------------------------------------------------
    "251": {"class_type": "VAEDecodeTiled",
            "inputs": {"samples": ["218", 0], "vae": ["244", 0], "tile_size": 512,
                       "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}},
    # AUDIO IS DECODED FROM STAGE 2 (node 218), exactly as ComfyUI's own LTX-2.5
    # template wires it (358 <- 369.out1). A stage-1 decode was tried while
    # chasing the silence and DISPROVEN as the cause (the real cause was the
    # frame count above); community workflow notes add that the first-pass SDE
    # audio is lower quality and the refined pass should be the source.
    "220": {"class_type": "LTXVAudioVAEDecode",
            "inputs": {"samples": ["218", 1], "audio_vae": ["221", 0]}},
    "242": {"class_type": "CreateVideo",
            "inputs": {"images": ["251", 0], "audio": ["220", 0], "fps": ["261", 0]}},
    "900": {"class_type": "SaveVideo",
            "inputs": {"video": ["242", 0], "filename_prefix": "video/agent",
                       "format": "auto", "codec": "auto"}},
}

# the contract the backend relies on -- assert it rather than hope
for nid, path in [("266", "value"), ("257", "value"), ("258", "value"),
                  ("225", "value"), ("260", "value")]:
    assert nid in W and path in W[nid]["inputs"], "missing substitution point %s" % nid
assert W["247"]["class_type"] == "CLIPTextEncode" and "text" in W["247"]["inputs"]
assert "noise_seed" in W["237"]["inputs"]
assert W["277"]["inputs"]["expression"] == "floor(a * b / 8) * 8 + 1"

# every link must point at a node that exists
for nid, node in W.items():
    for field, val in node["inputs"].items():
        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
            assert val[0] in W, "%s.%s -> missing node %s" % (nid, field, val[0])

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(W, fh, indent=1)
print("wrote %s (%d nodes)" % (OUT, len(W)))

# ---------------------------------------------------------------------------
# IMAGE-TO-VIDEO VARIANT (2026-09-04) -- the second half of the character chain
# (a canon-correct SDXL/Kontext still becomes LTX's first frame). Mirrors
# ComfyUI's own video_ltx2_5_i2v template exactly: resize -> LTXVPreprocess ->
# LTXVImgToVideoInplace on the stage-1 latent (strength 0.7) AND on the
# upsampled latent (strength 1.0), both behind one bypass boolean -- which is
# also precisely the shape of the office's 2.3 i2v graph, so the office's node
# IDs and its contract are kept: comfy_image.generate_video(start_frame=...)
# sets workflow["325"]["inputs"]["image"] and expects 201 to be the bypass.
# 325 LoadImage resolves against ComfyUI's INPUT ROOT only (no subfolders).
# ---------------------------------------------------------------------------
I2V_OUT = os.path.join(ROOT, "workflows", "comfy_i2v_ltx25_api.json")
V = json.loads(json.dumps(W))   # deep copy of the t2v graph
V["325"] = {"class_type": "LoadImage", "inputs": {"image": "START_FRAME_PLACEHOLDER"}}
V["201"] = {"class_type": "PrimitiveBoolean", "inputs": {"value": False}}   # False = i2v ON
# ResizeImagesByLongerEdge, not the template's ResizeImageMaskNode: that one is a
# V3 dynamic-combo node whose API-format inputs are not the widget names, and
# the office's 2.3 i2v already uses this node with exactly these inputs.
V["235"] = {"class_type": "ResizeImagesByLongerEdge",
            "inputs": {"images": ["325", 0], "longer_edge": 1536}}
V["248"] = {"class_type": "LTXVPreprocess",
            "inputs": {"image": ["235", 0], "img_compression": 18}}
# stage 1: condition the empty latent on the frame
V["249"] = {"class_type": "LTXVImgToVideoInplace",
            "inputs": {"vae": ["244", 0], "image": ["248", 0], "latent": ["228", 0],
                       "bypass": ["201", 0], "strength": 0.7}}
V["222"]["inputs"]["video_latent"] = ["249", 0]
# stage 2: re-condition the upsampled latent so the refine keeps the frame
V["230"] = {"class_type": "LTXVImgToVideoInplace",
            "inputs": {"vae": ["244", 0], "image": ["248", 0], "latent": ["253", 0],
                       "bypass": ["201", 0], "strength": 1.0}}
V["229"]["inputs"]["video_latent"] = ["230", 0]
for nid, node in V.items():
    for field, val in node["inputs"].items():
        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
            assert val[0] in V, "i2v %s.%s -> missing node %s" % (nid, field, val[0])
assert V["325"]["class_type"] == "LoadImage" and "image" in V["325"]["inputs"]
with open(I2V_OUT, "w", encoding="utf-8") as fh:
    json.dump(V, fh, indent=1)
print("wrote %s (%d nodes)" % (I2V_OUT, len(V)))
