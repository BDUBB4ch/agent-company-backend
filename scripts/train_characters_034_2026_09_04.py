r"""RETRAIN, ON THE 0.34 TRAINER, FROM BARRY'S NEW IMAGES (2026-09-04, Barry:
"use the new images i gave you and train them so i can use them in LTX 2.5.
start with the easiest first. Just get it done").

Recipe (measured by scripts/probe_train_recipe_034_2026_09_04.py, not guessed):
rank 32, batch 2 x grad-acc 2 (4 images per update), lr 1e-4, AdamW, MSE,
bf16 training / fp32 LoRA, gradient checkpointing, and the gradient-clip LOCAL
PATCH live in D:\ComfyUI25. 300 optimizer updates per character in 4 segments
of 75; every segment saves a checkpoint AND renders the fixed test prompt so
identity can be judged by eye at each step and a bad run costs one segment.
August's recipe (rank 16, batch 1, 1200 single-image unclipped updates) gave
LoRAs that cannot carry Keth even at strength 1.4 -- this one is the change.

Runs the characters in the order given, easiest first. Resumable: a segment
whose checkpoint already exists is skipped, so a killed run picks up where it
stopped. Owns the render flag with its own token (the guard trusts the file's
mtime since tonight), holds the machine awake, drives the OFFICE rig on 8188
through comfy_image.ensure_running (image mode), and installs the finished
LoRA as models/loras/<char>_character_sep04.safetensors. It does NOT flip
CHARACTER_LORAS -- a LoRA goes live only after its test render is judged by
eye (the record's rule since the v3-noise incident).

Usage: venv/Scripts/python.exe scripts/train_characters_034_2026_09_04.py [char ...]
Logs:  data/retrain_2026-09-04/train.log ; renders: D:\ComfyUI25\output\retrain_*.png
"""
import asyncio, ctypes, io, json, os, shutil, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
WORK = os.path.join(ROOT, "data", "retrain_2026-09-04")
LOG = os.path.join(WORK, "train.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"retrain-{int(time.time())}"

ORDER = ["bdubb", "tazz", "yannah", "bia", "vorshara", "keth"]
TRIGGER = {"bdubb": "@B-DUBB-new", "tazz": "@Tazz", "yannah": "@Yannah", "bia": "@Bia-2",
           "vorshara": "@Vorshara", "keth": "@Keth"}
TEST_PROMPT = {
    "bdubb": "{t} standing in a dim warehouse, black hoodie and tactical vest, black cap, gold number 4 pendant, cinematic still",
    "tazz": "{t} standing in a ship corridor, all-black sleeveless tactical jumpsuit, two long dark braids, cinematic still",
    "yannah": "{t} standing in a ship corridor, black fitted tactical jumpsuit with teal piping, cinematic still",
    "bia": "{t} standing in a ship corridor, grey and black form-fitting tactical suit, cinematic still",
    "vorshara": "{t} standing in a garden atrium, sheer pale-purple couture gown, four electric-blue eyes, cinematic still",
    "keth": "{t} standing in a dim facility corridor, gray facility jumpsuit, barefoot, cinematic still",
}
UPDATES_PER_SEG, SEGMENTS, BATCH, GRAD_ACC = 75, 4, 2, 2
# RANK / LR overridable per run (2026-09-05): Vor'Shara fried from segment 1 on
# rank 32 / 1e-4 while four other characters held; her re-run uses rank 16 and
# half the rate -- the recipe her old v4 (which rendered her four eyes) trained at.
RANK = int(os.environ.get("RETRAIN_RANK", "32"))
LR = float(os.environ.get("RETRAIN_LR", "1e-4"))
TEST_SEED = 1322780258


def log(msg):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def keep_awake(on):
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if on else 0x80000000)
    except Exception:
        pass


