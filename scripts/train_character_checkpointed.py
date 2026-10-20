"""CHECKPOINTED character LoRA training (generalised from the Keth v8 run), so a blown run is visible in ~30 minutes
instead of 4 hours.

WHY THIS EXISTS (2026-08-08). v3 fried, v5 came out good, v7 fried -- all on
the same data, same folder, same command. Reading ComfyUI's own trainer source
(tools/ComfyUI/comfy_extras/nodes_train.py) explains it:

  * The node's `seed` does NOT control the run. Noise PATTERN is seeded
    (`Noise_RandomNoise(seed + i*1000)`), but the image picked each step
    (`torch.randperm`) and the noise LEVEL (`torch.rand`) both come from the
    UNSEEDED GLOBAL RNG. Two runs with seed=0 see a different image order and
    a different sigma sequence -> different trajectory -> sometimes divergence.
  * batch_size=1 with grad_accumulation_steps=1 means every single step
    updates the weights from ONE image at ONE random noise level. Maximum
    gradient noise.
  * There is NO gradient clipping and NO LR schedule anywhere in that file --
    plain AdamW at a constant lr. Nothing absorbs an outlier step.
  * Upstream bug report with our exact signature (loss ~1.33 + "noisy mess of
    colour"): https://github.com/Comfy-Org/ComfyUI/issues/13089 -- open, no fix.

WHAT THIS CHANGES, using only knobs the node already exposes:
  * THE RECIPE IS UNCHANGED. 1200 steps, rank 16, lr 1e-4, grad_acc 1 -- the
    same training v5 and v7 got. Barry, 2026-08-08: "i thought we were training
    1200 steps still, just making sure its on track every 30 minutes."
    An earlier version of this script raised grad_accumulation_steps to 4 for
    stability; that was WRONG for this purpose, because it drops the run from
    1200 weight updates to 300 -- LESS training than v5 got, not a safer
    version of it. Reverted.
  * The ONLY change is VISIBILITY. The run is split into 8 segments of 150
    steps; each saves a checkpoint AND renders the test prompt. Total training
    is identical, but a fried run shows up after ~32 minutes instead of 4 hours,
    and you get 8 checkpoints to pick from instead of betting on the last one.

HONEST CAVEAT: continuing between segments restarts AdamW, so its momentum
resets every segment. That is a real behavioural difference from one unbroken
run -- it is the price of being able to see inside the run at all, and if
anything it is a mild stabiliser. Judge v8 on the renders, not on theory.

NOTE: 8 segments x 150 steps = 1200 steps at grad_acc=1 = 1200 weight updates,
exactly what v5 and v7 ran. ~4.3h at the observed 12.8 s/it.

Run (launch via Task Scheduler with a TIME trigger so it survives the session):
    venv/Scripts/python.exe scripts/train_keth_v8_checkpointed.py
"""
import json
import pathlib
import shutil
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import train_character_loras as T
import compare_keth_loras as C

ROOT = T.ROOT
LORAS = ROOT / "tools/ComfyUI/models/loras"
OUT_LORAS = ROOT / "tools/ComfyUI/output/loras"
PROGRESS = ROOT / "data" / "v8_progress"

CHAR = "keth"          # overridden by argv
FOLDER = "lora_keth_v5"  # overridden by argv
RANK = 16
LR = 1e-4
SEED = 0
GRAD_ACC = 1
SEG_STEPS = 150          # ~32 min per segment at the observed 12.8 s/it
SEGMENTS = 8             # 1200 iterations total = 300 optimizer updates
SEG_TIMEOUT = 5400       # 90 min -- generous; a segment that hits this is wrong


def build(steps_this_seg, cum_steps, seg_idx, continue_from):
    wf = json.loads(T.WORKFLOW.read_text(encoding="utf-8"))
    wf["2"]["inputs"]["folder"] = FOLDER
    n = wf["4"]["inputs"]
    n["steps"] = steps_this_seg
    n["rank"] = RANK
    n["learning_rate"] = LR
    n["seed"] = SEED + seg_idx          # vary per segment; global RNG varies anyway
    n["grad_accumulation_steps"] = GRAD_ACC
    if continue_from:
        n["existing_lora"] = continue_from
    wf["5"]["inputs"]["prefix"] = f"loras/{CHAR}_character_v8_seg{seg_idx}"
    wf["5"]["inputs"]["steps"] = cum_steps
    return wf


