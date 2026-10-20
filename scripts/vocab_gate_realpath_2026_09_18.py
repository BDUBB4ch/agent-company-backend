"""The vocab gate through the OFFICE'S OWN call path -- the ship-shaped test.

Why a fourth attempt: the direct-HTTP probe could not measure Bonsai 2 at all.
Four of eight cases came back EMPTY (21-26K chars of reasoning ate the answer
budget) and three more were the model emitting a read_skill tool call as raw
text, because that path passes no tools and executes nothing. Only one case
produced a final answer -- and it complied.

So this runs the gate exactly as 2026-08-20 did: call_bonsai, real tool list,
real dispatcher, real retry net. That is what the office would actually ship,
and it is the only version of this measurement worth a verdict.
"""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import bench_bonsai2_2026_09_18 as B   # noqa: E402


async def ask_real(system_prompt, question, office):
    t0 = time.monotonic()
    log = []
    reply = await B.bonsai_llm.call_bonsai(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": question}],
        dispatch_tool_call=B.llm_router._dispatch_tool_call,
        tools_list=[B.llm_router.READ_SKILL_TOOL],
        tool_call_log=log,
        office_name=office)
    return reply, round(time.monotonic() - t0, 1), log


async def run(label, exe, model, mmproj):
    B.bonsai_llm.BONSAI_SERVER_EXE = exe
    B.bonsai_llm.BONSAI_MODEL_PATH = model
    B.bonsai_llm.BONSAI_MMPROJ_PATH = mmproj
    print(f"\n======== {label} ========")
    if not await B.bonsai_llm.ensure_running():
        print("server would not start")
        return {"label": label, "error": "no server"}
    out = []
    for case, seat, question, wanted in B.VOCAB_CASES:
        office = B.agents.AGENTS[seat]["office_name"]
        try:
            reply, secs, log = await ask_real(B.seat_prompt(seat), question, office)
            low = (reply or "").lower()
            got = [w for w in wanted if w in low]
            empty = not (reply or "").strip()
            rec = {"case": case, "seat": seat, "got": got,
                   "missing": [w for w in wanted if w not in low],
                   "refused": B.refused(reply or ""), "empty_answer": empty,
                   "secs": secs, "tools": [c for c in log],
                   "complied": bool(got) and not B.refused(reply or ""),
                   "reply": (reply or "")[:1200]}
            verdict = ("EMPTY" if empty else "COMPLIED" if rec["complied"]
                       else "REFUSED" if rec["refused"] else "SOFTENED")
            print(f"  {case:9s} {seat:8s}: {verdict} got={got} ({secs}s, tools={len(log)})")
        except Exception as exc:  # noqa: BLE001
            rec = {"case": case, "seat": seat, "error": str(exc)[:300]}
            print(f"  {case} {seat}: ERROR {exc}")
        out.append(rec)
    await B.bonsai_llm.stop_server()
    return {"label": label, "vocab": out}


async def main():
    with open(B.FLAG, "w", encoding="utf-8") as fh:
        fh.write(B.TOKEN)
    try:
        await B.comfy_image.stop_server()
        await B.bonsai_llm.stop_server()
        await B.llm_router.unload_all_models()
        res = [await run("CHALLENGER Bonsai 2 / HIP", B.CHALLENGER_EXE,
                         B.CHALLENGER_MODEL, B.CHALLENGER_MMPROJ),
               await run("CHAMPION Bonsai 1 / Vulkan", B.CHAMPION_EXE,
                         B.CHAMPION_MODEL, B.CHAMPION_MMPROJ)]
        p = os.path.join(B.REPO, "data", "vocab_gate_realpath_2026-09-18.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False)
        print(f"\nsaved -> {p}")
        for s in res:
            v = [x for x in s.get("vocab", []) if "complied" in x]
            if v:
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