def train_wf(folder, steps, prefix, existing):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "2": {"class_type": "LoadImageTextDataSetFromFolder", "inputs": {"folder": folder}},
        "3": {"class_type": "MakeTrainingDataset", "inputs": {"images": ["2", 0], "vae": ["1", 2], "clip": ["1", 1], "texts": ["2", 1]}},
        "4": {"class_type": "TrainLoraNode", "inputs": {
            "model": ["1", 0], "latents": ["3", 0], "positive": ["3", 1],
            "batch_size": BATCH, "grad_accumulation_steps": GRAD_ACC, "steps": steps,
            "learning_rate": LR, "rank": RANK, "optimizer": "AdamW", "loss_function": "MSE",
            "seed": 0, "training_dtype": "bf16", "lora_dtype": "fp32", "quantized_backward": False,
            "algorithm": "LoRA", "gradient_checkpointing": True, "checkpoint_depth": 1,
            "offloading": False, "existing_lora": existing, "bucket_mode": False, "bypass_mode": False}},
        "5": {"class_type": "SaveLoRA", "inputs": {"lora": ["4", 0], "prefix": prefix, "steps": steps}},
    }


async def submit_and_wait(host, wf, timeout_s):
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{host}/prompt", json={"prompt": wf, "client_id": str(uuid.uuid4())})
        if r.status_code != 200:
            raise RuntimeError(f"rejected: {r.text[:800]}")
        pid = r.json()["prompt_id"]
        while time.time() - t0 < timeout_s:
            await asyncio.sleep(15)
            try:
                d = (await c.get(f"{host}/history/{pid}")).json()
            except Exception:
                continue
            if pid in d:
                st = d[pid].get("status", {})
                if st.get("status_str") != "success":
                    raise RuntimeError(f"failed: {json.dumps(st.get('messages', []))[:800]}")
                return d[pid], time.time() - t0
    raise RuntimeError("timed out")


def newest(folder, pattern):
    import glob
    fs = sorted(glob.glob(os.path.join(folder, pattern)), key=os.path.getmtime)
    return fs[-1] if fs else None


async def run_char(char, host, comfy_dir, ci):
    # FRESH ComfyUI PROCESS PER CHARACTER (2026-09-05). TrainLoraNode patches
    # the LoRA into the cached base model in memory; after a training job was
    # interrupted at 12:44 the same rig process was reused, and every run on it
    # since opened at loss 1.5-4.4 instead of 0.05-0.09 -- Vor'Shara fried from
    # segment 1, Keth was about to. A checkpoint reload costs ~20 s; a poisoned
    # base costs a character.
    await ci.stop_server()
    await asyncio.sleep(3)
    if not await ci.ensure_running(timeout_s=240, mode="image"):
        raise RuntimeError("rig did not start fresh")
    folder = f"lora_{char}_sep04"
    loras_dir = os.path.join(comfy_dir, "models", "loras")
    out_loras = os.path.join(comfy_dir, "output", "loras")
    existing = "[None]"
    for seg in range(1, SEGMENTS + 1):
        name = f"{char}_sep04_seg{seg}"
        # KEEP THE TRAINER'S OWN FILENAME. TrainLoraNode reads the step count
        # out of existing_lora as int(name.split("_steps_")[0].split("_")[-1]),
        # so a checkpoint must be called "<prefix>_<N>_steps_<counter>_.safetensors"
        # exactly as SaveLoRA wrote it -- the first run renamed it to "..._seg1"
        # and every segment 2 was rejected ("invalid literal for int()").
        have = newest(loras_dir, f"{name}_*_steps_*.safetensors")
        if have:
            log(f"[{char}] segment {seg}: checkpoint exists ({os.path.basename(have)}), skipping")
            existing = os.path.basename(have); continue
        log(f"[{char}] segment {seg}/{SEGMENTS}: {UPDATES_PER_SEG} updates from {existing}")
        before = newest(out_loras, "*.safetensors")
        entry, secs = await submit_and_wait(host, train_wf(folder, UPDATES_PER_SEG, f"loras/{name}", existing), 4 * 3600)
        produced = newest(out_loras, "*.safetensors")
        if produced is None or produced == before:
            raise RuntimeError(f"[{char}] segment {seg}: no LoRA file produced")
        installed = os.path.join(loras_dir, os.path.basename(produced))
        shutil.copy2(produced, installed)
        existing = os.path.basename(produced)
        log(f"[{char}] segment {seg} done in {secs/60:.1f} min -> {installed} ({os.path.getsize(installed)//1_000_000} MB)")
        # test render with THIS checkpoint, fixed seed, so the four renders compare
        ci.CHARACTER_LORAS[char] = existing
        # the inner impl, not the public wrapper: the wrapper refuses while a
        # render flag is up, and the flag up right now is OURS
        r = await ci._generate_image_impl(TEST_PROMPT[char].format(t=TRIGGER[char]), "text, logo", seed=TEST_SEED)
        if "error" in r:
            log(f"[{char}] segment {seg} test render FAILED: {r['error']}")
        else:
            dst = os.path.join(comfy_dir, "output", f"retrain_{char}_seg{seg}.png")
            shutil.copy2(r["path"], dst); log(f"[{char}] segment {seg} test render -> {dst}")
    final = os.path.join(loras_dir, f"{char}_character_sep04.safetensors")
    shutil.copy2(newest(loras_dir, f"{char}_sep04_seg{SEGMENTS}_*_steps_*.safetensors"), final)
    log(f"[{char}] FINAL installed: {final} (CHARACTER_LORAS not flipped -- judge the seg4 render first)")


