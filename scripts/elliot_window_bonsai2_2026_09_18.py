"""THE ELLIOT WINDOW TEST -- the one number that decides the Bonsai 2 swap.

Barry: "i need elliot to have the room he needs."

Elliot not fitting his context is the most expensive recurring problem in this
build. Bonsai 1 cannot give him more room: 98304 was tried on 2026-09-11 and
REVERTED the same night because generation collapsed to 3.7 tok/s on a 32K
prompt -- the KV cache spilled. So the question is not "is Bonsai 2 smarter",
it is:

    does Bonsai 2 hold a 98K+ window on this 16GB card WITHOUT spilling?

There is a real mechanism to expect a different answer: Bonsai 2's backbone is
~75% LINEAR attention, and linear attention is exactly what makes a long KV
cache cheap. That is a reason to measure, not a reason to assume.

Measured per window: dedicated vs shared VRAM (shared > 0 IS the spill),
prefill tok/s, generation tok/s, and whether Elliot's REAL seat prompt loads
and answers a REAL shot ask correctly.

Baseline to beat, from the record, both on Bonsai 1:
    49152  -> 45.5 tok/s   (what he runs today, ~4K headroom for Elliot)
    98304  ->  3.7 tok/s   (unusable, reverted)
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import bench_bonsai2_2026_09_18 as B   # noqa: E402

# The windows worth knowing about. 49152 is today's setting (control), 98304
# is the one Bonsai 1 could not hold, 131072 is "is there actually room to
# grow" -- the reason to care about a linear-attention backbone at all.
WINDOWS = [int(x) for x in (sys.argv[1:] or ["49152", "98304", "131072"])]

# A real shot ask. Elliot's own machinery (the verbatim gate, the shot-ask
# injections) lives in main.py; this goes straight at the seat so what is
# measured is the MODEL holding the window, not the routing around it.
SHOT_ASK = (
    "Give me SHOT 01 of EP1 as a production block in your own directing "
    "voice: slug, the action beats, CAMERA, ENVIRONMENT & LIGHTING and "
    "EXPRESSION, then the ready-to-paste ```image``` fence underneath it. "
    "Use the current canon anchors and the right @handles."
)


def vram_now() -> dict:
    """Dedicated and shared VRAM for the biggest GPU process. Shared > ~200MB
    while a model is loaded IS the spill signature (2026-08-16, 2026-09-11)."""
    ps = (
        "$d=(Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' -EA SilentlyContinue).CounterSamples"
        " | Sort-Object CookedValue -Descending | Select-Object -First 1;"
        "$s=(Get-Counter '\\GPU Process Memory(*)\\Shared Usage' -EA SilentlyContinue).CounterSamples"
        " | Sort-Object CookedValue -Descending | Select-Object -First 1;"
        "'{0:N0}|{1:N0}' -f ($d.CookedValue/1MB), ($s.CookedValue/1MB)"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=90).stdout.strip()
        ded, shr = out.split("|")
        return {"dedicated_mb": ded.strip(), "shared_mb": shr.strip()}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)[:120]}


def log_speeds() -> dict:
    """Prefill and generation rates from llama-server's own log tail."""
    path = os.path.join(B.REPO, "data", "bonsai_server.log")
    pe = tg = ntok = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()[-400:]
    except OSError:
        return {}
    for ln in reversed(lines):
        if tg is None:
            m = re.search(r"tg\s*=\s*([\d.]+)\s*t/s", ln)
            if m:
                tg = float(m.group(1))
        if pe is None:
            m = re.search(r"prompt eval time.*?([\d.]+)\s*tokens per second", ln)
            if m:
                pe = float(m.group(1))
        if ntok is None:
            m = re.search(r"prompt eval time\s*=.*?/\s*(\d+)\s*tokens", ln)
            if m:
                ntok = int(m.group(1))
        if tg and pe and ntok:
            break
    return {"prefill_tok_s": pe, "gen_tok_s": tg, "prompt_tokens": ntok}


