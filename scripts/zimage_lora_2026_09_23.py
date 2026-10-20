"""Z-Image Turbo character LoRA -- Vor'Shara first (Barry, 2026-09-23: "run the
training lora on my new zips" / "use vor sharas zip in her file").

    venv/Scripts/python.exe scripts/zimage_lora_2026_09_23.py dataset
    venv/Scripts/python.exe scripts/zimage_lora_2026_09_23.py probe      # 10 steps: does it run on AMD?
    venv/Scripts/python.exe scripts/zimage_lora_2026_09_23.py train [steps]
    venv/Scripts/python.exe scripts/zimage_lora_2026_09_23.py test <lora_file>

Source: "Lady Zora Zip.zip" in her Bia Project folder = the same 27 renders that
sit loose there (all opened on a contact sheet, data/zimage_lora/vorshara_sheet.jpg).
0 and 1 are left out (hooded figures in the background would be learned as part
of her). Every frame is made 768x1024 so the trainer never sees mixed sizes
(the 09-05 fried-Vor'Shara lesson), and the training folder holds ONLY frames +
captions (the dataset loader reads subfolders).

Recipe (community Z-Image Turbo recipe): the Ostris training adapter v2 is
applied to the Turbo model DURING training (it de-distills it so the LoRA learns
properly) and is NOT used at render time; rank 16, lr 1e-4, trigger "@Vorshara"
(a non-dictionary token, same token her SDXL LoRA uses).
Owns the render flag with its own token; drives the office rig on 8188.
"""
import asyncio, ctypes, glob, io, json, os, shutil, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
from config import COMFY_DIR  # noqa: E402

