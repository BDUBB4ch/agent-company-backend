"""FLUX.1 Kontext [dev] — put an existing character into a new pose/scene from a
REFERENCE IMAGE, with no training at all.

WHY THIS EXISTS (2026-08-09): SDXL LoRA training on ComfyUI's built-in node is a
coin flip on this machine — same command, same data gave keth v3 fried, v5 good,
v7 fried, v8 fried. Kontext sidesteps training entirely: hand it one of Barry's
existing good renders and an instruction, and it keeps the identity.

⚠️ LICENCE: FLUX.1 [dev] is NON-COMMERCIAL. This is a FILM tool only.
   B Dubb Grows / Gotcho Back product and marketing images stay on
   RealVisXL_V5.0_fp16 (chosen precisely because its outputs are commercial-OK).

PROMPTING — this is an INSTRUCTION model, not a description model. Rules taken
from BFL/ComfyUI guidance, not invented here:
  * Start with an action verb: "Change", "Place", "Make". Do NOT describe a
    scene from scratch.
  * Name the subject concretely -- "the grey-skinned alien man", never "he".
  * ALWAYS add an explicit preservation clause: "while preserving his exact
    facial features, eye colour and skin tone". Without it the model replaces
    the face.
  * The bare verb "transform" tends to trigger a full overhaul -- avoid it.
  * ONE change per generation. Chain edits across runs instead of asking for a
    new background AND a new outfit at once.
  * Short prompts drift. Be specific about subject, change, and what stays.
  * 512-token prompt limit.

Settings are copied from ComfyUI's own bundled template
(flux_kontext_dev_basic.json): 20 steps, cfg 1, euler/simple, FluxGuidance 2.5.

Usage:
    python scripts/kontext_generate.py <reference.png> "<instruction>" [prefix]

The reference must already sit in tools/ComfyUI/input/ (LoadImage only lists the
input ROOT, not subfolders -- known gotcha from the IP-Adapter work).
"""
import json
import pathlib
import sys
import time
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "comfy_kontext_api.json"
INPUT_DIR = ROOT / "tools" / "ComfyUI" / "input"

SEED = 42


def build(reference: str, prompt: str, prefix: str, seed: int = SEED, reference2: str = None):
    """reference2 is OPTIONAL. When given, the two images are stitched
    side-by-side (ComfyUI's own Kontext template does this) so Kontext can take
    IDENTITY from a face close-up and WARDROBE/PROPORTION from a full-body shot.
    Barry, 2026-08-09, on whether to supply whole-body refs: "use these".
    With one reference the stitch is bypassed entirely."""
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf["4"]["inputs"]["image"] = reference
    if reference2:
        wf["14"]["inputs"]["image"] = reference2
    else:
        wf["5"]["inputs"]["image"] = ["4", 0]
        wf.pop("14", None); wf.pop("15", None)
    wf["7"]["inputs"]["text"] = prompt
    wf["11"]["inputs"]["seed"] = seed
    wf["13"]["inputs"]["filename_prefix"] = prefix
    return wf


def run(reference: str, prompt: str, prefix: str, seed: int = SEED, timeout: int = 900,
        reference2: str = None):
    for r in filter(None, (reference, reference2)):
        if not (INPUT_DIR / r).is_file():
            raise SystemExit(f"reference not found in ComfyUI input root: {r}")
    wf = build(reference, prompt, prefix, seed, reference2)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"},
    )
    pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    print(f"{prefix}: queued {pid}\n   ref={reference}\n   prompt={prompt[:120]}...", flush=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"   FAILED: {str(st.get('messages', [])[-3:])[:900]}", flush=True)
                return None
            outs = [i["filename"] for n in hist[pid].get("outputs", {}).values()
                    for i in n.get("images", [])]
            print(f"   done in {time.time()-t0:.0f}s -> {outs}", flush=True)
            return outs
        time.sleep(3)
    print("   TIMEOUT", flush=True)
    return None


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ref, prompt = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else "kontext"
    run(ref, prompt, prefix)
