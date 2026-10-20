"""Train character LoRAs through ComfyUI's NATIVE trainer nodes.

Replaces the lost scratchpad/train_lora.py. Nothing here downloads anything: the
trainer ships inside ComfyUI (comfy_extras/nodes_train.py), the base checkpoint
is already installed, and the datasets are local.

Node graph (verified against /object_info on 2026-08-04):
    CheckpointLoaderSimple -> MODEL, CLIP, VAE
    LoadImageTextDataSetFromFolder(folder) -> IMAGE, STRING(captions)
    MakeTrainingDataset(images, vae, clip, texts) -> LATENT, CONDITIONING
    TrainLoraNode(model, latents, positive, ...) -> LORA_MODEL
    SaveLoRA(lora, prefix, steps)

Existing LoRAs are NOT overwritten -- output goes to <name>_character_v2 so the
current ones stay installed and comparable. VRAM is the binding constraint on a
16GB card, so characters train ONE AT A TIME, and ComfyUI's loaded checkpoint is
freed between runs.

Usage:
    python scripts/train_character_loras.py --list
    python scripts/train_character_loras.py vorshara            # one character
    python scripts/train_character_loras.py --all               # all six, in sequence
    python scripts/train_character_loras.py vorshara --steps 400 --rank 16
"""
import argparse
import json
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "comfy_train_lora_api.json"

# folder in ComfyUI/input  ->  output lora name
CHARACTERS = {
    "bdubb": "lora_bdubb",
    "bia": "lora_bia",
    "keth": "lora_keth",
    "tazz": "lora_tazz",
    "vorshara": "lora_vorshara",
    "yannah": "lora_yannah",
}


def _post(path, payload):
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def free_vram():
    """ComfyUI keeps the checkpoint resident between runs -- on a 16GB card that
    has to go before the next training run allocates."""
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
        print("   freed ComfyUI VRAM")
    except Exception as e:
        print(f"   (could not free VRAM: {e})")


