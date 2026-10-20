"""Breaker reliability fixes (2026-09-28) -- no GPU, no real model calls.

Stubs Bonsai and the Ollama fallback, then checks:
  A. a timeout on a HEALTHY server falls back and is NOT counted
  B. a timeout on an UNREACHABLE server IS counted (2 trip the breaker)
  C. requests refused while tripped are NOT counted and do NOT re-arm the window
  D. the 600s window then lets Bonsai back in
"""
import asyncio
import sys
import time

sys.path.insert(0, "backend")
import httpx
import bonsai_llm
import comfy_image
import llm_router

state = {"healthy": True, "bonsai_calls": 0, "fallbacks": 0}


async def fake_unload(*a, **k):
    return None


async def fake_stop():
    return None


async def fake_ensure():
    return True


async def fake_available():
    return state["healthy"]


async def fake_call_bonsai(*a, **k):
    state["bonsai_calls"] += 1
    raise httpx.ReadTimeout("")


async def fake_ollama(*a, **k):
    state["fallbacks"] += 1
    return "fallback answer"


llm_router._unload_models = fake_unload
comfy_image.stop_server = fake_stop
bonsai_llm.ensure_running = fake_ensure
bonsai_llm.is_available = fake_available
bonsai_llm.call_bonsai = fake_call_bonsai
llm_router.call_ollama = fake_ollama
bonsai_llm.event = lambda m: print("   event:", m)


async def one(office="Operations"):
    return await llm_router.call_bonsai_with_fallback("sys", [{"role": "user", "content": "hi"}],
                                                      office_name=office)


def reset():
    bonsai_llm._consecutive_failures = 0
    bonsai_llm._tripped_at = None


async def main():
    ok = True
    print("A. timeouts on a healthy server")
    reset(); state["healthy"] = True
    for _ in range(3):
        await one()
    a = bonsai_llm._consecutive_failures == 0 and not bonsai_llm.is_tripped()
    print("   failures counted:", bonsai_llm._consecutive_failures, "| tripped:", bonsai_llm.is_tripped(), "->", "PASS" if a else "FAIL")
    ok &= a

    print("B. timeouts on an unreachable server")
    reset(); state["healthy"] = False
    await one(); await one()
    b = bonsai_llm.is_tripped()
    print("   failures counted:", bonsai_llm._consecutive_failures, "| tripped:", b, "->", "PASS" if b else "FAIL")
    ok &= b

    print("C. calls while tripped")
    armed_at = bonsai_llm._tripped_at
    calls_before = state["bonsai_calls"]
    for _ in range(5):
        await one("MovieDirector")
    c = (bonsai_llm._tripped_at == armed_at and bonsai_llm._consecutive_failures == 2
         and state["bonsai_calls"] == calls_before)
    print("   window re-armed:", bonsai_llm._tripped_at != armed_at, "| failures:", bonsai_llm._consecutive_failures,
          "| Bonsai tried:", state["bonsai_calls"] - calls_before, "->", "PASS" if c else "FAIL")
    ok &= c

    print("D. after the window, one real try")
    bonsai_llm._tripped_at = time.time() - bonsai_llm._TRIP_RESET_SECONDS - 1
    state["healthy"] = True
    calls_before = state["bonsai_calls"]
    await one()
    d = state["bonsai_calls"] == calls_before + 1
    print("   Bonsai tried again:", d, "->", "PASS" if d else "FAIL")
    ok &= d

    print("ALL PASS" if ok else "SOMETHING FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