SRC = r"C:\Users\Owner\Desktop\Bia Project\Bia Project\Lady Vor’Shara Vel"
# Any character (2026-09-24): ZL_CHAR=vorshara|bdubb|tazz picks folder + trigger.
# Folders + captions are built by the per-character dataset builders (HANDOFF-2026-09-24).
CHARS = {
    "vorshara": ("lora_vorshara_zimage", "@Vorshara", ""),
    "bdubb": ("lora_bdubb_zimage", "@b-dubb", ""),
    "tazz": ("lora_tazz_zimage", "@Tazz", "pink and blue eyes, "),  # canon eyes; captions say violet
    # 2026-09-25 (Barry: "train them all"): built by scripts/zimage_datasets_2026_09_25.py from his Higgsfield zips
    "yannah": ("lora_yannah_zimage", "@yannah", ""),
    "ilnora": ("lora_ilnora_zimage", "@ilnora", ""),
}
CHAR = os.getenv("ZL_CHAR", "vorshara")
FOLDER, TRIGGER, TEST_EXTRA = CHARS[CHAR]
DATA = os.path.join(COMFY_DIR, "input", FOLDER)
WORK = os.path.join(ROOT, "data", "zimage_lora")
LOG = os.path.join(WORK, "train.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"zimage-lora-{time.time()}"
HOST = "http://127.0.0.1:8188"
ADAPTER = "zimage_turbo_training_adapter_v2.safetensors"
RANK, LR = 16, 1e-4
# 2026-09-25: training model + text encoder read from COPIES on the NVMe C: drive (tools/ComfyUI/models/*/_nvme).
# From D: (spinning disk) ComfyUI reported fast_disk=False and free RAM fell to 0.7 GB during the load -- the
# condition of both PC crashes. scripts/ram_watchdog.py kills ComfyUI under 5 GB free as a hard backstop.

# index on the contact sheet -> (view, horizontal centre for landscape crops)
VIEWS = {
    2: "upper body, front", 3: "face close-up, three-quarter view", 4: "face close-up, side view",
    5: "full body, front", 6: "full body, front", 7: "full body, front", 8: "full body, front",
    9: "upper body, three-quarter view", 10: "full body, front", 11: "full body, front",
    12: "full body, front", 13: "full body, front", 14: "full body, front", 15: "full body, back view",
    16: "full body, three-quarter view", 17: "full body, front", 18: "full body, side view",
    19: "full body, side view", 20: "full body, back view", 21: "full body, back view",
    22: "full body, front", 23: "full body, front", 24: "face close-up, front",
    25: "face close-up, front", 26: "full body, front",
}
CROP_X = {3: 0.37, 4: 0.33, 5: 0.55, 6: 0.5, 7: 0.47, 8: 0.55}


def log(msg):
    os.makedirs(WORK, exist_ok=True)
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def build_dataset():
    from PIL import Image
    files = sorted(glob.glob(os.path.join(SRC, "hf_*.png")))
    assert len(files) == 27, len(files)
    if os.path.isdir(DATA):
        shutil.rmtree(DATA)
    os.makedirs(DATA)
    for i, view in VIEWS.items():
        im = Image.open(files[i]).convert("RGB")
        w, h = im.size
        if w > h:  # landscape -> 3:4 window around the subject
            cw = int(h * 3 / 4)
            cx = int(CROP_X[i] * w)
            left = min(max(0, cx - cw // 2), w - cw)
            im = im.crop((left, 0, left + cw, h))
        im = im.resize((768, 1024), Image.LANCZOS)
        name = f"{i:03d}"
        im.save(os.path.join(DATA, name + ".png"))
        with io.open(os.path.join(DATA, name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{TRIGGER}, {view}")
    log(f"dataset: {len(VIEWS)} frames -> {DATA}")


def encode_wf():
    """PASS 1 (2026-09-25, two-pass to fit RAM): text encoder + VAE turn the pictures and captions into a saved
    training set. The 8 GB text encoder is never in memory at the same time as the 12 GB model."""
    return {
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": os.getenv("ZL_CLIP", "qwen_3_4b_nvme.safetensors"),
                                                   "type": "lumina2"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "5": {"class_type": "LoadImageTextDataSetFromFolder", "inputs": {"folder": FOLDER}},
        "6": {"class_type": "MakeTrainingDataset", "inputs": {
            "images": ["5", 0], "vae": ["4", 0], "clip": ["3", 0], "texts": ["5", 1]}},
        "9": {"class_type": "SaveTrainingDataset", "inputs": {
            "latents": ["6", 0], "conditioning": ["6", 1], "folder_name": f"zl_{CHAR}_dataset", "shard_size": 1000}},
    }


def train_wf(steps, prefix):
    """PASS 2: the model + the saved training set only."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": os.getenv("ZL_UNET", "z_image_turbo_int8_convrot_nvme.safetensors"), "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "lora_name": ADAPTER, "strength_model": 1.0}},
        "5": {"class_type": "LoadTrainingDataset", "inputs": {"folder_name": f"zl_{CHAR}_dataset"}},
        "7": {"class_type": "TrainLoraNode", "inputs": {
            "model": ["2", 0], "latents": ["5", 0], "positive": ["5", 1],
            "batch_size": 1, "grad_accumulation_steps": 1, "steps": steps,
            "learning_rate": LR, "rank": RANK, "optimizer": "AdamW", "loss_function": "MSE",
            # int8 base (2026-09-25): the bf16 model drove free RAM to 3 GB at load -- train the int8 model the
            # office already RENDERS with, native dtype + quantized backward. ZL_UNET/ZL_TDTYPE/ZL_QBACK override.
            "seed": 0, "training_dtype": os.getenv("ZL_TDTYPE", "none"), "lora_dtype": "bf16",
            "quantized_backward": os.getenv("ZL_QBACK", "1") == "1",
            "algorithm": "LoRA", "gradient_checkpointing": True, "checkpoint_depth": 1,
            "offloading": False, "existing_lora": "[None]", "bucket_mode": False, "bypass_mode": False}},
        "8": {"class_type": "SaveLoRA", "inputs": {"lora": ["7", 0], "prefix": prefix, "steps": steps}},
    }


def test_wf(lora, prompt, seed, prefix):
    import importlib.util
    spec = importlib.util.spec_from_file_location("zt", os.path.join(ROOT, "scripts", "zimage_test_2026_09_23.py"))
    zt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(zt)
    wf = zt.graph(prompt, 1024, 1024, seed, prefix, "lumina2")
    wf["11"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["1", 0], "lora_name": lora, "strength_model": 1.0}}
    wf["2"]["inputs"]["model"] = ["11", 0]
    return wf


def free_ram_gb():
    """Available physical RAM in GB from Windows itself (GlobalMemoryStatusEx) -- no extra package."""
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1e9
    except Exception:
        return None


async def submit_and_wait(wf, timeout_s):
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{HOST}/prompt", json={"prompt": wf, "client_id": str(uuid.uuid4())})
        if r.status_code != 200:
            raise RuntimeError(f"rejected: {r.text[:1500]}")
        pid = r.json()["prompt_id"]
        full_since = None
        low_ram_since = None
        while time.time() - t0 < timeout_s:
            await asyncio.sleep(10)
            # RAM GUARD (2026-09-25): both PC crashes (09-23, 09-24) hit at the model load with system RAM nearly
            # full (1.5 GB free). Free RAM under 6 GB for 30 s -> stop the job before Windows falls over.
            free_gb = free_ram_gb()
            if free_gb is not None and free_gb < 6.0:
                low_ram_since = low_ram_since or time.time()
                if time.time() - low_ram_since >= 30:
                    await c.post(f"{HOST}/interrupt")
                    log(f"RAM GUARD: only {free_gb:.1f} GB free for 30 s -- interrupted")
                    raise RuntimeError(f"ram guard: {free_gb:.1f} GB free")
            else:
                low_ram_since = None
            # CARD GUARD (2026-09-24, same rule as the Qwen 2.1 path): pinned full
            # for VRAM_GUARD_SECONDS = thrashing, the state that froze the PC. Stop.
            used = await asyncio.to_thread(comfy_image.gpu_dedicated_gb)
            if used is not None and used >= comfy_image.VRAM_GUARD_GB:
                full_since = full_since or time.time()
                if time.time() - full_since >= comfy_image.VRAM_GUARD_SECONDS:
                    await c.post(f"{HOST}/interrupt")
                    log(f"GUARD: card at {used:.1f} GB for {comfy_image.VRAM_GUARD_SECONDS}s -- interrupted")
                    raise RuntimeError(f"card guard: pinned at {used:.1f} GB")
            else:
                full_since = None
            try:
                d = (await c.get(f"{HOST}/history/{pid}")).json()
            except Exception:
                continue
            if pid in d:
                st = d[pid].get("status", {})
                if st.get("status_str") == "error":
                    raise RuntimeError(json.dumps(st.get("messages", []))[-2500:])
                return time.time() - t0, d[pid].get("outputs", {})
    raise RuntimeError("timed out")


async def with_gpu(fn):
    if comfy_image.render_in_progress():
        raise SystemExit("a render is already running")
    open(FLAG, "w").write(TOKEN)
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass
    try:
        await llm_router.unload_all_models()
        if not await comfy_image.ensure_running(timeout_s=600, mode="video"):
            raise SystemExit("ComfyUI did not start")
        return await fn()
    finally:
        try:
            if open(FLAG).read().strip() == TOKEN:
                os.remove(FLAG)
        except OSError:
            pass
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass


async def train(steps, prefix):
    async def go():
        log(f"encode start ({CHAR}): pictures + captions -> saved training set")
        esecs, _ = await submit_and_wait(encode_wf(), 60 * 60)
        # unload EVERYTHING before pass 2 -- the 8 GB text encoder stayed loaded and ate the RAM training needed
        import httpx
        async with httpx.AsyncClient(timeout=60) as c:
            await c.post(f"{HOST}/free", json={"unload_models": True, "free_memory": True})
        await asyncio.sleep(10)
        log(f"models unloaded; free RAM {free_ram_gb():.1f} GB")
        log(f"encode done in {esecs:.0f}s; train start: {steps} steps rank {RANK} lr {LR}")
        secs, _ = await submit_and_wait(train_wf(steps, prefix), 60 * 60 * 14)
        log(f"train done: {steps} steps in {secs:.0f}s ({secs / steps:.1f} s/step incl. load)")
    await with_gpu(go)


async def test(lora):
    prompts = [
        f"{TRIGGER}, {TEST_EXTRA}face close-up, front, standing in a garden atrium with a reflecting pool, warm golden light",
        f"{TRIGGER}, {TEST_EXTRA}full body, walking through a dark stone corridor lit by torches, cinematic still",
    ]

    async def go():
        for i, p in enumerate(prompts):
            secs, out = await submit_and_wait(test_wf(lora, p, 77 + i, f"zlora_{CHAR}_test{i}"), 1800)
            files = [img["filename"] for o in out.values() for img in o.get("images", [])]
            log(f"test {i}: {secs:.0f}s -> {files}")
    await with_gpu(go)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "dataset":
        build_dataset()
    elif cmd == "probe":
        asyncio.run(train(10, f"zlora_{CHAR}_probe"))
    elif cmd == "train":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
        asyncio.run(train(n, f"zlora_{CHAR}"))
    elif cmd == "test":
        asyncio.run(test(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