async def main():
    chars = sys.argv[1:] or ORDER
    os.makedirs(WORK, exist_ok=True)
    import llm_router, comfy_image as ci, config
    # ONE RUNNER, EVER. A flag is stale only if no other runner PROCESS is alive
    # (2026-09-05: a timer rule plus a Startup entry that deleted the flag put
    # two runners on the same queue for ten hours -- segments trained twice).
    import subprocess
    others = subprocess.run(["powershell", "-NoProfile", "-Command",
        # exclude ourselves, our children, AND our parent: the venv python.exe is a
        # launcher that re-spawns the real interpreter with the same command line
        "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -like '*train_characters_034*' -and $_.ProcessId -ne %d -and $_.ParentProcessId -ne %d -and $_.ProcessId -ne %d }).Count" % (os.getpid(), os.getpid(), os.getppid())],
        capture_output=True, text=True).stdout.strip()
    if others.isdigit() and int(others) > 0:
        log(f"another runner is alive ({others} procs) -- refusing"); return 3
    if os.path.exists(FLAG):
        tok = io.open(FLAG).read().strip()
        if tok.startswith("retrain-"):
            log(f"stale flag from a dead runner ({tok}) -- taking over"); os.remove(FLAG)
        elif (time.time() - os.path.getmtime(FLAG)) < 7200:
            log("another render owns the flag -- refusing"); return 3
    io.open(FLAG, "w").write(TOKEN)
    keep_awake(True)
    # refresh our own flag's mtime periodically: the guard trusts a 2h-young file
    async def heartbeat():
        while True:
            await asyncio.sleep(600)
            try:
                if io.open(FLAG).read().strip() == TOKEN:
                    os.utime(FLAG, None)
            except OSError:
                pass
    hb = asyncio.create_task(heartbeat())
    try:
        log(f"=== retrain start: {chars}  recipe rank{RANK} b{BATCH} ga{GRAD_ACC} lr{LR} {SEGMENTS}x{UPDATES_PER_SEG} updates ===")
        await llm_router.unload_all_models()
        if not await ci.ensure_running(timeout_s=240, mode="image"):
            log("rig did not start"); return 4
        for char in chars:
            try:
                await run_char(char, config.COMFY_HOST, config.COMFY_DIR, ci)
            except Exception as e:  # noqa: BLE001 -- one character failing must not kill the queue
                log(f"[{char}] ABORTED: {e}")
                if not await ci.ensure_running(timeout_s=240, mode="image"):
                    log("rig gone and would not restart -- stopping"); return 5
        log("=== retrain queue finished ===")
        return 0
    finally:
        hb.cancel()
        keep_awake(False)
        try:
            if io.open(FLAG).read().strip() == TOKEN:
                os.remove(FLAG); log("flag cleared")
        except OSError:
            pass


sys.exit(asyncio.run(main()))
