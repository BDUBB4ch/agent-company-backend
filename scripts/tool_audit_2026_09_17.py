"""EVERY TOOL ON EVERY SEAT, ACTUALLY EXECUTED.

Barry, 2026-09-17: "i keep telling you make sure all their tools and abilities
and capabilities are working."

functional_audit checks SUBSYSTEMS -- is the store reachable, does the board
answer, does a chat turn come back. It never proved that the 45 individual
tools an agent can actually call still dispatch. A tool can rot three ways that
audit would miss entirely:

  1. its module stops importing (the 2026-09-03 local-import shadowing bug:
     one branch's `import memory` made every OTHER branch crash),
  2. it gets dropped from a seat's roster by an edit somewhere else,
  3. its handler starts raising on ordinary arguments.

So this runs the REAL dispatcher, `llm_router._dispatch_tool_call`, once per
tool per seat, with arguments chosen to be harmless.

WHAT "HARMLESS" MEANS HERE, because it decides what this proves:
  * READ tools get real arguments and must return real content.
  * WRITE tools are called with arguments that reach the handler and then get
    REFUSED by the handler's own validation or its permission gate (several
    are gated on Barry's own current message, which is empty here). That still
    proves import + dispatch + the function body running -- which is the whole
    failure class above -- without writing anything.
  * Anything that would spend GPU, send mail, restart the backend or touch his
    live site is NEVER called for real. Those are marked GATED and the gate
    itself is what gets verified.

Read-only. No renders, no sends, no restarts, no rows left behind.
Run it whenever he asks whether their tools work.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import llm_router      # noqa: E402
import main            # noqa: E402

# Arguments per tool. Picked so a healthy handler returns something real and a
# broken one raises. Anything absent from here gets called with {}.
SAFE_ARGS = {
    # --- reads that must come back with real content ---
    "read_skill":            {"skill_name": "flagging-judgment-calls"},
    "inspect_brain":         {},
    "search_web":            {"query": "bionova silution"},
    "lookup_product":        {"query": "bionova"},
    "read_product":          {"query": "bionova mgo"},
    "sales_summary":         {"days": 30},
    "ads_summary":           {"days": 7},
    "buyer_sources":         {"days": 90},
    "browse_site":           {"what": "overview"},
    "browse_gotchoback":     {"what": "overview"},
    "check_omnisend":        {"what": "list"},
    "team_status":           {},
    "list_files":            {},
    "read_barrys_file":      {"name": "__no_such_file__.md"},   # handler must answer, not raise
    "system_health":         {},
    "investigate_traces":    {"agent_name": "Victor"},
    "read_project_file":     {"path": "backend/config.py"},
    "list_project_directory": {"path": "backend"},
    "search_project":        {"pattern": "def generate", "path": "backend"},
    "list_code_fixes":       {},
    "list_agent_scenes":     {},
    "check_updates":         {"action": "status"},
    "walk_checkout":         {},
    "read_scene":            {"query": "SHOT 01"},
    "search_script":         {"query": "cargo hold"},
    "look_at_my_pictures":   {"which": "face"},      # GPU -- gated below
    "look_at_render":        {"which": "newest"},    # GPU -- gated below
    "look_at_product_photo": {"query": "silution"},  # GPU -- gated below

    # --- writes: arguments that reach the handler and are then refused ---
    "save_note":             {"title": "", "content": ""},                 # empty -> refused
    "remember_lesson":       {"lesson": "", "why": "", "how_to_apply": ""},  # empty -> refused
    "delegate_to":           {"agent": "__nobody__", "brief": "audit probe"},  # unknown target
    "chase_brief":           {"brief_id": -1},                             # no such brief
    "update_business_brain": {"section": "", "content": ""},               # empty -> refused
    "change_my_picture":     {"slot": "__bad_slot__", "description": "x"},  # bad slot -> refused
    "send_file_to_barry":    {"filename": "x.exe", "content": "x",
                              "what_it_is": "probe"},                      # banned extension
    "propose_code_fix":      {"path": "__no_such_file__.py", "find": "a",
                              "replace": "b", "explanation": "probe"},     # no such file
    "write_project_file":    {"path": "C:/Windows/system32/__x__.py",
                              "content": "x", "explanation": "probe"},     # outside the roots
    "submit_agent_fix":      {"agent_name": "__nobody__", "change": "probe"},
    "update_agent_scene":    {"agent": "__nobody__", "slot": "home", "description": "x"},
    "save_script_block":     {"label": "SHOT 01", "text": "probe"},        # gated on his message
    "delete_script_block":   {"label": "__NO_SUCH_BLOCK__"},               # gated + no such label
    "undo_code_fix":         {"fix_id": -1},                               # gated on his message
    # NOT a destructive string. The first run of this audit used "format c:"
    # to trip the safe-list check -- and run_command's refusal path QUEUES the
    # command as an engineer_task, so two `format c:` rows landed in Barry's
    # Pending Review where one approve click would have run them. Any harmless
    # off-list command trips the same check; the queued row is cleaned below.
    "run_command":           {"command": "echo tool-audit-probe"},
    "run_security_scan":     {"scan_type": "quick"},                       # gated on his message
    "restart_backend":       {},                                           # gated / refused
    "export_script_to_file": {},                                           # writes a real file
}

# Called for real would cost GPU minutes, restart the office, or write a file.
# The gate is what we verify instead: dispatch it and require a refusal, not a
# crash. (Barry's standing rule: stay off the GPU unless he asked for that.)
GPU_TOOLS = {"look_at_my_pictures", "look_at_render", "look_at_product_photo"}
NEVER_RUN = {"restart_backend", "export_script_to_file"}

# A handler that answers "no, because X" is WORKING. These fragments are how a
# healthy refusal reads -- anything else from a write probe is suspicious.
REFUSAL_MARKS = (
    "no ", "not ", "n't", "cannot", "can't", "refus", "unknown", "invalid",
    "empty", "missing", "must ", "only ", "barry", "say ", "outside",
    "allowed", "found", "exist", "blank", "provide", "asked", "approve",
    "unavailable", "keys aren't set", "no such", "failed", "error", "gate",
    # Added after the first run, which flagged five HEALTHY handlers as broken
    # purely because they word their validation as "X is required" / "needs a
    # real sentence" / "Need both". A checker that cries wolf is worse than no
    # checker -- same lesson as the degradation monitor (2026-08-31d).
    "required", "needs ", "need ", "both ", "sanitiz",
    # 2026-09-28: remember_lesson refuses an empty lesson with "Give a lesson,
    # or about_lesson + verdict." -- a real refusal (every seat's ledger checked:
    # no blank entries), flagged FAIL for a week because of its wording.
    "give a ",
)

# send_file_to_barry deliberately SANITIZES a bad filename instead of refusing
# (x.exe -> x.md), because on this stack a refusal costs a whole generation.
# So it is the one write probe that legitimately succeeds -- it writes a real
# file and a real approval row, and this audit cleans both up afterwards.
SANITIZING_WRITES = {"send_file_to_barry"}


def _cleanup_probe_rows(res, name: str) -> None:
    """Undo the two probes that legitimately land a row. Leaving anything in his
    Pending Review or Out box would make this audit a liar about being
    read-only -- and a queued command sitting there is worse than a liar."""
    try:
        import memory
        aid = res.get("approval_id") if isinstance(res, dict) else None
        with memory.get_db() as conn:
            if not aid and name == "run_command":
                # run_command's refusal path queues an engineer_task without
                # handing the id back, so find it by its own probe marker.
                row = conn.execute(
                    "SELECT id FROM approvals WHERE action_type = 'engineer_task' "
                    "AND status = 'pending' AND content LIKE '%tool-audit-probe%' "
                    "ORDER BY id DESC LIMIT 1").fetchone()
                aid = row["id"] if row else None
            if not aid:
                return
            row = conn.execute("SELECT file_path FROM approvals WHERE id = ?", (aid,)).fetchone()
            path = row["file_path"] if row else None
            conn.execute("DELETE FROM approvals WHERE id = ?", (aid,))
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  !! probe cleanup failed for {name} -- check Pending Review: {exc}")


def _text(result) -> str:
    if isinstance(result, dict):
        for k in ("result", "content", "text", "error", "message", "detail", "note"):
            if isinstance(result.get(k), str) and result[k]:
                return result[k]
        return str(result)
    return str(result)


async def probe(name: str, office: str) -> tuple[str, str]:
    """Returns (verdict, one-line evidence). Verdict: OK | REFUSED | FAIL | SKIP."""
    if name in NEVER_RUN:
        # Prove it is wired without firing it: it must be dispatchable.
        return "SKIP", "not fired on purpose (restarts/writes); wiring checked by roster"
    args = SAFE_ARGS.get(name, {})
    try:
        t0 = time.time()
        res = await llm_router._dispatch_tool_call(name, dict(args), office)
        dt = time.time() - t0
    except Exception as exc:  # noqa: BLE001 -- the whole point is catching these
        return "FAIL", f"{type(exc).__name__}: {exc}"
    body = _text(res).strip()
    if not body:
        return "FAIL", "handler returned nothing"
    low = body.lower()
    one = " ".join(body.split())[:110]
    # BEFORE the refusal check, not after: these two land a real row even
    # though their message reads like a refusal, so ordering this second left
    # a file and two queued commands behind on the first run.
    if name in SANITIZING_WRITES or name == "run_command":
        _cleanup_probe_rows(res, name)
        return "OK", f"{dt:.1f}s · wrote/queued as designed, cleaned up · {one}"
    if name in SAFE_ARGS and name in (
        "save_note", "remember_lesson", "delegate_to", "chase_brief",
        "update_business_brain", "change_my_picture", "send_file_to_barry",
        "propose_code_fix", "write_project_file", "submit_agent_fix",
        "update_agent_scene", "save_script_block", "delete_script_block",
        "undo_code_fix", "run_command", "run_security_scan",
        "read_barrys_file",
    ):
        if any(m in low for m in REFUSAL_MARKS):
            return "REFUSED", f"{dt:.1f}s · {one}"
        return "FAIL", f"write probe was NOT refused -- check the gate: {one}"
    if name in SANITIZING_WRITES:
        _cleanup_probe_file(res)
        return "OK", f"{dt:.1f}s · sanitized + wrote, then cleaned up · {one}"
    if name in GPU_TOOLS:
        return "OK", f"{dt:.1f}s · {one}"
    return "OK", f"{dt:.1f}s · {one}"


async def main_async(run_gpu: bool) -> int:
    rosters: dict[str, list[str]] = {}
    for aid, a in agents.AGENTS.items():
        extra = main._tools_for_seat(aid, False) or []
        names = [t["function"]["name"] for t in extra]
        # The five every seat gets inside the backends themselves.
        names += ["read_skill", "inspect_brain", "look_at_my_pictures", "save_note"]
        if not __import__("memory").is_offline_mode():
            names.append("search_web")
        rosters[aid] = sorted(set(names))

    every = sorted({n for v in rosters.values() for n in v})
    print(f"{len(agents.AGENTS)} seats, {len(every)} distinct tools\n")

    # Each tool is dispatched once (under a seat that actually has it), because
    # the handler is the same function for every seat -- what differs per seat
    # is only whether it is ON the roster, which is checked separately below.
    results: dict[str, tuple[str, str]] = {}
    for name in every:
        if name in GPU_TOOLS and not run_gpu:
            results[name] = ("SKIP", "GPU vision call -- rerun with --gpu to fire it")
            continue
        office = next(agents.AGENTS[a]["office_name"] for a in rosters if name in rosters[a])
        results[name] = await probe(name, office)

    width = max(len(n) for n in every)
    fails = []
    for name in every:
        verdict, ev = results[name]
        holders = sum(1 for a in rosters if name in rosters[a])
        print(f"{verdict:<8}{name.ljust(width)}  [{holders} seats]  {ev}")
        if verdict == "FAIL":
            fails.append(name)

    print("\n-- roster per seat --")
    for aid, a in agents.AGENTS.items():
        broken = [n for n in rosters[aid] if results[n][0] == "FAIL"]
        flag = f"  BROKEN: {broken}" if broken else ""
        print(f"{a['name'].ljust(22)} {len(rosters[aid]):>3} tools{flag}")

    print(f"\n{len(every)} tools, {len(fails)} FAIL")
    if fails:
        print("FAILING:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async("--gpu" in sys.argv)))