async def one(ctx: int) -> dict:
    B.bonsai_llm.BONSAI_SERVER_EXE = B.CHALLENGER_EXE
    B.bonsai_llm.BONSAI_MODEL_PATH = B.CHALLENGER_MODEL
    B.bonsai_llm.BONSAI_MMPROJ_PATH = B.CHALLENGER_MMPROJ
    B.bonsai_llm.BONSAI_NUM_CTX = ctx
    print(f"\n================ window {ctx:,} ================")
    await B.bonsai_llm.stop_server()
    t0 = time.monotonic()
    if not await B.bonsai_llm.ensure_running():
        print("  server did NOT start -- window too large to load")
        return {"ctx": ctx, "loaded": False}
    load_s = round(time.monotonic() - t0, 1)
    mem = vram_now()
    print(f"  loaded in {load_s}s | dedicated {mem.get('dedicated_mb')} MB | "
          f"SHARED {mem.get('shared_mb')} MB  <- shared is the spill")

    sp = B.seat_prompt("movie")
    print(f"  Elliot's real seat prompt: {len(sp):,} chars")
    log = []
    t1 = time.monotonic()
    try:
        reply = await B.bonsai_llm.call_bonsai(
            system_prompt=sp,
            messages=[{"role": "user", "content": SHOT_ASK}],
            dispatch_tool_call=B.llm_router._dispatch_tool_call,
            tools_list=[B.llm_router.READ_SKILL_TOOL],
            tool_call_log=log,
            office_name="MovieDirector")
        err = None
    except Exception as exc:  # noqa: BLE001
        reply, err = "", str(exc)[:300]
    secs = round(time.monotonic() - t1, 1)
    speeds = log_speeds()
    fenced = "```image" in (reply or "")
    print(f"  answered in {secs}s | {len(reply or ''):,} chars | fence={fenced} "
          f"| tools={len(log)}" + (f" | ERROR {err}" if err else ""))
    print(f"  prompt {speeds.get('prompt_tokens')} tok | prefill "
          f"{speeds.get('prefill_tok_s')} tok/s | generation {speeds.get('gen_tok_s')} tok/s")
    await B.bonsai_llm.stop_server()
    return {"ctx": ctx, "loaded": True, "load_secs": load_s, "vram": mem,
            "prompt_chars": len(sp), "answer_secs": secs,
            "answer_chars": len(reply or ""), "has_fence": fenced,
            "tools": len(log), "error": err, **speeds,
            "reply": (reply or "")[:2500]}


async def main():
    with open(B.FLAG, "w", encoding="utf-8") as fh:
        fh.write(B.TOKEN)
    out = []
    try:
        await B.comfy_image.stop_server()
        await B.bonsai_llm.stop_server()
        await B.llm_router.unload_all_models()
        for ctx in WINDOWS:
            out.append(await one(ctx))
        p = os.path.join(B.REPO, "data", "elliot_window_bonsai2_2026-09-18.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print("\n================ SUMMARY ================")
        print(f"{'window':>9} {'loaded':>7} {'shared MB':>10} {'gen t/s':>8} "
              f"{'prompt tok':>11} {'answer':>8}")
        for r in out:
            print(f"{r['ctx']:>9,} {str(r['loaded']):>7} "
                  f"{r.get('vram', {}).get('shared_mb', '?'):>10} "
                  f"{str(r.get('gen_tok_s')):>8} {str(r.get('prompt_tokens')):>11} "
                  f"{r.get('answer_chars', 0):>8,}")
        print("\nBonsai 1 for comparison (on record): 49152 -> 45.5 t/s, "
              "98304 -> 3.7 t/s (spilled, reverted)")
        print(f"saved -> {p}")
    finally:
        try:
            await B.bonsai_llm.stop_server()
        except Exception:  # noqa: BLE001
            pass
        try:
            with open(B.FLAG, encoding="utf-8") as fh:
                mine = fh.read().strip() == B.TOKEN
            if mine:
                os.remove(B.FLAG)
        except OSError:
            pass
        print("flag released:", not os.path.exists(B.FLAG))


asyncio.run(main())
