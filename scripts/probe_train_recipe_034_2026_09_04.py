"""20-step probe of an UPGRADED LoRA recipe on ComfyUI 0.34 (D: rig), before any
overnight retrain is scheduled (2026-09-04, Barry: "retrain").

What it measures, so the retrain plan is built on numbers:
  * that a 0.34-valid training graph is accepted (the 0.29 JSON lacks the new
    required inputs: optimizer, loss_function, dtypes, algorithm, checkpointing...)
  * seconds per step at batch 2 / grad-acc 2 / rank 32 on this card
  * whether it fits 16GB at all (OOM shows here in five minutes, not at 3am)
The August recipe (rank 16, lr 1e-4, batch 1, 1200 single-image updates,
unclipped) produced LoRAs that cannot carry Keth even at strength 1.4 -- so
the retrain has to change the recipe, and this is the first look at the one
it would change to. The gradient-clip LOCAL PATCH is live in the D: tree.

Usage: venv/Scripts/python.exe scripts/probe_train_recipe_034_2026_09_04.py [folder] [steps] [batch] [grad_acc] [rank]
Standalone-render rule: own the flag, clear LLMs, clear only our flag.
"""
import asyncio, io, json, os, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
FOLDER = sys.argv[1] if len(sys.argv) > 1 else "lora_keth_v5"
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 20
BATCH = int(sys.argv[3]) if len(sys.argv) > 3 else 2
GRAD_ACC = int(sys.argv[4]) if len(sys.argv) > 4 else 2
RANK = int(sys.argv[5]) if len(sys.argv) > 5 else 32
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"train-probe-{int(time.time())}"


def workflow():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "2": {"class_type": "LoadImageTextSetFromFolderNode", "inputs": {"folder": FOLDER, "clip": ["1", 1],
                                                                        "resize_method": "None", "width": -1, "height": -1}},
        "4": {"class_type": "TrainLoraNode", "inputs": {
            "model": ["1", 0], "latents": ["3", 0], "positive": ["3", 1],
            "batch_size": BATCH, "grad_accumulation_steps": GRAD_ACC, "steps": STEPS,
            "learning_rate": 1e-4, "rank": RANK, "optimizer": "AdamW", "loss_function": "MSE",
            "seed": 0, "training_dtype": "bf16", "lora_dtype": "fp32", "quantized_backward": False,
            "algorithm": "LoRA", "gradient_checkpointing": True, "checkpoint_depth": 1,
            "offloading": False, "existing_lora": "[None]", "bucket_mode": False, "bypass_mode": False}},
        "5": {"class_type": "SaveLoRA", "inputs": {"lora": ["4", 0], "prefix": f"loras/probe_{FOLDER}_r{RANK}_b{BATCH}", "steps": STEPS}},
    }


async def main():
    import httpx, llm_router, comfy_image as ci, config
    if os.path.exists(FLAG):
        print("another render owns the flag -- refusing"); return 3
    io.open(FLAG, "w").write(TOKEN)
    try:
        await llm_router.unload_all_models()
        if not await ci.ensure_running(timeout_s=180, mode="image"):
            print("rig did not start"); return 4
        host = config.COMFY_HOST
        async with httpx.AsyncClient(timeout=60) as c:
            info = (await c.get(f"{host}/object_info")).json()
        wf = workflow()
        # the dataset side of the graph differs by version; wire whichever exists
        if "LoadImageTextSetFromFolderNode" in info:
            req = info["LoadImageTextSetFromFolderNode"]["input"]["required"]
            wf["2"]["inputs"] = {k: v for k, v in wf["2"]["inputs"].items() if k in req or k in info["LoadImageTextSetFromFolderNode"]["input"].get("optional", {})}
            print("dataset node: LoadImageTextSetFromFolderNode ->", list(req.keys()))
            outs = info["LoadImageTextSetFromFolderNode"]["output"]
            print("   outputs:", outs)
            if "MakeTrainingDataset" in info:
                wf["3"] = {"class_type": "MakeTrainingDataset", "inputs": {"images": ["2", 0], "vae": ["1", 2], "clip": ["1", 1], "texts": ["2", 1]}}
            else:
                # 0.34 shape: the folder node already returns LATENT + CONDITIONING?
                wf["4"]["inputs"]["latents"] = ["2", outs.index("LATENT")] if "LATENT" in outs else ["2", 0]
                wf["4"]["inputs"]["positive"] = ["2", outs.index("CONDITIONING")] if "CONDITIONING" in outs else ["2", 1]
        elif "LoadImageTextDataSetFromFolder" in info:
            wf["2"] = {"class_type": "LoadImageTextDataSetFromFolder", "inputs": {"folder": FOLDER}}
            wf["3"] = {"class_type": "MakeTrainingDataset", "inputs": {"images": ["2", 0], "vae": ["1", 2], "clip": ["1", 1], "texts": ["2", 1]}}
            print("dataset node: LoadImageTextDataSetFromFolder + MakeTrainingDataset (0.29 shape)")
        else:
            print("no dataset node found; training nodes present:", [k for k in info if "Train" in k or "Dataset" in k or "ImageText" in k]); return 5
        # every required input of TrainLoraNode must be present -- assert, don't guess
        need = set(info["TrainLoraNode"]["input"]["required"].keys())
        missing = need - set(wf["4"]["inputs"].keys())
        assert not missing, f"TrainLoraNode missing inputs: {missing}"
        t0 = time.time()
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{host}/prompt", json={"prompt": wf, "client_id": str(uuid.uuid4())})
            if r.status_code != 200:
                print("REJECTED:", r.text[:1200]); return 6
            pid = r.json()["prompt_id"]; print("accepted", pid, f"steps={STEPS} batch={BATCH} grad_acc={GRAD_ACC} rank={RANK}")
            entry = None
            while time.time() - t0 < 3600:
                await asyncio.sleep(10)
                try:
                    d = (await c.get(f"{host}/history/{pid}")).json()
                except Exception:
                    continue
                if pid in d:
                    entry = d[pid]; break
        if entry is None:
            print("timed out"); return 7
        st = entry.get("status", {})
        print("status", st.get("status_str"), "wall %.1f min" % ((time.time() - t0) / 60))
        if st.get("status_str") != "success":
            print(json.dumps(st.get("messages", []))[:1500]); return 8
        print("outputs:", json.dumps(entry.get("outputs", {}))[:300])
        return 0
    finally:
        if os.path.exists(FLAG) and io.open(FLAG).read().strip() == TOKEN:
            os.remove(FLAG); print("flag cleared")


sys.exit(asyncio.run(main()))