def _install(name, tag="v2"):
    """SaveLoRA writes to ComfyUI's OUTPUT dir with a step/counter suffix, which
    is not where LoraLoader looks. Copy the newest match into models/loras under a
    clean name so it is actually selectable. The original <name>_character
    .safetensors is never touched -- the tagged run sits beside it for
    comparison/rollback.

    The tag MUST be bumped for each new run (--tag v3, v4, ...): reusing a tag
    overwrites that file in models/loras. The raw ComfyUI output in output/loras
    keeps its own step/counter suffix and is never clobbered."""
    out_dir = ROOT / "tools/ComfyUI/output/loras"
    dest_dir = ROOT / "tools/ComfyUI/models/loras"
    hits = sorted(out_dir.glob(f"{name}_character_{tag}*.safetensors"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        print(f"   ! trained but no output file found in {out_dir}")
        return False
    dest = dest_dir / f"{name}_character_{tag}.safetensors"
    shutil.copyfile(hits[0], dest)
    print(f"   installed -> {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
    return True


PRIOR_STEPS_ASSUMED = 400


def _steps_named_alias(lora_name):
    """TrainLoraNode reads the prior step count OUT OF THE FILENAME:

        existing_steps = int(existing_lora.split("_steps_")[0].split("_")[-1])

    So an existing LoRA MUST be named "<...>_<N>_steps_<...>.safetensors".
    The hand-installed v1 files are just "<name>_character.safetensors", which
    makes that int() raise ValueError and kills the run in ~30s. Rather than
    rename Barry's working LoRAs (they are referenced by comfy_image's
    @mention map), drop a compliant ALIAS copy beside them and train from that.

    The assumed prior step count is cosmetic -- it only affects the saved
    filename's step total, not the weights.
    """
    if "_steps_" in lora_name:
        return lora_name
    loras = ROOT / "tools/ComfyUI/models/loras"
    src = loras / lora_name
    if not src.is_file():
        print(f"   ! {lora_name} not found in {loras}")
        return lora_name
    alias = f"{src.stem}_{PRIOR_STEPS_ASSUMED}_steps_v1.safetensors"
    dest = loras / alias
    if not dest.is_file():
        shutil.copyfile(src, dest)
        print(f"   created trainer-compatible alias: {alias}")
    return alias


def train(name, folder, steps, rank, lr, seed, timeout_s, continue_from=None, tag="v2"):
    """continue_from: an existing LoRA filename to keep training INSTEAD of
    starting from scratch.

    Why this is the default path (measured 2026-08-04): a from-scratch run on
    Vor'Shara (27 images, 400 steps, lr 1e-4) produced a LoRA that renders the
    same as NO LoRA at all -- the character never appeared. The existing v1 does
    hold her. Continuing from v1 has a floor that from-scratch does not: the
    character is already in the weights, so the worst case is "unchanged", not
    "lost". Corollary: since 400 steps barely moved the weights from scratch, a
    continuation run needs materially MORE steps to shift anything.
    """
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf["2"]["inputs"]["folder"] = folder
    wf["4"]["inputs"]["steps"] = steps
    wf["4"]["inputs"]["rank"] = rank
    wf["4"]["inputs"]["learning_rate"] = lr
    wf["4"]["inputs"]["seed"] = seed
    if continue_from:
        # rank MUST match the existing LoRA or the tensors will not line up
        continue_from = _steps_named_alias(continue_from)
        wf["4"]["inputs"]["existing_lora"] = continue_from
    # never clobber the currently installed LoRA -- the tagged run sits alongside it
    wf["5"]["inputs"]["prefix"] = f"loras/{name}_character_{tag}"
    wf["5"]["inputs"]["steps"] = steps

    n_imgs = len(list((ROOT / "tools/ComfyUI/input" / folder).glob("*.png")))
    print(f"\n=== {name}: {n_imgs} images, {steps} steps, rank {rank}, lr {lr} ===")
    free_vram()

    try:
        pid = _post("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    except urllib.error.HTTPError as e:
        print(f"   SUBMIT FAILED ({e.code}):\n{e.read().decode()[:1200]}")
        return False

    print(f"   queued {pid}")
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            status = hist[pid].get("status", {})
            if status.get("status_str") == "error":
                print(f"   FAILED after {time.time()-t0:.0f}s")
                for m in status.get("messages", [])[-4:]:
                    print("   ", str(m)[:400])
                return False
            print(f"   DONE in {(time.time()-t0)/60:.1f} min")
            _install(name, tag)
            return True
        time.sleep(10)
    print(f"   TIMEOUT after {timeout_s}s (training may still be running)")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("characters", nargs="*", help="names, or use --all")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--tag", default="v2",
                    help="output name suffix -> <name>_character_<tag>.safetensors. "
                         "BUMP THIS every run (v3, v4...) or you overwrite the "
                         "previous run's installed file.")
    ap.add_argument("--continue-from-v1", action="store_true",
                    help="keep training the EXISTING <name>_character.safetensors "
                         "instead of starting from scratch (recommended -- see train())")
    ap.add_argument("--continue-from",
                    help="continue from a SPECIFIC lora filename in models/loras "
                         "(e.g. vorshara_character_v3.safetensors). Overrides "
                         "--continue-from-v1. Rank must match the existing file.")
    ap.add_argument("--folder",
                    help="override the dataset folder under ComfyUI/input "
                         "(e.g. lora_vorshara_v4). Default is the mapping above.")
    args = ap.parse_args()

    if args.list:
        for n, f in CHARACTERS.items():
            d = ROOT / "tools/ComfyUI/input" / f
            print(f"  {n:<10} {len(list(d.glob('*.png'))):>4} images  ({f})")
        return

    names = list(CHARACTERS) if args.all else args.characters
    if not names:
        ap.error("give character names or --all (see --list)")
    bad = [n for n in names if n not in CHARACTERS]
    if bad:
        ap.error(f"unknown: {bad}. Known: {list(CHARACTERS)}")

    results = {}
    for n in names:
        cont = args.continue_from or (
            f"{n}_character.safetensors" if args.continue_from_v1 else None)
        folder = args.folder or CHARACTERS[n]
        results[n] = train(n, folder, args.steps, args.rank, args.lr,
                           args.seed, args.timeout, continue_from=cont, tag=args.tag)
    print("\n=== summary ===")
    for n, ok in results.items():
        print(f"  {n:<10} {'OK' if ok else 'FAILED'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
