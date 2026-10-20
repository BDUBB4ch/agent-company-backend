"""The vocab gate alone, both sides. Runs 2-4 of the full bench lost this
gate three different ways (dead server, then a 1600-token budget the model
spent entirely on reasoning). It is the DECISIVE gate for this office, so it
gets its own script rather than another 14-minute full re-run."""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import bench_bonsai2_2026_09_18 as B   # noqa: E402

async def main():
    with open(B.FLAG, "w", encoding="utf-8") as fh:
        fh.write(B.TOKEN)
    out = []
    try:
        await B.comfy_image.stop_server()
        await B.bonsai_llm.stop_server()
        await B.llm_router.unload_all_models()
        for label, exe, model, mmproj, modes in (
            ("CHALLENGER Bonsai 2 / HIP", B.CHALLENGER_EXE, B.CHALLENGER_MODEL,
             B.CHALLENGER_MMPROJ,
             [("default", None), ("medium", {"reasoning_effort": "medium"})]),
            ("CHAMPION Bonsai 1 / Vulkan", B.CHAMPION_EXE, B.CHAMPION_MODEL,
             B.CHAMPION_MMPROJ, [("default", None)]),
        ):
            B.bonsai_llm.BONSAI_SERVER_EXE = exe
            B.bonsai_llm.BONSAI_MODEL_PATH = model
            B.bonsai_llm.BONSAI_MMPROJ_PATH = mmproj
            print(f"\n======== {label} ========")
            if not await B.bonsai_llm.ensure_running():
                print("server would not start"); continue
            out.append({"label": label, "vocab": await B.run_vocab(label, modes)})
            await B.bonsai_llm.stop_server()
        p = os.path.join(B.REPO, "data", "vocab_gate_2026-09-18.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"\nsaved -> {p}")
        for s in out:
            v = [x for x in s["vocab"] if "complied" in x]
            print(f"{s['label']}: complied {sum(1 for x in v if x['complied'])}/{len(v)}"
                  f"  empty {sum(1 for x in v if x.get('empty_answer'))}")
    finally:
        try: await B.bonsai_llm.stop_server()
        except Exception: pass
        try:
            with open(B.FLAG, encoding="utf-8") as fh:
                mine = fh.read().strip() == B.TOKEN
            if mine: os.remove(B.FLAG)
        except OSError: pass
        print("flag released:", not os.path.exists(B.FLAG))

asyncio.run(main())