def newest_output():
    files = sorted(OUT_LORAS.glob("*.safetensors"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_segment(seg_idx, cum_steps, continue_from):
    wf = build(SEG_STEPS, cum_steps, seg_idx, continue_from)
    print(f"\n=== segment {seg_idx}/{SEGMENTS}  ->  {cum_steps} cumulative steps "
          f"(grad_acc={GRAD_ACC}, lr={LR}, rank={RANK}) ===", flush=True)
    print(f"    continuing from: {continue_from or 'SCRATCH'}", flush=True)

    before = newest_output()
    try:
        pid = T._post("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    except Exception as e:
        print(f"    SUBMIT FAILED: {e}", flush=True)
        return None
    print(f"    queued {pid}", flush=True)

    t0 = time.time()
    while time.time() - t0 < SEG_TIMEOUT:
        hist = json.loads(urllib.request.urlopen(f"{T.COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"    FAILED after {(time.time()-t0)/60:.1f} min", flush=True)
                for m in st.get("messages", [])[-4:]:
                    print("     ", str(m)[:400], flush=True)
                return None
            print(f"    trained in {(time.time()-t0)/60:.1f} min", flush=True)
            break
        time.sleep(10)
    else:
        print("    TIMEOUT", flush=True)
        return None

    saved = newest_output()
    if saved is None or (before is not None and saved == before):
        print("    ! no new LoRA file appeared in output/loras", flush=True)
        return None
    dest = LORAS / saved.name
    shutil.copyfile(saved, dest)
    print(f"    checkpoint -> {dest.name}", flush=True)
    return dest.name


# Trigger-led test prompts, phrased like the training captions (in-distribution).
# Canon words are deliberately NOT stacked in -- the point is to see what the
# weights hold on their own, not what the prompt can describe into existence.
TEST_PROMPTS = {
    "keth": "@Keth, close-up portrait, gray facility jumpsuit",
    "bia": "@Bia, close-up portrait",
    "tazz": "@Tazz, close-up portrait",
    "yannah": "@Yannah, close-up portrait",
    "bdubb": "@BDubb, close-up portrait",
    "vorshara": "@Vorshara, close-up portrait",
}


def test_render(lora_name, seg_idx, cum_steps):
    """Render a trigger-led test prompt with this checkpoint so the run can be
    judged WHILE it trains, instead of four hours later."""
    C.POSITIVE = TEST_PROMPTS.get(CHAR, f"@{CHAR}, close-up portrait")
    prefix = f"v8_{CHAR}_seg{seg_idx}_{cum_steps}steps"
    try:
        C.run(prefix, lora_name)
    except Exception as e:
        print(f"    test render failed: {e}", flush=True)


def wait_for_gpu(max_wait=8 * 3600):
    """Never start while another training job still owns the card -- running two
    at once froze the PC on 2026-08-07 and that bat now hard-exits. Polls until
    ComfyUI's queue has been empty for three consecutive checks."""
    clear = 0
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            q = json.loads(urllib.request.urlopen(f"{T.COMFY}/queue", timeout=30).read())
            busy = len(q.get("queue_running", [])) + len(q.get("queue_pending", []))
        except Exception:
            busy = 1
        if busy == 0:
            clear += 1
            if clear >= 3:
                return True
        else:
            clear = 0
            print(f"    GPU busy ({busy} job(s)) -- waiting...", flush=True)
        time.sleep(60)
    print("    gave up waiting for a free GPU", flush=True)
    return False


def main():
    global CHAR, FOLDER
    if len(sys.argv) >= 3:
        CHAR, FOLDER = sys.argv[1], sys.argv[2]
    PROGRESS.mkdir(parents=True, exist_ok=True)
    if not wait_for_gpu():
        return 1
    print(f"{CHAR.upper()} v8 -- checkpointed run")
    print(f"  folder={FOLDER}  rank={RANK}  lr={LR}  grad_acc={GRAD_ACC}")
    print(f"  {SEGMENTS} segments x {SEG_STEPS} iterations = {SEGMENTS*SEG_STEPS} "
          f"iterations = {SEGMENTS*SEG_STEPS//GRAD_ACC} optimizer updates", flush=True)
    T.free_vram()

    continue_from = None
    for seg in range(1, SEGMENTS + 1):
        cum = seg * SEG_STEPS
        name = run_segment(seg, cum, continue_from)
        if name is None:
            print(f"\nSTOPPED at segment {seg}. Last good checkpoint: "
                  f"{continue_from or 'none'}", flush=True)
            return 1
        continue_from = name
        test_render(name, seg, cum)
    print(f"\nALL SEGMENTS DONE. Final checkpoint: {continue_from}")
    print("Compare the v8_seg*.png renders in tools/ComfyUI/output and pick the "
          "best checkpoint -- later is NOT automatically better.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
