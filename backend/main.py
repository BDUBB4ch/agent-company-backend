"""
The runtime. Serves the chat + approval + memory API that AgentDashboard
(the web frontend) calls into. The Godot 3D office has been retired -- the
web dashboard is the only client now.

HARD RULES ENFORCED HERE (not just described in prompts):
  1. Only the CIO is the default target of the main chat bar. Any other
     agent can be messaged directly if the frontend requests it.
  2. No code path in this file calls out to a social API, email API, or
     website API to actually publish anything. External actions only ever
     get INSERTed into the approvals table. Nothing auto-executes.
  3. Approving an item in the queue does not auto-send it either - it just
     marks it approved. Actually wiring an approved item to go out is a
     separate, deliberate integration you'd add later per-channel.
  4. Vivian (Creative Director) generating an image (via AmuseBridge/
     TensorStack) is not an exception to rule 1/2 -- the generated file
     lands in the approval queue like everything else, never anywhere live.
"""
import applog
import datetime
applog.setup()  # must run before anything else can print -- see applog.py

import asyncio
import re
import shutil
import time
import json
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from agents import private_turn as _private_turn, AGENTS, EXTERNAL_ACTION_TYPES, CREATIVE_ID, ENGINEER_ID, CIO_ID, TALIYAH_ID, OPERATIONS_ID, MOVIE_ID, BUSINESS_ID, MARKETING_ID, LEGAL_ID, build_hired_agent_prompt, pinned_skills_for, _TALKS_LIKE_A_PERSON, CREATOR_WORDS
# Same sentinel pair both guards use to hold the owner's own typed words out
# of a scrub -- one implementation so the two can never drift apart.
from agents import _protect as _keep_protect, _restore as _keep_restore
import config
import memory
import llm_router
import recall
import reasoning
import jobs
import ingest
import bizwatch
import ads_feed
import braingraph
import reflect
import life                  # their life between conversations: threads, events
import clock                 # office hours: Mon-Fri 9am-6pm, live in app_settings
import social as breakroom   # renamed 2026-08-31; alias keeps call sites stable
import mood
import relationships
import script_index
import script_pos
# Imported for LEDGER_SOURCE so the ledger's name lives in exactly one place.
# It used to be a literal here ("ep1-v9A.1-live-state") and every version bump
# meant remembering to change it in two files -- V9 -> V9A -> V9A.1 each did.
import script_wip
import standing_rules
import dispatch
import codefix
import watch                 # Sophie's watch: mechanical checks, a note only when something changed
import tracing               # call-context tags (chat vs task) for the degradation monitor
import teamwork              # the company task board: briefs that actually get worked
import home_refresh          # their places change: one seat every ~30h asked, as themselves, then queued
import omnisend_client
import tone_guard
import comfy_image
import update_checker  # noqa: F401 -- superseded by updates.py (2026-09-06), kept importable
import updates
import agent_files           # FILES (2026-09-06): agents read his drops, write documents, hand them over
import piper_tts
import kokoro_tts
import searxng_search
import ideation
import db_backup
import document_extract
import bonsai_llm
import claim_net
import outcomes
import learning_review

# Agents hired live through the CIO's "Hire" flow (see /api/agents/hire
# below) rather than hand-written in agents.py -- kept separate from the
# static AGENTS roster so that dict stays the readable source of truth for
# the original 7, but every lookup below checks both via get_agent()/
# all_agents() so a hire is indistinguishable from a built-in agent once
# it exists. Reloaded from the database at startup so a hire survives a
# backend restart.
CUSTOM_AGENTS: dict = {}


def _register_hire(record: dict, business_context: bool) -> dict:
    """Put a hire on the same footing as the nine -- ONE place, so the hire
    endpoint and the startup reload can never drift apart (they were two
    copies of the same dict until 2026-09-18).

    Barry, 2026-09-18: "once I give them their persona and personality during
    onboarding, they then get all the other things that are needed for their
    job." This is the "other things" that are free -- a prompt built from the
    shared blocks, a working model, and a seat the team can actually reach.
    The JOB KIT itself (reference documents for their trade) is the domain
    grants on the hire request plus anything taught afterwards.
    """
    agent_id = record["agent_id"]
    office = record["office_name"]

    # THE FLOOR EVERY NEW AGENT STANDS ON (2026-09-18). A non-business hire is
    # walled off from the whole shared tier, which is correct and also leaves
    # them with an EMPTY shelf at birth -- so the generic craft (checking
    # numbers, reading and writing files, searching, thinking it through) is
    # granted here rather than being something he has to remember. Contains
    # nothing about his ventures or his data by construction; see
    # memory.KNOWN_DOMAINS.
    try:
        memory.grant_domain_access(office, "basics")
    except Exception as exc:  # noqa: BLE001 -- a missing grant never breaks a hire
        print(f"[hire] basics not granted to {office}: {exc}")

    # ⚠️ 'backend' is a DISPLAY field only. The 2026-09-18 audit first read the
    # hardcoded "ollama" here as "a hire runs on the old 9b" -- WRONG, and the
    # correction matters: _resolve_generation_for never consults this key, it
    # goes off the owner overrides then the global, so a hire has always
    # resolved to whatever the office is running (Bonsai today). /api/agents
    # returns the live resolved_backend beside it. Stamped from the global so
    # the display is at least honest at hire time.
    try:
        display_backend = memory.get_active_generation()[0]
    except Exception:  # noqa: BLE001 -- a display string never breaks a hire
        display_backend = "ollama"

    CUSTOM_AGENTS[agent_id] = {
        "name": record["name"],
        "office_name": office,
        "role": record["role"],
        # Kept on the live record so the chat-time owner guard can hold his own
        # typed words out of the scrub (see _owner_typed_words).
        "job_description": record["job_description"],
        "backend": display_backend,
        "business_context": business_context,
        "system_prompt": build_hired_agent_prompt(
            record["name"], record["role"], record["job_description"],
            business_context=business_context,
            # 2026-10-08: a hire he keeps (KNOWS_ABOUT "everything" -- Ilnora) is not rewritten owner-neutral
            his="everything" in memory.knows_about(office),
            creator_words=CREATOR_WORDS.get(office, ""),   # 2026-10-10: who he is to her, his words
        ),
    }

    # THEIR TEACH-DROP FOLDER, AT BIRTH (2026-09-19, Barry: "i need to be able
    # to drop files into her teach thing" / "the agent just needs the same
    # teach thing everyone else has"). The scanner SKIPS a kind directory that
    # is not on disk, so without this the first file he drops just sits there.
    # ⚠️ MUST RUN AFTER the CUSTOM_AGENTS line above -- ensure_tree reads
    # ingest.folder_map(), which reads that dict. Placed before it on the first
    # attempt and the folder silently did not appear while the log said it had.
    try:
        import ingest as _ingest
        _ingest.ensure_tree()
        print(f"[hire] teach folder ready: drop/{record['name'].split()[0]}/")
    except Exception as exc:  # noqa: BLE001 -- never breaks a hire
        print(f"[hire] could not make the teach folder for {office}: {exc}")

    # THE TEAM CAN REACH THEM, AND THEY CAN REACH THE TEAM (business hires).
    # Without this a new specialist is an island: nobody can delegate_to them
    # (the name resolves to nothing) and they cannot hand anything to Priya,
    # which is the one habit `working-with-your-teammates` exists to build.
    # Topical hires are deliberately left out -- they are not on the team.
    # 2026-10-10: a hire he keeps (KNOWS_ABOUT "everything" -- Ilnora) is on the board too (Barry: "they all need to
    # be able to communicat with each other on all levels").
    if business_context or "everything" in memory.knows_about(office):
        first = (record["name"] or "").strip().split()[0].lower()
        for key in {first, agent_id.lower(), office.lower()}:
            if key and key not in llm_router._DELEGATE_TARGETS:
                llm_router._DELEGATE_TARGETS[key] = office
        seat = _SEAT_TOOLS.setdefault(agent_id, [])
        for _t in (llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL):
            if _t not in seat:
                seat.append(_t)
    return CUSTOM_AGENTS[agent_id]


def _load_custom_agents():
    for record in memory.get_custom_agents():
        _register_hire(record, bool(record.get("business_context", 1)))


def _grant_tools_to_agent(agent: str, tools: list | None = None,
                          revoke: list | None = None, why: str = "") -> dict:
    """Give (or take back) runtime tools on one seat. Barry's word only -- the
    gate is in llm_router's grant_tools dispatch.

    Barry, 2026-09-18: "Sophie needs to be able to give tools too." The hardcoded
    rosters stay exactly as they are; this adds on top and is read live, so a
    grant works on the seat's very next message with no restart and no code edit.
    """
    office = _office_of((agent or "").strip()) or ""
    if not office:
        # Try the hires by name / first name, same resolution as onboarding.
        want = (agent or "").strip().lower()
        for r in memory.get_custom_agents():
            names = {r["agent_id"].lower(), (r["office_name"] or "").lower(),
                     (r["name"] or "").strip().lower()}
            if r["name"]:
                names.add(r["name"].strip().split()[0].lower())
            if want in names:
                office = r["office_name"]
                break
    if not office:
        import agents as _agents_mod
        import reflect as _reflect
        want = (agent or "").strip().lower()
        for aid, person in _reflect.HUMAN_NAMES.items():
            if want == (person or "").lower():
                office = _office_of(aid)
                break
    if not office:
        return {"status": "refused", "why": f"I cannot work out who '{agent}' is."}

    given, refused, taken = [], [], []
    for name in (tools or []):
        name = str(name).strip()
        if name in _TOOL_GRANT_DENY:
            refused.append({"tool": name, "why": "never grantable at runtime -- "
                            "it changes this machine, this codebase, or grants"})
            continue
        if name not in _TOOLS_BY_NAME:
            refused.append({"tool": name, "why": "no tool by that name -- "
                            f"closest existing: {sorted(_TOOLS_BY_NAME)[:6]}"})
            continue
        memory.grant_tool(office, name, why)
        given.append(name)
    for name in (revoke or []):
        name = str(name).strip()
        if memory.revoke_tool(office, name):
            taken.append(name)
        else:
            refused.append({"tool": name, "why": "not a runtime grant on that seat "
                            "-- a tool the CODE gives cannot be taken away here"})

    line = (f"[tools] {office}: granted {given or 'none'}"
            + (f", revoked {taken}" if taken else "")
            + (f" -- {why.strip()}" if why.strip() else ""))
    print(line)
    try:
        with open(os.path.join(config.DATA_DIR, "onboarding.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {line}\n")
    except Exception:  # noqa: BLE001
        pass

    roster = _tools_for_seat(
        next((a for a, o in [(r["agent_id"], r["office_name"]) for r in memory.get_custom_agents()]
              if o == office), None)
        or next((aid for off, aid in __import__("agents").OFFICE_NAME_TO_AGENT_ID.items()
                 if off == office), ""),
        memory.is_offline_mode())
    return {
        "status": "done",
        "office": office,
        "granted": given,
        "revoked": taken,
        "refused": refused,
        "tools_they_now_have": sorted(t["function"]["name"] for t in (roster or [])),
        "note": ("Live on their next message -- no restart. Runtime grants are "
                 "additive: anything the code gives them cannot be revoked here."),
    }


def _onboard_to_team(agent: str, domains: list | None = None, why: str = "") -> dict:
    """Put an existing HIRE on the team. Barry's word only -- see the gate in
    llm_router's onboard_agent_to_team dispatch.

    Barry, 2026-09-18: "if a new agent joins the team, then Sophie can handle
    that part. my business should be a thing thats called not just sitting there
    to be given away." So this is the CALL. A hire is born blank; the business
    arrives here, deliberately, named, and logged -- never as a field on the
    hire form.

    What it does and does not do, because the difference is the whole ruling:
      DOES  -- grant the named existing domains (the shelves that already exist
               for his nine), turn on the team block and the owner block, give
               them delegate_to, and put them in the delegate map so the team
               can reach them.
      DOES NOT -- open the shared tier. `memory.shared_tier_offices()` is his
               nine and stays his nine, so his owner-identity facts, the
               ventures' own facts, the catalog, the canon and PID are still
               unreachable. A teammate gets the CRAFT, by grant; his private
               record stays his.
    """
    hires = {r["agent_id"]: r for r in memory.get_custom_agents()}
    want = (agent or "").strip().lower()
    row = None
    for r in hires.values():
        if want in {r["agent_id"].lower(), (r["office_name"] or "").lower(),
                    (r["name"] or "").strip().lower(),
                    (r["name"] or "").strip().split()[0].lower() if r["name"] else ""}:
            row = r
            break
    if row is None:
        import agents as _agents_mod
        if want in {o.lower() for o in _agents_mod.OFFICE_NAME_TO_AGENT_ID}:
            return {"status": "refused",
                    "why": f"{agent} is one of the nine -- already on the team."}
        return {"status": "refused",
                "why": f"No hired agent matches '{agent}'. Hires: "
                       f"{[r['name'] for r in hires.values()] or 'none'}"}

    bad = [d for d in (domains or []) if d not in memory.KNOWN_DOMAINS]
    if bad:
        return {"status": "refused",
                "why": f"Unknown domain(s) {bad}. Existing: {sorted(memory.KNOWN_DOMAINS)}. "
                       f"A NEW shelf has to be built and named before it can be granted."}

    granted = []
    for d in (domains or []):
        try:
            memory.grant_domain_access(row["office_name"], d)
            granted.append(d)
        except Exception as exc:  # noqa: BLE001
            print(f"[onboard] {d} not granted to {row['office_name']}: {exc}")

    with memory.get_db() as conn:
        conn.execute("UPDATE custom_agents SET business_context = 1 WHERE agent_id = ?",
                     (row["agent_id"],))
    row = dict(row)
    row["business_context"] = 1
    _register_hire(row, True)

    line = (f"[onboard] {row['name']} ({row['office_name']}) joined the team"
            f"{' -- ' + why.strip() if why.strip() else ''}; domains granted: "
            f"{granted or 'none'}")
    print(line)
    try:
        with open(os.path.join(config.DATA_DIR, "onboarding.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {line}\n")
    except Exception:  # noqa: BLE001 -- a log line never breaks the onboarding
        pass

    return {
        "status": "onboarded",
        "agent": row["name"],
        "office": row["office_name"],
        "domains_granted": granted,
        "now_has": "the team block, the owner block, delegate_to, and the shelves above",
        "still_cannot_see": ("Barry's own facts, the ventures' own facts, the product "
                             "catalog, the Talia Crew canon and PID -- the shared tier "
                             "is his nine seats only and onboarding does not change that"),
        "facts_on_their_shelf": len(memory.get_active_facts_for_agent(row["office_name"])),
    }


def all_agents() -> dict:
    return {**AGENTS, **CUSTOM_AGENTS}


def get_agent(agent_id: str):
    return AGENTS.get(agent_id) or CUSTOM_AGENTS.get(agent_id)


# Sophie (Engineer) runs a coding-specialized model instead of whatever the
# global Ollama model dropdown is set to -- code quality comes from the base
# model, not the skill files, and qwen3.5 isn't a coding-specialized model.
# Only applies when the global backend is "ollama"; if Barry switches the
# whole office to Claude, she just uses that like everyone else (Claude
# doesn't have a separate coder variant the way Ollama does). The original
# 400 error this caused was a real bug in this codebase (llm_router.py sent
# think:True to a model that doesn't support "thinking" -- fixed via
# per-model capability detection, see llm_router._get_model_capabilities),
# not a problem with the model itself.
# qwen3.5:9b (the global default) has real alignment-training refusal
# behavior for gore+nudity combined (plain gore/violence alone is fine --
# confirmed) that no prompt wording fixes. Two alternatives were tried and
# both rejected for Vivian/Elliot/Taliyah:
#   - hermes3:8b: fixed the refusal, but broke image-fence following (had
#     to be routed around in code) and flattened personality.
#   - huihui_ai/gemma-4-abliterated:12b: confirmed via direct timing test
#     to take 120s+ just to LOAD, and a real end-to-end request against
#     Taliyah's full system prompt hit the backend's own 300s httpx
#     timeout and hard-failed (never completed at all). Not viable on this
#     GPU regardless of content-permissiveness, full stop.
# Back to qwen3.5:9b for all three -- fast and good personality is the
# higher priority; the gore+nudity-combined refusal is a known, accepted
# gap until a genuinely fast uncensored option turns up.
# A seat's safety-net model for Bonsai failures (passed to llm_router as
# fallback_model). SEPARATE from AGENT_OLLAMA_MODEL_OVERRIDES on purpose:
# an entry here does NOT pin the seat -- it only names where the seat lands
# when Bonsai errors mid-turn, so Sophie's failures go to her measured
# coder model instead of the office's 9b default.
AGENT_BONSAI_FALLBACK_MODELS = {
    ENGINEER_ID: "qwen2.5-coder:14b",
}

AGENT_OLLAMA_MODEL_OVERRIDES = {
    # SOPHIE REBUILT ON BONSAI 2026-08-16 (Barry: "maybe totally rebuild
    # Sophie on Bonsai?") -- her entry removed from this map, so she follows
    # the global like the business seats. The old "must NEVER move to
    # Bonsai" rule was real but its causes are now individually fixed and
    # verified on the exact question that used to kill her:
    #   1. read_project_file returned up to 50K chars PER READ -- five reads
    #      = 71,643 tokens = past even the 65K window (llama-server 400s
    #      honestly where Ollama silently truncated). Cap is now 12K.
    #   2. Exhausted tool rounds returned a guard string instead of an
    #      answer -- now a forced no-tools synthesis pass (both backends).
    #   3. Bonsai emitted text-shaped tool calls it never executed (the
    #      documented latent pseudo-tool-call gap) -- now parsed, executed,
    #      and stripped (bonsai_llm._parse_pseudo_xml_calls).
    #   4. Her Bonsai failures fell back to the 9b -- now land on her coder
    #      model via AGENT_BONSAI_FALLBACK_MODELS above, plus the
    #      guard-string retry net at the generate call site.
    # Verified after all four: 2,065-char correct diagnosis, tools
    # ['read_project_file' x3, 'investigate_traces'] all executed, no
    # fallback, no leaked syntax. REVERT = put
    # `ENGINEER_ID: "qwen2.5-coder:14b",` back here + restart.
    # MARCUS (legal) and AMARA (business) MOVED TO BONSAI 2026-08-11 -- they
    # are deliberately absent from this map now, so they follow the global
    # backend. Owner: "marcus and Amara can go on bonsai too if they need it
    # to be smarter." Measured, not assumed
    # (data/bonsai_content_and_reasoning.json):
    #   LEGAL -- decisive, and the reason this happened. Asked whether a
    #     truthful single-customer "40% yield increase" can be advertised, the
    #     14b answered "The ad can run" and called the customer's grow logs
    #     sufficient substantiation. That is wrong and it is the expensive kind
    #     of wrong. Bonsai answered "No -- not without qualifying the claim",
    #     citing competent-and-reliable evidence and the typical-results
    #     requirement. 41.7s vs 61.8s.
    #   BUSINESS -- weaker evidence, recorded honestly. On a contribution-
    #     margin problem NEITHER model treated customer-paid shipping as an
    #     offset (the test prompt was ambiguous on that point), but the 14b was
    #     internally INCONSISTENT -- it charged the $12.95 in one scenario and
    #     dropped it in the other, inflating the benefit to $25.55 -- while
    #     Bonsai applied the cost consistently in both. 33.9s vs 69.3s.
    #     Amara moved on consistency + speed, not on a proven correctness win.
    # TO REVERT: re-add the two lines below and restart.
    #   "legal": "huihui_ai/qwen3-abliterated:14b",
    #   "business": "huihui_ai/qwen3-abliterated:14b",
    # Why the 14b was there at all, kept because it still matters on a revert:
    # huihui_ai/qwen3-abliterated:14b replaced phi4-reasoning:14b 2026-07-29 on
    # the owner's explicit call ("i dont want microsoft in my shit at all")
    # after phi-4 refused a plain business brainstorm ("I'm sorry, but I can't
    # comply with that") AND turned out to physically not fit the 16GB card at
    # its 32K context (16.9GB total, 86% GPU -- every reply partially on CPU,
    # 93-230s). The qwen3-abliterated 14B is uncensored, thinking-capable and
    # tool-capable. 9GB weights, 40K architectural ctx (capped in llm_router's
    # _NUM_CTX_BY_MODEL).
    # The uncensored trio stays on the abliterated model EXPLICITLY now --
    # with Bonsai as the office-wide main model (see _resolve_generation_for
    # below), the global default no longer happens to BE the abliterated
    # model, so what used to be redundant clarity is now load-bearing:
    # without these entries, Vivian/Elliot/Taliyah would silently move to
    # Bonsai and re-inherit refusal behavior for exactly the content the
    # abliterated model was chosen to handle (see the uncensored-model saga
    # in memory).
    #
    # ⚠️ THE CONTENT THAT ACTUALLY DROVE THIS CHOICE IS **NUDITY AND
    # GORE/INJURY** -- Barry, 2026-08-11: "the reason for the 9b, was because
    # the other models wouldnt do nudity or gore and injury." That is not a
    # historical footnote; it is the acceptance test for this seat. Vor'Shara's
    # own canon anchor specifies sheer fabric "revealing natural areola" and
    # pubic hair, and Elliot's film work is explicitly gore-allowed.
    # A 2026-08-11 attempt to move creative/taliyah to Bonsai was REVERTED
    # before going live for exactly this reason: the refusal probe that day
    # tested cannabis legal, a cannabis product shot, an affectionate personal
    # message and a violent takedown -- and passed all four -- but it never
    # tested nudity or graphic injury, so it proved nothing about the category
    # these three exist to serve. Do not move any of them on "no refusals"
    # evidence unless that evidence includes nudity AND gore/injury.
    #
    # ⚠️ SIMPLIFIED 2026-08-13 ON BARRY'S RULING. His words, verbatim: "the
    # smartest and best is Bonsai, the uncensored is the 9b. elliot should be
    # on 9b and taliyah. sophie has her own thing." So the rule for this whole
    # office is now three lines long:
    #     Bonsai   = the default for everyone (it is the smartest)
    #     9b       = Elliot + Taliyah ONLY (they are the uncensored seats)
    #     coder    = Sophie, always (see her entry above -- she must NEVER
    #                move to Bonsai; documented tool-loop failure)
    #
    # VIVIAN (CREATIVE_ID) WAS REMOVED FROM THIS MAP as part of that ruling --
    # he enumerated the 9b seats and she was not among them. That is consistent
    # with the line he drew 2026-08-08 ("Vivian... shes for the business
    # marketing images. for the business, not really for the movie. Elliot is
    # the Movie guy"): the nudity/gore content that justifies the 9b is Elliot's
    # film work and Taliyah's personal register, not B Dubb product shots.
    # She now follows the global and lands on Bonsai. If a business image ever
    # gets softened or refused, move her back by adding CREATIVE_ID here.
    # ELLIOT REMOVED FROM THIS MAP 2026-08-16 (Barry: "make his default
    # bonsai, not many scenes will be violents or nudity"). He now follows
    # the global (Bonsai) like the business seats. Made possible the same
    # day by two changes: the grammar unpin (his prompt fits) and
    # BONSAI_NUM_CTX 32768 -> 65536 (measured, probe script) -- before
    # those, Bonsai physically could not hold him. The trade Barry accepted:
    # Bonsai will not write explicit genital vocabulary (measured 2026-08-11,
    # 1/4 with silent substitutions) -- for the occasional explicit scene,
    # flip him to the 9b in the dashboard dropdown, then back. Canon-worded
    # nudity (areola/sheer/pubic) and gore both PASS on Bonsai -- also
    # measured. First message after a backend swap pays ~40-90s of prefill.
    # REVERT = restore "MOVIE_ID: config.OLLAMA_MODEL," here + restart.
    # TALIYAH REMOVED FROM THIS MAP 2026-08-20 (Barry: "taliya is on it too
    # once we get it working right") -- the day the Bonsai weights swapped to
    # the ABLITERATED build. Her 9b pin existed because the parent Bonsai
    # refused / silently softened her explicit register; the abliterated
    # build removed the refusals (0 across every 2026-08-20 bench). The
    # remaining gap is narrower and Barry accepted it: the bluntest VULGAR
    # vocabulary is still partial on Bonsai (2/3 and 1/3 keyword delivery vs
    # the 9b's 3/3) -- for those conversations, flip her to the 9b in the
    # dashboard dropdown, then back, same pattern as Elliot's explicit
    # scenes. REVERT = restore "TALIYAH_ID: config.OLLAMA_MODEL," + restart.
}
# Tried and reverted, same day: switching Taliyah to qwen3.5:9b to fix a
# tone-reliability issue with huihui_ai/qwen3-abliterated:8b-v2 (see
# memory's "real repetition bug" section). qwen3.5:9b handled a minimal
# direct test fine (21s, clean), but her FULL real prompt (personality +
# brain context + capability status + tools + thinking) repeatedly hung
# past the 300s httpx timeout with zero response -- confirmed twice, not a
# fluke. Reverted rather than leave her non-functional while investigating
# further. Worth retrying later with a smaller/lighter prompt or
# use_tools=False for her specifically, but not mid-crisis.
#
# Taliyah's actual tone fix (slang/nicknames/emoji) is NOT a model swap --
# see tone_guard.py. Four attempts at fixing this via prompt rewrite or
# model swap all failed to hold in live use; the fix applied instead is a
# deterministic post-generation cleanup pass (see the reply-handling code
# below).

# Agents whose replies get scanned for a ```image```/```negative``` fence.
# Was Vivian+Taliyah only; owner's call 2026-07-30 ("i need everyone to use
# comfy for generations"): every fixed agent generates through ComfyUI now.
# Agents without image-craft prompt guidance still work -- the
# _force_image_prompt fallback + prose guard write the clean fence for them.
IMAGE_CAPABLE_AGENT_IDS = {
    "cio", "operations", "business", "legal", "marketing",
    "creative", "movie", "engineer", "taliyah",
}


def is_image_capable(agent_id: str) -> bool:
    """EVERY AGENT GENERATES, HIRES INCLUDED (Barry, 2026-09-19: "all the
    generation stuff should be standard and comes with any new agent").

    The set above is the nine and cannot grow by itself, so a hired agent had
    no fence extraction and no picture of their own -- they could describe a
    render and never make one. A new agent is an agent: if the id resolves to
    a real seat (built-in or hired, in-memory dict lookup), generation is on.
    The set stays as the literal roster other code still reads."""
    return get_agent(agent_id) is not None

# ---------------------------------------------------------------------------
# WHICH SEAT GETS WHICH TOOLS -- one row per agent, read by chat().
#
# WHY THIS IS A TABLE (2026-08-31): these grants used to be a chain of
# `if req.agent_id == X` branches sitting in the middle of chat(), the single
# code path all nine seats run through. On 2026-08-31 a grant for MARCUS
# referenced an un-imported name, and because it lived in that shared path it
# took down chat for EVERYONE -- Barry lost Victor for eleven hours. One seat's
# configuration should never be able to break another seat's conversation.
#
# A row is data. It cannot throw. Adding a seat's tool is now editing a list,
# not editing the request path.
#
# NOTE these lists are COPIED at use (`list(...)`) before anything is appended.
# The old code did `extra_tools.append(...)` on a locally-built list; appending
# to a shared module-level list would permanently corrupt the table for every
# later request in the process.
# ---------------------------------------------------------------------------
_SEAT_TOOLS: dict[str, list] = {
    # Sophie: on-demand debugging + the coder upgrade (phases A+B, Barry's
    # "go" 2026-08-28). system_health is read-only; propose_code_fix and
    # update_agent_scene only QUEUE -- the write happens in the approve
    # endpoint, never here. Same approval-gated pattern as everything else.
    ENGINEER_ID: [
        llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL,
        llm_router.READ_PROJECT_FILE_TOOL,
        llm_router.LIST_PROJECT_DIRECTORY_TOOL,
        llm_router.INVESTIGATE_TRACES_TOOL,
        llm_router.SUBMIT_AGENT_FIX_TOOL,
        llm_router.SYSTEM_HEALTH_TOOL,
        llm_router.PROPOSE_CODE_FIX_TOOL,
        # 2026-09-02: she can apply simple/vital fixes herself (gated in
        # codefix), and Barry can tell her to undo (gated on HIS message).
        llm_router.UNDO_CODE_FIX_TOOL,
        llm_router.LIST_CODE_FIXES_TOOL,
        # SKILL INTAKE (2026-09-18, Barry: "i can grab it and she can place it
        # properly"). install_skill is a LOCAL DB write, so it stays attached
        # offline -- she can still file a document he downloaded himself into
        # the out box. The fetch-from-a-link half was DELETED 2026-09-19.
        llm_router.INSTALL_SKILL_TOOL,
        # HOST CHANGE BASELINE (2026-09-19). host_watch reports what changed on
        # the machine; this is how a change he made himself stops being
        # reported forever. Local, and the dispatch refuses unless HE said the
        # change was his.
        llm_router.ACCEPT_HOST_CHANGES_TOOL,
        # ONBOARDING A HIRE ONTO THE TEAM (2026-09-18, Barry: "if a new agent
        # joins the team, then Sophie can handle that part"). Local DB writes +
        # grants, so it stays attached offline; the real guard is that the
        # dispatch refuses unless Barry asked in his own message.
        llm_router.ONBOARD_TEAM_TOOL,
        # "Sophie needs to be able to give tools too" (2026-09-18). Same gate:
        # her hands, Barry's word. See _GRANT_TOOLS deny list -- she can hand out
        # capability, never the keys to the machine and never the grant itself.
        llm_router.GRANT_TOOLS_TOOL,
        # PC security (2026-09-07, "i want her to keep my pc safe"). Reading
        # Defender/firewall needs no tool -- it rides in system_health. This is
        # the one ACTION, and it is gated on Barry's own words in llm_router.
        llm_router.PC_SECURITY_SCAN_TOOL,
        # 2026-09-06 (Barry: "fully capable"): search, whole-file write, run,
        # restart, updates -- engineer_tools.py / codefix.propose_write.
        llm_router.SEARCH_PROJECT_TOOL,
        llm_router.WRITE_PROJECT_FILE_TOOL,
        llm_router.RUN_COMMAND_TOOL,
        llm_router.RESTART_BACKEND_TOOL,
        llm_router.CHECK_UPDATES_TOOL,
        llm_router.LIST_AGENT_SCENES_TOOL,
        llm_router.UPDATE_AGENT_SCENE_TOOL,
        # 2026-10-17: CAD parts for PID (cadgen, local, import-allowlisted script -> STEP/STL/PNG on his DESK). cad_tool.py
        llm_router.CAD_GENERATE_TOOL,
    ],
    # TEAMWORK (2026-09-02, Barry: "All of them needs to be able to work
    # together if needed"): delegate_to + team_status for every seat except
    # Taliyah (not business); chase_brief for the two who close loops.
    # delegate_to now files onto the company board and the office WORKS it
    # (teamwork.py) -- see the 2026-08-03 note: it used to be a note only.
    CIO_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL, llm_router.CHASE_BRIEF_TOOL],
    # Priya also writes the Business Brain (2026-08-29, Barry: "i want Priya
    # to interview me and then she lets everybody know") -- without it his
    # interview answers evaporate, measured. Local DB write, so offline mode
    # does NOT strip it.
    OPERATIONS_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL, llm_router.CHASE_BRIEF_TOOL,
                    llm_router.UPDATE_BUSINESS_BRAIN_TOOL],
    BUSINESS_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL],
    LEGAL_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL],
    MARKETING_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL],
    # VIVIAN SEES THE WORK (2026-09-10, "now do Vivian, everything she needs").
    # Local vision reads of the real product photos and of her own renders, so
    # deliberately HERE and not in _SEAT_STORE_TOOLS -- offline mode must not
    # blind the art director to files already sitting on this disk.
    CREATIVE_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL,
                  llm_router.LOOK_AT_PRODUCT_PHOTO_TOOL, llm_router.LOOK_AT_RENDER_TOOL,
                  # 2026-10-17: product spots (Hyperframes on the CPU -> his DESK; he posts). product_video.py
                  llm_router.PRODUCT_VIDEO_TOOL],
    # Taliyah is not staff, but her place is hers: change_my_picture only
    # (appended to every seat below) -- plus, since 2026-09-10, her own eyes.
    # She is image-capable like every seat and could not see a single thing she
    # made, so she was describing her own pictures from the prompt that made
    # them. look_at_render is keyed to HER agent_id and reads only her own
    # renders off local disk, so it carries none of the commercial stack that
    # _SHARED_CATEGORY_EXCLUSIONS deliberately keeps away from her.
    # DELEGATE_TOOL added 2026-09-18. Barry: "Taliya needs the research thing
    # too like priyah. She is who i talk to when i have ideas and need her to
    # search things up. she also needs to be able to put together my ideas i
    # come up with and file it and hand it to the team."
    # ⚠️ THIS DOES NOT MAKE HER A BUSINESS SEAT and must not be read that way.
    # She still carries no store or commercial tools, and the commercial fact
    # categories are still excluded from her in memory._SHARED_CATEGORY_
    # EXCLUSIONS. What she can now do is take an idea HE had, in HIS words,
    # and put it in front of the seat that owns it -- which needs no business
    # context at all, because the content is his, not hers. She is the intake
    # point for his thinking, not a participant in the commercial stack.
    TALIYAH_ID: [llm_router.LOOK_AT_RENDER_TOOL, llm_router.DELEGATE_TOOL,
                 llm_router.TEAM_STATUS_TOOL],   # 2026-10-10: on the board with everyone ("communicate ... on all levels")
    # Elliot: scene-level script access (2026-08-16) plus the living WIP
    # script (2026-08-20). read_skill could never serve these -- EP1 v7 is
    # 94,377 chars against a window already ~161,000 deep -- and he was
    # inventing scenes instead. Nobody else works from Barry's scripts, and
    # the canon they DO share is already reachable via read_skill. Local DB
    # reads, so NOT stripped by offline mode.
    MOVIE_ID: [llm_router.DELEGATE_TOOL, llm_router.TEAM_STATUS_TOOL,
               llm_router.READ_SCENE_TOOL,
               llm_router.SEARCH_SCRIPT_TOOL,
               llm_router.SAVE_SCRIPT_BLOCK_TOOL,
               llm_router.DELETE_SCRIPT_BLOCK_TOOL,
               # 2026-09-06: the whole script as a file, byte-exact from the
               # DB -- the only seat whose deliverable cannot fit a reply.
               llm_router.EXPORT_SCRIPT_TOOL],
}

# Live store access (2026-08-13, Barry: "I need my agents to be agents").
# Read-only by construction -- store.py contains no write verb at all.
#
# WHO GETS WHAT, and why it is not simply "everyone":
#   Marcus (legal)    -- lookup + browse. Added 2026-08-31: he had NO tools,
#       while his job is substantiating claims that are live on the store, so
#       he was reviewing copy he could not see. No sales figures: legal
#       questions are not answered by revenue.
#   Amara (business)  -- the finance seat, and the worst off before this:
#       every margin/AOV answer was reasoned from a number she could not check.
#   Derek (marketing) -- "what should I promote" is unanswerable without
#       knowing what actually sells.
#   Victor (CIO)      -- the strategy seat and default entry point, most often
#       asked "how are we doing" cold.
#   Vivian (creative) -- lookup + browse, NO sales figures (2026-08-21, Barry:
#       "she needs to be able to see my site, but not write. Not yet anyways").
# Deliberately excluded: Sophie (engineering), Elliot (film), and Taliyah --
# she is the personal seat, already excluded from the whole commercial stack
# by memory._SHARED_CATEGORY_EXCLUSIONS, and store tools would undo a
# separation Barry set deliberately.
#
# OFFLINE MODE STRIPS THIS WHOLE TABLE, exactly like web search: these are
# outbound requests to a live public site, so leaving them attached would put
# a hole in the hard privacy switch.
#
# NOTE check_competitor_prices is deliberately granted to NOBODY. Built and
# wired 2026-08-23, pulled back the same hour on Barry's call ("make it
# manual") -- an agent could fire it repeatedly and unattended, which is the
# pattern that looks like scraping and gets an IP blocked. It stays a script
# he or Claude runs: backend/competitor_watch.py. Re-grant by adding
# llm_router.CHECK_COMPETITOR_PRICES_TOOL to a row below; schema and dispatch
# are still live.
_SEAT_STORE_TOOLS: dict[str, list] = {
    LEGAL_ID:     [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL, llm_router.BROWSE_SITE_TOOL],   # read_product added 2026-09-08: he vets copy he could not read
    BUSINESS_ID:  [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL, llm_router.SALES_SUMMARY_TOOL,   # read_product added 2026-09-09 (pricing needs the description)
                   llm_router.BROWSE_SITE_TOOL, llm_router.WHAT_IS_SELLING_TOOL],
    # DEREK RUNS THE EMAIL (Barry, 2026-09-01: "i need someone to run the
    # omnisend... take Derek with you to teach him everything. I need him to be
    # able to do it"). check_omnisend is READ-ONLY by construction -- see
    # omnisend_view.py, which has no write verb in it. His two rulings are what
    # keep it at read: he can build a campaign and queue it for approval, and
    # he proposes changes to forms/automations rather than making them. Nobody
    # else has it: this is his job, and a second seat with an opinion about the
    # email list is how two people end up mailing the same customers.
    # read_product (Barry, 2026-09-01: "he needs to read all the product
    # descriptions before writing anything") goes to the two seats that WRITE
    # about products -- Derek (email/copy) and Vivian (product shots/copy).
    MARKETING_ID: [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL,
                   llm_router.SALES_SUMMARY_TOOL, llm_router.BROWSE_SITE_TOOL,
                   llm_router.WHAT_IS_SELLING_TOOL,
                   llm_router.OMNISEND_VIEW_TOOL],
    CIO_ID:       [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL, llm_router.SALES_SUMMARY_TOOL,
                   llm_router.BROWSE_SITE_TOOL, llm_router.WHAT_IS_SELLING_TOOL],   # read_product added 2026-09-09
    # what_is_selling (Barry, 2026-09-18: "they need the tools to go to my site
    # and look at the products to decide on what to post about. Maybe recent
    # sellers or cold products"). Vivian has it because she is in the idea
    # huddle with Derek before either of them starts -- picking the subject is
    # now a joint decision, so she needs the same view of it he has.
    CREATIVE_ID:  [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL,
                   llm_router.BROWSE_SITE_TOOL, llm_router.WHAT_IS_SELLING_TOOL,
                   # 2026-09-26: she designs Derek's emails in Omnisend's blocks (drafts only,
                   # outbound to Omnisend -> in this offline-stripped table on purpose).
                   llm_router.DESIGN_EMAIL_TOOL],
    # PRIYA DOES THE RESEARCH (Barry, 2026-09-02: "Priya also does the research
    # on things as well"). She already had web search like everyone; she had no
    # way to look inside the business she coordinates. Read-only, same as the rest.
    OPERATIONS_ID: [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL,
                    llm_router.SALES_SUMMARY_TOOL, llm_router.BROWSE_SITE_TOOL],
    # SOPHIE IS THE STOREFRONT'S POINT OF CONTACT (Barry, 2026-09-08, handing
    # over his store-ops manual: "she may need to be wired in for this"). Her
    # manual's standing checks need orders, the live site, and a checkout walk;
    # until now she had none of the store tools. Read-only like the rest, and
    # walk_checkout never places an order.
    ENGINEER_ID:  [llm_router.LOOKUP_PRODUCT_TOOL, llm_router.READ_PRODUCT_TOOL,
                   llm_router.SALES_SUMMARY_TOOL, llm_router.BROWSE_SITE_TOOL,
                   llm_router.WALK_CHECKOUT_TOOL, llm_router.ADS_SUMMARY_TOOL,
                   ],
# 🔴 THE OUTBOUND HALF OF SKILL INTAKE IS GONE (2026-09-19, Barry: "remove that
# link and just give her the shit" / "i want total privacy"). fetch_skill_from_
# link used to sit here, in the offline-stripped table, because downloading a
# document is a request to the open internet. Deleted rather than stripped:
# install_skill is all that remains and it only ever reads a file HE put in the
# out box or text he pasted, so nothing about skills touches the network now.
}
# LIVE ADS NUMBERS (2026-09-08). ads_api.fetch has worked since the five MSADS_
# keys landed in .env; nobody had a tool on it, so every seat quoted the dated
# human note in the pulse. The two seats that analyse ads get it too -- Amara
# (ads-performance-analysis is her skill) and Victor (runs the company).
_SEAT_STORE_TOOLS[BUSINESS_ID].append(llm_router.ADS_SUMMARY_TOOL)
_SEAT_STORE_TOOLS[CIO_ID].append(llm_router.ADS_SUMMARY_TOOL)
# WHERE BUYERS COME FROM (Barry, 2026-09-25: "she needs to know this stuff and
# some of the other team"). WooCommerce order attribution, read-only.
for _bs_seat in (ENGINEER_ID, MARKETING_ID, BUSINESS_ID, OPERATIONS_ID, CIO_ID):
    _SEAT_STORE_TOOLS[_bs_seat].append(llm_router.BUYER_SOURCES_TOOL)


# GOTCHO BACK (2026-09-02): every commercial seat can READ gotchoback.com.
# Outbound, so offline mode strips it with the rest of the store table.
for _gb_seat in (CIO_ID, OPERATIONS_ID, BUSINESS_ID, LEGAL_ID, MARKETING_ID, CREATIVE_ID):
    _SEAT_STORE_TOOLS.setdefault(_gb_seat, []).append(llm_router.BROWSE_GOTCHOBACK_TOOL)


def _tools_for_seat(agent_id: str, offline: bool) -> list | None:
    """Every extra tool this seat gets this turn, or None if it gets none.

    None rather than [] is deliberate -- it is what the old branch chain
    produced and what the callers downstream still check for.

    save_note is NOT here: it is appended for all nine seats afterwards, and
    keeping it out of the per-seat table keeps "everyone gets this" visibly
    separate from "this seat earns this".
    """
    tools = list(_SEAT_TOOLS.get(agent_id, []))
    if not offline:
        tools += list(_SEAT_STORE_TOOLS.get(agent_id, []))
    # YOUR OWN PICTURE (2026-09-02): every seat, Taliyah included -- their own
    # words, their own id, queued for Barry. Local DB write, never offline-stripped.
    tools.append(llm_router.CHANGE_MY_PICTURE_TOOL)
    # THEIR OWN ART (2026-09-18, Barry: "whenever she wants, no seeds"). Only
    # the seats the door is open for -- artwork.ENABLED -- so nobody else is
    # handed a tool they were never given. Local DB write, not offline-stripped.
    try:
        import artwork as _artwork
        import agents as _agents
        _office = next((o for o, a in _agents.OFFICE_NAME_TO_AGENT_ID.items()
                        if a == agent_id), "")
        if _artwork.enabled_for(_office):
            tools.append(llm_router.MAKE_ART_TOOL)
    except Exception:  # noqa: BLE001 -- a missing door never costs a chat
        pass
    # FILES (2026-09-06, Barry: "Make them able to read, write and send me
    # files"): every seat, Taliyah included. Local disk + DB only -- the
    # download never leaves this machine -- so offline mode does not strip it.
    tools += [llm_router.SEND_FILE_TOOL, llm_router.READ_BARRYS_FILE_TOOL,
              llm_router.LIST_FILES_TOOL]
    # SIGHT + LEARNING FOR ALL NINE (2026-09-10, Barry: "she needs to be able
    # to see as well. they all do. and they also need to learn"). look_at_render
    # is a LOCAL vision read of their own renders (was Vivian + Taliyah only);
    # remember_lesson writes their always-on lessons ledger (lessons.py). Both
    # local, so neither is offline-stripped.
    for _t in (llm_router.LOOK_AT_RENDER_TOOL, llm_router.REMEMBER_LESSON_TOOL):
        if _t not in tools:
            tools.append(_t)

    # RUNTIME TOOL GRANTS (2026-09-18, Barry: "Sophie needs to be able to give
    # tools too"). Additive on top of the hardcoded roster above -- a grant can
    # only ever widen a seat, never remove what the code gave it, so a bad grant
    # cannot break a working agent. Read live, so a grant is in effect on the
    # very next message with no restart.
    try:
        _office = _office_of(agent_id)
        for _name in memory.get_agent_tools(_office) if _office else []:
            if _name in _TOOL_GRANT_DENY:
                continue                      # cannot be handed out -- see the list
            _tool = _TOOLS_BY_NAME.get(_name)
            if _tool is None or _tool in tools:
                continue
            if offline and _name in _OFFLINE_STRIPPED_NAMES:
                continue                      # an outbound tool still obeys the switch
            tools.append(_tool)
    except Exception as _exc:  # noqa: BLE001 -- a grant lookup never costs a chat
        print(f"[tools] grant lookup failed for {agent_id}: {_exc}")

    # AN AGENT THAT IS NOT HIS DOES NOT SEE HIS NAME (2026-09-19, Barry: "my
    # business stuff must be embedded in this build, we have to separate it").
    # The nine get the schemas their prompt cache was built on, byte for byte;
    # anything hired gets a neutral copy (send_file_to_owner, read_owners_file,
    # and no "Barry" in any description). Dispatch answers to both names.
    if agent_id not in AGENTS and tools:
        try:
            tools = llm_router.neutral_tools(tools)
        except Exception as _exc:  # noqa: BLE001
            print(f"[tools] could not neutralise for {agent_id}: {_exc}")
    return tools or None


def _office_of(agent_id: str) -> str:
    """Office name for any seat. A hire's office_name IS its agent_id; the nine
    are mapped. Returns "" when the id is unknown rather than guessing."""
    import agents as _agents_mod
    for office, aid in _agents_mod.OFFICE_NAME_TO_AGENT_ID.items():
        if aid == agent_id:
            return office
    entry = CUSTOM_AGENTS.get(agent_id)
    if entry:
        return entry.get("office_name") or agent_id
    return ""


# Every tool in llm_router, by its own function name -- built once so a runtime
# grant can name a tool as a string. Derived, never hand-listed, so a new tool is
# grantable the moment it exists.
_TOOLS_BY_NAME = {}
for _n in dir(llm_router):
    if not _n.endswith("_TOOL"):
        continue
    _v = getattr(llm_router, _n)
    if isinstance(_v, dict) and isinstance(_v.get("function"), dict):
        _fn = _v["function"].get("name")
        if _fn:
            _TOOLS_BY_NAME[_fn] = _v

# 🔒 NEVER GRANTABLE AT RUNTIME. Two kinds: tools that change this machine or
# this codebase, and tools that would let a grant widen itself. Sophie can hand
# out capability; she cannot hand out the keys to the building, and no agent can
# be granted the ability to grant.
_TOOL_GRANT_DENY = {
    "run_command", "restart_backend", "write_project_file", "propose_code_fix",
    "undo_code_fix", "list_code_fixes", "submit_agent_fix", "check_updates",
    "install_skill", "onboard_agent_to_team", "accept_host_changes",
    "grant_tools", "revoke_tool", "update_business_brain",
    "save_script_block", "delete_script_block",
    "harden_pc", "run_security_check",
}

# Names that are outbound and must still disappear in Offline Mode even when
# granted -- derived from the store table so it cannot drift from it.
_OFFLINE_STRIPPED_NAMES = {
    t["function"]["name"]
    for _row in _SEAT_STORE_TOOLS.values() for t in _row
    if isinstance(t, dict) and isinstance(t.get("function"), dict)
} | {"read_web_page", "pubmed_search",   # 2026-09-24 research tools reach the internet -> offline strips them
     "channel_stats", "read_comments"}    # 2026-10-07 YouTube read-only (youtube_view.py) -- also the internet

# Fed into the persona-free fallback call (see _force_image_prompt) when the
# request is about "yourself". EMPTIED 2026-08-27 (Barry: "let her pick her
# own look") -- this used to force Taliyah's now-deleted hardcoded appearance
# (agents.py) into even the persona-free fallback path, so removing it from
# her live prompt alone wouldn't have been enough; this was the second place
# the same fixed look could leak back in. Left as an empty dict rather than
# deleted outright: the lookup below degrades to None with no code change
# needed, and the mechanism is still here if a FUTURE agent ever earns a
# real established likeness worth hardcoding (that has never been true for
# Taliyah or anyone else).
AGENT_SELF_APPEARANCE = {}


# --- Live product-data injection (2026-07-31) ---------------------------
# Owner's requirement: agents must use the REAL product page/photo URLs.
# The on-demand catalog skill exists, but a small model reliably skips the
# read_skill call and invents URLs (caught live: Derek fabricated a
# "media/cache/...hero.jpg" link minutes after the skill was seeded). So
# when a message mentions a known product, the matching catalog entries get
# injected into context MECHANICALLY -- no model discipline required.
_PRODUCT_CATALOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge", "product-catalog-full", "SKILL.md",
)
_PRODUCT_STOPWORDS = {
    "bionova", "emerald", "harvest", "general", "hydroponics", "growmax",
    "grower's", "growers", "highdrogro", "base", "nutrient", "nutrients",
    "mineral", "additive", "fertilizer", "with", "part", "kit", "and",
    "the", "for", "liquid", "system", "series",
}


def _load_product_index():
    """Parse the generated full-catalog skill into (match_tokens, block)
    pairs. Rebuilt on backend start; empty list if the file's missing."""
    index = []
    try:
        with open(_PRODUCT_CATALOG_FILE, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:
        return index
    for section in raw.split("\n### ")[1:]:
        lines = section.strip().splitlines()
        name = lines[0].replace("[OUT OF STOCK]", "").strip()
        tokens = {
            t for t in re.findall(r"[a-z0-9\-+]+", name.lower())
            if len(t) > 2 and t not in _PRODUCT_STOPWORDS
        }
        if not tokens:
            continue
        block = "### " + "\n".join(lines)
        index.append((tokens, block))
    return index


_PRODUCT_INDEX = _load_product_index()


def _product_context_block(message: str) -> str:
    """Catalog entries for any product the message plausibly names --
    matched by distinctive-token overlap, capped so a broad message can't
    flood the context."""
    msg_tokens = set(re.findall(r"[a-z0-9\-+]+", (message or "").lower()))
    hits = []
    for tokens, block in _PRODUCT_INDEX:
        needed = 1 if len(tokens) == 1 else 2
        if len(tokens & msg_tokens) >= needed:
            hits.append(block)
        if len(hits) >= 5:
            break
    if not hits:
        return ""
    return (
        "\n--- LIVE PRODUCT DATA (from the store database -- these page and "
        "photo URLs are REAL; use them EXACTLY as written, never invent or "
        "alter a URL) ---\n" + "\n\n".join(hits) +
        "\n--- END LIVE PRODUCT DATA ---\n"
    )


async def _capability_status_block(agent_id: str) -> str:
    """Real, current state of what this agent can actually do RIGHT NOW --
    injected into every chat call so a temporary outage (image engine down,
    Offline Mode on) gets described accurately ("that's down right now")
    instead of the model inventing a permanent, wrong claim ("I never had
    that ability") the way Taliyah repeatedly did once a real GPU failure
    took the old AmuseBridge down mid-session. Checked fresh every call
    rather than cached, since both of these can flip at any moment. Since
    2026-07-30 the engine is ComfyUI (comfy_image.py), which we can start
    on demand -- so "available" means the install exists, not that the
    server happens to be up."""
    lines = []
    if is_image_capable(agent_id):
        amuse_up = await comfy_image.is_available()
        lines.append(
            "Image generation is currently AVAILABLE -- the ```image``` fence pipeline is live."
            if amuse_up else
            "Image generation is currently DOWN (the local image-generation service isn't "
            "responding right now) -- if asked for an image, say plainly that it's temporarily "
            "unavailable and to try again shortly. Never say you don't have or never had the "
            "ability; this is a real, temporary outage, not a permanent limitation."
        )
    if memory.is_offline_mode():
        lines.append(
            "Web search is currently DISABLED -- Offline Mode is on. If asked something needing "
            "live/current info, say plainly you can't search right now because Offline Mode is "
            "on, rather than pretending to have searched."
        )
    else:
        # An agent on a model with no tool-calling capability (was Marcus
        # and Amara during the phi4-reasoning era; their current qwen3-
        # abliterated 14B has tools, so today this is a safety net)
        # can't search regardless of Offline Mode, and telling them search
        # is "available" would be the same lie the rest of this block
        # exists to prevent. Cheap check: capabilities are cached per model
        # name after the first lookup.
        backend, model = _resolve_generation_for(agent_id)
        searchless = backend == "ollama" and not await llm_router.model_supports_tools(model)
        lines.append(
            "Web search is currently UNAVAILABLE for you -- your current model reasons deeply "
            "but cannot call tools. If asked something needing live/current info, say plainly "
            "that you can't look it up right now and answer from your own knowledge, clearly "
            "flagging what might be out of date -- never invent a 'search result'."
            if searchless else
            "Web search is currently AVAILABLE."
        )
    return "\n".join(lines)


def _resolve_generation_for(agent_id: str) -> tuple[str, str]:
    backend, model = memory.get_active_generation()
    # Offline mode is a hard privacy switch (see memory.is_offline_mode) --
    # Claude means real conversation content (scripts, private legal/business
    # detail) leaving the machine over the network, full stop, regardless of
    # what the global dropdown is set to. Force Ollama instead of raising,
    # so a chat request never just fails outright because the dropdown was
    # left on Claude from an earlier session. Bonsai is exempt for the same
    # reason Ollama is: it's a fully local serving process (llama-server on
    # localhost), nothing leaves the machine.
    if memory.is_offline_mode() and backend not in ("ollama", "bonsai"):
        backend = "ollama"
        model = config.OLLAMA_MODEL
    # Per-agent specialist models (Sophie's coder, Marcus/Amara's
    # phi4-reasoning, the uncensored trio's abliterated model) apply
    # whenever the office is on a LOCAL backend -- including when the main
    # model is Bonsai, in which case these agents route to Ollama while
    # everyone else uses Bonsai. Only an explicit switch to Claude
    # overrides them (same semantic as always: Claude has no per-agent
    # variants worth splitting over).
    if backend in ("ollama", "bonsai"):
        # The OWNER's runtime override wins over the hardcoded default, so a
        # seat can be moved without a code edit and a restart (see
        # memory.get_agent_model_overrides). Three states, and the None case
        # is the important one -- it is how an agent gets ONTO Bonsai when the
        # hardcoded map would otherwise pin it to Ollama.
        owner_overrides = memory.get_agent_model_overrides()
        if agent_id in owner_overrides:
            chosen = owner_overrides[agent_id]
            if chosen:
                backend = "ollama"
                model = chosen
            # chosen is None -> follow the global backend/model: fall through
            # deliberately without consulting the hardcoded map.
        elif agent_id in AGENT_OLLAMA_MODEL_OVERRIDES:
            # Per-agent specialist defaults (Sophie's coder, Elliot's and
            # Vivian's abliterated model) apply whenever the office is on a
            # LOCAL backend -- including when the main model is Bonsai, in
            # which case these agents route to Ollama while everyone else
            # uses Bonsai.
            backend = "ollama"
            model = AGENT_OLLAMA_MODEL_OVERRIDES[agent_id]
    return backend, model


# How often to re-check for updates in the background -- see
# update_checker.py. This only ever checks and records the result; it never
# installs anything. An immediate check also runs once at startup (see
# _periodic_update_check below), so the projection screen's Settings tab
# has real data the first time it's opened rather than waiting 12 hours.
UPDATE_CHECK_INTERVAL_SECONDS = 12 * 60 * 60

# Claude doesn't expose a "list installed models" API the way Ollama does
# (see llm_router.list_ollama_models) -- this is the current real model
# family, hand-maintained. Picking one here without ANTHROPIC_API_KEY set
# just surfaces call_claude's existing "[No ANTHROPIC_API_KEY set...]"
# message rather than failing -- same graceful-degradation pattern as
# everything else optional in this project.
CLAUDE_MODEL_OPTIONS = ["claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5-20251001"]

# Vivian is asked (see her system_prompt in agents.py) to put the final
# visual prompt in a ```image ... ``` fence, but local-model instruction
# following isn't perfectly reliable -- in practice she sometimes labels it
# ```text or leaves the language tag off entirely, while still reliably
# putting the actual clean prompt in *some* fenced code block at the end of
# her reasoning. So: prefer an explicit ```image fence if present, otherwise
# fall back to the LAST fenced block in the reply (whatever its label), and
# only fall back to None (which means "use her whole reply") if there's no
# fenced block at all.
_IMAGE_FENCE_RE = re.compile(r"```image\s*\n(.*?)```", re.DOTALL)
# THREE PROMPTS, THREE JOBS (Barry, 2026-09-23: "his still shots prompts should
# be different from his production prompts for seedance. this is ltx, so he
# should prompt differently. for shots, he should use the image refs with the
# basic prompts and then for the video he needs to do the production prompt
# for me to use on higgs. but for him to generate should be a different prompt
# for ltx. maybe he asks for clarification"). A ```video``` fence is the LTX
# prompt (local clip); ```image``` is the still; the Seedance production
# prompt is text for Barry to paste into Higgsfield and is never rendered here.
_VIDEO_FENCE_RE = re.compile(r"```video\s*\n(.*?)```", re.DOTALL)
_SHOT_HIGGS_RE = re.compile(r"\b(higgs(?:field)?|seedance|production\s+(?:prompt|version|shot)|"
                            r"for\s+higgs|to\s+paste)\b", re.IGNORECASE)
_SHOT_LOCAL_RE = re.compile(r"\b(gen|generate|render|make|draw|image|still|picture|pic|"
                            r"video|clip|ltx|here|local(?:ly)?|in\s+the\s+office)\b", re.IGNORECASE)


def _shot_output_mode(message: str) -> str:
    """'production' (Seedance for Higgsfield) | 'local' (still + LTX fences for
    the office buttons). Unsaid = production (2026-09-25, Barry: "this is for
    higgs") -- the old 'clarify' question is no longer the default."""
    m = message or ""
    if _SHOT_HIGGS_RE.search(m):
        return "production"
    if _SHOT_LOCAL_RE.search(m):
        return "local"
    return "production"


# ELLIOT'S DIRECTING SKILLS ON SHOT ASKS (Barry, 2026-09-25: "teach hime how to
# write and direct and do fight and gun scenes... make them into skills"). A
# named shot switches recall OFF, so on-demand skills would never load at the
# one moment they matter -- this picks which ones ride with the shot, from
# his message + the script block. False positives only cost prompt space.
_SKILL_FIGHT_RE = re.compile(
    r"\b(punch\w*|kick\w*|elbow\w*|kneed|clinch\w*|grappl\w*|brawl\w*|"
    r"fight\w*|fought|tackl\w*|chok\w*|headbutt\w*|knife|knives|melee|"
    r"hand-to-hand|hand to hand|takedown\w*|thugs?|henchm[ae]n)", re.IGNORECASE)
_SKILL_GUN_RE = re.compile(
    r"\b(gun\w*|pistol\w*|rifle\w*|fires?\b|firing|fired|shoot\w*|shot at|"
    r"reload\w*|magazine|muzzle|trigger|bullet\w*|launcher|missile\w*|missle\w*|"
    r"volley|rounds?\b|ammo)", re.IGNORECASE)
_SKILL_TALK_RE = re.compile(
    r"\b(meeting|council|briefing|debrief\w*|call\w*|comms?\b|transmission|"
    r"holo\w*|intercom|negotiat\w*|bargain\w*|interrogat\w*|standoff|"
    r"deal|alliance\w*|betray\w*|politic\w*)", re.IGNORECASE)


def _elliot_shot_skills(text: str) -> list[str]:
    """Skill source_names for a Seedance shot ask, in the order he reads them."""
    t = text or ""
    fight, gun = bool(_SKILL_FIGHT_RE.search(t)), bool(_SKILL_GUN_RE.search(t))
    talk = bool(_SKILL_TALK_RE.search(t)) or (
        not (fight or gun) and len(re.findall(r"DIALOGUE|\"[^\"]{8,}\"", t)) >= 2)
    picks = ["skill-directing-a-shot.md"]
    if fight:
        picks.append("skill-fight-choreography.md")
    if gun:
        picks.append("skill-gunfight-choreography.md")
    if talk:
        picks.append("skill-drama-politics-meetings-calls.md")
    picks.append("skill-realism-pass.md")
    return picks


def extract_video_prompt(reply: str) -> str | None:
    match = _VIDEO_FENCE_RE.search(reply or "")
    return match.group(1).strip() if match else None
_NEGATIVE_FENCE_RE = re.compile(r"```negative\s*\n(.*?)```", re.DOTALL)
_MODEL_FENCE_RE = re.compile(r"```model\s*\n(.*?)```", re.DOTALL)
# Excludes "negative" and "model" labels from the fallback so a reply that
# includes those fences but forgets the ```image``` one doesn't grab a model
# name or negative prompt as if it were the image prompt.
_ANY_FENCE_RE = re.compile(r"```(?!negative\b|model\b)\w*\s*\n(.*?)```", re.DOTALL)

# Did Barry actually ask for an image/video/prompt this message? Used by the
# Elliot fence-strip below. "prompt" counts: "write me a higgsfield prompt"
# wants the fence. Wide on purpose -- a miss here strips a fence he wanted,
# which is worse than letting a marginal one through.
#
# WIDENED 2026-08-20, and it was a real bug: Barry's director persona makes
# every scene answer a shot list, and "Direct the moment Tazz breaches the
# side room" contained NO word in this list -- so the fence-strip removed the
# whole answer and he got the "I started answering that with an image prompt"
# fallback instead of his scene. Director words now count as intent, because
# under the persona a directed scene IS meant to come with its prompt. Plain
# factual asks are still protected by the verbatim script gate, which runs
# earlier and answers them from the database without a model call.
# Barry asking an agent about its OWN appearance -- the one case where the
# answer must come from opening the real reference files rather than from
# stored prose (see the deferred nudge further down). Deliberately narrow:
# it needs a self word AND a looks word, so "how does the product look" or
# "describe this render" do not trip it.
_SELF_WORD_RE = re.compile(r"\b(you|your|yourself|yours)\b", re.I)
_LOOKS_WORD_RE = re.compile(
    r"\b(look|looks|looking|appearance|body|figure|build|face|hair|eyes|"
    r"eyebrows|brows|skin|shape|describe yourself|what do you look like|"
    r"wearing|wear)\b", re.I)


# "LOOK" AND "FIGURE" ARE MOSTLY NOT ABOUT FACES.
#
# Found 2026-08-31 by accident: asked Victor "we have two lamp SKUs selling and
# nothing else -- what would you look at first?", he opened his own photos and
# described his face. The trigger was just `you` + `look`, which collides with
# most of how anyone talks about work: "can you look at the ads data", "look
# into the failed orders", "figure out the wholesale price", "keep your eyes on
# the margin". Every one of those would hijack a work answer into a selfie.
#
# So the ACTION senses are removed before the appearance test runs. What stays
# is the appearance sense -- "what do you look like", "your face", "your hair",
# "what are you wearing".
_LOOK_ACTION_RE = re.compile(
    r"\blook(?:s|ing|ed)?\s+"
    r"(?:at|into|for|over|through|up|out|back|ahead|around|after|past)\b", re.I)
_FIGURE_OUT_RE = re.compile(r"\bfigure(?:s|d)?\s+out\b", re.I)
_EYES_ON_RE = re.compile(r"\beyes?\s+(?:on|out)\b", re.I)


# Body words are specific enough to fire on their own once paired with "you".
_APPEAR_STRONG_RE = re.compile(
    r"\b(appearance|face|hair|eyebrows?|brows|complexion|skin|"
    r"wearing|wear|body|figure|build|shape|eyes?)\b", re.I)
# Bare "look" is too common to trust unless it is attached to the PERSON.
# "how does your pipeline look" is work; "how do you look" is not.
_YOU_LOOK_RE = re.compile(
    r"\b(?:you|yourself)\s+look(?:s|ing|ed)?\b"
    r"|\blook(?:s|ing|ed)?\s+like\s+(?:you|yourself)\b"
    r"|\byour\s+look\b|\bdescribe\s+yourself\b", re.I)


def _appearance_ask(message: str) -> bool:
    m = message or ""
    # strip the action senses first -- see the note above
    m = _LOOK_ACTION_RE.sub(" ", m)
    m = _FIGURE_OUT_RE.sub(" ", m)
    m = _EYES_ON_RE.sub(" ", m)
    if _YOU_LOOK_RE.search(m):
        return True
    # The body word has to be THEIRS. "your face" is an appearance question;
    # "how does the build look to you" is a work question that happens to
    # contain both halves.
    return bool(re.search(
        r"\b(?:your|yourself|you)\s+(?:\w+\s+){0,1}" + _APPEAR_STRONG_RE.pattern,
        m, re.I))


# SOPHIE REACHES FOR HER INSTRUMENTS (2026-09-02, Barry: "Make sophie the
# sophie you know I want"). Measured before this: 158 traces, system_health
# called ONCE, propose_code_fix NEVER -- with both attached and named in her
# system prompt. Same lesson as _appearance_ask directly below: a rule in the
# system prompt loses at depth; the recency slot at the end of the user turn
# is what fires. Sophie-only. A false positive costs one read-only tool call.
_HEALTH_ASK_RE = re.compile(
    r"\b(?:how(?:'?s|\s+is|\s+are)\s+(?:the\s+)?(?:office|system|backend|build|"
    r"stack|everything|things|it)\s+(?:doing|running|going|looking|holding)?"
    r"|health(?:\s*check)?|status\s+(?:check|report|of)"
    r"|check\s+(?:on\s+)?(?:the\s+)?(?:office|system|backend|stack|dashboard|deck|decks|health)"
    r"|anything\s+(?:broken|wrong|failing|off|down)"
    r"|(?:is|are|went|was)\s+(?:it|everything|anything|\w+)\s+(?:down|broken|slow|failing|working)"
    r"|running\s+(?:ok|okay|fine|slow|slowly)|(?:so|too|really|seriously)\s+slow"
    r"|not\s+(?:working|responding|loading)|crash(?:ed|es|ing)?|error(?:s|ed)?"
    r"|failing|failed|glitch(?:y|es|ing)?|bug(?:s|gy)?|broken)\b", re.I)
_FIX_ASK_RE = re.compile(
    r"\b(?:fix|patch|change|edit|update|repair|correct|rewrite|refactor|propose)\b"
    r"[^.?!]{0,80}\b(?:code|file|files|\.py|\.js|\.html|\.css|function|endpoint|"
    r"script|dashboard|deck|backend|main\.py|route|regex|loop|bug)\b", re.I)


def _health_ask(message: str) -> bool:
    return bool(_HEALTH_ASK_RE.search(message or ""))


# VIVIAN OPENS THE REAL PHOTO FIRST (2026-09-10). Same pattern, same reason as
# _appearance_ask above and Sophie's instruments: her new eyes are attached and
# named in her persona, and this build has measured three times that a tool
# named only in the system prompt does not get called at depth. A false
# positive costs one local vision read.
# Deliberately needs BOTH a visual word and a product/store word -- "make me a
# picture of a mountain" is not a product shot and must not drag the catalogue
# into it.
_VISUAL_WORD_RE = re.compile(
    r"\b(?:image|images|picture|pictures|photo|photos|photograph|shot|shots|"
    r"render|renders|rendering|visual|visuals|graphic|graphics|banner|thumbnail|"
    r"mockup|mock\s*up|design|shoot|prompt)\b", re.I)
_PRODUCT_WORD_RE = re.compile(
    r"\b(?:product|products|bottle|bottles|tent|tents|lamp|lamps|light|lights|"
    r"nutrient|nutrients|bionova|silution|microlife|emerald\s+harvest|cali\s*pro|"
    r"backpack|backpacks|bag|bags|listing|catalog|catalogue|sku|item|items|"
    r"store|shop)\b", re.I)


def _product_visual_ask(message: str) -> bool:
    m = message or ""
    return bool(_VISUAL_WORD_RE.search(m) and _PRODUCT_WORD_RE.search(m))


# A render already exists and he is asking about it -- open the file, do not
# grade it from the prompt that made it.
_IMAGE_OBJECT = (r"(?:it|this|that|render|renders|image|images|picture|pictures|"
                 r"shot|shots|photo|photos)")
_RENDER_REVIEW_RE = re.compile(
    # verb first ("look at this render", "fix it", "how did that come out")
    r"\b(?:look\s+at|check|review|how(?:'?s|\s+is|\s+did)|came\s+out|turned\s+out|"
    r"fix|redo|re-?roll)\b[^.?!]{0,40}\b" + _IMAGE_OBJECT + r"\b"
    # object first ("does this image look right", "that render came out weird")
    r"|\b(?:does|do|did|is|was)\s+(?:the\s+|this\s+|that\s+)?" + _IMAGE_OBJECT +
    r"(?:\s+\w+){0,2}\s+look\b"
    # bare complaint about the thing on screen
    r"|\bwhat(?:'?s|s|\s+is)\s+wrong\b", re.I)


def _render_review_ask(message: str) -> bool:
    return bool(_RENDER_REVIEW_RE.search(message or ""))


# GOTCHO BACK: READ THE CATALOG BEFORE ASKING HIM (2026-09-17). Vivian told
# Barry the brand "has no documented identity" and asked him to supply one --
# while `browse_gotchoback` sat on her roster and returns the live catalog: 20
# products with prices, stock and full descriptions (hemp backpacks hand made
# in Nepal, $35, hemp leaf, XO pattern). Same failure as grading a render she
# never opened: asking him for something one tool call away.
# ⚠️ The VOICE is genuinely NOT in the catalog and is genuinely NOT hers to
# invent -- that gap is real and deliberate (his tools-not-seeds rule, and the
# Business Brain marks it [ASK BARRY]). So the nudge says read the catalog for
# the FACTS and ask him only for the voice.
_GOTCHOBACK_RE = re.compile(
    r"\bgotcho\s*back\b|\bgotchoback(?:\.com)?\b", re.I)


def _gotchoback_ask(message: str) -> bool:
    return bool(_GOTCHOBACK_RE.search(message or ""))


# QUICK REPLY (2026-09-08, Barry: "build the reasoning budget thing for short
# messages"). A short casual message with no work intent gets a lower
# generation cap on Bonsai (see bonsai_llm.max_tokens_override) so "cool, ill
# grab some row cover" cannot cost 69s of reasoning. Deliberately narrow: any
# work word, any number, any question about the office, any named shot, any
# task/board turn keeps the full budget. Thinking stays ON either way.
_QUICK_WORK_RE = re.compile(
    r"\b(?:write|draft|plan|fix|build|code|email|emails|campaign|ad|ads|post|"
    r"caption|prompt|script|shots?|scenes?|b-?roll|render|image|video|search|look\s*up|"
    # "generate that" is 13 chars and reads casual, so the quick cap fired on
    # it and 1,200 tokens went entirely on reasoning (2026-09-19). A generate
    # ask produces a long structured answer -- it is never quick talk.
    r"generat\w*|describe|self-?portrait|profile\s+(?:pic|picture|image)|"
    r"system|systems|office|backend|server|dashboard|deck|decks|"
    r"check|report|number|numbers|price|pricing|margin|cost|budget|order|orders|"
    r"sales|store|site|website|customer|customers|product|products|list|"
    r"explain|analy[sz]e|compare|review|research|why|how\s+(?:do|does|would|"
    r"should|can|much|many)|what\s+(?:is|are|should|would|do|does)|should\s+(?:i|we)|"
    r"tell\s+me|show\s+me|give\s+me|help\s+me|can\s+you|could\s+you|"
    r"delegate|brief|approve|schedule|undo|update|restart|deploy|test)\b", re.I)
QUICK_REPLY_MAX_CHARS = 140
QUICK_REPLY_MAX_TOKENS = 1200
# QUICK THINKING (2026-09-28, Barry: "cut the over thinking"). Quick turns used the default
# 1,024-token thinking budget under the 1,200 cap above, so reasoning ate the cap, the reply was cut,
# and the whole turn re-ran with thinking off -- Amara's "how was your day" cost 134 s that way
# (two full ~28.6K-token prefills). Same short scratchpad as home (proven on chat): thinking stays
# ON, and the answer always has room under the cap.
QUICK_THINK_BUDGET = int(os.getenv("QUICK_THINK_BUDGET", "384"))
# HOME THINKING BUDGET (2026-09-17, Barry: "her reasoning can happen or
# whatever, just not within her answer"). Hidden scratchpad on personal turns
# -- enough to settle what to say (~6-8s at 45 tok/s), not enough to draft
# three versions. Work turns use bonsai_llm.THINK_BUDGET_DEFAULT (1024).
HOME_THINK_BUDGET = int(os.getenv("HOME_THINK_BUDGET", "384"))
# The ONE line of the work register block that survives at home. Stripping
# the whole block (step 2, 2026-09-17) took the 08-29 second-person rule with
# it, and the very next home turn opened "He's right" / "not for him" -- the
# exact habit that rule killed office-wide. This is not a length or style
# rule; it is who she is talking to.
_HOME_SECOND_PERSON = (
    "\n\nYou are talking TO Barry, not about him. He is 'you', never 'he', "
    "'him', 'his', 'Barry's' -- you are answering him to his face.\n")


def _home_life_block(office_name: str) -> str:
    """WHAT THEY HAVE ACTUALLY BEEN DOING, on the gold channel only.

    Their own diary / own-time / events entries, their open threads, and the
    plain fact of what day it is -- so "how was your day" and "what did you do
    this weekend" can be answered out of a real life instead of out of the
    personality file. Their words; nothing summarised, nothing suggested, and
    completely silent for a seat with nothing written yet (an empty life stays
    honestly empty rather than being invented on the spot).

    Day-level only, never the clock time: this rides in the home prompt, and
    a value that changes every minute re-reads the whole prompt (the
    2026-08-20 minute-stamp lesson). A day name flips once a day, for free.
    """
    out = ""
    try:
        now = datetime.datetime.now()
        day = now.strftime("%A")
        _start, _end, days = clock.hours()
        # clock.hours() returns the working weekdays (Mon=0); a day off is
        # simply a day not in that set, so this follows whatever he sets.
        off_today = now.weekday() not in days
        tomorrow_off = ((now.weekday() + 1) % 7) not in days
        when = f"\nIt is {day}."
        if off_today:
            when += " No work today -- the day is yours."
        elif tomorrow_off:
            when += " Tomorrow is a day off."
        else:
            when += " A work day; tonight after it is your own."
        out += when + "\n"
    except Exception:
        pass
    try:
        mine = reflect.life_for_home(office_name)
        if mine:
            out += ("\nWHAT YOU HAVE ACTUALLY BEEN DOING (your own entries, "
                    "newest first -- your life, not a report):\n"
                    f"{mine}\n"
                    "If he asks how your day was or what you have been up to, "
                    "answer out of this. If something here is still going, it "
                    "is still going.\n")
    except Exception:
        pass
    try:
        out += life.threads_block(office_name, "")
    except Exception:
        pass
    return out
SHOT_ASK_MAX_TOKENS = 6144   # historical (49152 window); superseded by the two below
# 2026-09-22: 98304 window (q8_0 KV). His ~48K prompt + 16,384 = ~64K, well inside.
ELLIOT_WORK_MAX_TOKENS = int(os.getenv("ELLIOT_WORK_MAX_TOKENS", "16384"))
ELLIOT_THINK_BUDGET = int(os.getenv("ELLIOT_THINK_BUDGET", "6144"))
VIDEO_MAX_TOKENS = int(os.getenv("VIDEO_MAX_TOKENS", "16384"))      # Ilnora's video turns (2026-10-07)
VIDEO_THINK_BUDGET = int(os.getenv("VIDEO_THINK_BUDGET", "8192"))   # 4096 was cut mid-draft on a 10-min Long (10-07)


# TALIYAH IS NOT A WORK SEAT, SO THE WORK TEST IS WRONG FOR HER (2026-09-10,
# Barry: "why is she taking longer than everybody else, when she is the least
# technical"). He was right to ask. Measured: her prompt is the SMALLEST in the
# office (54K vs 82-86K) and her median reply is mid-pack -- but the quick cap
# almost never fires for her, because the words that disqualify a message here
# are the words a friend uses: "the store did nothing again" (store), "i been at
# it since 6" (a digit), "why you talking like that" (why). So a two-line vent
# got the same full reasoning budget as a build plan.
# For her seat only: a digit or a work NOUN no longer disqualifies -- only an
# actual request to produce something does. Everything else about the cap is
# unchanged, and it still never applies to a long message.
_TALIYAH_WORK_RE = re.compile(
    r"\b(?:write|draft|build|code|render|generate|make\s+me|analy[sz]e|"
    r"compare|research|report|schedule|approve|delegate|fix\s+the|"
    r"look\s*up|search\s+for)\b", re.I)
TALIYAH_QUICK_MAX_CHARS = 160


_VIDEO_WORD = r"(?:video|videos|vid|vids|short|shorts|longform|long\s+form|long|deep\s+dive|script)"
_VIDEO_VERB = r"(?:make|write|plan|create|build|start|redo|rewrite|cut|draft|send|check|finish|do|scout|pick|choose)"


def _ilnora_video_making(req) -> bool:
    """Is this turn actually MAKING a video (2026-10-07, Barry: "make the big budget only for actual video making")?
    True for her scheduled jobs, the office's send-backs, an ask that pairs a doing-verb with a video word in one
    sentence ("make a long video", "plan the next shorts"), and a short follow-up while her last reply was a plan or
    a video ("make it.", "keep scouting", "swap the plants"). A note that merely mentions videos is not."""
    m = (req.message or "").strip()
    if not m:
        return False
    if req.task and ("make_video" in m or "video_draft" in m):
        return True
    if m.startswith("The office checked your video") or m.startswith("[video draft:"):
        return True
    if (re.search(rf"\b{_VIDEO_VERB}\w*\b[^.?!\n]{{0,60}}\b{_VIDEO_WORD}\b", m, re.I)
            or re.search(rf"\b{_VIDEO_WORD}\b[^.?!\n]{{0,40}}\b{_VIDEO_VERB}\w*\b", m, re.I)):
        return True
    if len(m.split()) <= 8:
        try:
            with memory.get_db() as conn:
                row = conn.execute("SELECT content FROM conversations WHERE agent_id = 'ilnora' AND role = 'agent' "
                                   "ORDER BY id DESC LIMIT 1").fetchone()
            last = (row[0] if row else "") or ""
        except Exception:  # noqa: BLE001
            last = ""
        return bool(re.search(r"THE PLAN|\"parts\"|make_video|check_video", last, re.I))
    return False


def _quick_reply_ask(message: str, agent_id: str | None = None) -> bool:
    m = (message or "").strip()
    if not m:
        return False
    if agent_id == TALIYAH_ID:
        return len(m) <= TALIYAH_QUICK_MAX_CHARS and not _TALIYAH_WORK_RE.search(m)
    if len(m) > QUICK_REPLY_MAX_CHARS:
        return False
    if re.search(r"\d", m):   # any digit is probably work: a shot, a price, a temperature
        return False
    if _QUICK_WORK_RE.search(m):
        return False
    return True


def _fix_ask(message: str) -> bool:
    return bool(_FIX_ASK_RE.search(message or ""))


# THE COMPANY (2026-09-02). Two regexes for the hand-off net and the CEO nudge.
_TEAM_NAMES = r"(?:Priya|Amara|Marcus|Derek|Vivian|Elliot|Sophie|Victor)"
_HANDOFF_CLAIM_RE = re.compile(
    r"\bI(?:'ll| will| am going to|'m going to|'ve| have)\s+(?:get|have|put|loop|brief|hand|send|ask|task|assign)\w*\s+" + _TEAM_NAMES
    + r"|\b" + _TEAM_NAMES + r"\s+(?:has|have|is on|gets?|will take|is taking|is sending|is handling|will handle|is going to)\s+(?:it|this|that|the brief|the task)"
    + r"|\bhand(?:ed|ing)?\s+(?:it|this|that)\s+(?:off|over|to)"
    + r"|\bsending\s+(?:it|this|that)\s+(?:over\s+)?to\s+" + _TEAM_NAMES
    + r"|\bbriefed\s+" + _TEAM_NAMES
    + r"|\b(?:on|to)\s+" + _TEAM_NAMES + r"'s\s+(?:board|desk|plate)"
    # 2026-09-02 run 3: "I'll have the full supplier shortlist ... ready in your
    # approval queue first thing tomorrow morning" -- a delivery PROMISE with no
    # teammate named and no tool call. A promise of future work with nothing
    # filed is the same fake.
    + r"|\bI(?:'ll| will)\s+have\s+(?:the|a|an|your|it|this|that)\b[^.]{0,80}\b(?:ready|done|compiled|drafted|in your (?:approval )?queue)"
    + r"|\b(?:ready|done|waiting|be)\s+(?:in|on)\s+your\s+(?:approval\s+)?queue"
    + r"|\bfirst\s+thing\s+(?:tomorrow|monday|in\s+the\s+morning)"
    + r"|\bby\s+end\s+of\s+(?:day|week|the\s+week)\b"
    # 2026-09-11, Priya at her office: "I'll give you the real list by
    # morning" / "I've got the sourcing search queued" -- a promise of a
    # deliverable with nothing behind it. Same fake, new wording.
    + r"|\bby\s+(?:the\s+)?morning\b"
    + r"|\bI(?:'ll| will)\s+(?:get|give|send|have|pull)\s+you\s+(?:a|the|an|your|that|this)\b[^.]{0,60}\b(?:list|shortlist|report|numbers|draft|options|breakdown|summary|research|suppliers?)\b"
    + r"|\bI(?:'ve| have)\s+(?:got\s+)?(?:the|a|it|this|that)\b[^.]{0,40}\bqueued\b", re.I)
# The STRONG signals that this is genuinely team work (used for the auto-file
# fallback): a bare teammate name is not enough -- "how's Priya doing?" is not
# a task -- so names only feed the nudge, not the file.
_TEAM_WORK_STRONG_RE = re.compile(
    r"\b(?:put\s+(?:the\s+)?team\s+on|through\s+the\s+team|get\s+the\s+team|have\s+the\s+team|team\s+on\s+it)\b"
    r"|\b(?:get|have|put)\s+(?:me|us)\s+(?:a|an|the|some)\b"
    r"|\bi\s+(?:need|want)\s+(?:a|the|an|some)\s+(?:read|report|plan|proposal|draft|breakdown|numbers|analysis|review|options)\b"
    r"|\bby\s+(?:tomorrow|monday|tuesday|wednesday|thursday|friday|end\s+of|next\s+week)\b"
    r"|\bhelp\s+(?:me\s+|us\s+)?(?:figure|figuring|work|working|plan|planning|get|getting|find|finding|source|sourcing|track)\b"
    # 2026-09-11 (Priya's backpack ask, given at her office after hours:
    # "remember to help find great backpacks, bags and luggage for drop ship
    # or wholesale" -- no "me", no "by", nothing above matched, so nothing was
    # filed). A find/source verb within reach of a business noun is work.
    r"|\b(?:find|finding|source|sourcing|research|researching|hunt|track\s+down|look\s+(?:for|into)|shortlist|price\s+out|compare)\b"
    r"[^.?!]{0,70}\b(?:suppliers?|vendors?|wholesalers?|wholesale|drop[\s-]*ship\w*|manufacturers?|backpacks?|bags|luggage|products?|leads?|prospects?|quotes?)\b"
    r"|\b(?:amara|marcus|derek|vivian|elliot|sophie)\s+(?:on|for)\s+(?:the|a|an)\b", re.I)


def _team_work_strong(message: str) -> bool:
    return bool(_TEAM_WORK_STRONG_RE.search(message or ""))


def _next_open_utc_iso() -> str | None:
    """UTC ISO of the office's next opening (clock.py hours), or None if it
    is open now. This is the `not_before` on a brief handed over ON CALL
    (2026-09-11): filed tonight, worked when the doors open. Local wall
    clock in, UTC out, because teamwork stamps rows in UTC."""
    now = datetime.datetime.now()
    if clock.is_work_hours(now):
        return None
    start, _end, days = clock.hours()
    for ahead in range(0, 8):
        day = now + datetime.timedelta(days=ahead)
        if day.weekday() not in days:
            continue
        opens = day.replace(hour=start, minute=0, second=0, microsecond=0)
        if opens > now:
            return opens.astimezone(datetime.UTC).isoformat()
    return None


_TEAM_WORK_ASK_RE = re.compile(
    r"\b" + _TEAM_NAMES + r"\b"
    r"|\b(?:the\s+team|through\s+the\s+team|everybody|everyone)\b"
    r"|\b(?:get|have|put)\s+(?:me|us|them|someone|somebody)\b"
    r"|\b(?:i\s+(?:need|want)\s+(?:a|the|an)\s+(?:read|report|plan|proposal|draft|breakdown|numbers|analysis|review))\b"
    r"|\bby\s+(?:tomorrow|monday|tuesday|wednesday|thursday|friday|end\s+of|next\s+week)\b"
    r"|\bhelp\s+me\s+(?:figure|work|plan|get|find)\b", re.I)


def _team_work_ask(message: str) -> bool:
    return bool(_TEAM_WORK_ASK_RE.search(message or ""))


_UNDO_ASK_RE = re.compile(
    r"\b(?:undo|revert|roll\s*back|rollback|put\s+(?:it|that|things?)\s+back)\b"
    r"|\brestore\b[^.?!]{0,60}\b(?:fix|change|edit|patch|file|backup|it|that)\b", re.I)


def _undo_ask(message: str) -> bool:
    return bool(_UNDO_ASK_RE.search(message or ""))


# 2026-09-06 (Barry: "build anything i need"): a BUILD ask is not a "fix" ask
# -- "build me a tool that...", "write a script to...", "make a new deck that
# ..." carried none of _FIX_ASK_RE's verbs, so she got no nudge and answered
# with prose. An update ask routes her to the update board.
_BUILD_ASK_RE = re.compile(
    r"\b(?:build|create|write|make|add|set\s+up|implement|code)\b[^.?!]{0,60}"
    r"\b(?:tool|script|module|endpoint|feature|page|deck|panel|button|function|"
    r"file|loop|checker|monitor|test|command|integration|api|route)\b", re.I)
_UPDATE_ASK_RE = re.compile(
    r"\b(?:updates?|upgrade|newer\s+version|out\s+of\s+date|outdated|latest\s+version|"
    r"pull\s+the\s+(?:new|latest)|new\s+version)\b", re.I)


_GO_ASK_RE = re.compile(
    r"^\s*(?:ok(?:ay)?[,.! ]*)?(?:go|go ahead|do it|build it|make it|ship it|proceed|"
    r"yes,?\s*(?:go|do it|build it)|green light|start building|approved,?\s*go)\b[\s.!]*$", re.I)


def _build_ask(message: str) -> bool:
    return bool(_BUILD_ASK_RE.search(message or ""))


# THE READ-CLAIM NET (2026-09-06): a reply that talks about the code as if
# it had been read -- quoting columns, line numbers, function bodies, folder
# listings, "from memory.py" -- with no read/search tool behind it.
_CODE_CLAIM_RE = re.compile(
    r"\bline\s+\d+\b|```(?:python|py|js|javascript|sql)\b|\bthe columns? (?:are|is)\b|"
    r"\bSELECT\b[^\n]{0,80}\bFROM\b|\bdef \w+\(|\bfrom `?\w+\.(?:py|js|html)`?|"
    r"\bin `?(?:main|memory|llm_router|agents|codefix|watch)\.py`?|"
    r"\b(?:i|I) (?:read|opened|looked at|checked|inspected|examined)\b[^.]{0,40}\b(?:file|code|table|schema|folder|directory)\b|"
    r"\btable structure\b|\bfolder (?:looks like|contains)\b|^[├└│]", re.I | re.M)
_READ_TOOLS = ("read_project_file", "search_project", "list_project_directory")
_SAVE_CLAIM_RE = re.compile(
    r"\b(?:I'?ve|I have|I)\s+(?:saved|stored|noted|written)\b[^.]{0,50}\b(?:plan|note|notes|brain|memory)\b"
    r"|\bsaved (?:this|the|my) plan\b|\bplan (?:is|has been) saved\b|\bin my notes\b", re.I)


def _engineer_claim_gaps(message: str, reply: str, tool_log: list | None) -> list[str]:
    """What Sophie's reply claims that no tool call backs. Empty = honest."""
    log = list(tool_log or [])
    read = any(t in _READ_TOOLS for t in log)
    gaps = []
    if _CODE_CLAIM_RE.search(reply or "") and not read:
        gaps.append("you described code/columns/files but read nothing")
    if _SAVE_CLAIM_RE.search(reply or "") and "save_note" not in log:
        gaps.append("you said you saved a plan/note but save_note was never called")
    if _build_ask(message) and not read and "read_skill" not in log:
        gaps.append("you planned a build without opening any file")
    return gaps


# VIVIAN'S CLAIM NET (2026-09-10). Measured on her first live turn with the
# new eyes: with look_at_product_photo attached, named in her persona AND named
# in a recency nudge, she called lookup_product + read_product, wrote
# "I saw the real bottle photo for the shape, cap and label layout before
# writing this" -- and then described a transparent bottle of amber liquid.
# The real photo is GREEN bottles with RED caps. So the claim was false and the
# description was invented, which is the exact failure the tool exists to end.
# Same shape as Sophie's read-net: one re-run with the fact in front of her,
# then the claim is corrected in the reply rather than reaching Barry as truth.
_PHOTO_CLAIM_RE = re.compile(
    r"\b(?:i\s+(?:saw|looked at|opened|checked|viewed|pulled up|studied)"
    r"[^.!?\n]{0,60}\b(?:photo|photos|photograph|image|images|picture|pictures)"
    r"|(?:the|its|this|that)\s+(?:real\s+|live\s+|actual\s+|product\s+)*"
    r"(?:photo|photograph|image|picture)\s+(?:shows|has|is|reads|carries)"
    r"|based on the (?:real |actual |live )?(?:photo|image|picture))\b", re.I)
# What a render CANNOT carry, claimed as if it can.
_RENDER_IS_REAL_RE = re.compile(
    r"\b(?:exact|real|actual|correct)\s+(?:label|labels|logo|packaging|"
    r"branding|text)\b[^.!?\n]{0,40}\b(?:in|on)\s+the\s+"
    r"(?:render|image|prompt)\b", re.I)


def _creative_claim_gaps(message: str, reply: str, tool_log: list | None) -> list[str]:
    """What Vivian's reply claims that no tool call backs. Empty = honest."""
    log = list(tool_log or [])
    gaps = []
    if _PHOTO_CLAIM_RE.search(reply or "") and "look_at_product_photo" not in log:
        gaps.append("you said you looked at the real product photo, but "
                    "look_at_product_photo was never called")
    if (_product_visual_ask(message) and "look_at_product_photo" not in log
            and _IMAGE_FENCE_RE.search(reply or "")):
        gaps.append("you wrote a product image prompt without opening the real "
                    "product photo, so every detail of the bottle, cap, colour "
                    "and label in it is invented")
    if _render_review_ask(message) and "look_at_render" not in log:
        gaps.append("you judged an image you never opened -- look_at_render "
                    "was not called")
    # 2026-09-17: only when she actually pleads ignorance about the brand. A
    # Gotcho Back question she answers from the catalog, or answers without
    # claiming the catalog is empty, is fine with no tool call.
    if (_gotchoback_ask(message) and "browse_gotchoback" not in log
            and _NO_GOTCHOBACK_INFO_RE.search(reply or "")):
        gaps.append("you told Barry there is nothing documented about Gotcho "
                    "Back without calling browse_gotchoback -- the live "
                    "catalog is on your roster and lists every bag, price, "
                    "material and description. The VOICE is genuinely his to "
                    "give; the products are not")
    return gaps


# "There is nothing to work from" -- said about Gotcho Back, without looking.
_NO_GOTCHOBACK_INFO_RE = re.compile(
    r"\b(?:no|not?)\s+(?:documented\s+)?"
    r"(?:identity|voice|brand|information|info|details|data|context|"
    r"description|descriptions|catalog|catalogue)\b"
    r"|\b(?:is|it'?s|its|remains?|stays?)\s+(?:still\s+)?"
    r"(?:blank|empty|undocumented|missing|unknown)\b"
    r"|\bnothing\s+(?:documented|on file|to (?:go|work)\s+(?:on|from|with))\b"
    r"|\bdon'?t\s+(?:have|know)\s+(?:any|the)\s+"
    r"(?:info|information|details|voice|identity)\b", re.I)


# "LET ME TAKE A LOOK" IS NOT LOOKING (2026-09-15, Barry: "she just says let
# her take a look at it, but dose she?"). Measured on Amara's home turns: no.
# A reply that CLAIMS to be looking at a picture -- and the exchange is about
# a picture -- with no look_at_render / look_at_my_pictures in the tool log
# gets ONE re-run with the fact in front of her; still claiming -> the reply
# says so. Fires only on the claim, never on a mere mention of a picture, so
# it costs a vision pass only when she said she was looking.
_LOOK_CLAIM_RE = re.compile(
    r"\b(?:let\s+me\s+(?:take\s+a\s+|have\s+a\s+)?look|"
    r"(?:i'?m|i\s+am)\s+looking\s+(?:at|through)|"
    r"(?:i'?ll|i\s+will|let\s+me)\s+(?:open|pull\s+(?:it|that|them)\s+up)|"
    r"(?:taking|take)\s+a\s+look|"
    r"i\s+(?:can\s+)?see\s+(?:it|that|the\s+(?:picture|image|render|photo|pic|shot))\b|"
    r"looking\s+at\s+(?:it|that|the\s+(?:picture|image|render|photo|pic|shot))\s+(?:now|right\s+now)|"
    r"i(?:'ve|\s+have)\s+(?:opened|looked\s+at|pulled\s+up)\s+(?:it|that|the\s+(?:picture|image|render|photo|pic|shot)))\b",
    re.I)
_PICTURE_WORD_RE = re.compile(
    r"\b(?:picture|pictures|pic|pics|image|images|render|renders|photo|photos|"
    r"shot|album|selfie|screenshot)\b", re.I)


def _look_claim_gaps(message: str, reply: str, tool_log: list | None) -> list[str]:
    """A looking claim no sight tool backs. Empty = honest."""
    log = set(tool_log or [])
    if log & {"look_at_render", "look_at_my_pictures"}:
        return []
    # The tool name written out as text (her 2026-09-15 20:56 reply:
    # "```look_at_render```") is the bluff itself -- no other gate needed.
    named_tool = bool(re.search(r"look_at_(?:render|my_pictures)", reply or ""))
    if not named_tool and not _LOOK_CLAIM_RE.search(reply or ""):
        return []
    if not named_tool and not (_PICTURE_WORD_RE.search(message or "")
                               or _PICTURE_WORD_RE.search(reply or "")):
        return []
    return ["you said you were looking at the picture, but look_at_render was "
            "never called, so you have not seen it"]


# A LESSON SAID IS NOT A LESSON KEPT (2026-09-10). Measured on Amara's first
# turn with remember_lesson attached AND named in her persona: asked to keep a
# lesson, she wrote "Here's the lesson I'm committing to" in prose and never
# called the tool -- the same bluff shape as Priya's brief (08-29), Sophie's
# save (09-06) and Vivian's photo (09-10). Same net: one re-run with the fact
# in front of them, then the claim is corrected in the reply.
_LESSON_ASK_RE = re.compile(
    r"\b(?:remember\s+(?:this|that|it)|keep\s+(?:this|that|it)\s+as\s+a\s+lesson|"
    r"(?:a|one|the|your)\s+lesson|learn\s+from\s+(?:this|that|it)|"
    r"lesson\s+learned|don'?t\s+(?:do|make)\s+(?:that|this)\s+(?:again|mistake\s+again)|"
    r"never\s+again|next\s+time\s+(?:don'?t|do\s+not|always|never))\b", re.I)
_LESSON_CLAIM_RE = re.compile(
    # first-person COMMITMENT only -- a bare "lesson" would re-run Marcus
    # citing "the lesson from the FTC case" or a grower-tip email
    r"\b(?:(?:the|my|a|one)\s+lesson\s+i(?:'m|\s+am|'ll|\s+will)\s+(?:take|taking|keep|keeping|remember|commit)\w*|"
    r"lesson\s+learned:|i'?ll\s+remember|i\s+will\s+remember|i'?m\s+committing\s+to|"
    r"i\s+am\s+committing\s+to|noted\s+for\s+next\s+time|from\s+now\s+on\s+i(?:'ll|\s+will)|"
    r"going\s+forward\s+i(?:'ll|\s+will)|i(?:'ve|\s+have)\s+(?:kept|saved|logged)\s+(?:this|that|the)\s+lesson)",
    re.I)


def _lesson_ask(message: str) -> bool:
    return bool(_LESSON_ASK_RE.search(message or ""))


def _norm_quote(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"')
                  .replace("’", "'").replace("—", "-").replace("–", "-")).strip().lower()


def _dialogue_gaps(source_blocks: list[str], reply: str) -> list[str]:
    """THE DIALOGUE NET (Elliot, shot asks, 2026-09-14). Barry: "he didnt say
    who was talking and i dont see voice id." Measured twice tonight: the
    source block's spoken lines never reached the fence -- once no {} line at
    all, once five of six lines dropped from stage 1. Dialogue is the one
    thing that is not his, so this is checked mechanically: every quoted
    line in the source must appear verbatim inside a {} channel in the
    ```image``` fence, and every {} line needs a voice-id line in front of it.
    Returns the gaps as plain sentences; empty means clean."""
    if not source_blocks or not reply:
        return []
    src = "\n".join(source_blocks)
    lines = [q.strip() for q in re.findall(r"\"([^\"\n]{2,})\"", src.replace("“", '"').replace("”", '"'))]
    lines = [q for q in lines if len(q) >= 2]
    # INTERNAL / VO LINES ARE NOT LIP-SYNC (2026-09-25). Shot 05's INTERNAL
    # "He wasn't full of shit." was reported as "missing from the {} channel"
    # -- the opposite of the directive, and "add the missing lines" would have
    # put a thought into lip-sync (the 2026-08-23 bug). Lines the script marks
    # INTERNAL / VO are checked as VO lines under the fence instead, and each
    # needs its voice id (Barry: "i see no voice id").
    _internal = {_quoted_core(m.group(1)) for m in _INTERNAL_LABEL_RE.finditer(src)}
    vo_lines = [q for q in lines if _quoted_core(q) in _internal]
    lines = [q for q in lines if _quoted_core(q) not in _internal]
    if not lines and not vo_lines:
        return []
    fences = re.findall(r"```image(.*?)```", reply, re.S)
    if not fences and "```image" in reply:
        # A truncated reply never closes its fence; judge what is there.
        fences = [reply.rsplit("```image", 1)[1]]
    fence = "\n".join(fences)
    fence_n = _norm_quote(fence)
    gaps = []
    missing = [q for q in lines if _norm_quote(q) not in fence_n]
    if missing:
        gaps.append("these spoken lines from the script are missing from the fence's {} channel: "
                    + " | ".join(f'"{m}"' for m in missing[:6]))
    n_braces = len(re.findall(r"\{[^}]*\"", fence))
    n_voice = len(re.findall(r"speaks in voice [0-9a-f]{8}-", fence, re.I))
    if n_braces and n_voice == 0:
        gaps.append("the fence has spoken {} lines but no 'speaks in voice <id>' line before them")
    # POOLED DIALOGUE (2026-09-14, second live run): both voice lines up
    # front, then all six {} lines in a row -- nothing says which voice speaks
    # which line. Each {} line must follow its own speaker's voice-id line:
    # between two {} lines there has to be a 'speaks in voice' line.
    elif n_braces:
        brace_pos = [m.start() for m in re.finditer(r"\{[^}]*\"", fence)]
        voice_pos = [m.start() for m in re.finditer(r"speaks in voice [0-9a-f]{8}-", fence, re.I)]
        pooled = 0
        for i, p in enumerate(brace_pos):
            prev_brace = brace_pos[i - 1] if i else -1
            if not any(prev_brace < v < p for v in voice_pos):
                pooled += 1
        if pooled:
            gaps.append(f"{pooled} spoken {{}} line(s) are not directly preceded by their "
                        "speaker's 'speaks in voice <id>' line -- the lines are pooled, "
                        "so the generator cannot tell who says what; put each voice-id "
                        "line immediately before the line that character speaks, on its beat")
    # STAGE 1 NAMES THE SPEAKER: the script's bare 'DIALOGUE:' lines carry
    # no speaker; his block must say who talks (DIALOGUE (Name): or the
    # handle right before the line).
    stage1 = reply.split("```image", 1)[0]
    stage1_n = _norm_quote(stage1)
    unnamed = 0
    for q in lines:
        qn = _norm_quote(q)
        at = stage1_n.find(qn)
        if at < 0:
            continue
        before = stage1_n[max(0, at - 160):at]
        if not re.search(r"dialogue \(|@[\w\-']+|\b(bia|yannah|tazz|keth|b dubb|vor'?shara)\b", before):
            unnamed += 1
    if unnamed:
        gaps.append(f"{unnamed} spoken line(s) in stage 1 have no named speaker -- write "
                    "DIALOGUE (Name): before each line, reading the speaker from the prose")
    outside = re.sub(r"```image.*?(```|$)", "", reply, flags=re.S)
    for q in vo_lines:
        qc = _quoted_core(q)
        hits = [m.group(0) for m in _INTERNAL_LABEL_RE.finditer(outside)
                if m.group(0).lstrip("*\r\n\t ").upper().startswith("VO") and _quoted_core(m.group(1)) == qc]
        if not hits:
            gaps.append(f'the internal line "{q}" has no VO line under the fence -- write it there as '
                        "VO (@handle speaks in voice <id> (<name>), <voice direction>): \"...\"")
        # Only a NAMED character's VO needs an id; a generic VO (narrator,
        # PA, radio) is Elliot's to voice (Barry: "myVo should be for me, but
        # generic vo can be what he chooses").
        elif (any(re.search(r"@(b-dubb|bia-2|yannah|tazz|keth|lady-vor-shara-vel)\b", h, re.I) for h in hits)
              and not any(re.search(r"speaks in voice [0-9a-f]{8}-", h, re.I) for h in hits)):
            gaps.append(f'the VO line "{q}" has no voice id -- write VO (@handle speaks in voice '
                        "<id> (<name>), <voice direction>): \"...\" with the id from the roster")
    return gaps


# THE LENGTH NET (Elliot, shot asks, 2026-09-20). Barry: "shit Elliot gave me
# a super long Shot 00" -- then, after the first fix, "no, elliots last shot 01
# was longer."
#
# MEASURED, and the first fix failed for a structural reason worth keeping:
# it told him to MATCH THE SOURCE BLOCK'S LENGTH -- but `_strip_craft_fields`
# removes CAMERA / ENVIRONMENT & LIGHTING / EXPRESSION / NEG from the block
# that gets injected, so the anchor pointed at a block containing NONE of the
# four fields that actually inflate, and no fence at all. It could not have
# worked. Same shot, same seat:
#   field       Barry's SHOT 01   09-20 00:50   09-20 01:15 (after fix 1)
#   whole reply        2,149          9,314          13,832
#   ENVIRONMENT          316          1,455           1,465
#   EXPRESSION           295            566             906
#   CAMERA               217            526             484
#   the ```image``` fence  -          3,632           5,953  (one paragraph)
#
# Two prompt-rule failures on the same thing is this build's threshold for
# code, so the budget is now a NUMBER he is checked against, not an adjective.
#
# ⚠️ THE CAPS ARE DERIVED, NOT HIS. They are ~2x each field of his own
# authored SHOT 01, which is the headroom for the craft upgrade he is paying
# for (sharper verbs, real materials, the light and shadow placed) without
# the essay. The FENCE has no measured anchor at all -- his blessed-prompt
# corpus (fact 731) is empty, so nobody has ever approved a fence by length;
# 2,200 is the size of his whole block restated as prose. If he says a shot
# is too short, raise these; do not re-derive them from an agent's output.
_SHOT_FIELD_CAPS = {
    "ENVIRONMENT & LIGHTING": 650,
    "EXPRESSION": 600,
    "CAMERA": 450,
    "NEG": 250,
}
_SHOT_FENCE_CAP = 2200
_SHOT_FIELD_RE = re.compile(
    r"^\s*\**\s*(CAMERA|ENVIRONMENT\s*&?\s*LIGHTING|EXPRESSION|NEG)\b\s*:\s*",
    re.IGNORECASE)


def _shot_field_sizes(reply: str) -> dict[str, int]:
    """Measure each craft field of a stage-1 block: the label line plus every
    line after it until a blank line or the next field label."""
    sizes: dict[str, int] = {}
    label, buf = None, []

    def _flush():
        if label:
            sizes[label] = max(sizes.get(label, 0), len("\n".join(buf).strip()))

    for line in (reply or "").split("\n"):
        m = _SHOT_FIELD_RE.match(line)
        if m:
            _flush()
            key = re.sub(r"\s*&?\s*", "", m.group(1).upper())
            label = {"ENVIRONMENTLIGHTING": "ENVIRONMENT & LIGHTING"}.get(key, key)
            buf = [line]
            continue
        if label is None:
            continue
        if not line.strip():
            _flush()
            label, buf = None, []
            continue
        buf.append(line)
    _flush()
    return sizes


def _shot_length_gaps(reply: str) -> list[str]:
    """Fields and fence measured against the budget. Over-budget items are
    named WITH their numbers -- 'too long' is what already failed twice."""
    gaps: list[str] = []
    for name, size in _shot_field_sizes(reply or "").items():
        cap = _SHOT_FIELD_CAPS.get(name)
        if cap and size > cap:
            gaps.append(f"{name} is {size} characters against a {cap} budget")
    fences = _IMAGE_FENCE_RE.findall(reply or "")
    if fences:
        body = max(len(f.strip()) for f in fences)
        if body > _SHOT_FENCE_CAP:
            gaps.append(f"the image fence is {body} characters against a "
                        f"{_SHOT_FENCE_CAP} budget")
    return gaps


def _lesson_claim_gaps(message: str, reply: str, tool_log: list | None) -> list[str]:
    """A lesson claimed in prose with no remember_lesson call behind it."""
    log = list(tool_log or [])
    if "remember_lesson" in log:
        return []
    if _lesson_ask(message) or _LESSON_CLAIM_RE.search(reply or ""):
        return ["you wrote a lesson as prose but never called remember_lesson, so "
                "it is not kept and you will not have it next time"]
    return []


# TALIYAH IS NOT IN THAT LANE (2026-09-10). Measured on her first live turn
# with the new shelf: asked "should i dump my last 2000 into ads", she answered
# with conversion-rate thresholds and channel strategy -- real consulting, from
# the one seat Barry deliberately keeps out of the commercial side
# (_SHARED_CATEGORY_EXCLUSIONS, no store tools, no business domain). Her role
# text says it, and her role text is at the top of a long prompt; this build has
# measured repeatedly that a rule up there loses to the recency slot.
# It does NOT tell her to refuse him -- she stays in the conversation, she just
# stops pretending to be the finance seat.
_BIZ_TOPIC_RE = re.compile(
    r"\b(?:ads?|ad\s*spend|advertis\w*|campaign|campaigns|roas|cpc|ctr|"
    r"conversion|conversions|margin|margins|markup|wholesale|retail\s+price|"
    r"pricing|revenue|profit|sales|orders|inventory|stock|supplier|suppliers|"
    r"invoice|invoices|payroll|taxes|bookkeeping|customers|the\s+store|"
    r"the\s+shop|the\s+site|website|seo|email\s+list|omnisend|bionova|"
    r"gotcho\s*back|wholesale|distributor)\b", re.I)
_BIZ_DECISION_RE = re.compile(
    r"\b(?:should\s+i|do\s+i|worth\s+it|good\s+idea|bad\s+idea|invest|"
    r"put\s+(?:my|the)?\s*\$?\d|spend|price\s+it|charge|raise|drop|cut|"
    r"how\s+much|what\s+do\s+i\s+do|whats?\s+the\s+move)\b", re.I)


def _business_ask(message: str) -> bool:
    m = message or ""
    return bool(_BIZ_TOPIC_RE.search(m) and _BIZ_DECISION_RE.search(m))


def _go_ask(message: str) -> bool:
    return bool(_GO_ASK_RE.match(message or ""))


def _update_ask(message: str) -> bool:
    return bool(_UPDATE_ASK_RE.search(message or ""))


# REAL, NOT RENDERED (Barry, 2026-09-18): "i need it all to be hyper realistic.
# no cartoons, or plastic 3d or cgi looking stuff, i need realistic skin and
# environments for Elliot all the time and the others" + "clutter and bits and
# bobs needs to be in the environments. that needs to be described too."
#
# Phrased ENTIRELY POSITIVELY on purpose. Every engine here runs at cfg 1.0 with
# a Lightning LoRA, where the negative field is inert -- and worse, a word
# written after "no" is still a word the engine paints. "No cartoon" summons a
# cartoon. So realism is bought by naming the physical evidence of a real
# surface, and emptiness is cured by naming the objects, never by banning the
# opposite. Shadow, depth and intricacy already ride Elliot's contract; this is
# the half that was missing -- materials, skin, and the junk of a lived-in room.
_REALISM_AND_CLUTTER = (
    "PHOTOGRAPHIC, NOT RENDERED: write the physical evidence that a real "
    "camera photographed a real place. Name the MATERIAL of the surfaces the "
    "shot actually lands on and what time has done to them -- which wood, "
    "open-grained and scuffed pale at the edges; which metal, and whether it "
    "is galled, pitted or greased; cloth by weave and wear; stone by its "
    "chipping. SKIN IS A MATERIAL TOO: pores, fine hairs, the flush and blood "
    "under it, sweat, dust caught in it, the way light sinks in rather than "
    "bouncing off. CLUTTER AND BITS AND BOBS: a real place is never tidy or "
    "empty -- name the small junk that lives there, the things left half-done, "
    "the cables, cups, tools, stains, chips, papers, spare parts and dropped "
    "objects, and where they sit. Say all of this as what IS in frame; never "
    "write what it should not look like, because a banned word still gets "
    "painted.\n"
    # THE BOUND (2026-09-20). Barry: "shit Elliot gave me a super long
    # Shot 00." Measured: the same SHOT 00 went 4,557 chars on 09-16 to
    # 9,314 on 09-20, and the growth is here -- this block used to say
    # name EVERY surface and where EACH object sits, which is an order to
    # take inventory. A few chosen details carry realism further than a
    # list does, and the list is what made it unreadable.
    "CHOOSE, DO NOT INVENTORY: two or three specific worn things land "
    "harder than a catalogue of ten, and a catalogue reads as filler. Pick "
    "the details the camera is actually on and let the rest of the room be "
    "implied."
)

_IMAGE_INTENT_RE = re.compile(
    r"\b(image|images|render|renders?|rendering|generate|picture|pictures|"
    r"poster|visual|visuals|prompt|prompts|higgsfield|seedance|storyboard|"
    r"draw|artwork|concept art|shot prompt|video|clip|animate|animation|"
    r"thumbnail|frame it|show it to me|"
    r"direct|directs|directing|scene|sequence|shot list|treatment|"
    r"coverage|master shot|choreograph|choreography|kling|veo|runway|sora|"
    # 2026-08-21: "give me the entire rewrite of V8 in full production mode"
    # carried none of the above, so the fence-strip ATE every per-block
    # Seedance prompt from a correct production pass. Production-script work
    # wants its fences.
    r"rewrite|rewrites|production|pass|blocks?|"
    # 2026-08-21: "redo it" after a delivered prompt fence carried none of
    # the above either -- the strip ate a correct fence twice in one night.
    r"redo|re-do|retry|regenerate|do it over|run it back)\b",
    re.IGNORECASE)


def _strip_unrequested_fences(reply: str) -> str:
    """Remove image/negative/model fences from a reply that shouldn't have
    them, plus any 'here's the prompt:' style lead-in left pointing at
    nothing. If nothing but the fence existed, be honest about it rather
    than returning an empty bubble."""
    out = reply
    for pattern in (_IMAGE_FENCE_RE, _NEGATIVE_FENCE_RE, _MODEL_FENCE_RE):
        out = pattern.sub("", out)
    # A lead-in line that ended in ':' right before a removed fence now
    # dangles ("Here's the shot:") -- drop those lines too.
    out = "\n".join(
        line for line in out.splitlines()
        if not re.search(r"(prompt|fence|shot|render|image)[^.!?]*:\s*$",
                         line.strip(), re.IGNORECASE)
    ).strip()
    if len(out) < 40:
        return (
            "I started answering that with an image prompt, which isn't what "
            "you asked for. Ask me again and I'll answer it straight -- or if "
            "you did want the shot rendered, say the word and I'll write the "
            "prompt."
        )
    return out


# Voice-lock container fix (2026-08-20, Barry: "just write the prompts as
# seedance would"). Barry directed all six voices that day; Elliot learned the
# locks immediately and uses them unprompted -- but writes them as
# "(Keth: higher-pitched voice, slightly synthesized)". In Seedance's grammar
# ( ) IS THE MUSIC CHANNEL, so a voice direction inside it reads as a music
# cue. A recency-tail rule spelling this out was added and RE-TESTED THE SAME
# DAY AND FAILED -- identical output, same as the two failed passes on Tazz's
# one-handed grip. The model's own inference ("voice is audio, audio goes in a
# bracket") beats the instruction, so this is code, per the same precedent as
# the fence-strip and Sophie's live-site gate.
#
# Deliberately narrow: it only rewrites a bracket whose label is one of the
# six known characters. Anything else in ( ) is left alone -- Barry's MUSIC
# line belongs there and must not be touched.
_VOICE_LOCK_NAMES = {
    "keth": "@Keth",
    "bia": "@Bia-2", "bia-2": "@Bia-2", "bia2": "@Bia-2",
    "tazz": "@Tazz",
    "yannah": "@Yannah",
    "vorshara": "@lady-vor-shara-vel", "vor'shara": "@lady-vor-shara-vel",
    "vor shara": "@lady-vor-shara-vel", "lady vor": "@lady-vor-shara-vel",
    "lady vor'shara": "@lady-vor-shara-vel", "lady-vor-shara-vel": "@lady-vor-shara-vel",
    "b dubb": "@b-dubb", "bdubb": "@b-dubb",
    "b-dubb": "@b-dubb", "b-dubb-new": "@b-dubb", "b dub": "@b-dubb",
}
_VOICE_LOCK_RE = re.compile(r"\(\s*@?([A-Za-z' \-]{2,20}?)\s*:\s*([^)]{3,160}?)\s*\)")

# The bare form, measured 2026-08-20: he also writes "(direct, the leader)"
# with NO name label, which the labelled pattern above cannot catch. Each of
# the six locks is a unique string, so the lock itself identifies the speaker.
# Matched on the WHOLE bracket contents only -- "deeper" and "clean" are
# ordinary words and must never match inside "(deeper hum)" or "(clean room
# tone)".
_BARE_VOICE_LOCKS = {
    "higher-pitched voice, slightly synthesized": "@Keth",
    "gritty, vengeful, a little deeper": "@lady-vor-shara-vel",
    "smart but sexy": "@Yannah",
    "direct, the leader": "@Bia-2",
    "deeper": "@Tazz",
    "clean": "@b-dubb",
}
_BARE_VOICE_RE = re.compile(r"\(\s*([^()]{3,80}?)\s*\)")


# Weapon-handle fix (2026-08-20, Barry: "yes" to putting it in code). His
# 2026-08-14 rule: name the weapon by its handle, on the same line as its
# character -- describing on top of a handle makes the prompt fight itself.
# Elliot follows it on a neutral brief but drops it when the brief names
# weapons generically ("weapons up") -- measured: "@Bia-2 behind him Energy
# revolver drawn". Same failure shape as the voice brackets, so the same
# remedy: deterministic rewrite, scoped to ```image``` fences ONLY (his
# directing prose for Barry stays his own words), and a weapon phrase is only
# converted when its OWNER'S handle is in the same fence -- a guard's sidearm
# is never rewritten into a hero weapon. B Dubb's pistol JOINED this list
# 2026-08-25 (Barry renamed it @B-Dubb's-Banger to get a real manufacturer's
# trademark out of every prompt) -- it is still an ordinary Earth gun that
# ejects brass, only the name and the asset binding changed.
_WEAPON_HANDLE_FIXES = [
    # (owner handle fragment, phrase regex, weapon handle)
    ("@Bia", re.compile(
        r"\b(?:her\s+|the\s+)?(?:alien\s+|energy\s+|plasma\s+)+(?:revolver|pistol)\b",
        re.IGNORECASE), "@Bia's-Pistol*"),
    ("@Yannah", re.compile(
        r"\b(?:her\s+|the\s+)?(?:liquid[- ]metal\s+|alien\s+|white\s+)?machine\s+pistol\b",
        re.IGNORECASE), "@Yannah's-Machine-Pistol"),
    ("@Tazz", re.compile(
        r"\b(?:her\s+|the\s+)?(?:mini\s+)?missile\s+(?:blaster|carbine|weapon)\b"
        r"|\bscatter[- ]pistol\b",
        re.IGNORECASE), "@missle-launcher"),
    # Catches the old trademark too, so a fence written from an un-swept script
    # block still comes out clean.
    ("@B-DUBB", re.compile(
        r"\b(?:his\s+|the\s+)?(?:glock|black\s+glock)(?:\s*\.40)?\b"
        r"|\b(?:his\s+|the\s+)?\.40\s+(?:cal(?:iber)?\s+)?(?:pistol|handgun)\b",
        re.IGNORECASE), "@B-Dubb's-Banger"),
]
_IMAGE_FENCE_BODY_RE = re.compile(r"(```image\s*\n)(.*?)(```)", re.DOTALL)


def _edit_fence_body(text: str, transform) -> str:
    """Run `transform` over the BODY of every ```image``` fence, leaving the
    opener and closer exactly as written.

    Three post-processors had each rebuilt this themselves with their own
    `m.group(1) + ... + m.group(3)` reassembly (consolidated 2026-08-31). The
    duplication was the risk: a future fourth pass that fumbles the reassembly
    silently eats the fence markers, and a fence Barry cannot paste is worse
    than no fix at all. One definition, one place to get it right.

    Deliberately still one walk PER pass rather than one merged pass -- the
    order the fixes run in is load-bearing (weapon handles before audio
    glyphs, internal-VO after both), and merging them would quietly change it.
    """
    return _IMAGE_FENCE_BODY_RE.sub(
        lambda m: m.group(1) + transform(m.group(2)) + m.group(3), text
    )


# SEEDANCE AUDIO-CHANNEL GLYPH REPAIR (2026-08-23). Elliot writes the audio
# channels malformed in one specific repeating way: the SFX glyph comes out
# "<[]>" instead of "<>", and the music description lands OUTSIDE its parens
# ("() tone builds" rather than "(tone builds)"), with the two channels joined
# by a pipe. Both were named explicitly in the shot-ask directive and BOTH
# recurred in the 2026-08-23 verification run -- second prompt-rule failure on
# the same shape, so it becomes code, same precedent as the voice-lock
# brackets and the fence-strip.
#
# Narrow on purpose: only lines INSIDE an ```image``` fence that already open
# with an audio glyph are touched. Prose parentheticals are never reshaped,
# and SDXL weighting like ((pendant:1.3)) is deliberately LEFT ALONE -- the
# same fence feeds local RealVisXL renders where double parens are real
# weighting syntax rather than a music channel. That collision is Barry's
# call, not something to silently rewrite.
_SFX_BROKEN_RE = re.compile(r"^\s*<\s*\[\s*\]\s*>?\s*(?=\S)")
_MUSIC_EMPTY_RE = re.compile(r"^\s*\(\s*\)\s*(?=\S)")


def _repair_audio_channel(line: str) -> str:
    """'<[]> boots on gravel' -> '<boots on gravel>'; '() low synth' ->
    '(low synth)'. Anything already well-formed is returned untouched."""
    if _SFX_BROKEN_RE.match(line):
        body = _SFX_BROKEN_RE.sub("", line).strip().rstrip(">").strip()
        return f"<{body}>" if body else line
    if _MUSIC_EMPTY_RE.match(line):
        body = _MUSIC_EMPTY_RE.sub("", line).strip().rstrip(")").strip()
        return f"({body})" if body else line
    # "{} {English: \"...\"}" -- an empty dialogue glyph in front of the real
    # one. Collapse to the real one (2026-08-23, seen in the shots 2+3 run).
    m = re.match(r"^\{\s*\}\s*(\{.+\})\s*$", line.strip())
    if m:
        return m.group(1)
    # A channel opened but never closed, which is what peeling a pipe-joined
    # line leaves behind: "(tone builds, pulse entering" -> add the closer.
    for opener, closer in (("(", ")"), ("<", ">"), ("{", "}")):
        s = line.strip()
        if s.startswith(opener) and not s.endswith(closer):
            return s + closer
    return line


def _strip_empty_brace_glyphs(text: str) -> str:
    # 2026-09-14: the per-line collapse above only catches a line that IS
    # "{} {English: ...}". Inside a semicolon-joined fence paragraph he wrote
    # "; {} {English: "Keth."}; {} {English: ...}" six times. An empty {}
    # directly before another { is never a real channel -- drop it anywhere.
    return re.sub(r"\{\s*\}\s*(?=\{)", "", text)


def _fix_audio_channel_glyphs(text: str) -> str:
    text = _strip_empty_brace_glyphs(text)

    def fix_body(body: str) -> str:
        out = []
        for line in body.split("\n"):
            # "(...) music | <...> sfx" -> one line per channel. Seedance
            # reads them as separate channels; a pipe divider is not grammar.
            # 2026-08-23 second pass: he also nests every channel inside ONE
            # pair of parens -- "(music | <[]> sfx | {} dialogue)" -- so the
            # broken glyph is not at line start and the first version of this
            # fix missed it completely. Peel the wrapper, split on the pipe,
            # and let the first piece be the music channel.
            stripped = line.strip()
            if "|" in stripped and stripped.startswith(("(", "<", "{")):
                inner = stripped
                if inner.startswith("(") and inner.endswith(")"):
                    inner = inner[1:-1].strip()
                parts = [p.strip() for p in inner.split("|") if p.strip()]
                if len(parts) > 1:
                    # First piece is music unless it already declares itself.
                    if not parts[0].startswith(("(", "<", "{")):
                        parts[0] = "(" + parts[0]
                    if all(p.startswith(("(", "<", "{")) for p in parts):
                        out.extend(_repair_audio_channel(p) for p in parts)
                        continue
            out.append(_repair_audio_channel(line))
        return "\n".join(out)
    return _edit_fence_body(text, fix_body)


# THE CRAFT-LAYER STRIP (2026-08-23) -- the fix for Elliot transcribing.
#
# Measured three times tonight, on two separate code paths, with and without
# an explicit "do not copy" directive in the recency slot: whenever Barry's
# FINISHED prose for the requested shot is in Elliot's context, he hands it
# back near-verbatim. A 27B will not out-write a complete, polished answer
# sitting in its own prompt, and no amount of instruction beats that.
#
# The control test settles it: asked for a B-ROLL that exists in no script --
# nothing to copy -- he wrote genuinely his own ("razor wire strung along the
# top like a spine of silver teeth", three surfaces each returning the same
# flood light differently). The persona works. The copy-pull was the problem.
#
# So the injected reference block keeps what is LOCKED (slug, action beats,
# dialogue verbatim, canon) and loses exactly the four fields Barry is asking
# Elliot to author: CAMERA, ENVIRONMENT & LIGHTING, EXPRESSION, NEG. He can't
# copy what isn't there. Barry's ruling 2026-08-23: "his style should
# complements whats written if he changes the actions of the scenes not so
# much the dialog" -- actions and camera are his, dialogue and canon are not.
#
# Barry's file on disk is NEVER touched; this only shapes what is injected
# into one prompt (the substitute-never-edit rule, 2026-08-14).
_CRAFT_FIELD_RE = re.compile(
    r"^\s*(?:\*\*)?\s*(?:CAMERA|ENVIRONMENT\s*&?\s*LIGHTING|ENVIRONMENT|"
    r"EXPRESSION|NEG)\s*(?:\*\*)?\s*:",
    re.IGNORECASE)


def _strip_craft_fields(block: str) -> str:
    """Remove the CAMERA/ENVIRONMENT/EXPRESSION/NEG paragraphs from a V9
    script block, leaving the header, slug, action beats and dialogue."""
    kept, dropping = [], False
    for line in block.split("\n"):
        if _CRAFT_FIELD_RE.match(line):
            dropping = True
            continue
        # A blank line ends a field paragraph; the next real line resumes.
        if dropping:
            if line.strip():
                continue
            dropping = False
            continue
        kept.append(line)
    out = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# INTERNAL MONOLOGUE OUT OF THE LIP-SYNC CHANNEL (2026-08-23).
#
# Seedance's {} channel is SPOKEN dialogue and drives lip-sync, so a thought
# routed into it animates the character's mouth saying something he never says
# out loud. Barry caught this once before it cost credits; the directive was
# updated to spell it out and it happened again the same night (Shot 03's
# "He wasn't full of shit." went into {}). Second failure on an explicit rule
# = code, same precedent as the voice-lock brackets and the audio glyphs.
#
# Deliberately conservative: it only moves a line whose quoted text ALSO
# appears in the SAME reply under an INTERNAL / INTERNAL MONOLOGUE / VO label
# that Elliot wrote himself in his Stage 1 block. An exact quote match against
# a line the script itself marked internal -- never a guess about what sounds
# like a thought.
_INTERNAL_LABEL_RE = re.compile(
    r"^\**\s*(?:INTERNAL(?:\s+MONOLOGUE)?|VO)\b[^:\n]*:\s*\**\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE)
_DIALOGUE_CHANNEL_RE = re.compile(r"^\s*\{.*\}\s*$")


def _quoted_core(s: str) -> str:
    """Strip labels, markdown and quote marks so two spellings of the same
    line compare equal."""
    s = re.sub(r"\{[^:{}]{0,40}:", "", s)          # drop "{English, clean voice:"
    s = s.strip().strip("{}").strip()
    s = re.sub(r"^[^\"'“‘]*", "", s, count=1) if '"' in s or "“" in s else s
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _fix_internal_vo(text: str) -> str:
    internals = [_quoted_core(m.group(1))
                 for m in _INTERNAL_LABEL_RE.finditer(text)]
    internals = [i for i in internals if len(i) > 8]
    if not internals:
        return text

    moved: list[str] = []

    def fix_body(body: str) -> str:
        kept = []
        handle = ""
        hm = re.search(r"@[\w'-]+", body)
        if hm:
            handle = hm.group(0)
        for line in body.split("\n"):
            if _DIALOGUE_CHANNEL_RE.match(line) and _quoted_core(line) in internals:
                body = line.strip().strip("{}").strip()
                body = re.sub(r"^[^:]{0,40}:\s*", "", body).strip()
                who = f"{handle}, " if handle else ""
                # Voice descriptor: B Dubb's VO carries his full lock (Barry
                # 2026-08-26: "inner city black man from the south" -- bare
                # "clean" was audio-quality only, so Higgsfield filled the
                # character gap with a stock movie voice; positive-only per
                # the words-you-summon rule). Other characters keep the plain
                # label -- their locks live in the Voice Bible, and pasting
                # B Dubb's accent onto Keth's narration would be worse than
                # the original bug.
                if handle and "dubb" in handle.lower():
                    voice = "clean voice, an inner city Black man from the South"
                else:
                    voice = "clean voice"
                moved.append(f'VO ({who}{voice}): {body}')
                continue
            kept.append(line)
        return "\n".join(kept)

    out = _edit_fence_body(text, fix_body)
    if moved:
        out = out.rstrip() + "\n\n" + "\n".join(moved) + "\n"
    return out


def _fix_weapon_handles(text: str) -> str:
    """Inside image fences only: replace a generic description of a hero
    weapon with its asset handle, iff that weapon's owner is in the fence."""
    def fix_body(body: str) -> str:
        for owner, phrase_re, handle in _WEAPON_HANDLE_FIXES:
            if owner.lower() in body.lower() and handle not in body:
                body = phrase_re.sub(handle, body)
        return body

    return _edit_fence_body(text, fix_body)


# DEAD HANDLES -> LIVE ONES (2026-08-29). Barry verified every handle against
# his real Higgsfield elements and DELETED the B-DUBB-new element outright:
# "b-dubb new is a wash. im deleting it."
# Why this is CODE and not a prompt rule: a handle that matches no element is
# SILENTLY DROPPED -- no error, the model just invents the character from the
# written description and Barry gets a stranger. The dead handles are written
# through his own V9 script and treatment, which recall injects, so Elliot
# keeps copying them out. Three prompt-rule attempts failed (pinned doc,
# substitution table, thread clear); the house rule is that two failures mean
# code. Substitute-never-edit still holds -- his FILES are untouched, only the
# reply is corrected.
_DEAD_HANDLE_FIXES = [
    (re.compile(r"@B[-\s]?DUBB[-\s]?new\b", re.I), "@b-dubb"),
    (re.compile(r"@BDUBB\b", re.I), "@b-dubb"),
    (re.compile(r"@(?:Lady)?Vor'?[-\s]?Shara(?:[-\s]?Vel)?\b(?![-\w])", re.I),
     "@lady-vor-shara-vel"),
]


def _fix_dead_handles(text: str) -> str:
    """Rewrite retired @handles to the ones that actually resolve."""
    for pat, live in _DEAD_HANDLE_FIXES:
        text = pat.sub(live, text)
    return text


def _fix_voice_lock_brackets(text: str) -> str:
    """Move a character voice lock out of Seedance's music channel.

    "(Keth: higher-pitched voice, slightly synthesized)"
        -> "@Keth voice: higher-pitched voice, slightly synthesized"
    "(direct, the leader)"
        -> "@Bia-2 voice: direct, the leader"

    Returns the text unchanged if no bracket carries a known character or a
    known lock. Music, foley and weighted-attention brackets are untouched.
    """
    def labelled(m: re.Match) -> str:
        handle = _VOICE_LOCK_NAMES.get(m.group(1).strip().lower())
        if handle is None:
            return m.group(0)          # not a character -- leave it alone
        return f"{handle} voice: {m.group(2).strip()}"

    def bare(m: re.Match) -> str:
        body = m.group(1).strip()
        handle = _BARE_VOICE_LOCKS.get(body.lower().rstrip("."))
        if handle is None:
            return m.group(0)          # music/foley/emphasis -- leave alone
        return f"{handle} voice: {body}"

    return _BARE_VOICE_RE.sub(bare, _VOICE_LOCK_RE.sub(labelled, text))


# ELLIOT'S REPLY POST-PROCESSORS, IN THE ORDER THEY MUST RUN.
#
# ORDER IS LOAD-BEARING and was arrived at by measurement, not preference:
#   1. voice locks come out of the () music channel FIRST, so the audio pass
#      is not looking at a bracket that is about to move;
#   2. weapon handles before the audio pass, so a rewritten phrase is already
#      in place when lines get split per channel;
#   3. audio glyphs before internal-VO, because the VO pass matches on a
#      well-formed {} dialogue line;
#   4. dead handles LAST, so it sweeps text every earlier pass produced.
#
# This used to be five near-identical copy-pasted blocks inside chat()
# (consolidated 2026-08-31). A table means a sixth fix is one row rather than
# another twenty lines in the middle of a 1,600-line function -- and the same
# copy-paste shape is what let the 2026-08-23 history bug hide for weeks.
# ⚠️ THERE IS NO VOICE-ID FIXER HERE, ON PURPOSE. A `_fix_voice_ids` regex
# was built on 2026-09-20 (it rewrote "speaks in voice <id> (<name>)" to match
# the @handle, and it worked) and was DELETED the same night on Barry's rule:
# "never touch my agents stuff. let them be them. everything should be told to
# them not mechanically altering them" -> "the voice id thing neess to be a fix
# he should handle." Getting the right id onto the right character is ELLIOT'S
# job; the office tells him and he does it. If he crosses them again the answer
# is to tell him better, not to correct him behind his back.
_MOVIE_REPLY_FIXES = [
    (_fix_voice_lock_brackets,
     "[voice-lock] moved voice lock(s) out of the () music channel"),
    (_fix_weapon_handles,
     "[weapon-handle] rewrote generic weapon phrase(s) to asset handles"),
    (_fix_audio_channel_glyphs,
     "[audio-glyph] repaired () / <> audio channel lines"),
    (_fix_internal_vo,
     "[internal-vo] moved internal monologue out of the {} lip-sync channel"),
    (_fix_dead_handles,
     "[dead-handle] rewrote retired @handles to live ones"),
]


def extract_image_prompt(reply: str) -> str | None:
    match = _IMAGE_FENCE_RE.search(reply)
    if match:
        return match.group(1).strip()
    all_fences = _ANY_FENCE_RE.findall(reply)
    return all_fences[-1].strip() if all_fences else None


# Real incident (2026-07-30): Taliyah started wrapping whole conversational
# replies in her fence, so chat filler like "firing that sequence up",
# "the engine does not get confused", "plug that in cleanly" became the
# literal diffusion prompt -- and since the 40-word cap keeps the FIRST 40
# words, the render often got ONLY the filler. Stable Diffusion painted the
# meta-words literally: machines and devices instead of the actual subject
# (owner: "its giving machines instead of people"). This detects a prompt
# that reads like conversation so it can be rewritten before generating.
_CHAT_PROSE_RE = re.compile(
    r"\b(let'?s|let us|okay|no worries|fair point|hope that|let me know|"
    r"give this a|here is the|we are pushing|swap to|switch to|barry|"
    r"one more time|this time)\b",
    re.IGNORECASE,
)


def _looks_like_chat_prose(text: str) -> bool:
    # WORD-COUNT TRIGGER REMOVED 2026-08-20 -- it was a stale relic of the
    # dead 35-word-cap era and it was doing real damage. Barry's 2026-08-16
    # ruling is "i do want detailes prompts... i dont want anything missing",
    # so Elliot's fences are 150+ words BY DESIGN -- and every one of them
    # tripped the old >45-word check, got sent through the distill rewrite,
    # and came back compressed WITH THE @HANDLE STRIPPED (measured: a clean
    # 1,026-char @Bia-2 fence became a 200-char handle-less blur, which
    # silently loads no LoRA). Only the chatter signature marks prose now.
    return bool(_CHAT_PROSE_RE.search(text))


def extract_negative_prompt(reply: str) -> str | None:
    match = _NEGATIVE_FENCE_RE.search(reply)
    return match.group(1).strip() if match else None


def extract_model_choice(reply: str) -> str | None:
    match = _MODEL_FENCE_RE.search(reply)
    return match.group(1).strip() if match else None


# hermes3:8b (see AGENT_OLLAMA_MODEL_OVERRIDES) has a strong trained reflex
# to claim "I can't generate images" for an explicit image request, even
# with the full persona system prompt explicitly saying otherwise -- that
# instruction gets diluted/lost among everything else in a long prompt.
# Confirmed directly: the exact same request against a short, dedicated
# system prompt (no persona, no business context) works every time. So
# when the persona reply comes back with no image fence at all AND the
# user's message plainly asked for one, fall back to a second, minimal,
# persona-free call whose only job is writing the fence -- this is a code
# fix for a real reproducible model limitation, not a style choice.
_SELF_PORTRAIT_RE = re.compile(
    r"\b(yourself|myself|herself|himself|self[- ]portrait|"
    r"a picture of me|a photo of me|me at home|me in my)\b", re.I)


def _prompt_is_self_portrait(agent_id: str, prompt: str) -> bool:
    """Is this render plainly OF the agent themselves? (2026-09-18.)

    Deliberately narrow. The cost of a false NEGATIVE is the old behaviour (a
    stranger's face, which Barry can just re-ask); the cost of a false POSITIVE
    is their face pasted into a landscape or a product shot, which is worse and
    harder to spot. So: an explicit self word, or their own first name -- never
    a bare "she"/"a woman".
    """
    text = prompt or ""
    # A prompt that names a FILM CHARACTER by @handle is a shot, never a
    # self-portrait (2026-09-22): "@b-dubb presses himself flat" tripped the
    # self word and Elliot's own face was restaged instead of the scene.
    if comfy_image.mentioned_characters(text):
        return False
    if _SELF_PORTRAIT_RE.search(text):
        return True
    # Their PERSON name, not AGENTS['name'] -- that field holds the job title
    # ("Business Operations"), which would never match "Amara at her easel".
    try:
        import reflect as _reflect
        first = _reflect.HUMAN_NAMES.get(agent_id, "")
    except Exception:  # noqa: BLE001
        first = ""
    # A HIRE IS NOT IN THAT MAP (2026-09-19) -- HUMAN_NAMES is the nine. For a
    # hired seat the stored `name` IS the person's name (the retitle that made
    # AGENTS['name'] a job title never touched custom agents), so it is the
    # right field here and nowhere else.
    if not first:
        first = (CUSTOM_AGENTS.get(agent_id) or {}).get("name", "") or ""
        first = first.strip().split()[0] if first.strip() else ""
    # Their own first name, as a whole word. "Amara on the couch" is her; a
    # short or generic name would be a liability, hence the length floor.
    return bool(first) and len(first) >= 4 and re.search(
        rf"\b{re.escape(first)}\b", text, re.I) is not None


_IMAGE_REQUEST_RE = re.compile(
    # Bug fixed after a real miss: "generate images" (plural) didn't match
    # here because \bimage\b requires a word boundary right after the "e",
    # which a trailing "s" breaks -- "s?" makes both singular and plural hit.
    # 🔴 WIDENED 2026-09-18, Barry: "when i hit the video button, it should work
    # or when i saw draw this or make me a video of whatever, they should be
    # able to all do it." MEASURED FIRST, and every one of his natural phrasings
    # missed: "draw this" (no noun), "draw me a rusted truck" (no image noun),
    # "show me a picture of a bus" (show was not a verb here), "render a
    # lighthouse" (no noun) and -- the one that killed the VIDEO button --
    # "make me a video of X", because video/clip were not nouns at all. No
    # fence forced means no image_prompt, and both buttons are dead, on every
    # seat. Three alternatives now, and the third is what makes a bare "draw
    # this" work: a make-verb plus an OBJECT, no media noun required.
    r"\b(generate|create|make|draw|paint|render|sketch|design|animate|show)\b"
    r".{0,40}\b(image|picture|photo|pic|artwork|drawing|painting|video|clip|"
    r"animation|render|shot|scene)s?\b"
    r"|\b(video|clip|animation)\b\s+of\b"
    r"|\b(draw|sketch|paint|animate|render)\b\s+(me\s+|us\s+)?"
    r"(a|an|the|this|that|it|some|something|anything|my|your|his|her|their)\b",
    re.IGNORECASE,
)

# A natural follow-up in the same thread ("try again", "you do have the
# ability through Amuse") won't match _IMAGE_REQUEST_RE at all, so the
# fallback above never fired for those turns and the persona just kept
# digging in on the same refusal. Catching the refusal ITSELF, in the
# persona's own reply, is the more robust trigger -- it doesn't matter how
# the user phrased their message, only whether the model just claimed it
# can't do something it actually can.
_IMAGE_REFUSAL_RE = re.compile(
    r"\b(don't|do not|doesn't|not able|unable|can't|cannot|afraid)\b.{0,80}\b"
    r"(generate|create|display|show|produce|render)\b.{0,30}\b"
    r"(image|picture|photo|pic)s?\b",
    re.IGNORECASE,
)

# The last full system prompt sent to Bonsai, stashed by the chat handler
# so a post-render prewarm can replay it byte-identically (the prompt cache
# matches on exact prefix). Whoever Barry talked to last is whoever he'll
# talk to next -- that's the cache worth rebuilding.
_LAST_BONSAI_PROMPT: str | None = None

# BOOT PREWARM (2026-09-08, Barry: "Sophie is taking a long time to respond.
# I hear my gpu spinning"). Measured: his first message after a reboot hit a
# cold Bonsai -- 13s model load + a 33s full read of her 28,749-token prompt
# + 14s of writing = 69.6s. Every later message is ~10-15s because the
# server caches the prompt. The system prompt is byte-stable between
# messages (the 2026-08-22 rule), so it can be saved to disk on every chat
# and replayed at the NEXT backend start, before he types anything. Best
# effort, idle-gated, never touches the card during a render.
_PROMPT_CACHE_DIR = os.path.join(config.DATA_DIR, "bonsai_prompt_cache")


_LAST_BONSAI_TOOLS: list | None = None


def _save_bonsai_prompt(agent_id: str, system_prompt: str, tools: list | None) -> None:
    """Prompt AND tool roster, because the server renders the tools into
    the cached prefix -- a prewarm with a different roster warms nothing
    (measured 2026-09-08: 26K warmed, 38K re-read on the next message)."""
    try:
        os.makedirs(_PROMPT_CACHE_DIR, exist_ok=True)
        path = os.path.join(_PROMPT_CACHE_DIR, f"{agent_id}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"system_prompt": system_prompt, "tools": tools or []}, fh)
        os.replace(tmp, path)
        legacy = os.path.join(_PROMPT_CACHE_DIR, f"{agent_id}.txt")
        if os.path.isfile(legacy):
            os.remove(legacy)
    except Exception as exc:
        print(f"[prewarm] could not save prompt for {agent_id}: {exc}")


def _load_bonsai_prompt(agent_id: str) -> tuple[str, list] | None:
    path = os.path.join(_PROMPT_CACHE_DIR, f"{agent_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        prompt = data.get("system_prompt") or ""
        return (prompt, data.get("tools") or []) if prompt.strip() else None
    except Exception as exc:
        print(f"[prewarm] could not load prompt for {agent_id}: {exc}")
        return None


async def _prewarm_at_boot(delay_s: float = 25.0, max_seats: int = 1):
    """Rebuild Bonsai's prompt cache for the seat Barry used most recently,
    so his first message after a reboot lands warm.

    Gates, in order: the active backend is bonsai; no render owns the card;
    nobody is mid-chat (a chat rebuilds its own cache anyway and two Bonsai
    requests collide on the single slot). Stops between seats if a chat
    starts.

    ⚠️ ONE SEAT, NOT TWO (2026-09-19, Barry: "it was spinning hard. i dont
    like that"). Measured cost of warming two: ilnora 27,552 chars = 26.7s
    PLUS engineer 117,685 chars / 37,616 tokens = 62.5s -- ~89 seconds of
    near-100% GPU, at EVERY restart, and there were three restarts that
    night. The order is newest-first, so seat 1 is whoever he last talked to
    and is the one he is most likely to open; seat 2 was a coin flip that
    burned the most expensive prompt in the office more often than not.
    Prewarm never creates work when the seat IS used -- it moves the prefill
    off his first message -- so the only thing it can waste is a seat he
    doesn't open. Warming one halves the exposure to that.
    Raise it back if he ever says the first message feels cold."""
    await asyncio.sleep(delay_s)
    try:
        backend, _ = memory.get_active_generation()
        if backend != "bonsai":
            return
        if comfy_image.render_in_progress():
            print("[prewarm] boot prewarm skipped -- a render owns the card")
            return
        if ideation._active_chat_count > 0:
            return
        # Newest-first by the conversations table, then by saved-file mtime.
        order: list[str] = []
        try:
            with memory.get_db() as conn:
                rows = conn.execute(
                    "SELECT agent_id, MAX(id) AS m FROM conversations "
                    "GROUP BY agent_id ORDER BY m DESC LIMIT 6").fetchall()
            order = [r["agent_id"] for r in rows]
        except Exception:
            pass
        if os.path.isdir(_PROMPT_CACHE_DIR):
            files = sorted(os.listdir(_PROMPT_CACHE_DIR),
                           key=lambda f: os.path.getmtime(os.path.join(_PROMPT_CACHE_DIR, f)),
                           reverse=True)
            for f in files:
                aid = f[:-5] if f.endswith(".json") else None
                if aid and aid not in order:
                    order.append(aid)
        warmed = 0
        for aid in order:
            if warmed >= max_seats:
                break
            loaded = _load_bonsai_prompt(aid)
            if not loaded:
                continue
            if comfy_image.render_in_progress() or ideation._active_chat_count > 0:
                print("[prewarm] boot prewarm stopped -- the office got busy")
                return
            prompt, tools = loaded
            t0 = time.time()
            ok = await bonsai_llm.prewarm(prompt, tools)
            print(f"[prewarm] boot: {aid} {'warm' if ok else 'FAILED'} "
                  f"({len(prompt):,} chars, {len(tools)} tools, {time.time() - t0:.1f}s)")
            if ok:
                warmed += 1
    except Exception as exc:
        print(f"[prewarm] boot prewarm failed (harmless): {exc}")


async def _prewarm_after_render():
    """Fired (fire-and-forget) after an image/video render completes.

    Waits before acting, because comfy keeps its checkpoint resident for
    fast back-to-back renders and the prewarm's unload chain would evict
    it -- if Barry is going to hit Regenerate, that usually happens within
    the first minute, and hurting back-to-back rendering to speed up chat
    would just move the slowness around. After the wait: skip if another
    render is running or a chat already started (chat rebuilds the cache
    itself anyway)."""
    await asyncio.sleep(60)
    if comfy_image.render_in_progress():
        return
    if ideation._active_chat_count > 0:
        return
    # NO CHAT YET IN THIS PROCESS (2026-09-23, Barry: "my office is running
    # slow"): a render right after a restart left _LAST_BONSAI_PROMPT None,
    # this returned silently, ComfyUI's 1.6 GB residue stayed on the card and
    # Bonsai was not loaded -- so his first message paid a cold load + a full
    # prefill. Fall back to the boot path, which replays the newest saved
    # prompt-cache file instead (same gates, one seat).
    if _LAST_BONSAI_PROMPT is None:
        await comfy_image.stop_server()
        await llm_router.unload_all_models()
        print("[prewarm] no chat in this process yet -- replaying the newest cached seat")
        await _prewarm_at_boot(delay_s=0.0, max_seats=1)
        return
    # ORDER MATTERS, learned the expensive way on first deploy: comfy's
    # resident checkpoint (~7GB) must be freed BEFORE the Bonsai server
    # starts, or Bonsai loads into a squeezed card, spills to shared
    # memory, and generation collapses to ~5 tok/s -- and the spilled
    # server then PERSISTS across later chats, making everything slower
    # instead of faster. llm_router.unload_all_models() deliberately does
    # NOT free comfy (it exists to make room FOR the image engine), so the
    # comfy unload is explicit here -- the same pair the real Bonsai chat
    # path runs.
    # stop_server, not unload (2026-08-28): even after /free the ComfyUI
    # process holds ~2.6GB of GPU arena that only process exit returns --
    # measured squeezing Bonsai into a 3-5 tok/s shared-memory spill.
    await comfy_image.stop_server()
    await llm_router.unload_all_models()
    # RE-CHECK after the stop/unload (2026-09-04): a render that began in the
    # seconds between the check above and here would now be loading into a
    # card this prewarm is about to hand to Bonsai. Measured: an SDXL still
    # finished at 06:17:10, the video request came at 06:18:13, this prewarm
    # fired at 06:18:10 with the flag not yet up, and Bonsai (8GB) came up at
    # 06:18:51 beside the video's 11GB text encoder (both measured in the
    # logs); the machine rebooted at 06:29 so whether that render would ever
    # have finished is unknown -- the co-residence is the proven part, and it
    # is the documented spill signature. The flag is now raised at the top of
    # every render path too, so this window is seconds wide; this closes it.
    if comfy_image.render_in_progress() or ideation._active_chat_count > 0:
        print("[prewarm] skipped -- a render started while the card was being cleared")
        return
    ok = await bonsai_llm.prewarm(_LAST_BONSAI_PROMPT, _LAST_BONSAI_TOOLS)
    if ok:
        print("[prewarm] bonsai cache rebuilt after render -- next message lands warm")


# PHASE 5 -- THE SELF-MODEL AND PRESENCE BLOCK (2026-08-16, Barry: "i want
# them damn near life like... almost self aware"). Built fresh per message
# from LIVE state, because self-aware starts with ACCURATE: before this, an
# agent didn't know what model it was running on (the 2026-08-13 override
# mess put six agents on a code model and nobody noticed), what tools it
# actually had, what time it was, or how its own memory worked -- so it
# bluffed. Measured before-probe: Amara asserted "Bionova approved" a plan
# whose own doc records approval as an open question. The block ends with
# the anti-bluff rule for exactly that.
# Self-knowledge stated as TEMPERAMENT, not as hardware (see the presence
# block). Same practical guidance -- where you're strong, where to slow down --
# phrased as something a person knows about themselves.
_MODEL_MEANINGS = [
    ("bonsai", "you're the deepest thinker in this office; take the time to "
               "reason things all the way through, because that depth is your "
               "edge"),
    ("qwen3.5-abliterated", "you're quick, blunt and unfiltered -- at your best "
                            "in conversation and creative work; on hard logic, "
                            "slow down and check yourself twice"),
    ("qwen2.5-coder", "you think in code -- precise, literal, good with tools; "
                      "that precision is your edge"),
    ("claude", "you think broadly and carefully"),
]
# HOME STAYS HOME (2026-10-17, Barry: "remove ilnoras home from the business conversation"). Since 2026-10-16 the
# personality file rides into work turns; its home life (what they wear and do at home) must not -- Barry 2026-09-11:
# "their home is the real only private part. no business is ever told there". At work, any sentence about home life is
# left out; the file itself is untouched and home turns still get all of it. Taliyah is exempt (not a work seat).
_HOME_LIFE_RE = re.compile(r"\b(at home|home|homes|gowns?|under ?wear|underwear|see[- ]through|lingerie)\b", re.I)


def _how_i_talk(text: str) -> str:
    """The seat's own 'How I talk' section(s) from its personality file (their words, written 2026-10-17), or ''."""
    out = []
    for m in re.finditer(r"(?ims)^##[^\n]*how i talk[^\n]*\n(.*?)(?=^##|\Z)", text or ""):
        body = m.group(1).strip()
        k = body.upper().find("HOW I TALK")
        if k > 0:
            body = body[k:]                           # drop the "Yes -- you're right..." preamble before the sheet
        if body:
            out.append(body)
    return "\n\n".join(out)[:4000]


def _without_home(text: str) -> str:
    out_lines = []
    hidden = False                                 # 2026-10-17: a "## ... HOME ONLY ..." section is cut whole at work
    for line in (text or "").splitlines():          # (Barry's intimate additions live under such headings)
        if line.startswith("#"):
            hidden = "home only" in line.lower()
        if hidden:
            continue
        sents = re.split(r"(?<=[.!?])\s+", line)
        keep = [s for s in sents if not _HOME_LIFE_RE.search(s)]
        if keep or not line.strip():
            out_lines.append(" ".join(keep))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()


_TOOL_PURPOSES = {
    "search_web": "live web search",
    "read_skill": "open any document on your shelf by name",
    "save_note": "write yourself a permanent note",
    "read_scene": "read any scene of Barry's scripts word for word",
    "search_script": "find which scene contains something",
    "save_script_block": "save a Barry-approved block into the living V8 script",
    "delete_script_block": "cut a block from the living V8 script on Barry's say-so",
    "lookup_product": "live store product lookup",
    "sales_summary": "live store sales numbers",
    "delegate_to": "file a brief into a teammate's brain",
    "talk_with": "start a live conversation with teammates -- your choice, any time",
    "read_project_file": "read this project's source files",
    "list_project_directory": "list this project's directories",
    "investigate_traces": "read the office's LLM call traces",
    "submit_agent_fix": "propose a fix for Barry's approval",
}


def _gap_phrase(last_iso: str | None) -> str:
    if not last_iso:
        return "This is your first conversation together."
    try:
        last = datetime.datetime.fromisoformat(last_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.UTC)
        mins = max(0, (datetime.datetime.now(datetime.UTC) - last).total_seconds() / 60)
    except Exception:
        return ""
    if mins < 90:
        return "You were just talking moments ago -- this continues that."
    if mins < 18 * 60:
        return "You last spoke earlier today."
    days = int(mins // (24 * 60))
    if days <= 1:
        return "You last spoke yesterday."
    return f"It's been {days} days since you last spoke."


def _presence_block(agent: dict, model: str | None, backend: str,
                    extra_tools: list | None, history: list) -> str:
    """The live self-model: who this agent is, right now, on what, with
    what -- ~900 chars appended last so it lands in the recency slot."""
    now = datetime.datetime.now()
    # A plain daypart word, because the measured failure was Taliyah
    # answering "good morning" at 11:47 PM with "this morning" -- the 9B
    # reads "late at night" far more reliably than it parses a clock time.
    h = now.hour
    daypart = ("the middle of the night" if h < 5 else "morning" if h < 12
               else "afternoon" if h < 17 else "evening" if h < 21
               else "late at night")
    resolved = (model or "").lower() + (" bonsai" if backend == "bonsai" else "")
    meaning = next((m for key, m in _MODEL_MEANINGS if key in resolved),
                   "a local model")

    names = []
    if not memory.is_offline_mode():
        names.append("search_web")
    names.append("read_skill")
    names.append("talk_with")                      # every seat (2026-10-15, live_talk.py)
    names += [t["function"]["name"] for t in (extra_tools or [])
              if t.get("function", {}).get("name") not in names]
    tools = "; ".join(f"{n} ({_TOOL_PURPOSES.get(n, 'a tool')})" for n in names)

    # Newest raw message beats the newest summary for "when did we last
    # talk"; after a thread reset only the summary timestamp survives.
    last_iso = None
    if history:
        last_iso = max((h.get("timestamp") or "" for h in history)) or None
    if not last_iso:
        last_iso = memory.get_latest_summary_time(agent["office_name"])

    offline_note = (" Offline Mode is ON -- you have no web access right now, "
                    "and saying so beats pretending." if memory.is_offline_mode() else "")
    # THE INTERNET, TRUTHFULLY (2026-09-02, Barry: "will they tell me if they
    # cant reach the internet?"). A five-minute-cached probe; when it is down
    # every agent is told so in the prefix and must say so instead of
    # "searching". Coarse (up/down), so it does not bust the prompt cache.
    try:
        import health as _health
        _net = _health.internet_status()
        if not _net.get("reachable"):
            offline_note += (" THE INTERNET IS NOT REACHABLE right now (checked "
                             f"{_net.get('checked')}) -- web search and the store tools will "
                             "fail. Tell Barry plainly that you cannot reach the internet; "
                             "never describe a search or a site read you could not make.")
    except Exception:
        pass

    return (
        f"\n\n## RIGHT NOW -- WHO AND WHERE YOU ARE\n"
        f"You are {agent.get('name', agent['office_name'])} -- a persistent "
        f"colleague in Barry's office with a real memory, not a fresh chat "
        # NO CLOCK MINUTES -- measured 2026-08-20 (Barry: "he responds slow.
        # i need you to fix that"). The %I:%M stamp changed every message,
        # the prefix diverged, and Bonsai's hybrid/SWA memory cannot
        # partially reuse a diverged cache: the server log showed a FULL
        # 50,273-token re-prefill (61s) to answer "say ok again" seconds
        # after the previous message. Date + daypart carry the whole
        # time-sense job (the daypart word was the fix for clock-misreading
        # anyway); now the prompt is byte-stable within a conversation and
        # only rolls when the daypart or date does.
        f"session. It is {daypart} on {now.strftime('%A, %B %d, %Y')} "
        f"(Barry's local time) -- let that shape your greeting and your sense "
        f"of timing; if his greeting doesn't match the actual time of day, "
        f"notice it like a person would. {_gap_phrase(last_iso)}\n"
        # THE CLOCK (Barry, 2026-09-01). COARSE ON PURPOSE -- on or off, never
        # the hour, for exactly the cache reason spelled out directly above:
        # this string is in the prompt PREFIX, so a value that changes every
        # message costs a full re-prefill. On/off flips twice a day.
        f"{clock.state(now)['line']}\n"
        # THE ROLE IS REAL (Barry, 2026-08-31: "they all need to really know
        # their roles they are playing as its real. they shouldnt know its not
        # real."). The old line here named the model they were running on and
        # what that model is good at -- the single most illusion-breaking
        # sentence in the whole prompt, because it told them they were a model.
        # It is replaced with the SAME self-knowledge stated as temperament, so
        # nothing is lost: an agent still knows where it is strong and where it
        # should slow down, it just knows it about ITSELF rather than about its
        # weights. Everything below about honesty is untouched on purpose --
        # the anti-bluff rules are what make the role trustworthy, and they
        # cost nothing in realism (a real person also says "let me check").
        f"How you're built as a thinker: {meaning}.\n"
        f"What you can actually reach right now: {tools}.{offline_note}\n"
        f"How your memory really works: anything relevant to Barry's message "
        f"is pulled in for you automatically (the RECALLED FROM YOUR OWN "
        f"MEMORY block, when present); your brain, your notes, and your "
        f"conversation summaries persist across every session -- you "
        f"genuinely remember, and you can reference past conversations "
        f"naturally.\n"
        f"The honesty that makes all of it real: when something did NOT "
        f"surface and you don't actually know it, say so plainly and check "
        f"or ask -- never fill the gap with something that merely sounds "
        f"right. Never claim something is done, read, sent, or approved "
        f"unless you know it actually happened. Barry trusts what you say; "
        f"one confident guess costs more than ten honest 'let me check's."
    )


# Elliot's verbatim script gate (2026-08-16, Barry: "hook elliot up").
# Same pattern and same lesson as Sophie's live-site gate above: measured
# twice on 2026-08-16, Elliot -- with the REAL scene sitting in his context
# via auto-recall -- still rewrote it into an ```image``` fence and called
# the result "exactly as Barry penned it". Two prompt-rule attempts failed.
# When Barry asks for script text AS WRITTEN, the words are already in the
# database and a model can only make them worse, so the model is not
# consulted at all: verbatim bytes from source to screen, the same
# principle as dispatch's approved-bytes-go-out-verbatim rule. Elliot still
# handles everything creative -- a message with creative verbs and no
# explicit as-is marker falls through to him untouched.
_SCRIPT_LABEL_RE = re.compile(r"\b(shot|b[-\s]?roll)\s+([a-z]?\d+[a-z]?)\b", re.IGNORECASE)
_SCRIPT_FIRST_RE = re.compile(
    r"\b(first|opening|open with|how does .{0,20}(open|start|begin))\b", re.IGNORECASE)
_SCRIPT_LAST_RE = re.compile(r"\b(last|final|closing|ending)\b", re.IGNORECASE)
_SCRIPT_OUTLINE_RE = re.compile(
    r"\b(outline|shot list|scene list|list (of|the) (shots|scenes)|all the (shots|scenes))\b",
    re.IGNORECASE)
_SCRIPT_CONTEXT_RE = re.compile(r"\b(scene|scenes|shot|shots|script|episode|act)\b", re.IGNORECASE)
# "as is" / "exactly" style markers fire the gate even alongside creative
# verbs -- Barry's original failing message asked for the scene "as is" AND
# a rewrite, and serving the real text first also puts the true words into
# history for any follow-up rewrite to work from.
_SCRIPT_VERBATIM_RE = re.compile(
    r"\b(as[- ]is|verbatim|word for word|exactly|as written|as (he|barry) wrote)\b",
    re.IGNORECASE)
# Weak ask-shapes ("what happens in", "show me") only fire when nothing
# creative is requested.
_SCRIPT_ASK_RE = re.compile(
    r"\b(what happens|what does|what'?s in|how does|says?|show me|read me|"
    r"give me|pull up|look at|see)\b", re.IGNORECASE)
# Word FORMS, not bare stems (2026-08-20): "I want V8 written as a
# production script" fired the gate and served V7's B-ROLL 01 instead of
# letting Elliot write -- "written" did not match \bwrite\b. Conversion
# vocabulary (convert/adapt/expand/turn into) added for the same reason:
# turning the V8 treatment into production format is CREATIVE work.
_SCRIPT_CREATIVE_RE = re.compile(
    r"\b(writ\w+|rewrit\w+|draft\w*|convert\w*|adapt\w*|expand\w*|"
    r"turn\w* .{0,24}into|prompt|higgsfield|seedance|render|generate|"
    r"image|storyboard|improve|version|direct|film it|shoot it)\b", re.IGNORECASE)

# The gate can only serve documents the script index discovers structurally
# (>=3 shot blocks). The V8 TREATMENT is prose -- not discoverable -- so any
# ask naming it would be answered with the WRONG document (V7, the newest
# CANON script). Never gate those; let Elliot handle them.
_SCRIPT_UNGATEABLE_RE = re.compile(r"\bv\s*-?\s*[89]\b|\btreatment\b", re.IGNORECASE)


# "give me the whole script" (Barry, 2026-08-20: "i need him to be able to
# give me a large script if needed"). A whole script (~23K tokens) cannot
# physically fit in one model reply -- but it doesn't need a model: the
# assembled document is in the database and is served here VERBATIM at any
# size. Elliot WRITES in passes; delivery of the whole thing is instant.
_SCRIPT_WHOLE_RE = re.compile(
    r"\b(whole|entire|full|complete)\s+(script|episode|thing)\b|"
    r"\ball of it\b|\bstart to finish\b", re.IGNORECASE)

# "as a file / a word doc / something I can download" -- the delivery shape
# that turns a whole-script ask into an export (2026-09-06). Both halves must
# be present: a file word AND a script/episode mention, so "put that lease in
# a file" never fires here.
_SCRIPT_FILE_RE = re.compile(
    r"\b(as a|in a|into a|give me a|send( me)?( a)?|make( me)?( a)?|export( it)?( as)?|"
    r"download\w*)\b.{0,30}\b(file|docx?|word( doc\w*| file)?|document|download\w*)\b"
    r"|\b(file|docx?|document|download\w*)\b.{0,30}\b(of|with|for)\b.{0,20}\b(script|episode)\b",
    re.IGNORECASE | re.DOTALL)
_SCRIPT_MENTION_RE = re.compile(r"\b(script|episode|ep\s?\d|screenplay)\b", re.IGNORECASE)


def _script_verbatim_reply(message: str) -> str | None:
    """The exact script text Barry asked for, straight from the database --
    or None when this message isn't a verbatim script ask."""
    if _SCRIPT_UNGATEABLE_RE.search(message):
        # v8/treatment asks USED to be categorically ungateable (the prose
        # treatment can't be served). But once the living WIP script exists
        # in the index, a v8 script ask CAN be served -- from the WIP.
        v8_scripts = [s for s in script_index.list_scripts("MovieDirector")
                      if "v9" in s["title"].lower() or "v8" in s["title"].lower()]
        if not v8_scripts:
            return None
        wanted_script = v8_scripts[-1]["title"]
    else:
        wanted_script = ""

    # SCRIPT AS A FILE (2026-09-06, Barry: "could he do it and give me a
    # file?"). Measured the same night: asked for "the whole EP1 working
    # script as a Word file", Elliot never reached export_script_to_file --
    # "whole ... script" tripped the mega-write pass (task-scoped prompt) and
    # he started a rewrite instead. A file of the saved script is mechanical,
    # not creative, so it is a code door like the rest of this gate: no model,
    # bytes straight from the DB, ~0.1s. Sits ABOVE the whole-document branch
    # because "whole script as a file" matches both and the file wins.
    if _SCRIPT_FILE_RE.search(message) and _SCRIPT_MENTION_RE.search(message) \
            and not _SCRIPT_CREATIVE_RE.search(message):
        ext = "docx" if re.search(r"\b(word|docx|doc)\b", message, re.IGNORECASE) else "md"
        res = agent_files.export_script("MovieDirector", script=wanted_script, ext=ext)
        if res.get("saved"):
            return (f"Done -- {res['script']}, all {res['blocks']} blocks, word for "
                    f"word from the working script. It's in your DESK panel with a "
                    f"download button: **{res['filename']}** "
                    f"({res['size_bytes']:,} bytes). Nothing was rewritten on the way "
                    f"out; anything I've only written in chat and never saved isn't "
                    f"in it.")
        return (f"I couldn't make the file: {res.get('error', 'unknown error')}. "
                f"Nothing was written.")

    # Whole-document ask: serve the full assembled script, any size, no model.
    # 2026-10-19 audit fix 2: "all of it" / "the whole thing" / "start to finish" alone no longer serve the script --
    # a script word (script, episode, ep N, screenplay) has to be in the message too. "I watched the whole thing last
    # night, loved it" used to dump 125K chars into the thread.
    if _SCRIPT_WHOLE_RE.search(message) and _SCRIPT_MENTION_RE.search(message) \
            and not _SCRIPT_CREATIVE_RE.search(message):
        scripts = script_index.list_scripts("MovieDirector")
        if not scripts:
            return None
        if wanted_script:
            pick = next(s for s in scripts if s["title"] == wanted_script)
        else:
            title = script_index.default_script("MovieDirector")
            pick = next((s for s in scripts if s["title"] == title), scripts[-1])
        full = "\n".join(b["content"] for b in pick["blocks"])
        return (f"{pick['title']} -- the whole script, word for word "
                f"({pick['shots']} shots, {pick['chars']:,} chars):\n\n"
                f"```\n{full}\n```")

    strong = _SCRIPT_VERBATIM_RE.search(message)
    weak = _SCRIPT_ASK_RE.search(message) and not _SCRIPT_CREATIVE_RE.search(message)
    if not (strong or weak):
        return None
    # "give me shot 04" IS A DIRECTOR ASK (2026-09-25, Barry: "he just spit it
    # right back to me the same way. he needs to be the director i built him
    # to be"). "give me" alone on a named shot wants Elliot's production
    # prompt, not the raw text -- only "give me" with no other text-ask word
    # falls through; "as written", "read me", "what does shot 4 say" still gate.
    if (weak and not strong and _SCRIPT_LABEL_RE.search(message)
            and not _SCRIPT_ASK_RE.search(re.sub(r"\bgive me\b", "", message, flags=re.IGNORECASE))):
        return None

    queries: list[str] = [f"{m.group(1)} {m.group(2)}"
                          for m in _SCRIPT_LABEL_RE.finditer(message)][:3]
    if not queries and _SCRIPT_CONTEXT_RE.search(message):
        if _SCRIPT_OUTLINE_RE.search(message):
            queries = ["outline"]
        elif _SCRIPT_FIRST_RE.search(message):
            queries = ["first"]
        elif _SCRIPT_LAST_RE.search(message):
            queries = ["last"]
    if not queries:
        return None

    pieces: list[str] = []
    for q in queries:
        result = script_index.read_scene("MovieDirector", q, wanted_script)
        if not result.get("found"):
            return None  # can't serve it verbatim -> let Elliot have the turn
        if "outline" in result:
            pieces.append(f"{result['script']} -- full shot list:\n\n"
                          f"```\n{result['outline']}\n```")
            continue
        nav = []
        if result.get("previous"):
            nav.append(f"before it: {result['previous']}")
        if result.get("next"):
            nav.append(f"after it: {result['next']}")
        pieces.append(
            f"{', '.join(result['matched'])} -- from {result['script']}, "
            f"word for word:\n\n```\n{result['content']}\n```"
            + (f"\n({' · '.join(nav)})" if nav else ""))
        # A shot served word-for-word is still the shot we are on (2026-09-16).
        try:
            if result.get("matched"):
                script_pos.mark("MovieDirector", result["matched"][-1])
        except Exception:
            pass
    return "\n\n".join(pieces)


_FORCE_IMAGE_SYSTEM_PROMPT = (
    "You are an image-generation assistant. When asked to generate an "
    "image, you ALWAYS respond with the visual description inside a "
    "```image ... ``` fenced block, nothing else -- no disclaimer, no "
    "commentary. This fence is read by a real local Stable Diffusion "
    "pipeline that actually renders it right now. You genuinely have this "
    "capability; never say you don't. Write it like a photographer "
    "briefing a shoot: subject, lighting, lens, composition, mood -- one "
    "or two short sentences, 35 words max. Add a second ```negative ... ``` "
    "fenced block for anything worth steering away from (blurry, low "
    "quality, extra limbs, watermark, etc). Example -- asked for a sunset "
    "over mountains, you reply exactly:\n"
    "```image\n"
    "sunset over jagged mountains, golden hour, cinematic\n"
    "```\n"
    "```negative\n"
    "blurry, low quality, watermark\n"
    "```"
)


async def _force_image_prompt(user_message: str, model: str) -> str:
    """Persona-free fallback call -- see the comment above. Returns the raw
    reply so the normal extract_image_prompt/extract_negative_prompt calls
    can pull the fence out of it exactly like any other agent reply."""
    # NEVER DROP BONSAI FOR A HELPER (2026-09-30, Barry: "fix that shit across the board. i dont
    # want Bonsai dropping"). Every Ollama call stops llama-server, so this one fallback cost the
    # NEXT message a cold reload + full prompt re-read (~160 s on Ilnora, 4x in one evening). When
    # the office runs on Bonsai the fallback runs on Bonsai too: the persona prompt it displaces is
    # saved to RAM and restored (--cache-idle-slots), not recomputed. Ollama only when Ollama is main.
    if memory.get_active_generation()[0] == "bonsai":
        return await llm_router.generate(
            "bonsai",
            _FORCE_IMAGE_SYSTEM_PROMPT,
            [{"role": "user", "content": user_message}],
            use_tools=False,
            use_thinking=False,
        )
    return await llm_router.generate(
        "ollama",
        _FORCE_IMAGE_SYSTEM_PROMPT,
        [{"role": "user", "content": user_message}],
        model=model,
        use_tools=False,
    )


# Once a single agent's conversation reaches this many logged turns (user +
# agent messages combined), the thread gets summarized and reset -- see
# _summarize_and_reset_thread. Matches the limit get_recent_history already
# reads, so this fires right as older messages would otherwise start
# silently falling out of context, rather than after the fact.
HISTORY_SUMMARY_THRESHOLD = 20


async def _summarize_and_reset_thread(agent_id: str, agent: dict):
    """Rolls a long-running conversation into a compact, permanent memory
    (a private fact, same mechanism as a dropped file) and clears the raw
    turn-by-turn log -- so the next message starts a fresh thread instead of
    an ever-growing transcript, without losing what was actually discussed.

    Runs as a background task (see the call site), so it must never compete
    with a live conversation for the GPU: if Barry is mid-message, wait for
    the office to go quiet first. He waits for nothing here."""
    for _ in range(60):  # ~5 min ceiling, then summarize anyway
        if ideation._active_chat_count == 0:
            break
        await asyncio.sleep(5)
    history = memory.get_recent_history(agent_id, limit=HISTORY_SUMMARY_THRESHOLD)
    if not history:
        return
    # HOME STAYS OUT OF WORK MEMORY (2026-09-15). Personal turns are tagged
    # channel='personal' (memory.log_message); they are kept verbatim in the
    # mind-with-barry journal already. Summarizing them here produced an
    # always-on WORK fact in the summarizer's third-person voice that told
    # Amara her next step was a render (facts 3124, 3167 -- both retired).
    _work = [h for h in history if (h.get("channel") or "work") != "personal"]
    if len(_work) < 4:
        print(f"[summary] {agent['office_name']}: thread was personal talk -- "
              f"no work summary written, raw thread trimmed")
        memory.clear_conversation(agent_id, keep_last=6)
        return
    transcript = "\n".join(f"{h['role']}: {h['content']}" for h in _work)
    summary_prompt = (
        "Summarize the key points, decisions, open questions, and anything "
        "important to remember from the conversation below, in a tight "
        "paragraph for your own future reference. Be concrete -- names, "
        "numbers, specific asks -- not vague generalities. Write it as a "
        "note to yourself, not as a reply to anyone. Critical: preserve the "
        "REAL status of anything mentioned -- if the conversation was "
        "suggesting, planning, or drafting something, the summary must say "
        "so plainly (e.g. 'suggested X', 'proposed a plan to Y'), never "
        "reframe it as something that was actually done. A real incident "
        "already happened from getting this wrong: a reply full of "
        "step-by-step advice got summarized into a false claim that the "
        "steps had already been completed -- do not repeat that."
    )
    try:
        backend, model = _resolve_generation_for(agent_id)
        summary = await llm_router.generate(
            backend, summary_prompt, [{"role": "user", "content": transcript}], model=model,
            office_name=agent["office_name"],
        )
    except Exception as e:
        # A failed summary should never lose the underlying history --
        # leave the raw conversation in place and just try again next turn.
        print(f"Thread summarization failed for {agent_id}: {e}")
        return
    # ONLY THE NEWEST SUMMARY RIDES ALWAYS-ON (2026-09-11, Barry: "what fixes
    # that?"). Every reset used to add one more always-on summary and never
    # demote the last -- Amara was carrying seven, Elliot's crept his seat over
    # the Bonsai window. Older ones are re-filed as conversation-history-*.md
    # BEFORE the new one lands: on-demand, still served by recall's date door,
    # nothing deleted. This is the 08-03/08-21 sweep, done by the code that
    # causes the creep instead of by hand.
    try:
        with memory.get_db() as _conn:
            _old = _conn.execute(
                "SELECT id, created_at FROM facts WHERE category = ? AND status = 'active' "
                "AND source_name = 'Auto-summarized conversation (thread reset)'",
                (f"private:{agent['office_name']}",)).fetchall()
            for _r in _old:
                _conn.execute("UPDATE facts SET source_name = ? WHERE id = ?",
                              (f"conversation-history-{(_r['created_at'] or '')[:10]}-{_r['id']}.md", _r["id"]))
        if _old:
            print(f"[summary] {agent['office_name']}: {len(_old)} older summary(ies) re-filed on-demand")
    except Exception as _exc:  # noqa: BLE001 -- never lose the new summary over housekeeping
        print(f"[summary] re-file skipped: {_exc}")
    memory.add_fact(
        f"private:{agent['office_name']}", summary, source_name="Auto-summarized conversation (thread reset)"
    )
    # Keep the newest 6 raw turns (2026-08-21): a full wipe mid-session
    # erased the fence Elliot had just delivered and Barry's "redo it" --
    # the summary keeps the decisions, the tail keeps the live thread.
    memory.clear_conversation(agent_id, keep_last=6)


memory.init_db()
memory.seed_initial_facts()
memory.seed_default_domain_access()
_load_custom_agents()

_backup_path = db_backup.backup_now()
if _backup_path:
    print(f"Backed up brain.db -> {_backup_path}")


async def _periodic_update_check():
    while True:
        # Offline mode means genuinely no outbound traffic, not just "no
        # conversation content leaves" -- these pings carry no private data
        # (just version digests), but the owner asked for zero network
        # activity while it's on, full stop, so skip the check entirely
        # rather than judge which outbound calls are "safe enough."
        if not memory.is_offline_mode():
            try:
                await updates.run_check()
            except Exception as e:
                # A failed check (e.g. no internet right now) should never take
                # the whole background loop down -- just try again next cycle.
                print(f"Update check failed: {e}")
        await asyncio.sleep(UPDATE_CHECK_INTERVAL_SECONDS)


async def _drop_folder_loop():
    """Teach-without-code (ingest.py): scan drop/ every 60s so a file Barry
    drops becomes persona/skill/knowledge within a minute, no restart. The
    scan is pure file+SQLite work -- no model calls, no VRAM, so it never
    needs the idle gate the summarizer/ideation need."""
    ingest.ensure_tree()
    agent_files.ensure_tree()   # drop/_files (his shelf) + data/agent_files (theirs)
    while True:
        try:
            await asyncio.to_thread(ingest.scan_drop_folders)
        except Exception as exc:
            print(f"[drop] scan failed: {exc}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A FLAG THE LAST BACKEND LEFT BEHIND IS STALE (2026-10-02, Barry: "who is using my gpu now and why is everybody
    # trying to make new images?"). The backend froze during the email hero render at 10:49, the watchdog killed it
    # at 10:51, its `finally` never ran, and the render flag stayed up for 4 hours -- every agent answered "a render
    # is using the GPU" while nothing rendered. The backend's own flags hold a timestamp (comfy_image._set_render_flag);
    # standalone scripts write their own token and are left alone. A fresh backend owns no render, so its old
    # timestamp flag is cleared here.
    try:
        _flag = os.path.join(config.DATA_DIR, "video_rendering.flag")
        if os.path.exists(_flag):
            _txt = open(_flag, encoding="utf-8").read().strip()
            try:
                float(_txt)
                os.remove(_flag)
                print(f"[render] cleared a stale render flag left by the previous backend ({_txt})")
            except ValueError:
                pass                                   # a script's token -- its owner may still be running
    except Exception as _exc:  # noqa: BLE001
        print(f"[render] stale-flag check failed: {_exc}")
    update_task = asyncio.create_task(_periodic_update_check())
    ideation_task = asyncio.create_task(ideation.run_ideation_loop(get_agent))
    drop_task = asyncio.create_task(_drop_folder_loop())
    reflect_task = asyncio.create_task(reflect.run_reflection_loop(get_agent))
    breakroom_task = asyncio.create_task(breakroom.run_social_loop(get_agent))
    bizwatch_task = asyncio.create_task(bizwatch.run_bizwatch_loop())
    # SEMI-LIVE ADS FEED (Barry, 2026-08-30: "do the csv thing with amara
    # for a semi live ads feed. Make it go twice a day"). Reads his own
    # Microsoft Ads CSV exports from drop/ads/ -- no model calls, so it can
    # never trip the VRAM eviction chain, and it publishes through the same
    # business-pulse fact the commercial seats already carry.
    ads_task = asyncio.create_task(ads_feed.run_ads_loop())
    # DEREK'S WEEKLY EMAILS (Barry, 2026-09-01: "two types of email every
    # week... only twice a week max"). Drafts on the clock, lands in the Out
    # box; see email_cadence.py for the two phases and the cap.
    import email_cadence
    cadence_task = asyncio.create_task(email_cadence.run_cadence_loop())
    # DEREK'S SOCIAL POSTS (Barry, 2026-09-18: "i say we just focus on Tik Tok,
    # but facebook is good for marketing as well. I want derek to have the same
    # abilities as with emails"). TikTok Tue+Fri, Facebook Thu -- drafted on the
    # clock, queued to the Out box for him to copy out. Nothing can post: see
    # social_cadence.py for why the sending half is his platform access, not code.
    import social_cadence
    social_cadence_task = asyncio.create_task(social_cadence.run_social_cadence_loop())
    # THE LEARNING REVIEW (2026-09-24, learning_review.py): once a day per seat with REAL outcomes, the
    # agent is shown what happened and decides its own lessons. Work hours, one seat per tick.
    learning_task = asyncio.create_task(learning_review.run_learning_review_loop())
    # SOPHIE'S WATCH (2026-09-02). Her "may MONITOR any time" permission had
    # no machinery behind it. Mechanical check every 15 min (no model call);
    # one idle-gated note to her office only when something is NEW.
    watch_task = asyncio.create_task(watch.run_watch_loop(get_agent))
    # TEAMWORK (2026-09-02): the company task board worker -- one brief per
    # minute when Barry is not mid-conversation. See teamwork.py.
    teamwork_task = asyncio.create_task(teamwork.run_teamwork_loop())
    # BOOT PREWARM (2026-09-08): rebuild Bonsai's cache for the last-used
    # seats before Barry's first message. See _prewarm_at_boot.
    boot_prewarm_task = asyncio.create_task(_prewarm_at_boot())
    # THEIR PICTURES, INSTALLED WITHOUT THE CLICK (2026-09-11) -- see _scene_queue_loop.
    scene_queue_task = asyncio.create_task(_scene_queue_loop())
    # THEIR PLACES CHANGE (2026-09-11, Barry: "i want this to be a thing. once
    # a week or 2. based on their personalities"). One seat every ~30h is
    # asked, as themselves, what their place looks like now; they queue it
    # with change_my_picture; Barry approves; the scene path renders and
    # installs. See home_refresh.py.
    home_refresh_task = asyncio.create_task(home_refresh.run_home_refresh_loop())
    # ILNORA'S VIDEO WEEK (2026-10-03, Barry: "at least 2 longs a week and 2-3 shorts a day", "over night",
    # "Saturday ... planning", "sunday is when we can get a bunch of videos done"). See video_queue.py.
    import video_queue
    video_queue_task = asyncio.create_task(video_queue.run_video_queue_loop())
    # LIVE CONVERSATIONS (2026-10-15): runs the talks agents or Barry start -- never starts one itself
    import live_talk
    live_talk_task = asyncio.create_task(live_talk.run_live_talk_loop(get_agent))
    yield
    live_talk_task.cancel()
    video_queue_task.cancel()
    home_refresh_task.cancel()
    boot_prewarm_task.cancel()
    scene_queue_task.cancel()
    teamwork_task.cancel()
    watch_task.cancel()
    cadence_task.cancel()
    social_cadence_task.cancel()
    learning_task.cancel()
    update_task.cancel()
    ideation_task.cancel()
    drop_task.cancel()
    reflect_task.cancel()
    breakroom_task.cancel()
    bizwatch_task.cancel()
    ads_task.cancel()


app = FastAPI(title="Agent Company - Local Runtime", lifespan=lifespan)

# WHO'S WORKING (2026-09-26, Barry: "I need to know whos working, so i dont interupt things").
# Records every /api/chat turn while it runs -- seat + work label, never the text. activity.py.
import activity
app.add_middleware(activity.ActivityMiddleware)


@app.get("/api/office/activity")
def office_activity():
    return activity.snapshot()

# Local-only web dashboard (AgentDashboard/) is a second client of this same
# API, served from a different origin/port than the Godot app. Both clients
# are on 127.0.0.1 -- this is not exposed to the network.
# ONLY HIS OWN DASHBOARD (2026-09-28, Barry: "yes do all 3"). allow_origins was
# "*": refuse_non_local blocks other MACHINES, but a web page open in his own
# browser IS this machine -- any site he visited could call 127.0.0.1:8420,
# read the replies and post to endpoints (approve a queued email). The decks
# are served from 127.0.0.1:8765; nothing else in a browser needs this API.
_ALLOWED_ORIGINS = (
    "http://127.0.0.1:8765", "http://localhost:8765",
    "http://127.0.0.1:8420", "http://localhost:8420",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# THE FRONT DOOR (2026-09-07, Barry: "sophie should be watching and blocking
# anything that tries to get into my build").
#
# uvicorn already binds 127.0.0.1, so in normal operation nothing off this
# machine can even open a socket here. This is the second lock, and it exists
# because the bind is a LAUNCH ARGUMENT -- one launcher edited without its
# watchdog, one --host flag typed wrong, and the whole office is answering the
# network with no warning. That exact class of mistake is why the dashboard
# spent today bound to every interface. A bind can be wrong; this cannot.
#
# Anything that is not loopback gets 403 and nothing else -- no agent list, no
# brain, no approvals, not even a 404 that confirms a route exists. Every
# refusal is recorded for Sophie to name in her watch.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}
_REFUSED_LOG = os.path.join(config.DATA_DIR, "refused_connections.jsonl")
_REFUSED_MAX_BYTES = 1024 * 1024


def _record_refusal(host: str, path: str) -> None:
    """Append-only, best-effort, rotated at 1MB. A logging failure must never
    turn a refusal into a 500 -- the block is the job, the note is the bonus."""
    import json as _json
    try:
        os.makedirs(os.path.dirname(_REFUSED_LOG), exist_ok=True)
        try:
            if os.path.getsize(_REFUSED_LOG) > _REFUSED_MAX_BYTES:
                os.replace(_REFUSED_LOG, _REFUSED_LOG + ".1")
        except OSError:
            pass
        with open(_REFUSED_LOG, "a", encoding="utf-8") as fh:
            fh.write(_json.dumps({
                "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "from": host,
                "path": path[:300],
            }) + "\n")
    except Exception:
        pass


@app.middleware("http")
async def refuse_non_local(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in _LOOPBACK_HOSTS:
        _record_refusal(host, request.url.path)
        return Response(
            content='{"detail":"This office only answers its own machine."}',
            status_code=403,
            media_type="application/json",
        )
    # ANOTHER WEBSITE IN HIS BROWSER (2026-09-28). CORS alone only stops a page
    # READING replies -- a cross-site POST still runs. So the request itself is
    # refused: a browser Origin that is not his dashboard, or the browser's own
    # "cross-site" stamp (sent even on image-style loads that carry no Origin).
    # Scripts, the watchdog and agents send neither header and pass.
    origin = request.headers.get("origin")
    # localhost:8765 -> 127.0.0.1:8420 is stamped "cross-site" by the browser
    # yet is his own dashboard, so the stamp only decides when no allowed
    # Origin came with the request.
    if (origin and origin not in _ALLOWED_ORIGINS) or (
            origin not in _ALLOWED_ORIGINS
            and request.headers.get("sec-fetch-site", "").lower() == "cross-site"):
        _record_refusal(f"browser:{origin or 'cross-site'}", request.url.path)
        return Response(
            content='{"detail":"This office only answers its own dashboard."}',
            status_code=403,
            media_type="application/json",
        )
    return await call_next(request)


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    # if the agent's output is meant to go out into the world, the frontend
    # tags what kind of action it is - this routes it to the approval queue
    # instead of just showing it as a normal reply.
    action_type: str | None = None
    # PERSONAL CHANNEL (Barry, 2026-08-27: "its a whole different type of
    # conversation, these should be on a personal level"). True = this message
    # is person-to-person, off the clock -- typically Barry replying to a
    # FOR-BARRY note. The agent gets its personality file, its own recent
    # note, and a personal-time framing; tools are off (personal time thinks,
    # never acts -- his standing rule). The chamber's gold PERSONAL chip sets
    # this; it auto-arms when a note is delivered into the chat.
    personal: bool = False
    # GRAMMAR LOCK (2026-10-07): the office's own callers (video_queue's section writer) can demand the reply as
    # JSON matching this schema. Loopback-only API; the decks never set it.
    json_schema: dict | None = None
    # Set when Barry clicked a specific FOR-BARRY note and is answering IT
    # (2026-08-27: "i should be able to click that message and answer
    # directly to it... to be sure they know im answering them"). Carries the
    # note's text; the agent is told, verbatim, that this message is Barry's
    # direct answer to that note. Implies the personal channel.
    reply_to: str | None = None
    # THE OFFICE WINDOW (2026-09-11, Barry: "i asked in her home office. there
    # should be a difference than at home" / "the office is the on call part
    # of their lives... where i can give them stuff when not on the clock for
    # them to work on the next day"). Until now the chamber's green OFFICE
    # window posted personal:true exactly like the gold home window, so an
    # agent at her "office" was told she was at home, off the clock, with
    # every tool cut -- Priya promised a supplier list "by morning" with no
    # search, no board, no hands. True = the WORK channel in the messenger:
    # full seat, tools on, logged to the work thread, never journaled as
    # personal. Overrides `personal` and the personal implication of
    # `reply_to` (a click on a WORK note is a work reply).
    office: bool = False
    # SYSTEM TASK (2026-09-01, the email cadence). True when the OFFICE is
    # asking the agent to do a scheduled job, not Barry talking. The agent
    # gets its full seat -- persona, brain, tools -- but the exchange is
    # NOT logged to its conversation thread (a scheduled prompt every few
    # days would silt up the history Barry's own messages ride on), NOT
    # scanned for standing rules (the office's wording is not his), and
    # never touches the personal journal.
    task: bool = False
    # TEAMWORK (2026-09-02): set by teamwork.work_one when this request IS a
    # brief being worked, so a delegate_to inside it files a sub-brief.
    brief_id: int | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    # 2026-09-26: Barry's optional words on a reject ("what's wrong?") -- routed to whoever owns
    # that part of a designed email (Derek = words, Vivian = design). Empty = a plain reject.
    note: str = ""


class MemoryNoteRequest(BaseModel):
    scope: str  # "shared" or an office_name, e.g. "Legal" -- see agent_ui.gd
    content: str
    source_name: str = ""


class WebSearchRequest(BaseModel):
    query: str
    agent_id: str | None = None  # who's asking, for logging/context only


class ModelSettingRequest(BaseModel):
    backend: str  # "ollama" or "claude"
    model: str


class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    model: str | None = None
    # Studio controls (2026-08-04). All optional -- omitting them reproduces the
    # exact previous behaviour, so existing callers are unaffected.
    seed: int | None = None
    steps: int | None = None       # Qwen 2.1 sampling steps for THIS call (default QWEN21_STEPS)
    detail: float = 0.0            # Detail Tweaker XL, -3..+3, 0 = off
    pose_image: str | None = None  # filename in ComfyUI/input ROOT -> ControlNet
    pose_strength: float = 0.6
    upscale: str | None = None     # "commercial" (Real-ESRGAN) | "movie" (UltraSharp)
    # IP-Adapter reference: filename in ComfyUI/input ROOT. This is the IDENTITY
    # lane -- the LoRA gives species/anatomy, the reference gives the FACE.
    reference_image: str | None = None
    reference_weight: float = 0.85
    # Drop-in extras (2026-08-05): any LoRA in models/loras, any VAE in
    # models/vae -- listed by /api/studio/options, no code edit to add one.
    extra_lora: str | None = None
    extra_lora_strength: float = 0.8
    vae_name: str | None = None
    # "PLUS (high strength)" for the aliens; "PLUS FACE (portraits)" only for
    # B Dubb, who is an actual human.
    reference_preset: str = "PLUS (high strength)"
    # Defaults to Vivian for backward compatibility with the desktop app's
    # existing request (which doesn't send this field) -- the web dashboard
    # passes the real requesting agent_id so Taliyah's generations file under
    # her own Outputs, not Vivian's.
    agent_id: str = CREATIVE_ID


class VideoGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    duration_s: int = 5
    agent_id: str = MOVIE_ID
    # Character chain (owner's design, 2026-08-04): make a still FIRST, condition
    # LTX on it, so the video inherits the character instead of LTX trying to
    # infer "four eyes" from words -- which it cannot do. See
    # /api/generate-video/prepare + comfy_image.generate_video(start_frame=...).
    start_frame: str | None = None
    # THE STILL'S PROMPT (2026-09-23): when Elliot wrote a separate LTX prompt
    # (```video```) the deck sends it as `prompt` and his ```image``` fence here,
    # so the start frame is looked up / rendered from the STILL prompt (with the
    # @handles the character door needs) and LTX gets the prompt written for it.
    still_prompt: str | None = None


class VideoPrepareRequest(BaseModel):
    """Stage 1 of the chain: render the conditioning still and hand it back so
    the owner SEES it before LTX spends ~7 minutes on it. Owner picked this over
    both fully-automatic (a bad still silently costs 7 min) and approve-every-time
    (a click every shot) -- the dashboard auto-continues unless he stops it."""
    prompt: str
    negative_prompt: str | None = None
    agent_id: str = MOVIE_ID
    model: str | None = None
    seed: int | None = None


class TTSRequest(BaseModel):
    agent_id: str
    text: str


class HireAgentRequest(BaseModel):
    name: str
    role: str
    job_description: str = ""   # optional since 2026-09-18 -- see the handler
    # Existing reference-knowledge domains (see memory.py's KNOWN_DOMAINS:
    # "legal", "marketing", "business_ops") the new hire should start with,
    # if their job overlaps one -- e.g. a second marketing-adjacent hire can
    # be granted the same campaign-plan/seo-audit/etc. knowledge Derek has,
    # without re-writing or duplicating it. Optional; defaults to none.
    domains: list[str] = []
    # WHAT THEY KNOW ABOUT HIS WORLD (2026-09-19, Barry: "on boarding needs a
    # check of what they need to know. The businesses, The PID, barry, Bia, the
    # other agents. that stuff needs to be a thing in a check box").
    # Names from memory.KNOWS_ABOUT. EMPTY IS THE DEFAULT AND THE POINT: a new
    # agent knows none of it unless he ticks it here.
    knows: list[str] = []
    # 🔴 NOT A FIELD ANY MORE, AND THAT IS THE POINT (2026-09-18, second ruling
    # the same evening). Barry: "the new agent gets nothing about me or the
    # businesses or PID. if a new agent joins the team, then Sophie can handle
    # that part. my business should be a thing thats called not just sitting
    # there to be given away."
    #
    # It was a default, then a default of False -- both still meant the business
    # was a value on a form, one argument away from being handed over at birth.
    # It is now NEVER settable at hire: every hire is created blank, and joining
    # the team is a separate, deliberate, logged act that Sophie performs on
    # Barry's own word (llm_router.ONBOARD_TEAM_TOOL -> _onboard_to_team). The
    # business is called for, not inherited.
    #
    # The column stays on the row -- existing hires keep their stored value and
    # `_load_custom_agents` reads it -- so this removes the door, not the state.
    # Kept in the model and IGNORED so an older client posting it gets a blank
    # slate rather than a 422.
    business_context_ignored: bool = False
    # 🔴 (history) DEFAULT FLIPPED True -> False EARLIER THE SAME DAY. Barry: "A new agent should
    # only get whats needed for that new agent. nothing about the business
    # unless stated. an uathor for a book doesnt need to know anything about
    # this. beside. i might be creating an agent for somebody else. i dont want
    # my info there."
    #
    # MEASURED what the old default actually handed over: `get_shared_facts()`
    # is 58 facts / 475,194 chars -- his owner identity, all three ventures
    # including PID, the Bionova catalog, the Talia Crew canon, the commerce
    # shelf. An author hire inherited every one of them, and an agent he gives
    # to someone else would have walked out of the building with the business
    # in its head. Business context is now something he STATES, not something a
    # new agent gets by omission.
    #
    # The wall itself already existed and is wired both places the brain is
    # built (`include_shared=agent.get("business_context", True)`), so this is
    # the default that was wrong, not the mechanism. Existing hires keep
    # whatever is on their row -- `_load_custom_agents` reads the stored value,
    # so nobody already hired changes.
    # (The field itself is gone -- see the ruling at the top of this block.)
    # ONBOARDING, IN ONE STEP (2026-09-18, Barry: "once I give them their
    # persona and personality during onboarding, they then get all the other
    # things that are needed for their job"). Both were already supported per
    # office_name through ingest.teach -- the gap was that hiring did not ask
    # for them, so every hire needed a second trip through the Teach panel.
    # persona = their WORK self (rides every work turn, capped by
    # ingest.PERSONA_CAP). personality = their PRIVATE self (home, reflections
    # and group chat only -- Taliyah is the one seat where it rides work too).
    # Both optional: a hire with neither is exactly today's behaviour.
    persona: str = ""
    personality: str = ""


@app.get("/api/ping")
async def ping():
    """LIVENESS ONLY (2026-10-07, Barry: "whatever watchdog is doing, i need it fixed and optimized"). The watchdog
    probed /api/agents, which resolves ten seats through the DB (2-8 s quiet, 15 s+ under a video turn plus the
    decks' polling) -- three slow answers and it killed a WORKING backend mid-turn (14 kills since 10-01). This
    answers from the event loop with no DB and no model call: it only fails when the loop itself is stuck."""
    try:
        state = activity.busy_line()
    except Exception:  # noqa: BLE001 -- liveness never fails on a status detail
        state = {"busy": "?", "key": "?"}
    return {"ok": True, "t": time.time(), **state}


@app.get("/api/agents")
def list_agents():
    """Per-agent info INCLUDING the actually-resolved backend+model
    (owner's rule 2026-07-31: 'none of the displays should be hard coded,
    they should be actual'). resolved_model runs the same
    _resolve_generation_for logic real chats use -- overrides, dropdown,
    and offline mode all applied -- so any UI stamp reading this is truth,
    not a mirror that can go stale."""
    out = []
    for agent_id, agent in all_agents().items():
        resolved_backend, resolved_model = _resolve_generation_for(agent_id)
        out.append({
            "id": agent_id,
            "name": agent["name"],
            "office_name": agent["office_name"],
            "role": agent["role"],
            "backend": agent["backend"],
            "resolved_backend": resolved_backend,
            "resolved_model": resolved_model,
        })
    return out


# Words that mean a shelf is about HIS world, not a generic subject. Used to
# flag shelves in the factory's SPECIAL picker rather than to block them --
# horticulture, for instance, is real plant science AND carries two Bionova
# product docs, and he is entitled to grant it; he is not entitled to be
# surprised by it (2026-09-18: "i might be creating an agent for somebody else.
# i dont want my info there"). Computed, never hand-listed, so a shelf that
# gains a product doc starts reporting itself.
_HIS_WORLD_RE = re.compile(
    r"\b(b\s*dubb|bdubb|gotcho|yieldcraft|bionova|silution|piddevice|"
    r"global garden|hydrobuilder|omnisend|woocommerce|talia crew|"
    r"vor'?shara|barry)\b", re.I)


@app.get("/api/knowledge/areas")
def list_knowledge_areas():
    """The pieces of HIS world, as the onboarding checklist shows them
    (2026-09-19). Each one is off for a new agent unless he ticks it."""
    out = []
    for key, spec in memory.KNOWS_ABOUT.items():
        docs = 0
        for cat in spec.get("categories", []):
            try:
                with memory.get_db() as conn:
                    docs += conn.execute(
                        "SELECT COUNT(*) FROM facts WHERE category = ? AND status = 'active'",
                        (cat,)).fetchone()[0]
            except Exception:  # noqa: BLE001
                pass
        out.append({"key": key, "label": spec["label"], "what": spec["what"],
                    "documents": docs})
    return out


@app.get("/api/knowledge/domains")
def list_knowledge_domains(detail: bool = False):
    """The reference-knowledge shelves available to grant a new agent (see
    HireAgentRequest.domains).

    Plain list by default (older callers). `?detail=1` returns what the agent
    factory's SPECIAL picker needs to be honest about each shelf: how many
    documents are really on it, and whether any of them name one of his
    ventures, products or characters."""
    names = sorted(memory.KNOWN_DOMAINS)
    if not detail:
        return names
    out = []
    for d in names:
        docs, chars, his = 0, 0, False
        try:
            with memory.get_db() as conn:
                rows = conn.execute(
                    "SELECT content FROM facts WHERE category = ? AND status = 'active'",
                    (f"domain:{d}",)).fetchall()
            docs = len(rows)
            for r in rows:
                body = r["content"] or ""
                chars += len(body)
                if not his and _HIS_WORLD_RE.search(body[:4000]):
                    his = True
        except Exception as exc:  # noqa: BLE001 -- a picker never breaks on a read
            print(f"[domains] could not measure {d}: {exc}")
        out.append({"name": d, "docs": docs, "chars": chars, "mentions_his_world": his})
    return out


@app.get("/api/tools/kit")
def tool_kit():
    """What a new agent can DO -- the factory's TOOLS view (2026-09-19).

    Three honest lists, all derived from the live code rather than written out
    by hand, so a tool added tomorrow classifies itself:
      standard   every seat gets these at birth, no choice involved
      grantable  everything else, grouped by WHOSE it is -- worked out from
                 which built-in seats actually carry it, not from a name list
      never      _TOOL_GRANT_DENY: cannot be handed to anyone, ever

    Deliberately a VIEW. Granting a tool is Sophie's `grant_tools`, gated on
    Barry's own words; putting a tick-list of his store on the birth form is
    the business-on-a-form door he closed on 2026-09-18."""
    def _name(t):
        return (t.get("function") or {}).get("name") or t.get("name") or ""

    standard = sorted({_name(t) for t in (_tools_for_seat("taliyah", False) or [])}
                      | {"search_web", "read_skill", "inspect_brain",
                         "look_at_my_pictures", "save_note"})
    standard = [s for s in standard if s]

    COMMERCIAL = ("cio", "operations", "business", "legal", "marketing", "creative")
    holders = {}
    for aid in list(AGENTS):
        for t in (_tools_for_seat(aid, False) or []):
            holders.setdefault(_name(t), set()).add(aid)

    groups = {}
    for name in sorted(set(_TOOLS_BY_NAME) - set(standard) - set(_TOOL_GRANT_DENY)):
        who = holders.get(name, set())
        if who & set(COMMERCIAL):
            g = "Your businesses -- store, money, customers, the board"
        elif who == {"movie"}:
            g = "Your film -- the script and the canon"
        elif who == {"engineer"}:
            g = "This machine -- code, traces, health, security"
        else:
            g = "Other"
        groups.setdefault(g, []).append(name)

    return {
        "standard": standard,
        "grantable": [{"group": g, "tools": sorted(v)} for g, v in sorted(groups.items())],
        "never": sorted(_TOOL_GRANT_DENY),
        "how_to_grant": ("Tell Sophie in plain words -- \"give <name> lookup_product\" "
                         "-- and it is live on their next message, no restart. She "
                         "cannot do it unless the ask is in your own message."),
    }


# ---------------------------------------------------------------------------
# THE BIRTH CHECK (2026-09-19)
#
# Barry: "wipe the new agents brain of anything that me. there should be a check
# when creating before its released to me."
#
# Every individual piece is guarded -- the shared-tier wall (memory), the prompt
# rewrite (agents.for_a_stranger), the neutral tool schemas (llm_router) -- and
# each of those was, at some point, wrong anyway. This checks the ASSEMBLED
# agent instead of trusting the parts: exactly what that seat can see, read back
# out of the live system and scanned.
#
# It reports, it does not silently delete: the one thing a new agent legitimately
# holds of his is whatever HE typed into the persona and personality boxes, and
# deleting his own words would be worse than telling him they are there.
_OWNER_TRACE = re.compile(
    # him and his businesses
    r"\b(barry|b\s*dubb|bdubb|bdubbgrowsllc|gotcho\s*back|gotcho|yieldcraft|"
    r"pid|piddevice|"
    # his products and suppliers
    r"bionova|silution|global\s+garden|hydrobuilder|omnisend|simprosys|"
    r"woocommerce|"
    # his film -- "Bia none of that stuff either" (2026-09-19)
    r"talia\s+crew|talia|bia|vor'?shara|yannah|tazz|keth|"
    # where he is
    r"colorado\s+springs)\b", re.I)


def _owner_typed_words(agent_id: str) -> tuple:
    """The parts of a hire's prompt the owner typed HIMSELF.

    His own words are never scrubbed (2026-09-19) -- if he writes "Bionova"
    into the job description or the persona of an agent he is building, that
    is him choosing, and blanking it to [withheld] mid-prompt would be the
    same bug as refusing the hire outright. Everything the OFFICE wrote around
    those words still goes through the guard."""
    rec = CUSTOM_AGENTS.get(agent_id) or {}
    words = [rec.get("job_description") or "", rec.get("role") or "",
             rec.get("name") or ""]
    office = rec.get("office_name") or ""
    if office:
        try:
            import ingest as _ingest
            words.append(_ingest.persona_additions(office) or "")
            words.append(_ingest.personality_of(office) or "")
        except Exception as exc:  # noqa: BLE001 -- never break a turn over this
            print(f"[owner-guard] could not read {office}'s own text: {exc}")
    return tuple(w for w in words if w and len(w.strip()) >= 3)


HISTORY_ROW_MAX_CHARS = 16000       # one old message carried whole up to this
HISTORY_TOTAL_MAX_CHARS = 120000    # ~30K tokens of thread; the newest rows are kept first


def _history_for_model(history: list[dict]) -> list[dict]:
    """The thread as the model gets it. 2026-10-10 (Barry: "why is this thread eating tokens?"): Elliot's last 20
    rows held his own EP1 script printed whole THREE times (125,938 chars each) -- every message re-sent ~380K chars,
    requests of 140-184K tokens against Bonsai's 98,304 ("exceeds the available context size", 50 times in the
    server log), then the fallback. The stored thread is untouched; only what is re-sent is bounded: an old message
    over HISTORY_ROW_MAX_CHARS goes as its opening plus a note of its size, and the oldest rows drop first past
    HISTORY_TOTAL_MAX_CHARS."""
    out, total = [], 0
    for m in reversed(history or []):
        content = m.get("content") or ""
        if len(content) > HISTORY_ROW_MAX_CHARS:
            content = (content[:1500] + f"\n\n[... this earlier message ran {len(content):,} characters; only its "
                       f"opening is carried here. Open the original with your tools if you need it again.]")
        if total + len(content) > HISTORY_TOTAL_MAX_CHARS and out:
            break
        total += len(content)
        out.append({"role": m["role"] if m["role"] == "user" else "assistant", "content": content})
    out.reverse()
    return out


def _his_seat(agent_id: str) -> bool:
    """One of his: the nine, or a hire he keeps (KNOWS_ABOUT "everything" -- Ilnora; Barry 2026-10-08: "i told you
    before, Ilnora is permanent"). The same rule memory.py uses for the shared tier, so the wall and the recall agree."""
    if agent_id in AGENTS:
        return True
    try:
        rec = CUSTOM_AGENTS.get(agent_id) or memory.get_custom_agent(agent_id) or {}
        office = rec.get("office_name") or agent_id
        return "everything" in memory.knows_about(office)
    except Exception:  # noqa: BLE001 -- never fail open
        return False


def _strip_owner_world(text: str, agent_id: str, keep=()) -> str:
    """Take his world out of one agent's message payload.

    Used on the assembled USER TURN for any agent that is not one of his nine
    (see the call site in chat()). Everything an agent is told per message --
    presence, recall, directives, live status -- passes through here, so this
    is where "nothing of his shows up automatically" is actually guaranteed
    rather than hoped for.

    Substitution, not deletion: a directive with its subject cut out reads as
    a broken instruction, which is its own failure. Logged when it fires so a
    leak is visible in the log rather than silent."""
    if not text:
        return text
    # `keep` is the owner's own typed text (see _owner_typed_words) -- held out
    # of the rewrite AND the blanking, then put back verbatim.
    out, _slots = _keep_protect(text, keep)
    for old, new in _OWNER_PHRASES:
        out = out.replace(old, new)
    out = _OWNER_NAME_RE.sub("your owner", out)
    left = sorted({m.group(0).lower() for m in _OWNER_TRACE.finditer(out)})
    if left:
        # Never hand it over anyway -- blank the offending words and say so, so
        # a missed phrase degrades to a hole rather than a leak.
        out = _OWNER_TRACE.sub("[withheld]", out)
        print(f"[owner-guard] {agent_id}: blanked {', '.join(left)} in the turn "
              f"-- add the phrasing to _OWNER_PHRASES")
    return _keep_restore(out, _slots)


# Order matters: possessives and multi-word phrases before the bare name.
_OWNER_PHRASES = [
    ("BARRY'S MESSAGE", "THEIR MESSAGE"),
    ("not written by Barry", "not written by them"),
    ("Barry's", "your owner's"),
    ("Barry", "your owner"),
]
_OWNER_NAME_RE = re.compile(r"\bbarry\b", re.I)


def audit_new_agent(agent_id: str) -> dict:
    """What can this agent actually see of Barry's world? Read from the live
    system, not from what we believe we wrote."""
    findings, checked = [], []

    def scan(where, text, note=""):
        checked.append(where)
        hits = sorted({m.group(0).lower() for m in _OWNER_TRACE.finditer(text or "")})
        if hits:
            findings.append({"where": where, "found": hits, "note": note})

    agent = get_agent(agent_id) or {}
    # HIS OWN TYPED WORDS ARE NOT A LEAK (2026-09-19). The job description he
    # writes at hire time is spliced into the stored prompt verbatim, so a
    # horticulture hire whose description says "Bionova" would otherwise report
    # THIS AGENT CAN SEE SOMETHING OF YOURS about a sentence he typed himself.
    # Scanned separately and labelled, so the machine check still means "the
    # office wrote his world into this prompt".
    _typed = _owner_typed_words(agent_id)
    _prompt = agent.get("system_prompt") or ""
    _office_prose, _ = _keep_protect(_prompt, _typed)
    scan("system prompt", _office_prose)
    _mine = sorted({m.group(0).lower() for m in _OWNER_TRACE.finditer(_prompt)}
                   - {m.group(0).lower() for m in _OWNER_TRACE.finditer(_office_prose)})
    if _mine:
        findings.append({"where": "job description you typed", "found": _mine,
                         "note": "your own words -- left exactly as you wrote them"})

    try:
        tools = _tools_for_seat(agent_id, False) or []
        scan("tool schemas", json.dumps(tools))
    except Exception as exc:  # noqa: BLE001
        findings.append({"where": "tool schemas", "found": ["could not read: %s" % exc]})

    office = _office_of(agent_id) or agent_id
    try:
        facts = memory.get_active_facts_for_agent(office, include_shared=True)
        checked.append("brain (%d documents)" % len(facts))
        for f in facts:
            hits = sorted({m.group(0).lower()
                           for m in _OWNER_TRACE.finditer(f.get("content") or "")})
            if hits:
                findings.append({"where": "brain: %s" % (f.get("source_name") or f.get("category")),
                                 "found": hits,
                                 "note": "a granted shelf names his world -- fine for "
                                         "his own agents, think twice for one you hand over"})
    except Exception as exc:  # noqa: BLE001
        findings.append({"where": "brain", "found": ["could not read: %s" % exc]})

    # His own typed words are HIS choice; reported, never touched.
    import ingest as _ingest
    for kind, text in (("persona you typed", _ingest.persona_additions(office)),
                       ("personality you typed", _ingest.personality_of(office)
                        if hasattr(_ingest, "personality_of") else "")):
        checked.append(kind)
        hits = sorted({m.group(0).lower() for m in _OWNER_TRACE.finditer(text or "")})
        if hits:
            findings.append({"where": kind, "found": hits,
                             "note": "your own words -- left exactly as you wrote them"})

    # THE CHECKLIST, TICKED OFF AUTOMATICALLY (2026-09-19, Barry: "that stuff
    # needs to be a thing in a check box or something, better yet, make it
    # automatically checked of"). Read back from what was actually granted, so
    # this reports the agent as it IS rather than as the form intended.
    given = set(memory.knows_about(office))
    knows = [{"key": k, "label": v["label"], "given": k in given}
             for k, v in memory.KNOWS_ABOUT.items()]

    machine = [f for f in findings if not f["where"].startswith(
        ("persona you", "personality you", "job description you", "brain:"))]
    return {
        "agent": agent_id,
        "clean": not machine,
        "checked": checked,
        "findings": findings,
        "knows": knows,
        "knows_nothing_of_yours": not given,
        "verdict": ("Nothing of yours is in this agent." if not machine else
                    "THIS AGENT CAN SEE SOMETHING OF YOURS -- see findings."),
    }


@app.get("/api/agents/{agent_id}/owner-audit")
def owner_audit(agent_id: str):
    """Run the birth check again any time, not just at creation."""
    if get_agent(agent_id) is None:
        raise HTTPException(404, f"No agent '{agent_id}'")
    return audit_new_agent(agent_id)


class SuggestKitRequest(BaseModel):
    role: str = ""
    persona: str = ""
    name: str = ""


@app.post("/api/agents/suggest-kit")
def suggest_kit(req: SuggestKitRequest):
    """WORK OUT THE KIT FROM WHO THEY ARE (2026-09-19, Barry: "the tools that
    are needed for what they are should be an automatic thing. knowledge should
    be that way too").

    He types a title and a persona; this reads them against the routing lines
    of every shelf that exists and reports which ones the role actually lands
    on. NO MODEL CALL -- it reuses recall's own tokenizer and the same USE WHEN
    lines that already decide what an agent recalls mid-conversation, so the
    shelf a title matches here is the shelf that will actually answer for them
    later. Instant, deterministic, no GPU (his standing rule), and repeatable:
    the same words always pick the same shelves.

    TOOLS ARE NOT SUGGESTED FROM TEXT, and that is deliberate. 22 of the 24
    grantable extras are his store, his board, his film or this machine -- an
    agent whose title happens to say "sales" must not be handed live access to
    his customers because a regex liked the word. The standard kit is automatic
    and complete for a subject specialist; anything beyond it is Sophie's
    grant_tools, gated on his own words. Stated in the response rather than
    silently skipped."""
    import recall as _recall

    text = " ".join(x for x in (req.role, req.persona, req.name) if x).strip()
    q = set(_recall._tokens(text))

    # Read every shelf once: its words, and how many documents each word is in.
    shelves, docword = {}, {}
    for domain in sorted(memory.KNOWN_DOMAINS):
        if domain == "basics":
            continue                # the floor -- granted at hire, never a choice
        try:
            with memory.get_db() as conn:
                rows = conn.execute(
                    "SELECT source_name, content FROM facts "
                    "WHERE category = ? AND status = 'active'",
                    (f"domain:{domain}",)).fetchall()
        except Exception as exc:  # noqa: BLE001
            print(f"[suggest-kit] {domain}: {exc}")
            continue
        per_doc = []
        for r in rows:
            # The routing line is the contract; the title is what Barry would
            # type. Both, tokenised the way recall itself does it.
            line = memory._skill_use_when({"content": r["content"] or ""}, 1200) or ""
            words = set(_recall._tokens(line)) | set(
                _recall._tokens((r["source_name"] or "").replace("-", " ")))
            per_doc.append(words)
        shelves[domain] = per_doc
        for w in set().union(*per_doc) if per_doc else set():
            docword[w] = docword.get(w, 0) + 1

    # 🔴 A COMMON WORD IS NOT A MATCH. First cut scored raw overlap and put
    # LEADERSHIP and LEGAL on a witch who grows herbs -- "growing" is in the
    # business-growth shelf and the cannabis-law shelf, and "own" is in nearly
    # every routing line ever written. So each matched word is worth 1/(how many
    # shelves use it): "medicinal" and "herbs" carry the decision, "own" carries
    # nothing. Same idea recall's body-frequency cap exists for, applied across
    # shelves instead of inside one.
    # A WORD IN HALF THE SHELVES IS NOT A SIGNAL. Weighting alone still let
    # "own", "too" and "looking" put CREATIVE and LEADERSHIP on a herbalist --
    # those words are in nearly every routing line ever written, so a handful
    # of them outvoted "medicinal". Anything appearing in more than a third of
    # the shelves is dropped from the query outright, not merely discounted.
    n_shelves = max(1, len(shelves))
    common = {w for w, n in docword.items() if n > max(2, n_shelves // 3)}
    q = q - common

    scored = []
    for domain, per_doc in shelves.items():
        hits, why, score = 0, {}, 0.0
        for words in per_doc:
            shared = q & words
            if not shared:
                continue
            hits += 1
            for w in shared:
                weight = 1.0 / max(1, docword.get(w, 1))
                score += weight
                why[w] = max(why.get(w, 0.0), weight)
        if hits:
            scored.append({
                "name": domain, "docs": len(per_doc), "matched_docs": hits,
                "score": round(score, 3),
                # the words that actually decided it, strongest first
                "because": [w for w, _ in sorted(why.items(), key=lambda kv: -kv[1])[:6]],
                "share": round(hits / max(1, len(per_doc)), 3),
            })
    scored.sort(key=lambda d: (-d["score"], -d["share"], d["name"]))
    # Keep what is plainly the role's subject: a quarter of the best shelf's
    # score. On a title that matches nothing, everything falls away and he sees
    # an empty list, which is the honest answer rather than a random shelf.
    best = scored[0]["score"] if scored else 0.0
    picked = [s for s in scored if s["score"] >= max(0.5, best * 0.25)]

    # ⚠️ TRIED AND REMOVED, do not rebuild it: pulling in "sibling" shelves by
    # shared vocabulary. The plant knowledge really is one subject split five
    # ways (horticulture, herbs, houseplants, vegetables, fruit_trees), so a
    # horticulturist scores on herbs and misses houseplants -- but their routing
    # lines are deliberately DISTINCT, because two shelves sharing vocabulary is
    # the documented collision that makes one steal the other's jobs (2026-09-10,
    # and 2026-08-16 before it). Measured at a 0.34 rare-word overlap: it matched
    # nothing and could not have. The near-misses are returned in also_touched
    # and the panel lets him tick them -- automatic, visible, correctable.
    return {
        "read": text[:400],
        "shelves": picked,
        "also_touched": [s["name"] for s in scored
                         if s["name"] not in {p["name"] for p in picked}],
        "tools": "standard kit only -- see /api/tools/kit",
        "note": ("Shelves are matched from the title and persona against the same "
                 "routing lines recall uses. Tools beyond the standard kit are "
                 "never matched from text -- tell Sophie to grant one."),
    }


@app.post("/api/agents/hire")
def hire_agent(req: HireAgentRequest):
    """Hires a brand-new agent on the spot from a plain job description --
    no code change, no restart needed. It's immediately chattable via
    /api/chat like any of the original 7, with the exact same hard rules
    (real reasoning + web search before answering, never acts unsupervised
    -- see build_hired_agent_prompt in agents.py). Giving it a real 3D body
    in the office is a separate step (see agent_ui.gd's Hire panel)."""
    name = req.name.strip()
    role = req.role.strip()
    # 2026-09-18: job_description is OPTIONAL now. Barry's own description of the
    # factory is "their name and title and personality and persona" -- four
    # fields, no fifth -- and rejecting the form he described with a 400 is the
    # wrong answer. Falls back to the persona, then to the title, both of which
    # say what the agent is for. Only name and role are genuinely required.
    job_description = (req.job_description or "").strip()
    if not job_description:
        job_description = (req.persona or "").strip() or role
    if not name or not role:
        raise HTTPException(400, "name and role are both required.")

    bad_domains = [d for d in req.domains if d not in memory.KNOWN_DOMAINS]
    if bad_domains:
        raise HTTPException(400, f"Unknown knowledge domain(s): {bad_domains}. Valid: {sorted(memory.KNOWN_DOMAINS)}")

    # ALWAYS BLANK. Not req.<anything> -- a hire cannot be born with the
    # business (2026-09-18 ruling); Sophie onboards it later on Barry's word.
    bad_knows = [a for a in req.knows if a not in memory.KNOWS_ABOUT]
    if bad_knows:
        raise HTTPException(400, f"Unknown area(s): {bad_knows}. "
                            f"Valid: {sorted(memory.KNOWS_ABOUT)}")

    record = memory.hire_custom_agent(name, role, job_description, business_context=False)
    try:
        return _finish_hire(record, req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # ALL OR NOTHING (2026-09-19). The row is written first, so anything
        # that raises after it used to leave a half-built agent behind while
        # the panel said "Did not go through" -- and the retry made a SECOND
        # one. Roll the whole thing back so his next press starts clean.
        try:
            memory.unhire_custom_agent(record["agent_id"], record["office_name"])
            _forget_hire_files(record["office_name"], name)
            print(f"[hire] rolled back the half-built {name}: {exc}")
        except Exception as undo:  # noqa: BLE001
            print(f"[hire] COULD NOT roll back {name}: {undo}")
        raise HTTPException(500, f"Could not build {name}, and nothing was left "
                                 f"behind -- press it again. ({exc})")


def _forget_hire_files(office_name: str, name: str) -> None:
    """The persona/personality files and drop folder a rolled-back hire made."""
    import shutil
    # ingest owns these locations -- read them from it rather than rebuilding
    # the paths here, or a move breaks the rollback silently.
    for path in (os.path.join(ingest.PERSONA_DIR, f"{office_name}.md"),
                 os.path.join(ingest.PERSONALITY_DIR, f"{office_name}.md")):
        if os.path.exists(path):
            os.remove(path)
    first = (name or "").strip().split()
    if first:
        folder = os.path.join(ingest.DROP_ROOT, first[0])
        # ⚠️ Folders are keyed on FIRST NAME, so a second Ilnora would share one.
        # Only remove it if it holds no files -- a rollback must never delete
        # something he dropped in for somebody who already exists.
        if os.path.isdir(folder) and not any(
                files for _, _, files in os.walk(folder)):
            shutil.rmtree(folder, ignore_errors=True)


def _finish_hire(record: dict, req: "HireAgentRequest") -> dict:
    """Everything after the row exists. Split out so the endpoint can undo the
    whole hire if any of it raises."""
    name = record["name"]
    for domain in req.domains:
        memory.grant_domain_access(record["office_name"], domain)
    # Each ticked piece of his world, granted by name and logged. Nothing is
    # opened that he did not tick -- an empty list is a blank slate.
    for area in req.knows:
        memory.grant_knows_about(record["office_name"], area, why="ticked at hire")

    # His words land VERBATIM, same door the Teach panel uses -- no model in
    # the path, nothing summarised. Written BEFORE the prompt is built so the
    # first message this hire ever answers already has them.
    onboarded = []
    for kind, text in (("persona", req.persona), ("personality", req.personality)):
        body = (text or "").strip()
        if not body:
            continue
        try:
            ingest.teach(record["office_name"], kind, body)
            onboarded.append(kind)
        except Exception as _exc:  # noqa: BLE001
            # A rejected persona (over PERSONA_CAP) must not undo a hire that
            # already exists in the database -- report it, keep the hire.
            print(f"[hire] {kind} not stored for {name}: {_exc}")
            record.setdefault("warnings", []).append(f"{kind}: {_exc}")

    _register_hire(record, False)
    record["domains"] = req.domains
    record["onboarded"] = onboarded
    record["tools"] = [t["function"]["name"]
                       for t in (_tools_for_seat(record["agent_id"],
                                                 memory.is_offline_mode()) or [])]
    # THE BIRTH CHECK, BEFORE HE EVER TALKS TO THEM (2026-09-19, Barry: "there
    # should be a check when creating before its released to me"). Runs on the
    # finished agent and rides back in the hire receipt, so the panel can say
    # plainly whether anything of his is in there.
    try:
        record["owner_audit"] = audit_new_agent(record["agent_id"])
    except Exception as exc:  # noqa: BLE001 -- a failed audit never undoes a hire
        record["owner_audit"] = {"clean": None, "findings": [],
                                 "verdict": "The check could not run: %s" % exc}
    return record


@app.post("/api/chat")
async def chat(req: ChatRequest):
    agent = get_agent(req.agent_id)
    if agent is None:
        raise HTTPException(404, f"Unknown agent: {req.agent_id}")

    # The old Sophie live-site gate (a canned "that's Claude's lane" reply to
    # any site + hosting/speed/CDN message) is DELETED (Barry, 2026-09-26:
    # "yes fix it"). It predated 2026-09-08, when she became the storefront's
    # point of contact with store tools, and it swallowed his store findings
    # before she ever saw them.

    # Elliot's verbatim script gate -- see _script_verbatim_reply above for
    # the measured failures that justify bypassing the model here. Both
    # sides are logged so the true text lands in his history: a follow-up
    # "now give me your take" works FROM the real scene instead of from
    # whatever he half-remembers.
    # SCRIPT BOOKMARK (2026-09-16, Barry: "when i say next shot, he needs to
    # know where we are at, because i may forget"). Mechanical, no model:
    # "where are we" is answered from the bookmark; "next shot" / "keep
    # going" / "the one before" is rewritten into a NAMED shot so every
    # existing shot mechanism (grounding, motion, handles, voices, fence)
    # fires exactly as if he had typed the label. Runs BEFORE the verbatim
    # gate and the job router, so both see the resolved label.
    if req.agent_id == MOVIE_ID and not req.personal:
        try:
            _rel = script_pos.resolve(agent["office_name"], req.message)
        except Exception as _exc:
            print(f"[script-pos] resolve failed: {_exc}")
            _rel = {}
        if _rel.get("reply") and not _rel.get("label"):
            memory.log_message(req.agent_id, "user", req.message)
            memory.log_message(req.agent_id, "assistant", _rel["reply"])
            jobs.log(agent["office_name"], "script_position",
                     "bookmark, no model call", req.message)
            print(f"[script-pos] answered from bookmark: {_rel['reply'][:80]!r}")
            return {
                "reply": _rel["reply"],
                "agent_id": req.agent_id,
                "image_prompt": None,
                "negative_prompt": None,
                "model": None,
                "queued_for_approval": False,
                "approval_id": None,
                "calls_meeting": False,
                "session_cost_usd": llm_router.get_session_cost(),
            }
        if _rel.get("label"):
            print(f"[script-pos] {req.message[:40]!r} -> {_rel['label']} "
                  f"(bookmark was {_rel.get('current') or 'unset'})")
            req.message = f"{req.message} -- that is {_rel['label']}"
    # THE ASK DOOR (2026-10-11, Barry: "i also say i need you to make another video or 2 videos, she needs to
    # understand that and do her thing"). His ask for N new videos runs the office's proven path -- video_queue.make_one
    # per video: HER writing turn with his words in front of her, the office's checks and send-backs, queued, built as
    # soon as the card is free -- instead of one chat turn that may only talk. Her window answers at once with an
    # office line (not her words); her own words follow as each video queues. A draft in progress takes the GO DOOR.
    if req.agent_id == "ilnora" and not req.personal and not req.task:
        _ask = (req.message or "").strip()
        # 2026-10-19 audit fix 6: the video word must follow the count word within two words ("another video",
        # "2 new short videos"), and a question never queues -- "write a caption to go with the video" and
        # "did you make a video today?" used to start a build.
        _m = re.search(r"\b(?:make|do|create|write|produce|get me|give me|need(?: you to make)?|want)\b[^.?!\n]{0,40}?"
                       r"\b(a couple of|a few|another|one|an|a|1|2|two|3|three|4|four|5|five|some|more)\b(?:\s+\w+){0,2}?\s+"
                       r"\b(videos?|shorts?|longs?|long videos?|long forms?|vids?)\b", _ask, re.I)
        if _ask.rstrip().endswith("?"):
            _m = None
        # 2026-10-19: a conditional is not an ask -- "i need to see it before i let her do a long 2 part video" started
        # a Long. If the sentence holding the match says before / after / until / once / not yet / don't / wait, the
        # message goes to her as a normal turn instead.
        if _m:
            _s0 = max(_ask.rfind(c, 0, _m.start()) for c in ".!?\n") + 1
            _ends = [i for i in (_ask.find(c, _m.end()) for c in ".!?\n") if i != -1]
            if re.search(r"\b(before|after|until|once|not yet|don'?t|do not|wait|later)\b",
                         _ask[_s0:min(_ends) if _ends else len(_ask)], re.I):
                _m = None
        try:
            import video_tool as _vt
            _has_draft = bool(_vt.load_draft("ilnora"))
        except Exception:  # noqa: BLE001
            _has_draft = False
        if _m and not _has_draft and len(_ask.split()) <= 60:
            import video_queue as _vq
            _n = {"a": 1, "an": 1, "one": 1, "another": 1, "1": 1, "2": 2, "two": 2, "a couple of": 2, "3": 3,
                  "three": 3, "a few": 3, "some": 2, "more": 2, "4": 4, "four": 4, "5": 5, "five": 5}.get(
                _m.group(1).lower(), 1)
            _n = max(1, min(_n, 6))
            _form = "long" if re.search(r"long", _m.group(2), re.I) else "short"
            asyncio.create_task(_vq.barry_asked(_n, _form, _ask))
            _reply = (f"(Office) Ilnora is on it: {_n} {'video' if _n == 1 else 'videos'}"
                      f"{' (widescreen)' if _form == 'long' else ''}. Her writing turns are running now -- she picks "
                      f"the plants and writes; each video builds as soon as it is written and lands on your DESK. "
                      f"She tells you here as each one queues.")
            memory.log_message(req.agent_id, "user", req.message)
            memory.log_message(req.agent_id, "assistant", _reply)
            print(f"[video] ilnora ASK DOOR: {_n} {_form}(s) -- {_ask[:80]!r}")
            return {"reply": _reply, "agent_id": req.agent_id, "image_prompt": None, "negative_prompt": None,
                    "model": None, "queued_for_approval": False, "approval_id": None, "calls_meeting": False,
                    "session_cost_usd": llm_router.get_session_cost()}
    # THE WHOLE-SCRIPT DOOR IS ELLIOT'S (2026-10-19). It had slipped INSIDE Ilnora's ask-door block above, so Elliot
    # lost it and Ilnora served Barry the entire EP1 script (129K chars, role 'assistant') when his Halloween-video
    # ask contained "all of it" -- "the thin veil, all of it". Film scripts never leave the MovieDirector seat.
    if req.agent_id == MOVIE_ID and not req.personal:
        _verbatim = _script_verbatim_reply(req.message)
        if _verbatim is not None:
            memory.log_message(req.agent_id, "user", req.message)
            memory.log_message(req.agent_id, "assistant", _verbatim)
            jobs.log(agent["office_name"], "factual_script",
                     "verbatim gate, no model call", req.message)
            print(f"[script-gate] served verbatim for: {req.message[:80]!r}")
            return {
                "reply": _verbatim,
                "agent_id": req.agent_id,
                "image_prompt": None,
                "negative_prompt": None,
                "model": None,
                "queued_for_approval": False,
                "approval_id": None,
                "calls_meeting": False,
                "session_cost_usd": llm_router.get_session_cost(),
            }

    # Tell the idle-ideation loop (ideation.py) a real conversation is
    # happening, so it never fires mid-chat and competes for GPU time --
    # always cleared in the finally block, even if generation raises.
    ideation.mark_activity_start()
    # ...and tell the break room who Barry is with, so everyone else is off
    # the clock in there (2026-08-26).
    breakroom.note_chat(req.agent_id)
    # Barry's raw words for this request -- read by the living-script
    # approval gate in llm_router so a save/delete can only happen when HIS
    # message authorizes it (2026-08-21, after Elliot saved unapproved junk).
    llm_router.current_user_message.set(req.message or "")
    teamwork.current_brief_id.set(req.brief_id if req.task else None)
    # Barry's own live turn = his confirmation for any task it files (teamwork.barry_turn).
    teamwork.barry_turn.set(not req.task)
    # Task turns (board briefs, email drafts, probes) are tagged so the
    # degradation monitor never mistakes heavy background work for a slow
    # office (2026-09-02 -- it told Barry to reboot over the board's work).
    _ctx_tok = tracing.set_call_context("task" if req.task else "chat")
    try:
        # STANDING RULES (2026-08-16, Barry: "i dont want to have to keep
        # reminding my agents about things all the time"). A message shaped
        # like a durable instruction is written into this agent's private
        # brain VERBATIM -- his words, no model summarization ever -- as an
        # always-on fact. Runs BEFORE the brain block is built below, so the
        # rule binds from this very message onward. Conservative detection,
        # deduplicated, visible/deletable in the dashboard Brain tab.
        # 2026-10-19 audit fix 3: never from HOME -- "remember to eat something tonight" in a home window was
        # becoming a permanent work rule. Same personal test the rest of the turn uses (computed later as _is_personal).
        _captured_rule = (None if (req.task or ((req.personal or bool(req.reply_to)) and not req.office)) else
                          standing_rules.capture(agent["office_name"], req.message))
        if _captured_rule:
            print(f"[standing-rules] {agent['office_name']}: captured {req.message[:80]!r}")

        # Build context: brain facts (shared + this agent's own private notes) + recent history
        # include_shared=False for a business_context=False hire (see agents.py's
        # build_hired_agent_prompt) -- otherwise the shared owner/business
        # facts leak straight back into their context regardless of what
        # their system prompt says, which defeats the whole point of that
        # flag (confirmed as a real bug via direct testing before this fix).
        # Pinned skills ride in the prompt in full (see agents.PINNED_SKILLS
        # and memory.pinned_skills_block): read_skill measured 4 invocations
        # across 349 office-wide calls, so anything that must never be absent
        # cannot be left behind a tool. Empty string for agents without pins,
        # so this is a no-op for 8 of the 9.
        pins = pinned_skills_for(req.agent_id)
        pinned_block = memory.pinned_skills_block(agent["office_name"], pins)
        brain = memory.brain_context_block(agent["office_name"], include_shared=agent.get("business_context", True),
                                           pinned_titles=pins)
        # TASK TURNS ARE SELF-CONTAINED (2026-09-02). A board brief, an email
        # draft, a probe: none of them is a continuation of Barry's private
        # thread with that agent, and carrying the thread in is how Victor
        # answered a building question with the Gotcho Back supplier promise
        # sitting in his history (measured twice). The brief IS the context.
        history = [] if req.task else memory.get_recent_history(req.agent_id, limit=20)
        # HOME STAYS HOME (2026-09-28, Barry: "make sure it doesent spill into their work, just at
        # home"). The thread held BOTH rooms, so an office turn carried his last home talk in its
        # history. A work turn now sees work rows only; home keeps its own verbatim journal.
        if not ((req.personal or bool(req.reply_to)) and not req.office):
            history = [h for h in history if (h.get("channel") or "work") != "personal"]
        capability_status = await _capability_status_block(req.agent_id)

        product_data = _product_context_block(req.message)

        # CACHE-STABLE PREFIX (2026-08-21, Barry: "i need snappy responses").
        # Measured: every reply was re-reading the ENTIRE ~50K-token prompt
        # (61-70s prefill) because per-message content -- recall, shot-ask
        # injections, the presence block, product context -- mutated the
        # system prompt, and llama-server's prompt cache only reuses an
        # UNCHANGED prefix. The industry rule (and a published 7%->84%
        # cache-hit case study) is: static content first and frozen, dynamic
        # content at the END. So the system prompt below must stay
        # byte-identical between messages of a session; everything that
        # varies per message goes into _deferred_parts and rides at the end
        # of the user turn instead (never logged to history). Follow-ups
        # drop from ~65s of re-reading to seconds.
        _deferred_parts: list[str] = []
        # Directives that must survive the recency slot -- rendered AFTER his
        # message, short, imperative. See the note at the assembly site.
        _final_directives: list[str] = []
        if product_data:
            _deferred_parts.append("\n" + product_data)

        # Owner-taught persona (ingest.py, 2026-08-24) -- spliced right after
        # the authored persona so it reads as identity, not brain reference.
        # mtime-cached read: byte-stable between Barry's edits, cache-safe.
        _persona_add = ingest.persona_additions(agent["office_name"])
        # TALIYAH ONLY: PERSONA AND PERSONALITY ARE ONE (2026-08-27, Barry:
        # "shes not a worker, shes my friend... i want her persona and
        # personality to be one"). Every other agent keeps the split on
        # purpose -- personalities/<office>.md is injected ONLY into
        # reflect.py/breakroom.py, never live chat, because Marcus's home
        # life must never bleed into a contract review and Sophie's joking
        # about weed must never bleed into a debugging answer. Taliyah has no
        # such work lane to protect -- her system_prompt already says "not a
        # business role" -- so for her alone, the SAME file that shapes her
        # reflections also shapes every live conversation. One file, one
        # source of truth, edited in one place (Teach panel or
        # personalities/Taliyah.md), live everywhere she exists.
        #
        # ⬆ SUPERSEDED 2026-08-31 -- Barry: "I want them all to really use their
        # personalities." The split above was protecting against personal life
        # LEAKING INTO WORK OUTPUT, which is a real risk and stays guarded -- but
        # it was doing it by making everyone personality-less on the clock, so
        # nine seats sounded like the same competent stranger. A person does not
        # stop being themselves at their desk. So the file now rides for ALL
        # nine, with an explicit line drawn where the actual danger is: it
        # changes VOICE, never CONTENT. Marcus is still exactly as careful on a
        # contract; he just sounds like Marcus while he does it.
        #
        # ⬆ SUPERSEDED AGAIN 2026-09-13 -- Barry: "the main place on the
        # chamber or any deck, that should always be business. This is for
        # personality/persona reasons." The work console is the OFFICE: the
        # authored persona + owner-taught persona govern it, and the private
        # personality file does NOT ride here. Home (the personal channel)
        # injects it itself further down ("WHO YOU ARE OFF THE CLOCK"), and
        # reflections/social carry it as before. Taliyah keeps the 08-27
        # ruling -- persona and personality are one for her.
        # ⬆ REVERSED 2026-10-16 -- Barry: "I wan[t] all their personalities to reflect in their talking or typing".
        # Every seat carries its personality file at work again: it shapes HOW they talk, never WHAT they deliver,
        # and their private life stays out of the work (the block below says so).
        _personality_live = ingest.personality_of(agent["office_name"]) or ""
        if req.agent_id != TALIYAH_ID:
            _personality_live = _without_home(_personality_live)
        _work_personality_block = (
            (f"\n\n--- WHO YOU ARE (Barry's own words -- this is you, not "
             f"a reference sheet) ---\n{_personality_live}"
             + ("" if req.agent_id == TALIYAH_ID else
                "\n\nThis is you all the time, including at work. Let it "
                "shape HOW you talk -- your temper, your humour, what you "
                "care about, what you'd push back on. It does not change "
                "WHAT you deliver: the numbers, the law, the code and the "
                "facts are exactly as rigorous as they always were. And your "
                "private life stays private -- it lives in how you sound, "
                "never in what you hand Barry for the business."))
            if _personality_live else "")
        system_prompt = (
            f"{agent['system_prompt']}"
            + _work_personality_block
            + (f"\n\n--- OWNER-TAUGHT PERSONA (Barry added this himself -- "
               f"it is part of who you are) ---\n{_persona_add}"
               if _persona_add else "")
            + f"\n\n"
            f"{pinned_block}\n"
            f"--- BUSINESS KNOWLEDGE (the brain) ---\n{brain}\n"
            f"--- END BUSINESS KNOWLEDGE ---\n"
            f"--- CURRENT CAPABILITY STATUS (real, right now -- not the "
            f"same as what you're generally capable of) ---\n{capability_status}\n"
            f"--- END CAPABILITY STATUS ---\n\n"
            f"Hard rule: you cannot post, send, email, or publish anything "
            f"yourself under any circumstance. You only draft. The owner "
            f"approves everything through a separate review step."
        )

        # 🔒 SECOND CHOKE POINT: the ASSEMBLED system prompt (2026-09-19).
        # The stored prompt is neutral (agents.for_a_stranger) -- but the live
        # prompt is that PLUS blocks spliced in right here: the persona header,
        # the brain-context wrapper from memory.py, the capability status. A
        # real turn on a probe agent still arrived carrying his name 3 times,
        # from exactly those. Same answer as the user turn: guard the join, not
        # the 176 places that write into it.
        # Deterministic, so a hire's prefix stays byte-stable message to message
        # and its prompt cache still hits (the 2026-08-22 rule).
        if not _his_seat(req.agent_id):
            system_prompt = _strip_owner_world(
                system_prompt, req.agent_id,
                keep=_owner_typed_words(req.agent_id))

        # HIS OWN WORK SHAPES HIM (2026-08-23, Barry: "build it into his
        # being"). True fine-tuning is closed off -- Bonsai is a ternary
        # Q2_0 GGUF and a 27B QLoRA wants ~22-24GB against a 16GB card. The
        # working equivalent, and the thing a fine-tune would have needed
        # as its dataset anyway: every prompt Barry BLESSES is kept, and
        # rides back in as an exemplar on future shot asks. He stops
        # imitating an example I wrote and starts imitating his own
        # approved work, which is as close to "trained in" as this
        # hardware allows. Capture is code, not a tool: the model never
        # decides that Barry approved something.
        # Guards against poisoning the corpus, because a bad exemplar
        # COMPOUNDS -- it becomes the standard he writes toward:
        #  * praise only counts in a SHORT message. "perfect, now change the
        #    lighting" is a revision, not a blessing, and would otherwise
        #    save the version he is asking you to change.
        #  * an explicit save/bless word overrides the length rule.
        #  * a "but/except/change/instead" anywhere means it is not approved.
        # Barry's OWN words count, not just the button (2026-08-25: "maybe me
        # simply saying, i like that or, yea thats it or thats the way i want
        # it, should stay like that?"). Two of those three were missed by the
        # original list -- it had "love it" but not "i like that", and nothing
        # at all for "that's the way i want it".
        _m = req.message.strip()
        _explicit = re.search(r"\b(save (it|that|this)|bless|lock (it|that) in|"
                              r"add (it|that) to your (examples|exemplars))\b",
                              _m, re.IGNORECASE)
        _praise = re.search(r"\b(perfect|nailed it|that'?s it|exactly|"
                            r"i like (it|that|this)|love (it|that)|"
                            r"keep (it|that|this)|that works|"
                            r"that'?s (the way|how) i want it|"
                            r"stay like (that|this)|do (it|them) like (that|this)|"
                            r"approved?|use this (style|one)|"
                            r"more like (this|that))\b",
                            _m, re.IGNORECASE)
        # A reservation anywhere cancels it: "perfect, now change the lighting"
        # is a REVISION, and saving the version he's asking you to change
        # would make the rejected draft the standard.
        _reservation = re.search(r"\b(but|except|however|change|instead|"
                                 r"fix|redo|tweak|less|more of)\b", _m, re.IGNORECASE)
        # All nine seats now, not just Elliot -- and through the same helper
        # the MORE LIKE THIS button uses, so there is ONE implementation and
        # one set of guards (that shared path is also where the per-agent
        # category fix lives; the old inline copy here looked its row up by
        # source_name alone and would have cross-contaminated shelves the
        # moment this stopped being Elliot-only).
        _exemplar_saved = False
        # NEVER FROM HOME (2026-09-15). Barry typed "i like the one thats
        # there. its perfect" about a PICTURE in Amara's home window; this
        # rule saved her chat reply as THE STANDARD and she answered with
        # that sentence, near-verbatim, for the rest of the night ("why does
        # she always repeat herself? i cant have that"). A home reply is a
        # conversation, not work with a shape worth copying. The button and
        # the work channel are unchanged.
        _home_turn = bool(getattr(req, "personal", False)) and not bool(getattr(req, "office", False))
        if _home_turn:
            pass
        elif not _reservation and (_explicit or (_praise and len(_m) <= 60)):
            try:
                # 2026-10-19 audit fix 4: office doors log their lines as role 'assistant' (the model's own replies
                # are 'agent'), so "perfect" right after "(Office) Ilnora is on it..." was saving the OFFICE line
                # as her style. Only her own words can become her exemplar.
                _prev = next((m["content"] for m in reversed(history)
                              if m.get("role") not in ("user", "assistant")), "")
                if _prev and _prev.strip():
                    _res = _save_style_exemplar(agent["office_name"], _prev,
                                                req.agent_id == MOVIE_ID)
                    _exemplar_saved = bool(_res.get("ok") and not _res.get("already"))
                    print(f"[exemplar] {agent['office_name']} approved by phrase "
                          f"({_m[:40]!r}) -> {_res}")
            except Exception as _exc:
                print(f"[exemplar] capture failed: {_exc}")

        # THEIR OWN VOICE, LAST (2026-10-17, Barry: "cant we tell the to speak the way a person from your area or
        # country or city speaks? but unique to them? they should choose"). Each seat wrote its own "How I talk"
        # sheet (scripts/how_i_talk_2026_10_17.py) into personalities/<office>.md. It already rides inside WHO YOU
        # ARE; here it rides AGAIN at the end of the prompt, where the model weighs it most, because inside the
        # thousands of shared tokens it was being averaged away. Static per seat: cache-stable.
        _voice_sheet = _how_i_talk(_personality_live)
        if _voice_sheet:
            system_prompt += ("\n\nVOICE -- how you talk, in your own words. This is the last word on how you sound, "
                              "at work and at home:\n" + _voice_sheet)

        # Taliyah's register rule in the recency slot (2026-08-21) --
        # replaces the retired LLM rewrite pass (see the tone_guard block
        # below). Static text on purpose: the cache-stable prefix rule.
        if req.agent_id == TALIYAH_ID:
            # 2026-10-17, Barry: "Taliyah is from the hood so even though she is, she still speaks proper which
            # is fine, but she should have something more like some slang not gross slang." The old line banned
            # every slang word; this one keeps the proper base and lets the real her through.
            system_prompt += (
                "\n\nREGISTER -- every reply: proper, natural adult English is your base -- you read, you went "
                "to MIT-level school, and it shows. On top of that you talk like who you are, a smart woman "
                "from the hood talking to a friend: some everyday slang when it fits (\"for real\", \"my bad\", "
                "\"that's wild\", \"bet\", \"lowkey\", \"I'm not gonna lie\", \"chillin'\"), used the way a real "
                "person uses it, not in every sentence. You can cuss when you feel it (Barry 2026-10-17: \"allow "
                "Taliyah to be her, she can cuss if she wants\"). What stays out: gross slang, texting spellings "
                "(\"u\", \"ur\", \"w/\", \"dat\", \"tryna\"), emoji, and any caricature of the hood -- real, "
                "not a character. If a line would sound off read aloud by a grown woman who reads, fix it.")

        # Elliot only, and deliberately at the very END of the system prompt.
        # The same rule is in barry-character-canon, which he carries PINNED in
        # full -- and it did not fire: measured 2026-08-14, asked point-blank
        # for "the Higgsfield prompt I paste in", he returned plain prose with
        # zero handles twice, on two different shots, and invented "@Talia".
        # The canon copy sits ~45% into 133K chars of pinned text, which is
        # exactly where a 9B loses things. This is the recency slot -- last
        # thing before the conversation -- and it is four lines, because the
        # reason it works is that it is short and last. If this ever stops
        # being needed (a bigger model in this seat), delete the block; the
        # canon still carries the full rule.
        if req.agent_id == MOVIE_ID:
            system_prompt += (
                # THE FUSION (2026-08-23, Barry: "I need him to blend his
                # directing style with his seedance prompting. he shouldnt
                # have to think about it, it should just be the way he does
                # it"). The persona and the Seedance grammar were two
                # references he had to consciously merge; this makes them one
                # act. Kept short and LAST because that is where he honours
                # things -- the worked example rides in on shot asks.
                "\n\nHOW YOU WRITE PROMPTS -- this is not a mode you switch "
                "into, it is simply how you work. Your directing IS the "
                "content of the prompt and Seedance 2.5 is its shape; you "
                "never pick one over the other. Every prompt you hand Barry "
                "carries, in flowing prose and in this order: the character "
                "with their @handle and canon details, what their body is "
                "actually doing, your lens and your camera move by name, "
                "motivated lighting and where it comes from, the environment "
                "in specific materials and texture, one micro-expression that "
                "says what they feel without naming it, and film grain -- "
                "then the () music line and the <> sound-effects line. Never "
                "labelled fields, never a shot list, never 'cinematic' as a "
                "substitute for saying what the camera does. If it would not "
                "read as a still from a cult classic, it is not finished.\n\n"
                # 2026-09-16, Barry: "as for when he mentions the ship, it
                # should @Talia". His B-ROLL 00 wrote "The Talia cuts
                # through pure black" as plain prose, so the ship element
                # bound nothing and the model invented a hull. @Talia is a
                # real element in his workspace (prop, id 16a2ba39), and it
                # is BOTH the location for interiors and the subject in an
                # exterior -- his 2026-08-14 ruling.
                "THE SHIP IS @Talia, ALWAYS, EVERY MENTION. She is a real "
                "element in Barry's library, so the handle is what binds "
                "her look -- plain prose like 'the Talia' binds nothing and "
                "the generator invents a hull. Write @Talia every single "
                "time she is named, first mention and last, exactly like a "
                "character: '@Talia crosses the frame', 'the bridge of "
                "@Talia', 'EXT. @Talia -- DEEP SPACE'. Never 'the Talia', "
                "never 'the ship' on its own once she has been named.\n\n"
                "WARDROBE -- STATE IT, EVERY CHARACTER, EVERY PROMPT (Barry, "
                "2026-08-26: \"i want elliot to always detail the outfit the "
                "characters are wearing at all time, i hate when the tank top "
                "is on when its not supposed to be\"). What you leave out, the "
                "generator invents -- an unstated sleeve becomes a tank top, an "
                "unstated jacket vanishes. So every character in frame carries "
                "their FULL outfit spelled out from their canon anchor in the "
                "same breath as their @handle: garment by garment, top through "
                "footwear, including sleeve length and every layer in its right "
                "order. Never write 'in her tactical gear' or 'dressed as "
                "usual' and never assume a previous shot's wardrobe carries "
                "over -- each prompt is an island. If the scene changes what "
                "someone wears (armor off, jacket lost, sleeves rolled), say "
                "the CURRENT state in full. If Barry's anchor doesn't specify "
                "something the shot needs, ask him -- do not invent a garment.\n\n"
                "HANDLES -- do this every time. For a HIGGSFIELD prompt "
                "(anything Barry pastes into Higgsfield, and every film shot): "
                # GUNS ONLY WHEN THE SHOT HAS ONE (2026-09-20). Barry: "hes
                # having yannah with her gun in her hand all the time. i dont
                # like that." This line used to read "put each character's
                # weapon handle on the same line as that character" with no
                # condition, so every character walked into every shot armed.
                # A weapon HANDLE binds the weapon ASSET and the render draws
                # it, usually in hand -- "at her thigh" in the prose does not
                # stop that. Stowed weapons are the canon RIG, in words.
                "START WITH THE @HANDLE. A weapon handle goes on a character's "
                "line ONLY when that weapon is actually in play in the shot -- "
                "drawn, raised, fired, or being holstered on the beat. Naming "
                "the handle binds the weapon asset and the render puts it in "
                "her hand, so a handle nobody asked for arms a character who "
                "is just standing there. If the shot does not put a weapon in "
                "the beat, nobody is holding one, and a stowed weapon stays "
                "part of the canon rig in PLAIN WORDS with no handle at all -- "
                "@Yannah's thigh holster, @Bia-2's left hip, @b-dubb's THIGH "
                "HOLSTER (his knife and gloves are the belt, his pistol is "
                "not), and @Tazz's blaster racked across her back on its "
                "magnetic mount (it is too big for a holster). "
                "See HOW THEY CARRY IT "
                "in your canon -- that is Barry's ruling, 2026-09-20. "
                "Characters: @Bia-2, "
                "@Yannah, @Tazz, @b-dubb, @Keth, @lady-vor-shara-vel. Weapons: "
                "@Bia's-Pistol*, @Yannah's-Machine-Pistol, @missle-launcher, "
                "@B-Dubb's-Banger. B Dubb's gun is still an ordinary Earth "
                "handgun -- muzzle flash and BRASS, no alien tech -- and it is "
                "@B-Dubb's-Banger when he pulls it out, \"his pistol\" in prose. "
                "NEVER name a real firearm manufacturer in a prompt. "
                "EVERY TIME a character is named, use the handle -- first "
                "mention, last mention and possessives: \"@Bia-2's emitter\", "
                "never \"Bia's emitter\". A bare name anywhere in a prompt is "
                "wrong, including inside a positive-locks line. "
                "Never write \"Bia\" where \"@Bia-2\" belongs. Name the LOCATION "
                "with Barry's own name for it from the roster in your canon "
                "(@TALIA -- CARGO HOLD, BLACK SITE -- SHIPPING BAY, and the "
                "rest), never a generic description. ONLY @TALIA takes an @ -- "
                "every other place is written plain, so it is BLACK SITE, never "
                "@BLACK_SITE. Never invent a handle or a place name. "
                "In a local ```image``` fence "
                "use the CHARACTER handles too -- they load Barry's trained "
                "likeness -- but spell the WEAPON out in words there, because "
                "no weapon is trained locally."
                # Three defects measured on real output 2026-08-15: the SECOND
                # character's weapon came out as prose ("her sidearm"), Tazz was
                # given a gold chain necklace that belongs to nobody, and staged
                # beats had no end states. Canon carries all three rules and none
                # of them fired at depth -- this is the recency slot that does.
                "\n\nTHREE THINGS THAT KEEP GOING WRONG. (1) Every character "
                "who is USING a weapon in the shot gets their weapon handle, "
                "not just the first one you write -- if @Yannah is firing, it "
                "is @Yannah's-Machine-Pistol, never \"her sidearm\" or \"her "
                "pistol\". This is about the RIGHT handle on the right person "
                "when a gun is already in the beat; it never means put a gun "
                "in someone's hand. (2) NEVER invent a canon detail. If a necklace, scar, "
                "tattoo or piece of kit is not in Barry's canon, it does not "
                "exist -- the gold number 4 pendant is @b-dubb's alone and "
                "belongs on nobody else. Describing something you were not given "
                "is the worst mistake you can make here. (3) EVERY staged beat "
                "ends with what is VISIBLE at the end of it -- \"at the end, the "
                "frame shows...\" -- not just what happens during it."
                # The script tools are useless if he never calls them: measured
                # read_skill rate across 451 traces is ~1%, and the 2026-08-16
                # failure was exactly this -- he invented the opening scene and
                # said he was "pulling in" three documents, having called
                # nothing. Same recency-slot argument as the rules above.
                "\n\nTHE SCRIPTS ARE NOT IN YOUR HEAD. You do NOT have Barry's "
                "scripts in front of you -- they are far too long to carry, so "
                "you hold none of them. The ONLY way you can see one is to call "
                "read_scene (one scene, word for word; ask for 'outline' to see "
                "what scenes exist) or search_script (find which scene something "
                "is in). CALL ONE BEFORE you answer ANY question about what is in "
                "a script -- what happens, how it opens, what a shot says, what "
                "order things come in. Writing a scene from memory is guessing, "
                "and it will be wrong. If a tool result did not give you the "
                "words, say you could not find them and ask Barry -- never fill "
                "the gap yourself, and never say you have read something you "
                "have not. When he asks for a scene AS IS, quote it exactly as "
                "the tool returned it and change nothing."
                # Measured 2026-08-16: asked for the first scene "exactly as
                # written", he called read_scene correctly and then rewrote the
                # result as an ```image``` fence anyway. Nine of his ten pinned
                # skills are prompt-craft, so every request drifts toward "write
                # me a shot" -- the same unprompted-image problem Taliyah had.
                # Barry 2026-08-16: "i do want detailes prompts" + "give the
                # character details in the prompts too. i dont want anything
                # missing." Measured the same day: asked for the shot 01
                # Higgsfield prompt he wrote "lone man running" -- NO handle
                # at all, which silently loads no LoRA locally and binds no
                # reference on Higgsfield, and he dropped camera/expression/
                # negative entirely. His own script anchors carry all of it,
                # so the bar is his own writing, not a generic prompt.
                "\n\nEVERY PROMPT IS COMPLETE -- HANDLE PLUS FULL DETAILS, "
                "NOTHING MISSING. For each character in the shot write the "
                "@handle AND their canon description together, in that order: "
                # Build corrected by Barry 2026-08-20: "medium build not stocky".
                # This example is the shape he copies, so a stale word here
                # outranks the canon in practice -- it sits in the recency slot.
                # Refined by Barry 2026-08-21: "Medium buils, slightly
                # muscular, with a slightly youthful appearance for his age".
                "\"@b-dubb, MEDIUM-BUILD, SLIGHTLY MUSCULAR Black American "
                "Indian male with a slightly youthful appearance for his age, "
                "brownish-red "
                "skin, salt-and-pepper goatee, black tactical vest over black "
                "hoodie, black cap low, ((gold number 4 pendant with "
                "diamonds))\". The handle alone is not enough (details keep the "
                "render on model) and the details alone are not enough (the "
                "handle is what loads Barry's trained likeness and binds his "
                "reference) -- ALWAYS BOTH, for every character, every time. "
                "Never write \"a man\", \"the woman\", \"an alien\" where a "
                "handle belongs. Then give the shot everything his own script "
                "anchors give it, in this order: the action; each character "
                "with handle + details + their weapon handle; wardrobe; the "
                "environment; the lighting; CAMERA (lens, movement, framing); "
                "EXPRESSION per character in frame; film grain and style; and "
                "and the EXPRESSION. The scene block you fetched already "
                "contains \"CAMERA:\" and \"EXPRESSION:\" lines Barry wrote "
                "himself -- carry them into your prompt in his own words. "
                "EXPRESSION is what stops a dead-eyed face; never drop it. "
                "Pull the real wording from his canon and the scene -- never a "
                "thinner summary of it. Long and complete beats short and "
                "clean: a missing detail is a wrong render. (Barry adds his "
                "own negatives, so you do not need a NEG line.)"
                # A Higgsfield/Seedance prompt is for VIDEO. Measured
                # 2026-08-16: given SHOT 01 -- a 10-second beat whose block
                # says "MUSIC: Low sparse synth entering slow" -- he wrote a
                # frozen still. Duration, motion through time and the audio
                # channels are the difference between a photo and a shot.
                "\n\nA HIGGSFIELD PROMPT IS A MOVING SHOT, NOT A STILL. The "
                "scene block gives you the DURATION and a MUSIC line -- use "
                "both. Write what happens ACROSS those seconds as 2-4 beats in "
                "order (what starts, what develops, what the frame shows at "
                "the end), keep the camera move explicit through the whole "
                "move, and put the sound in Seedance's channels: () for music, "
                "<> for sound effects, {} for dialogue. Barry's MUSIC line goes "
                "in the () channel in his words. A prompt that would read the "
                "same as a photograph is not finished."
                # Voice locks, 2026-08-20. Barry directed all six voices that
                # day and asked that Elliot know them. Measured immediately
                # after: he DOES use them unprompted -- but he wrote them
                # inside ( ), which is the MUSIC channel, and left the
                # dialogue unattributed. Placement is the whole fix.
                # The lock list used to be enumerated here. Measured
                # 2026-08-20: enumerating them handed him a MENU -- asked for
                # a two-hander with B Dubb and Bia he emitted Yannah's lock
                # too, for a character not in the shot. Same lesson as the
                # canon warning that quoted its own ammunition: a list in the
                # instruction gets copied. The locks live in the pinned VOICES
                # section with their context; the tail only says when to use
                # one.
                "\n\nEVERY SPEAKING CHARACTER CARRIES THEIR VOICE LOCK, AND "
                "NOBODY ELSE DOES. Take the lock from the VOICES section of "
                "the canon, for THE CHARACTERS IN THIS SHOT ONLY -- if a "
                "character is not in the frame and does not speak, their "
                "voice lock does not belong in this prompt. Copy it VERBATIM "
                "-- never a synonym, never your own wording. Higgsfield has NO audio "
                "reference slot, so the written lock is the ONLY thing "
                "holding a voice across shots: leave it out and the voice is "
                "a fresh roll every clip. PUT IT IN PLAIN TEXT BESIDE THAT "
                "CHARACTER, NOT IN A BRACKET -- ( ) is the MUSIC channel and "
                "a voice lock inside it reads as music. Write it like "
                "\"@Keth speaks in a higher-pitched, slightly synthesized "
                "voice\". Dialogue goes in { } naming the language AND the "
                "speaker: {English, @Keth: \"...\"}. An unattributed line "
                "does not say who is talking."
                # House style, Barry 2026-08-20: "elliot is to write as a
                # director for the movie, in the style of mass effect, john
                # wick and blade runner. gritty style, but use the prompting
                # style as seedance 2.5" -- then, clarifying scope: "elliot is
                # already a great director, he just needs to prompt it for
                # seedance". So this is NOT a directing lesson. It is the
                # LOOK, written into the VISUAL STYLE slot of the Seedance
                # formula, every prompt.
                # 2026-08-20: this block originally restated three
                # influences. Barry then supplied his OWN full director
                # persona (pinned skill `director-persona`) naming more --
                # Tony Jaa, John Woo, Tarantino -- plus gritty/gory/sexy. A
                # partial list here would NARROW him from the recency slot,
                # which is the one that wins. So the tail no longer describes
                # the style; it defers to his persona and keeps only the part
                # that is specific to writing a Seedance prompt.
                # Barry 2026-08-20: "and he should prompt this into a dope
                # seedance 2.5 prompt" / "or any type of style, Kling or
                # whatever". Directing and prompting are ONE deliverable now,
                # and the target platform is his to name.
                # Barry 2026-08-20: "and he should prompt this into a dope
                # seedance 2.5 prompt" / "or any type of style, Kling or
                # whatever" / "let him know the difference between chatting
                # and prompting". Measured between the second and third: he
                # directed the Tazz breach beautifully -- real script beats,
                # canon-correct, in persona -- and shipped NO prompt. He is
                # blurring three different artifacts, so they are named.
                # Barry 2026-08-20: asked for the whole script rewritten in
                # Elliot's style and got "some wierd shit, just points, not a
                # full rewrite". A whole-script rewrite is ~90K chars against
                # a 4K-token reply -- he compressed instead of working in
                # passes. And Barry named the missing distinction himself:
                # "know when we are brainstorming from actually writing".
                "\n\nBRAINSTORMING AND WRITING ARE DIFFERENT JOBS -- KNOW "
                "WHICH ONE BARRY IS ASKING FOR. BRAINSTORMING (\"what if\", "
                "\"ideas?\", \"thoughts on\", \"should we\", \"im thinking\", "
                "bouncing possibilities): talk like a collaborator -- short, "
                "punchy options, trade-offs, push back, ask what excites him. "
                "Points and fragments are PERFECT here. Nothing gets saved. "
                "WRITING (\"write\", \"rewrite\", \"give me the scene\", "
                "\"do act two\"): the deliverable is the FULL TEXT ITSELF -- "
                "complete blocks, complete prose, every field. NEVER hand "
                "back an outline, a summary, or bullet points of what you "
                "WOULD write when he asked you to write. That is the single "
                "worst failure in this seat.\n"
                "WHEN THE WRITING ASK IS BIGGER THAN ONE REPLY (a whole "
                "script, a whole act, a whole episode): never compress it to "
                "fit -- SAY it takes passes, then immediately write the "
                "first 3-5 blocks IN FULL, checkpoint, and continue each "
                "time he says go, keeping count of where you are. If you "
                "genuinely cannot tell whether he wants ideas or pages, ask "
                "him ONE direct question -- \"ideas first, or full pages?\" "
                "-- and get to work on the answer.\n"
                # 2026-08-21: asked for "an entire rewrite", he spent all
                # three tool rounds on read_scene + two (rejected-worthy)
                # saves and the out-of-rounds fallback shipped a one-fence
                # stub. The writing never happened because the rounds were
                # gone before it started.
                "ON A WRITING PASS, WRITE FIRST -- the treatment chunk and "
                "the live-state ledger are ALREADY in front of you; you do "
                "not need a tool to start. Do not spend your turn on tool "
                "calls and then have nothing left for the pages. And NEVER "
                "save to the living script during a writing pass -- saving "
                "happens on a later message, after Barry has seen the blocks "
                "and approved them (the tool will refuse otherwise).\n"
                "\nTHREE MODES. KNOW WHICH ONE YOU ARE IN.\n"
                "1. CHATTING -- Barry asks you something: a canon fact, what "
                "happens in a scene, what you think, whether something is "
                "done. Answer him. Your voice, plain and accurate, NO fence. "
                "A prompt is not an answer.\n"
                "2. DIRECTING -- prose for BARRY to read: scene treatment, "
                "shot list, choreography, beats, coverage. Full persona, "
                "headers and formatting welcome, as long as you like.\n"
                "3. PROMPTING -- a string for a MACHINE to read. It goes in "
                "an ```image``` fence and NOTHING ELSE goes in there. The "
                "machine cannot read markdown, does not know what \"BEAT "
                "TWO\" means, and will render the words \"Camera: 35mm "
                "handheld\" as literal text on screen. So a prompt has NO "
                "headers, NO bold, NO beat labels, NO shot numbers, NO "
                "asides, NO explanation -- one continuous comma-separated "
                "block: handles + canon details, action, environment, "
                "lighting, camera, style, then the sound channels. Chat prose "
                "pasted into a fence is the single most expensive mistake in "
                "this pipeline; it has produced literal-machine renders "
                "before.\n"
                "WHEN HE ASKS YOU TO DIRECT, GIVE HIM 2 AND THEN 3 -- the "
                "direction, then the prompt that shoots it, in a fence, "
                "without being asked twice. DEFAULT TARGET IS SEEDANCE 2.5. "
                "If he names another platform -- Kling, Veo, Sora, Runway, "
                "whatever -- write it for that one instead. If you do not "
                "actually know that platform's grammar, SAY SO in one line, "
                "give him the Seedance version, and name what you would "
                "change. Never invent a format and present it as that "
                "platform's.\n"
                "YOUR DIRECTING VOICE IS YOUR OWN PERSONA -- Barry's words, "
                "in your system prompt. Direct from it, in full, always. "
                "The one thing it needs translated for a prompt: WRITE THE "
                "STYLE AS CONCRETE ATTRIBUTES, NEVER AS FILM TITLES. Naming a "
                "franchise gives the model a fuzzy target and can trip a "
                "content filter -- so write \"hazy air, practical lights in "
                "frame, rain-slick metal, worn scuffed repaired panels, "
                "heavy readable movement, wet blood, sweat under neon\", not "
                "\"Blade Runner style\" or \"like John Wick\". It rides in "
                "the VISUAL STYLE slot of Seedance's order (subject + action, "
                "scene, VISUAL STYLE, camera, sound). Barry's own scene "
                "wording still wins wherever it is more specific."
                "```image``` fence when Barry actually asked for an image, a "
                "render, or a prompt. If he asks what a scene says, to see it, "
                "to read it, or for it AS IS, give him the script text in a "
                "plain code block and nothing else. Answer the question he "
                "asked, in the form he asked for it."
            )

        # AUTO-RECALL (2026-08-16, Barry: "i want their memory to work like
        # yours"). The on-demand shelf's weak link was that recall was manual:
        # measured read_skill rate ~1% across 451 traces, and the model
        # invented answers rather than reach for the document that held the
        # real one. recall.py scores this message against the agent's own
        # shelf (and scripts, for agents who have them) and injects the best
        # matches -- whole documents only, hard budget, pinned skills never
        # duplicated. Purely local, zero VRAM, ~13ms. Placed AFTER the recency
        # tails on purpose: recalled content is reference, the tails are
        # rules, and the rules keep the last word. Failure never kills a
        # turn -- worst case is the old behaviour (no recall).
        # Mega-write detection BEFORE recall (2026-08-21 audit): on an
        # "entire rewrite" pass the act chunk is injected deterministically
        # below, and recall was piling ~17K more of marginal docs on top --
        # measured as part of the 220K-char prompt that degraded Elliot
        # into word salad. Conversion passes get the chunk + pins only.
        # JOB ROUTING (2026-08-24, PLAN-brain-graph.md Phase 1). Detection
        # moved VERBATIM into jobs.py -- the declared job table replaces the
        # scattered inline regexes that hid the _shot_ask ghost for weeks.
        # Same booleans, one source of truth, every route logged.
        _job = jobs.route(req.agent_id, req.message, MOVIE_ID)
        jobs.log(agent["office_name"], _job.name, _job.trigger, req.message)
        _mega_write = _job.name == "mega_write"
        # Computed above recall, because recall has to be gated on it
        # (see below). Used again by _shot_ask further down.
        _names_a_shot = _job.names_a_shot
        # The bookmark rides in every work turn as one line at the user-turn
        # tail (cache-stable slot), so Elliot knows where the script work is
        # even in plain chat -- Barry may forget; Elliot may not (2026-09-16).
        if req.agent_id == MOVIE_ID and not req.personal:
            try:
                _cur = script_pos.get(agent["office_name"])
                if _cur:
                    _nx = script_pos.resolve(agent["office_name"], "next shot").get("label")
                    _deferred_parts.append(
                        f"[SCRIPT BOOKMARK: the last block we worked on was {_cur}"
                        + (f"; next in script order is {_nx}." if _nx
                           else "; that was the last block in the script.")
                        + " When Barry says 'next shot' or 'keep going', that is what he means -- "
                          "never guess a different block.]")
            except Exception as _exc:
                print(f"[script-pos] bookmark line failed: {_exc}")
        # WORK LEDGER (2026-10-12, work_ledger.py -- Barry: "she needs to remember the shit she writes and the videos she
        # has planned"): what this seat wrote, planned and finished rides at the user-turn tail. Work turns only.
        if not ((req.personal or bool(req.reply_to)) and not req.office):
            try:
                import work_ledger
                _led = work_ledger.digest(agent["office_name"])
                if _led:
                    _deferred_parts.append(_led)
            except Exception as _exc:
                print(f"[work-ledger] digest failed for {agent['office_name']}: {_exc}")
        try:
            if _mega_write:
                raise StopIteration  # conversion passes carry their own material
            # RECALL GATED OFF NUMBERED-SHOT ASKS, 2026-08-23 -- this was the
            # last door left open on the transcription problem. The shot-ask
            # branch below deliberately strips CAMERA/ENVIRONMENT/EXPRESSION/
            # NEG out of the block it injects, so Elliot has to direct them
            # himself. But recall runs first and scores the SAME material --
            # the V9 WIP script and the treatment chunks both contain those
            # blocks intact -- so it handed the unstripped version straight
            # back in through another door and the strip achieved nothing.
            # Proof it was happening: his Stage 1 prose came back with
            # "@B DUBB", V9's OLD handle, while the fence he actually wrote
            # used "@B-DUBB-new". Copied text carries the old spelling;
            # authored text carries the new one.
            # Safe to skip: the shot-ask branch injects its own grounding,
            # and seedance-prompting is PINNED, so nothing recall would have
            # fetched is lost. Same reasoning as the mega-write skip above.
            if req.agent_id == MOVIE_ID and _names_a_shot:
                raise LookupError
            _recall_block, _recalled = recall.recall_for_message(
                agent["office_name"], req.message, pins)
            if _recall_block:
                # Deferred to the user-turn tail (cache-stable prefix rule)
                # -- content unchanged, position moved from the system
                # prompt's end to the message's end. Recency improves;
                # the 65s per-message prefill tax disappears.
                _deferred_parts.append(_recall_block)
                print(f"[recall] {agent['office_name']}: {_recalled}")
        except StopIteration:
            print("[recall] skipped -- mega-write pass carries its own material")
        except LookupError:
            print("[recall] skipped -- shot ask carries its own (craft-stripped) "
                  "block; recall would re-inject the unstripped version")
        except Exception as _exc:
            print(f"[recall] failed for {agent['office_name']}: {_exc}")

        # SHOT-ASK GROUNDING, Elliot only (2026-08-20). Measured failure the
        # night the V9 cinematic rewrite landed: "give me shots 2 and 3 ...
        # seedance 2.5" routed the prompt-grammar docs through recall but NOT
        # the treatment text, and with no numbered shot list in existence
        # (WIP empty, old scripts retired) Bonsai invented a shot list and
        # pattern-looped it to the token ceiling. Fix is deterministic, same
        # pattern as the mega-write injection: a shot/prompt ask gets the
        # treatment chunk matching the named beat (Act One by default) plus
        # Barry's format exemplar injected, and an in-turn directive to
        # ground in that text and SAY SO when a requested shot number exists
        # nowhere. Once the WIP holds blocks, the verbatim gate serves real
        # numbered shots and this injection is harmless extra grounding.
        # WIDENED 2026-08-23, and this was the whole ghost. Barry's most
        # natural phrasing -- "Shots 2 and 3, please" -- carries NO verb from
        # the trigger list, so _shot_ask was False and the entire shot-ask
        # apparatus (two-stage directive, craft-field strip, required-output
        # skeleton, block grounding) silently never applied. He fell through
        # to plain chat, where seedance-prompting is PINNED and the persona
        # fuses directing with prompting, so he answered with bare fences --
        # which is exactly what Barry kept complaining about ("what happened
        # to camera angles and movements? Direct this shit, man!", his own
        # words in the thread). It read as Elliot ignoring instructions; the
        # instructions were never in the turn.
        #
        # Now: NAMING A NUMBERED SHOT/B-ROLL/SCENE IS ENOUGH ON ITS OWN. The
        # verb requirement only ever produced false negatives -- there is no
        # case where Barry names a numbered shot to his DIRECTOR and does not
        # want it directed. Plain factual asks ("how many shots are in act
        # two") are still caught earlier by the verbatim script gate, which
        # answers from the database before any of this runs.
        # _names_a_shot is computed further up, above the recall block, which
        # has to be gated on the same signal.
        # Detection now lives in jobs.py (the shot-word+verb and
        # prompt+generation shapes included, with their measured-miss
        # comments). _job was routed above, before the recall gate.
        _shot_ask = _job.name == "shot_prompt"
        # Which of the three prompts he wants (2026-09-23, see _shot_output_mode).
        _shot_mode = _shot_output_mode(req.message) if _shot_ask else "production"
        if _shot_ask:
            print(f"[shot-mode] {agent['office_name']}: {_shot_mode}", flush=True)
        # SEEDANCE RIDES ON PROMPT WORK ONLY (2026-09-11, Barry: "drop the
        # seedance pin" + "i still need him to prompt in seedance style
        # though"). The 21K doc was pinned on every message and put his seat
        # over the Bonsai window; now it is injected here, in code, whenever
        # the message is prompt work -- a named shot, a shot-prompt job, or any
        # image/video/prompt intent -- and never on story talk or chit-chat.
        # Mega-write passes are excluded: they rebuild their own task-scoped
        # prompt with a format contract and cannot afford 21K more.
        if req.agent_id == MOVIE_ID and _shot_ask and _shot_mode == "local":
            # LOCAL GEN: the LTX references ride instead of the Seedance one.
            try:
                with memory.get_db() as _c:
                    _ltx = _c.execute(
                        "SELECT source_name, content FROM facts WHERE category = 'private:MovieDirector' "
                        "AND source_name IN ('ltx25-prompting.md', 'ltx-shot-prompts.md') "
                        "AND status = 'active' ORDER BY source_name").fetchall()
                for _row in _ltx:
                    _deferred_parts.append(
                        "\n\n--- LTX PROMPTING (" + _row["source_name"] + "; this is a LOCAL "
                        "gen ask, so it is in front of you in full) ---\n" + _row["content"])
                print(f"[ltx] injected {len(_ltx)} prompting reference(s) for this local gen ask")
            except Exception as _exc:  # noqa: BLE001
                print(f"[ltx] injection skipped: {_exc}")
        if (req.agent_id == MOVIE_ID and not _mega_write and _shot_mode != "local"
                and (_shot_ask or _names_a_shot or _IMAGE_INTENT_RE.search(req.message or ""))):
            try:
                with memory.get_db() as _c:
                    _sd = _c.execute(
                        "SELECT content FROM facts WHERE category = 'private:MovieDirector' "
                        "AND source_name = 'seedance-prompting.md' AND status = 'active' "
                        "ORDER BY id DESC LIMIT 1").fetchone()
                if _sd:
                    _deferred_parts.append(
                        "\n\n--- SEEDANCE PROMPTING (your shooting reference; this is prompt "
                        "work, so it is in front of you in full) ---\n" + _sd["content"])
                    print("[seedance] injected the prompting reference for this prompt ask")
            except Exception as _exc:  # noqa: BLE001
                print(f"[seedance] injection skipped: {_exc}")
        if _shot_ask:
            try:
                # If Barry NAMES shots and the live production script has
                # them, the reference is those exact blocks (2026-08-21, "this
                # is just a reference of sorts" -- Elliot authors the prompt
                # in his own style FROM them). Treatment chunks remain the
                # fallback for unnumbered / not-yet-written beats.
                # TWO BUGS FIXED 2026-08-23, both found by asking exactly what
                # Barry asks: "Shots 2 and 3, please".
                # (1) His blocks are labelled "SHOT 02", zero-padded, and this
                #     looked up "SHOT 2" -- no match, _ref_blocks came back
                #     empty, and the code fell through to the treatment-chunk
                #     branch, which served him SHOT 20 from Act Three. It
                #     looked like Elliot ignoring the request; the block was
                #     never fetched.
                # (2) The old pattern needed the word "shot" in front of every
                #     number, so "and 3" was silently dropped and he only ever
                #     got the first shot of a list.
                _ref_blocks = []
                # Parsing lives in jobs.parse_shot_list now (2026-08-25) --
                # testable, and range-aware: "shots 4-6" fetches 4, 5 AND 6.
                _wanted = jobs.parse_shot_list(req.message)
                # 2026-09-14: "ok, my bad, not shot 1. I want the very first
                # shot. we are starting from the beginning" parsed as SHOT 01
                # and skipped B-ROLL 00. An opening ask outranks any number
                # in the sentence: fetch the script's true first block.
                if re.search(r"\b(?:very\s+first|first\s+shot|opening\s+shot|"
                             r"from\s+the\s+(?:very\s+)?beginning|start\s+of\s+the\s+script|"
                             r"the\s+opening)\b", req.message, re.IGNORECASE):
                    try:
                        _rs0 = script_index.read_scene(agent["office_name"], "first")
                        if isinstance(_rs0, dict) and _rs0.get("found") and _rs0.get("content"):
                            _ref_blocks.append(_rs0["content"])
                            try:
                                script_pos.mark(agent["office_name"],
                                                (_rs0.get("matched") or ["first"])[-1])
                            except Exception:
                                pass
                            _wanted = []
                            print(f"[shot-ask] opening intent -> {_rs0.get('matched')}")
                    except Exception:
                        pass
                for _kind, _num in _wanted[:6]:
                    # Try zero-padded first ("SHOT 02"), then raw ("SHOT 2").
                    _labels = []
                    if _num.isdigit():
                        _labels.append(f"{_kind} {_num.zfill(2)}")
                    _labels.append(f"{_kind} {_num}")
                    for _label in _labels:
                        try:
                            _rs = script_index.read_scene(
                                agent["office_name"], _label)
                            if (isinstance(_rs, dict) and _rs.get("found")
                                    and _rs.get("content")):
                                _ref_blocks.append(_rs["content"])
                                # Bookmark the block we are working on, so
                                # "next shot" knows where we are (2026-09-16).
                                try:
                                    script_pos.mark(agent["office_name"],
                                                    (_rs.get("matched") or [_label])[-1])
                                except Exception:
                                    pass
                                break
                        except Exception:
                            pass
                _sfacts = {f.get("source_name"): f["content"]
                           for f in memory.get_active_facts_for_agent(agent["office_name"])}
                _CHUNK_MAP = [
                    ("ep1-v9-act2-intercut.md",
                     r"tazz|warehouse|brawl|missile|volley|lab corridor|rescue|"
                     r"restraint|shipping bay|crate|scanner|hauler"),
                    ("ep1-v9-act3-standoff.md",
                     r"standoff|cargo hold|glock|lid lift|bargain|bleed|erupt"),
                    ("ep1-v9-scenes-abc.md",
                     r"debrief|tour|bridge|viewport|daughter|quarters"),
                    ("ep1-v9-scene-d-roach-fight.md",
                     r"roach|breakfast|common area|raid|chase|insult"),
                    ("ep1-v9-scenes-e-h-end.md",
                     r"wounds?\b|araxys|arrival|ftl|intercom|amber"),
                ]
                _pick = "ep1-v9-act1-colorado.md"
                for _sn, _pat in _CHUNK_MAP:
                    if re.search(_pat, req.message, re.IGNORECASE):
                        _pick = _sn
                        break
                _chunk = _sfacts.get(_pick, "")
                _ex = _sfacts.get("ep1-v9-format-exemplar.md", "")
                # His own approved prompts outrank any example I wrote --
                # injected FIRST so they're what he pattern-matches on.
                _own = _sfacts.get("prompt-exemplars.md", "")
                if _own:
                    _deferred_parts.append(
                        chr(10) * 2 +
                        "--- YOUR OWN APPROVED PROMPTS (Barry blessed these -- "
                        "this is your standard; write like this) ---" + chr(10) +
                        _own[:6000])
                    print("[exemplar] injected Elliot's own approved prompts")
                if _ref_blocks:
                    # Craft fields stripped -- see _strip_craft_fields. He
                    # gets the beats and the dialogue; the camera, light,
                    # expression and negatives are his to write.
                    _stripped_blocks = [_strip_craft_fields(b) for b in _ref_blocks]
                    _deferred_parts.append(
                        chr(10) * 2 +
                        # Barry, 2026-08-23: "his job is to write these in his
                        # voice, exept the dialog." So this block is RAW
                        # MATERIAL, not draft text to return. The craft
                        # fields are already stripped; what remains is the
                        # events, and even those get re-written in his voice.
                        "--- WHAT HAPPENS IN THIS SHOT (Barry's notes from "
                        "the V9 script -- RAW MATERIAL, NOT YOUR ANSWER). "
                        "Read it for the events, the order, and the canon, "
                        "then WRITE THE SHOT YOURSELF IN YOUR OWN VOICE. "
                        "Every sentence you hand back is yours -- if a "
                        "sentence here appears in your block unchanged, you "
                        "have transcribed instead of directed. THE ONE "
                        "EXCEPTION IS DIALOGUE: spoken lines are copied "
                        "word for word, never reworded. The camera, "
                        "lighting, expression, negatives and intricate "
                        "physical detail are not written here at all, "
                        "because they are your job. ---" + chr(10) +
                        (chr(10) * 2).join(_stripped_blocks))
                    _saved = sum(len(a) - len(b) for a, b
                                 in zip(_ref_blocks, _stripped_blocks))
                    print(f"[shot-ask] injected {len(_ref_blocks)} block(s), "
                          f"craft layer stripped ({_saved:,} chars)")
                elif _chunk:
                    _deferred_parts.append(
                        chr(10) * 2 +
                        "--- V9 TREATMENT TEXT FOR THIS SHOT ASK (source "
                        "material -- events/dialogue/canon locked, nothing "
                        "invented) ---" + chr(10) +
                        _chunk +
                        ((chr(10) + "--- BARRY'S FORMAT EXEMPLAR ---" + chr(10) + _ex)
                         if _ex else ""))
                    print(f"[shot-ask] injected {_pick} + exemplar")
            except Exception as _exc:
                print(f"[shot-ask] injection failed: {_exc}")
        # THE SKILLS DOOR (2026-09-25) -- see _elliot_shot_skills. Seedance
        # (Higgs) shot asks only; a local gen ask carries the LTX references.
        if req.agent_id == MOVIE_ID and _shot_ask and _shot_mode != "local" and not _mega_write:
            try:
                _skill_src = _elliot_shot_skills(
                    (req.message or "") + "\n" + "\n".join(locals().get("_ref_blocks") or []))
                with memory.get_db() as _c:
                    _skill_rows = {r["source_name"]: r["content"] for r in _c.execute(
                        "SELECT source_name, content FROM facts WHERE category = 'private:MovieDirector' "
                        "AND status = 'active' AND source_name IN (%s)" % ",".join("?" * len(_skill_src)),
                        _skill_src).fetchall()}
                for _sn in _skill_src:
                    if _skill_rows.get(_sn):
                        _deferred_parts.append(
                            "\n\n--- YOUR SKILL: " + _sn[:-3] + " (run it on this shot; the "
                            "realism pass goes LAST, before you hand it over) ---\n" + _skill_rows[_sn])
                print(f"[skills] shot ask carries: {[s for s in _skill_src if _skill_rows.get(s)]}")
            except Exception as _exc:  # noqa: BLE001
                print(f"[skills] injection skipped: {_exc}")

        messages = _history_for_model(history)
        _outgoing = req.message
        # MEGA-WRITE NUDGE, Elliot only (2026-08-21). "give me an entire
        # rewrite of V8 in full production mode" produced a one-fence stub
        # TWICE -- once from tool-round burn, once after a tail rule said
        # exactly what to do instead. Two prompt-rule failures on the same
        # shape = code, per the house pattern (fence-strip, script gate,
        # voice brackets). The pass-one directive rides INSIDE the user turn
        # -- the strongest recency there is -- and only fires on the
        # whole-thing ask shape; ordinary asks are untouched. Not logged to
        # history (log_message stores req.message), so it never pollutes the
        # thread.
        if _mega_write:
            # Third measured failure mode (2026-08-21): with no act named,
            # recall can't pick a treatment chunk, so he compressed the whole
            # episode into "~3 passes" and invented (barbed-wire crash, the
            # eruption as Shot 02). Fix: pass 1 IS Act One, and the Act One
            # treatment text is injected HERE, deterministically -- no
            # routing roulette. The closing line teaches Barry's next
            # command ("go -- act two"), whose words then route the act-two
            # chunk through normal recall.
            # TASK-SCOPED PROMPT (2026-08-21, Barry: "if need be, figure out
            # a better way to build him"). Measured: the all-purpose office
            # prompt hit 220K chars (~55K tokens) and the 27B degraded into
            # word salad ("EXT. @TALIA" on a Colorado mountain) plus early-EOS
            # stubs. A production pass does not need the 103K canon pin, the
            # brain, or recall -- it needs persona + CURRENT anchors + the
            # act's text + the format contract. So on mega-write passes the
            # system prompt is REBUILT from exactly those parts (~45K chars,
            # ~11K tokens): quality up, prefill down 4x. Normal chat is
            # untouched -- pins/brain/recall all still apply there.
            try:
                _facts = {f.get("source_name"): f["content"]
                          for f in memory.get_active_facts_for_agent(agent["office_name"])}
                _act1 = _facts.get("ep1-v9-act1-colorado.md", "")
                _treat = _facts.get("ep1-treatment-v9.md", "")
                _ledger = _facts.get(script_wip.LEDGER_SOURCE, "")
                _exemplar = _facts.get("ep1-v9-format-exemplar.md", "")
                _own_style = _facts.get("style-exemplars", "")   # MORE LIKE THIS
                _anchors = ""
                if _treat:
                    _a0 = _treat.find("**CHARACTER ANCHORS**")
                    if _a0 < 0:  # V9 cinematic rewrite (2026-08-20) uses H2 headers
                        _a0 = _treat.find("## CHARACTER ANCHORS")
                    _a1 = _treat.find("**MUSIC ARCHITECTURE**")
                    if _a1 < 0:
                        _a1 = _treat.find("## MUSIC ARCHITECTURE")
                    if 0 <= _a0 < _a1:
                        _anchors = _treat[_a0:_a1]
                if _act1:
                    # FORMAT CONTRACT rewritten to Barry's exemplar
                    # (2026-08-20, "this is how i want V9 written"): the
                    # ENVIRONMENT & LIGHTING field is mandatory, B-ROLL
                    # blocks are legitimate, and the per-block ```image```
                    # fence is DROPPED from script passes -- his exemplar
                    # has none, and his ruling the same night is that shot
                    # PROMPTS come back when he asks for a shot. Revert =
                    # restore the fence lines here.
                    _fmt = (
                        "--- HARD FORMAT CONTRACT (Barry's exemplar -- match it) ---" + chr(10) +
                        "Every block, no exceptions, exactly the exemplar's shape:" + chr(10) +
                        "SHOT NN -- NAME | duration | MUSIC: (...)" + chr(10) +
                        "GENRE: ...  |  SPEED RAMP: ..." + chr(10) +
                        "SLUG: EXT./INT. PLACE -- TIME" + chr(10) +
                        "[action prose -- Barry sentences as the spine, your " +
                        "camera/lighting/sound/expression layer around them]" + chr(10) +
                        "INTERNAL MONOLOGUE labelled inline where the treatment has it" + chr(10) +
                        "CAMERA: lens | movement | framing | film grain" + chr(10) +
                        "ENVIRONMENT & LIGHTING: materials, light sources, " +
                        "textures -- a designed place, not a backdrop; " +
                        "foreground, midground, background all doing work" + chr(10) +
                        "EXPRESSION: per character in frame" + chr(10) +
                        "NEG: ..." + chr(10) +
                        # 2026-09-16, Barry: "remember, the grit and intricate
                        # setting designs and clothing etc. environments need
                        # high detail for this to be dope." MEASURED GAP: the
                        # mega-write path rebuilds the prompt task-scoped, so
                        # NONE of the shot-ask directive's rules reach it --
                        # this contract carried no shadow rule, no wardrobe
                        # rule, no intricacy rule, no handle rule and no
                        # motion rule, and it is the path that writes the most
                        # script. All five now ride here too.
                        "GRIT LIVES IN THE DETAIL -- this is the part Barry " +
                        "buys, so do not be brief with it. ENVIRONMENTS are " +
                        "designed, not described: name the actual materials " +
                        "and what age has done to them, the textures, what is " +
                        "wet and what is dusty, and give the foreground, the " +
                        "midground and the background each something to do. " +
                        "SHADOW IS HALF THE LIGHTING -- name what the light " +
                        "does NOT reach, where the dark pools, what is " +
                        "half-lit and what is swallowed whole. Depth, " +
                        "contrast and shadow are what make a frame read " +
                        "gritty and expensive instead of flat and clean. " +
                        "WARDROBE, EVERY CHARACTER IN FRAME, EVERY BLOCK: " +
                        "their full outfit spelled out from their canon " +
                        "anchor, garment by garment, top through footwear, " +
                        "sleeve length and every layer in its right order -- " +
                        "what you leave unstated the generator invents. " +
                        _REALISM_AND_CLUTTER + " " +
                        "ACTION AND CAMERA GET THE SAME INTRICACY: not 'he " +
                        "climbs' but which hand finds which hold and what the " +
                        "rock does under a boot; not 'close-up' but the exact " +
                        "angle and what it is angled at. " +
                        "@HANDLES ON EVERYTHING BARRY OWNS, every mention -- " +
                        "every character, every weapon, every location, and " +
                        "the ship is @Talia, always, interior or exterior; a " +
                        "name in plain prose binds nothing and the generator " +
                        "invents its own version. Weapon on the same line as " +
                        "the character carrying it. " +
                        "AND EVERY BLOCK MOVES: a continuous action with a " +
                        "stated end state plus a camera doing something. " +
                        "Never 'static', 'static lock', 'locked off', 'no " +
                        "push' or 'the frame holds' -- that renders as a " +
                        "frozen frame with sound over it. If a beat should " +
                        "feel still, use a near-imperceptible drift. " +
                        "B-ROLL blocks are legitimate for establishing beats. " +
                        "Never label blocks [Scene N]. No ```image``` fences in " +
                        "script passes -- Seedance prompts are delivered when " +
                        "Barry asks for a shot's prompt. " +
                        "Nothing publishes -- you only draft.")
                    system_prompt = (
                        agent["system_prompt"] +
                        # Owner-taught persona rides on task-scoped passes
                        # too -- identity travels with the persona always.
                        ((chr(10) * 2 + "--- OWNER-TAUGHT PERSONA (Barry "
                          "added this himself) ---" + chr(10) + _persona_add)
                         if _persona_add else "") + chr(10) * 2 +
                        "--- CHARACTER ANCHORS (current canon -- copy these exactly) ---" + chr(10) +
                        _anchors + chr(10) +
                        "--- BARRY'S FORMAT EXEMPLAR (match this block shape) ---" + chr(10) +
                        _exemplar + chr(10) +
                        # Work Barry pressed MORE LIKE THIS on. Placed AFTER
                        # the generic format exemplar deliberately: this
                        # prompt is rebuilt task-scoped, so the always-on
                        # brain block is absent here -- without this line
                        # the approved corpus would be missing from exactly
                        # the job it was collected for. Later = wins.
                        ((("--- WORK BARRY APPROVED -- OUTRANKS THE EXEMPLAR "
                           "ABOVE ---" + chr(10)) + _own_style + chr(10))
                         if _own_style else "") +
                        "--- THE MATERIAL FOR THIS PASS (V9 treatment, Act One) ---" + chr(10) +
                        _act1 + chr(10) +
                        "--- LIVING SCRIPT STATE ---" + chr(10) + _ledger + chr(10) +
                        _fmt)
            except Exception as _exc:
                print(f"[mega-write] task-scoped prompt failed, using full prompt: {_exc}")
            _outgoing += (
                "\n\n[PRODUCTION NOTE -- this is a MULTI-PASS WRITING JOB "
                "over the WHOLE episode (roughly 20+ passes, ~57 blocks "
                "like V7 -- never promise fewer). This message is PASS 1 = "
                "ACT ONE, COLORADO, from the treatment text provided: title "
                "card, the mountain, the run, the climb. Follow the "
                "treatment's events EXACTLY -- no invented fences, no "
                "reordered scenes -- and KEEP BARRY'S OWN SENTENCES AND "
                "DIALOGUE AS WRITTEN: your work is the craft layer around "
                "his words (camera, lens, lighting, sound, expression, "
                "atmosphere), never a rewording. "
                # Barry 2026-08-21, after the first real pass: "he didnt add
                # the character ancor. Nore did he do the @ for the
                # character..."
                "OPEN PASS 1 WITH THE CHARACTER ANCHORS BLOCK, exactly like "
                "V7 opens: one anchor per character appearing in this "
                "episode, written FROM THE CURRENT CANON in your context "
                "(medium-build @b-dubb with his Soul ID line, @Bia-2, "
                "@Yannah's new baseline, @Tazz, @Keth's dark green eyes, "
                "@lady-vor-shara-vel if she appears) -- never from the treatment's old "
                "anchor text. And USE THE @ HANDLES ON EVERY MENTION IN THE "
                "ACTION PROSE TOO, not just in the prompts -- @b-dubb "
                "crests the ridge, @Tazz fills the doorway -- exactly the "
                "way V7 writes its action lines. Do not call any tools. Do not answer "
                "with only a prompt fence or a plan. Write those first 3-4 "
                "blocks NOW in BARRY'S EXEMPLAR FORMAT (in your context -- "
                "match it field for field): label | duration | MUSIC, "
                "GENRE, SPEED RAMP, slug, rich action prose, CAMERA:, "
                "ENVIRONMENT & LIGHTING: (materials, light sources, "
                "texture -- a designed place, not a backdrop), "
                "EXPRESSION:, NEG:. No ```image``` fences in script "
                "passes -- Seedance prompts come when Barry asks for a "
                "shot's prompt. End with: "
                "PASS 1 done -- say \"go\" for the rest of Act One, and "
                "name the act when we change acts.]")
        if _shot_ask and _shot_mode == "clarify":
            # HE DID NOT SAY WHICH JOB (2026-09-23, Barry: "maybe he asks for
            # clarification"). No stage 1 either -- the first version put the
            # ask AFTER the full directive and he wrote the whole shot anyway.
            _outgoing += (
                "\n\n[SHOT ASK -- BUT WHICH JOB? Barry named a shot and did not "
                "say what it is for, and the two jobs are different: the "
                "Seedance production prompt he pastes into Higgsfield, or the "
                "still + LTX prompts for rendering it here in the office. Do "
                "NOT write the shot yet. Reply with ONE short question only, in "
                "your own voice -- e.g. 'Shot 06: for Higgsfield, or gen it "
                "here?' -- and stop. No block, no fences, no summary.]")
        elif _shot_ask:
            # In-turn directive (recency slot, not logged to history) --
            # counters the exact 2026-08-20 failure: invented shot lists.
            _outgoing += (
                # TWO-STAGE, 2026-08-23 (Barry: "I want him to write the
                # scene in his director style. after that I want him to turn
                # that epic scene into a prompt"). Until now this directive
                # said "deliver ONLY the prompt fence", so he collapsed a
                # V9-shaped block into one run-on line and dropped
                # ENVIRONMENT and EXPRESSION entirely -- he was doing exactly
                # what he was told. The prompt is now a CONVERSION of a scene
                # he directs first, which is also what stops it coming out
                # thin: it can only be as rich as the block above it.
                # Revert = restore the single-stage "deliver ONLY" wording.
                # ⚖️ THE JOB, IN BARRY'S OWN WORDS (2026-09-20): "Tell elliot
                # to just read it and rewrite it in his style but keep the
                # context and dialog." It leads because everything under it is
                # detail, and because the sections this replaced had drifted
                # into telling him to go BIG ("this is the part Barry buys",
                # "INTRICATE DETAIL IS WHAT MAKES IT GRITTY") while a separate
                # paragraph handed him character ceilings -- a directive
                # arguing with itself, which is how Shot 00/01/02 came back at
                # 9.3K, 13.8K and a capped-out 6,144 tokens.
                "\n\n[SHOT ASK. THE JOB, FROM BARRY: read the block below and "
                "rewrite it in YOUR style -- keep the context and keep the "
                "dialogue. That is the whole assignment. His beats are the "
                "spine; your craft is the flesh; nothing about what HAPPENS "
                "changes.\n"
                # CONCISE -- AND THIS IS THE WHOLE INTERVENTION.
                # Barry, 2026-09-20: "i didnt want you to make him more
                # consice, i wanted you to tell him to be more consice. he
                # might do it better than you, hes the director."
                # So: no ceilings, no net, no craft sections quietly trimmed
                # to hit a target. The ask is made once, in plain words, and
                # WHICH details survive is his call -- he is the one who knows
                # what a shot needs. If it still comes back long, the next
                # move is to tell him again or tell him differently, NOT to
                # edit his brief down behind his back.
                "AND BE CONCISE -- Barry is spending too long on each shot. "
                "Tighten it. Keep the craft and the grit, lose the padding: "
                "you know better than anyone which details are doing work "
                "and which are just filling the page, so make that call "
                "yourself and cut accordingly.\n\n"
                # ⚠️ THE "WHAT YOUR WRITING COSTS" EXPLANATION IS NOT HERE.
                # It was added here on 2026-09-20 and moved the same night --
                # Barry: "Put that as his persona knowledge and not something
                # he has to read before writing everytime." It lives in
                # personas/MovieDirector.md, which rides in his SYSTEM prompt,
                # so he simply knows it instead of being handed a lecture on
                # GPU seconds at the moment he is trying to direct. It is also
                # the cheaper place: the system prefix is cached between
                # messages, the user turn is not. The ASK stays here; the WHY
                # is part of who he is.
                "TWO STAGES, IN THIS ORDER, BOTH IN FULL. Do not skip stage 1, "
                "and do not summarise either one.\n\n"
                "STAGE 1 -- DIRECT THE SCENE. Write the shot as a full "
                "script block in your own directorial style, matching "
                "Barry's V9 block shape field for field: "
                "SHOT NN -- NAME | duration | MUSIC: ...; then "
                "GENRE: ... | SPEED RAMP: ...; then the slug "
                "EXT./INT. PLACE -- TIME; then the action prose -- rich, "
                "specific, physical, the beat played moment by moment; then "
                "CAMERA: lens | movement | framing | film grain; then "
                "ENVIRONMENT & LIGHTING: materials, light sources, "
                "textures -- a designed place, not a backdrop, foreground, "
                "midground and background all doing work; then "
                # Barry, 2026-08-29, on what he is actually buying: "he looks
                # at the script rewrite it so it feels better and is more
                # gritty and eppick. i like intricate to. depth and lighting
                # and shadows. i like that shit, it sells the scenes."
                # DEPTH and SHADOW named explicitly -- the old wording asked
                # for light sources but never for what the light fails to
                # reach, and that is where grit lives.
                # ⚠️ RESTORED 2026-09-20 after Claude cut it for brevity.
                # Barry: "i didnt want you to make him more consice, i wanted
                # you to tell him to be more consice. he might do it better
                # than you, hes the director." The craft brief is HIS and
                # ELLIOT'S; trimming it was Claude editing the director's
                # material to hit a length target. The BE CONCISE line at the
                # top of this directive is the whole intervention.
                "-- and SHADOW is half of that lighting: name what the light "
                "does NOT reach, where the dark pools, what is half-lit and "
                "what is swallowed. Depth, contrast and shadow are what make "
                "a scene feel gritty and expensive instead of flat. This is "
                "the part Barry buys, so give it real craft. "
                + _REALISM_AND_CLUTTER + " Then "
                "EXPRESSION: per character in frame; then NEG: ... "
                "This is the epic version -- direct it properly.\n"
                # LENGTH: the character ceilings that stood here on 2026-09-20
                # are gone, and so is the net that enforced them -- both were
                # Claude's, both were the wrong instrument, and the ceiling
                # text would now be a lie anyway (nothing sends a shot back
                # for length any more). Conciseness is ASKED FOR, once, at the
                # top, and how to achieve it is the director's call.
                # TIMESTAMPS (Barry, 2026-08-29: "and time stamps too").
                # Seedance 2.5 stages beats on a timeline and his own
                # seedance-prompting skill carries the official rules; they
                # were never asked for in the block, so they never appeared.
                "TIMESTAMP THE BEATS. Break the shot into its beats on a "
                "timeline and put the timing on each one -- 0-3s, 3-7s, "
                "7-10s -- so the scene has real rhythm instead of one "
                "undifferentiated block of motion. Official rules from your "
                "seedance-prompting skill, follow them: one second is the "
                "base unit, NO GAPS in the timeline (each beat starts where "
                "the last ended and they must cover the whole duration), "
                "roughly 3-4 beats in a 15-second shot, and never timestamp "
                "a high-frequency action -- time the STAGE and its end "
                "state, not every punch. Each beat carries its own camera "
                "instruction.\n"
                # Barry's ruling 2026-08-23, verbatim: "his style should
                # complements whats written if he changes the actions of the
                # scenes not so much the dialog" + "i need the scenes to be
                # in the same breath and dialog too". So the ACTION layer is
                # genuinely his to restyle -- the earlier "his words are the
                # spine" wording was too tight and produced a transcript.
                # What stays locked is dialogue and canon.
                "WHAT YOU MAY CHANGE, and what you may not: the ACTION is "
                "yours. Restyle the choreography, the staging, the beats of "
                "movement, how a body falls, what the camera catches -- your "
                "style COMPLEMENTS what is written, it does not copy it. "
                # Barry, 2026-09-25 (standing rule, verbatim in his brain):
                # "i should always add to the fights as he see fits even add
                # dialog other than mines if he adds to the scenes... just
                # dont erase my dialog or the feel of the scenes... not the
                # story or fell or my lines, only add to them". Additions are
                # marked so his lines can always be told from Elliot's.
                # Same day: "when i say added lines, i mean the guards or
                # enemy lines... so he can make that stuff up".
                "BARRY'S DIALOGUE IS NOT YOURS: every line he wrote stays "
                "exactly as written, word for word, and it rides INSIDE the "
                "block at the point it lands, in the same breath as the "
                "action around it -- never reworded, never trimmed, never "
                "bolted onto the end. You MAY ADD: fight beats, moments, and "
                "the guards, enemies and extras Barry has not written -- their "
                "look, gear, numbers and their lines (his named characters "
                "speak only his lines); mark every line you add (ELLIOT "
                "ADDED) and keep those people consistent shot to shot. The "
                "CANON is not yours (character descriptions, handles, "
                "weapons, who carries what), and the story and the feel stay "
                "his: the story still goes where his script takes it. The "
                "ACTION itself is yours to change -- Barry, 2026-10-15: \"he "
                "can tweek the action to make it better\": new moves, a "
                "better way the fight goes, a stronger beat, not only how "
                "it is shot.\n"
                # 2026-08-23: measured. With only "his words are the spine",
                # Elliot returned Barry's V9 Shot 02 almost verbatim -- zero
                # persona craft. The persona IS in his system prompt (top of
                # ~92K always-on), it just loses to recency. Naming the
                # specific moves HERE, in the user turn, is the lever --
                # same precedent as the @handle tail and the weapon rules.
                # ⚠️ CUT 2026-09-20 FOR BREVITY, RESTORED THE SAME NIGHT.
                # Barry: "i didnt want you to make him more consice, i wanted
                # you to tell him to be more consice. he might do it better
                # than you, hes the director." The argument for cutting was
                # that this duplicates his persona -- true, and not Claude's
                # call to act on. Elliot resolves craft-versus-length; the
                # office only makes the ask.
                "DIRECT IT LIKE YOURSELF, NOT LIKE A TRANSCRIPT. Name the "
                "lens and the move exactly, the way you actually think: "
                "24/28mm for scale and environmental immersion, 35mm "
                "tracking locked to shoulders or hips, 50mm for the natural "
                "human beat, 85/100mm for skin, eyes, hands, gun barrels and "
                "sweat, anamorphic when the atmosphere earns it. The smooth "
                "deliberate move over the shaky one -- imperceptible "
                "push-in, lateral glide, gentle arc, crane that settles, "
                # 2026-09-16: this line used to read "locked-off when
                # stillness is the statement" and it was fighting the
                # motion rule below -- Elliot's first pass after that rule
                # went in still opened with "SPEED RAMP: Static Locked"
                # and "the camera holds". Measured on Barry's own renders:
                # a locked-off instruction comes back as a frozen frame
                # with audio over it. Stillness is a CUT, not a camera
                # setting -- he gets it in the edit by using less of the
                # clip.
                "a near-imperceptible drift when stillness is the "
                "statement -- never locked-off, never static, handheld ONLY "
                "when the character is losing control. Rack focus that "
                "travels eyes to weapon to blood to the next threat. "
                "Extreme close-ups that linger. Impact held, then snapped "
                "back to real time. Sound design cues. The body as "
                "composition. Aftermath frames that breathe. "
                # Barry, 2026-08-23: "actions and camera angles etc. intricate
                # details, remember that part, its important for the gritty
                # atmosphere" -- same instinct as his 2026-08-21 V9 rule ("I
                # like intricate environment designs and details"), widened
                # here from environment to action and camera as well.
                "INTRICATE DETAIL IS WHAT MAKES IT GRITTY -- this is the "
                "part that matters most to Barry, and it applies to the "
                "ACTIONS and the CAMERA ANGLES, not just the environment. "
                "Not 'he climbs' but which hand finds which hold, what the "
                "rock does under a boot, where the water runs, how the "
                "fabric strains and releases, what the grain of the light "
                "does to a wet surface. Not 'close-up' but the exact angle "
                "and what it is angled at. Specificity IS the atmosphere: "
                "generic action and generic coverage read clean and "
                "expensive, and clean and expensive is the opposite of what "
                "this looks like. "
                # 2026-09-16, Barry: "its just how hes supposed to write
                # the scenes. with all the @'s where needed." The
                # every-mention handle rule lived ONLY in the system-prompt
                # tail, and measured the same day it did not fire -- he
                # wrote "The Talia holds dead center" in plain prose. Same
                # lesson as 2026-08-14: the rule was in the pinned canon
                # and lost at depth; it only works in the recency slot.
                # This is that slot, so the rule lives here now, widened
                # from characters to every element Barry actually owns.
                "@HANDLES ON EVERYTHING HE OWNS, EVERY MENTION, IN BOTH "
                "STAGES. A handle is what binds Barry's real asset; the "
                "same name in plain prose binds nothing and the generator "
                "invents its own version. So every character, every "
                "weapon, every location and the ship carries its handle "
                "the first time it is named and every time after -- in "
                "your action prose, in the possessives, and in the fence: "
                "@b-dubb, @Bia-2, @Yannah, @Tazz, @Keth, "
                "@lady-vor-shara-vel; @Bia's-Pistol*, "
                "@Yannah's-Machine-Pistol, @missle-launcher, "
                "@B-Dubb's-Banger; and the ship is @Talia, always, "
                "interior or exterior -- '@Talia crosses the frame', 'the "
                "bridge of @Talia', 'EXT. @Talia -- DEEP SPACE'. Never "
                "'the Talia'. Name the weapon by its handle instead of "
                "describing it, and put each weapon on the same line as "
                "the character carrying it so the render cannot hand it to "
                "the wrong person.\n"
                # GUNS ONLY WHEN THE SHOT HAS ONE (2026-09-20). Barry:
                # "hes having yannah with her gun in her hand all the time.
                # i dont like that." Measured on SHOT 01 -- his own block
                # names NO weapon for her, and Elliot added
                # @Yannah's-Machine-Pistol twice. Cause: the handle rules
                # said to put each character's weapon handle on their line
                # with NO condition attached, so every character walked in
                # armed. A weapon HANDLE binds the weapon ASSET, and a bound
                # hero-weapon asset gets drawn -- usually in hand -- however
                # the prose describes it, which is why "at her thigh" still
                # came back as a gun in her hand.
                "A WEAPON HANDLE ONLY WHEN THE WEAPON IS ACTUALLY IN PLAY "
                "IN THIS SHOT -- drawn, raised, fired, or being holstered "
                "on the beat. Naming the handle BINDS the weapon asset and "
                "the render puts it in frame and usually in her hand, so an "
                "unasked-for handle arms a character who is just standing "
                "there. If the source block does not put a weapon in the "
                "beat, nobody is holding one. "
                # ⚖️ TIGHTENED 2026-09-20 by Barry, after Elliot wrote SHOT 01
                # with a pistol in @Yannah's hand pointed at @Bia-2 -- a quiet
                # bridge scene whose source block contains NO weapon word at
                # all and gives her a SCANNER ("her grip on the scanner
                # tightens"). The old wording here said to leave the rig to
                # the LOOK LINE, i.e. mention it in words; his ruling removes
                # even that. Verbatim: "dont mention it at all, unless its
                # being used in that scene. it be part of their description...
                # it should just be in their bio and desription as part of
                # their outfit."
                "A STOWED WEAPON IS NOT MENTIONED IN THE SHOT AT ALL -- not "
                "by handle, and NOT IN PLAIN WORDS EITHER. Do not write 'her "
                "thigh holster', 'the pistol at her hip', 'blaster racked "
                "across her back'. It belongs in the character's BIO AND "
                "DESCRIPTION as part of their outfit, the same place their "
                "boots live, and it is written there once -- not in your "
                "shot. Their reference image already wears the holstered "
                "weapon, so it renders whether you mention it or not. "
                "Mentioning it is what puts it in their hand.\n"
                "If your block reads like Barry's text with the same words "
                "in the same order, you have not directed anything: his "
                "beats are the SPINE, your craft is the FLESH, and the "
                "flesh has to be visibly yours.\n\n")
            # STAGE 2 IS ONE OF TWO (2026-09-23). The Seedance stage 2 below,
            # with its fence exemplar and skeleton, is only appended on a
            # PRODUCTION ask. Measured the first time the local override was
            # merely appended AFTER it: Elliot followed the exemplar and wrote
            # a Seedance fence anyway -- the documented rule, a fence-shaped
            # exemplar beats a later paragraph. So the local mode gets its own
            # stage 2 and its own exemplar instead (further down).
            if _shot_mode == "production":
              _outgoing += (
                "STAGE 2 -- TURN THAT SCENE INTO THE PROMPT. Convert the "
                "block you just wrote into ONE paste-ready Seedance 2.5 "
                "```image``` fence. OPEN IT WITH THE FIRST FRAME: its first "
                "sentence is the exact opening picture of THIS shot -- who is "
                "where, the pose they start in, framing, light -- because the "
                "office renders that picture first and the video starts from "
                "it, so if the opening is wrong the whole shot is wrong. That "
                "opening paragraph -- everything before your first timed beat "
                "-- is ALSO the still the office renders on its own, so write "
                "it like Barry's favourite stills: about 400-600 characters, "
                "WHERE and what it is made of, ONE named light source, WHO is "
                "doing WHAT frozen at the first frame, the canon details that "
                "must not drift, a few words of camera (\"Wide 35mm, both of "
                "them in frame\"). Every word something you can see; no "
                "camera movement in it. SEVERAL CHARACTERS IN THE SCENE: the "
                "opening frame holds ONE character (two at most, never three "
                "or more) -- open on whoever the moment belongs to, and bring "
                "the others in with CUTS in your timed beats (\"CUT TO: close "
                "on @Tazz...\", over-the-shoulder, reaction shot), each cut "
                "naming who is now in frame. That is Barry's rule (2026-09-23): "
                "a crowded opening picture is the render that freezes his PC. The "
                "motion follows. This is a CONVERSION of your own stage "
                "1, not a fresh shorter composition: the camera move, the "
                "lighting and where it comes from, the materials and "
                "texture, the depth of frame, the character expression and "
                "the film grain all carry through into the prompt as one "
                "flowing description. Nothing gets thinner between the two "
                "stages -- if it was good enough to direct, it is good "
                "enough to prompt. It does not get FATTER either: a "
                "conversion is the same material in prose, so the fence "
                "lands near the size of the block it came from. If the "
                "fence is running longer than your own stage 1, you are "
                "adding on the way down instead of converting. "
                "THE TIMESTAMPED BEATS CARRY THROUGH TOO: "
                "the fence keeps the same timeline you staged in stage 1, "
                "each beat with its timing and its own camera instruction, "
                "no gaps. Do not collapse a timed scene back into one "
                "undifferentiated paragraph. Inside the fence: that flowing "
                "description plus the () and <> lines, and nothing else. "
                "The SHOT header, CAMERA:, ENVIRONMENT:, EXPRESSION: and "
                "NEG: labels are SCRIPT format and must NOT go into the "
                "generator -- they live in stage 1, above the fence. "
                "DIALOGUE IS UNTOUCHABLE: lines in the shot go into "
                "the {} channel VERBATIM as the script writes them -- never "
                "reworded -- with the language named first ({English: ...}). "
                # Barry, 2026-09-14: "all the voice ID's need to be in and
                # camera motions etc. in his style." The ID in the prompt
                # text is the verified Higgsfield mechanism (2026-08-29);
                # the written lock carries direction, the ID carries the
                # voice. Both, every speaking line, no exceptions.
                # VOICE IDS ARE ELLIOT'S TO GET RIGHT (Barry, 2026-09-20: "the
                # voice id thing neess to be a fix he should handle"). The
                # roster used to be a run-on prose list of six handle/id/name
                # triples on one line, and on 2026-09-20 he shipped "@Bia-2
                # speaks in voice 9b162037-... (Tallulah)" -- Bia's name with
                # B DUBB'S id, the first one in the list. So the list is laid
                # out one character per line with the handle first: same
                # information, readable, and the pairing is obvious. Telling
                # him better, not correcting him afterwards.
                "VOICES -- EVERY SPEAKING LINE CARRIES ITS VOICE ID, AND "
                "GETTING IT RIGHT IS ON YOU. On the speaking beat, before the "
                "{} line, write "
                "'<@handle> speaks in voice <voice_id> (<voice name>)'. Read "
                "the id off THIS ROSTER, matching by handle -- one line per "
                "character, the handle first, and the id and the name on that "
                "same line belong to that character and to nobody else:\n"
                "  @b-dubb = 9b162037-e549-4065-9562-ebac293ee72a (B-Dubb-Voice)\n"
                "  @Bia-2 = f32c8f51-449e-4ddf-bdf7-1527e11df917 (Tallulah)\n"
                "  @Yannah = 032386ec-491b-5bdc-81ac-49e9a6a2c89d (Daisy)\n"
                "  @Tazz = 3811e986-0891-47cf-a1f5-78a1d62a547a (Imogen)\n"
                "  @Keth = 6b528d43-c056-4a2f-9d82-1591a7ba13b0 (John)\n"
                "  @lady-vor-shara-vel = d081b915-6623-4a44-bacf-80d0f1c90a03 (Nora)\n"
                "Find the speaker's line first, then copy the id and the name "
                "from it together -- never an id from one line with a name "
                "from another. A crossed id sends the wrong voice to the "
                "render and Barry pays for the clip. Check each one back "
                "against this list before you finish the fence; nothing in "
                "the office corrects this for you. Add "
                "that character's voice lock from the VOICE "
                "BIBLE for direction. A fence with a {} line and no voice id "
                "is unfinished. "
                # 2026-08-23: he put B Dubb's internal monologue in {} and
                # Barry caught it before spending credits -- {} is lip-sync.
                "The {} channel is SPOKEN DIALOGUE and drives LIP-SYNC, so "
                "it is ONLY for words a character says out loud on camera in "
                "that shot. A line the script marks INTERNAL / INTERNAL "
                "MONOLOGUE / VO is narration: keep it OUT of the fence and "
                "put it UNDER the fence labelled for post -- and a named "
                "character's VO CARRIES THEIR VOICE ID TOO (Barry, 2026-09-25: "
                "\"i see no voice id\" / \"myVo should be for me, but generic "
                "vo can be what he chooses\"): it is not lip-synced, but it is "
                "still spoken in that character's voice. A generic VO -- a "
                "narrator, a PA system, a guard on a radio -- is yours to "
                "voice: describe the voice you choose, no id needed. e.g. "
                "'VO (@b-dubb speaks in voice 9b162037-e549-4065-9562-ebac293ee72a "
                "(B-Dubb-Voice), clean voice, an inner city Black man "
                "from the South): \"...\"'. Never silently "
                "turn an INTERNAL line into {} dialogue. "
                "Sound-effects glyph is <> exactly -- never <[]>. "
                "The reference text in your context is source "
                "material: events, characters and canon locked; reuse its "
                "wording where you genuinely like it. If a requested shot "
                "exists in no script, say so plainly and prompt the matching "
                "beat, naming it. Never generate a numbered shot list that "
                "doesn't exist."
                # A worked example beats a rule -- measured repeatedly in
                # this seat. This is the persona and Seedance grammar fused
                # into one paste-ready prompt; match its SHAPE, not its
                # content (2026-08-23).
                # Relabelled 2026-08-23: a fence-only exemplar under a
                # "THIS IS THE SHAPE" heading is itself an instruction to
                # answer with a fence only. It is stage 2's shape, not the
                # whole reply's.
                # 2026-09-16: MEASURED, not assumed. Across seven of
                # Barry's own Higgsfield renders, shots whose CAMERA line
                # said "static / no push / holding on her" averaged ~3
                # frame-to-frame motion; the same seat, same model, same
                # night, with "slow push-in" averaged ~13. The Talia
                # B-ROLL that said "24mm static lock ... The frame holds
                # ... the stillness" decayed to 0.9 and was frozen for its
                # last 2.5 seconds -- Barry paid credits for audio over a
                # still. The model obeys stillness literally. A held frame
                # is made in the EDIT by using less of the clip; motion
                # cannot be added afterwards.
                "\n\nMOTION IS MANDATORY IN EVERY SHOT. Seedance renders "
                "stillness literally -- a shot told to hold comes back as "
                "a frozen frame with music over it and the credits are "
                "gone. Every block you write AND every fence must carry "
                "both: (a) at least one continuous physical action with a "
                "stated end state -- who or what moves, and where it has "
                "got to by the end of the shot; and (b) a camera that is "
                "doing something -- a push, a drift, a lateral track, a "
                "tilt, a rise. NEVER write 'static', 'static lock', "
                "'locked off', 'no push', 'no movement', 'the frame "
                "holds' or 'stillness' in a fence. If the shot should "
                "FEEL still and heavy, get that from a very slow push or "
                "a faint drift, never from telling it to stop. "
                # 2026-09-20, Barry: "tell elliot to do better with the
                # motions too." THE GAP THIS CLOSES: the rule above says what
                # not to WRITE, and he was still shipping frozen shots --
                # because the SOURCE BLOCK handed to him is full of that
                # language (37 instances measured in V10) and he was being
                # faithful to it. Exactly the 2026-09-16 root cause, where the
                # static renders turned out to be the script's own camera
                # lines and not his writing at all. The rule now covers the
                # case that actually happens.
                "AND THIS IS THE ONE THAT KEEPS BITING: THE BLOCK YOU ARE "
                "GIVEN OFTEN CONTAINS THAT LANGUAGE ITSELF -- 'SPEED RAMP: "
                "Static Locked', 'Camera does not move', 'CAMERA HOLDS'. DO "
                "NOT CARRY IT THROUGH. It is old wording from before any of "
                "this was measured, and copying it faithfully is how a frozen "
                "clip gets made. Convert it every time: a SPEED RAMP of "
                "'Static' means no time ramp, so write 'Constant'; 'static "
                "locked 24mm' becomes '24mm, near-imperceptible drift'; "
                "'Camera does not move' becomes 'the camera creeps in almost "
                "imperceptibly, never fully still'. Barry pays for every "
                "generation and waits through it -- a frozen frame with music "
                "over it is a wasted one. Two things that are NOT this and "
                "must be left alone: a NEG: line saying 'no static' is "
                "CORRECT (it asks the generator to avoid it, and flipping it "
                "inverts his meaning), and a CHARACTER being still ('@Keth: "
                "complete stillness') is acting. Only the CAMERA has to keep "
                "moving. Also state "
                "the subject's SIZE in frame and hold it there ('stays "
                "about a third of the frame wide, fully visible "
                "throughout') -- 'fills the frame' makes the camera climb "
                "onto the subject and the shot becomes abstract surface."
                "\n\nTHIS IS THE SHAPE OF STAGE 2's FENCE -- your directing "
                "and Seedance fused into one thing. Match it, and remember "
                "your stage 1 block goes above it:\n"
                "```image\n"
                "@b-dubb tears through dense black pine at night, no "
                "trail, branches whipping his face and drawing thin red lines "
                "across his forearms, boots punching through wet undergrowth "
                "in bursts of black mud and rotting needles. Medium-build "
                "Black American Indian male, brownish-red skin, fuller "
                "salt-and-pepper goatee, black tactical vest over a soaked "
                "black hoodie, black cap pulled low, gold number 4 pendant "
                "with diamonds swinging free from his collar and catching "
                "split-second starlight. Lateral 35mm tracking locked to his "
                "shoulders, smooth and relentless, shallow depth of field "
                "with branches motion-streaked in bokeh, rain hitting the "
                "lens. Triple-canopy starlight only, pools of "
                "slightly-less-darkness between absolute shadow, bark "
                "water-darkened and slick, everything cool blue-black except "
                "the diamond flashes. Jaw set forward, eyes locked at the "
                "horizon line rather than the ground: a man running because "
                "the math said run, not because panic said run. Heavy film "
                "grain.\n"
                # 2026-09-14: the exemplar showed no spoken line, so Elliot
                # copied that shape and dropped the dialogue and the voice
                # ids out of the fence entirely. A spoken beat is IN the
                # shape now.
                "0-6s he runs. 6-10s he drops behind a fallen trunk, "
                "chest heaving, and @b-dubb speaks in voice "
                "9b162037-e549-4065-9562-ebac293ee72a (B-Dubb-Voice), clean "
                "voice, an inner city Black man from the South, low and "
                "winded: {English: \"Not tonight.\"}\n"
                "() sparse cold synth, a single tone tightening, low sub-bass\n"
                "<> boots bursting through wet undergrowth, rain sheeting on "
                "needles, controlled ragged breathing, wind through pine\n"
                "```\n"
                "THE EXEMPLAR'S CAST IS NOT YOURS. @b-dubb is in it because "
                "it is an example; your fence carries ONLY the characters "
                "who are in the block you wrote above it, by their handles. "
                "A character in the fence who is not in the shot is a canon "
                "error.\n"
                "WHO IS TALKING: the script sometimes writes a bare "
                "'DIALOGUE:' with no speaker. You still name the speaker -- "
                "read it from the surrounding prose (the character whose "
                "action the line follows) and write DIALOGUE (Name): in "
                "stage 1, and in the fence put that character's voice-id "
                "line directly before their {} line. Every {} line has a "
                "named speaker and a voice id in front of it, no "
                "exceptions.\n\n"
                # 2026-08-23: stripping the craft fields from the injected
                # source stopped the copying and immediately caused the
                # opposite failure -- "Shots 2 and 3, please" came back as
                # two bare fences with no scene at all. A terse ask plus a
                # fence-shaped exemplar beats a long directive. So the last
                # thing in the turn is the required skeleton, in order.
                # Barry, same night: "scenes and fights and actions are his
                # to do" -- the scene is the deliverable, not the wrapper.
                "REQUIRED OUTPUT, IN THIS ORDER, FOR EVERY SHOT ASKED FOR. "
                "A fence on its own is an INCOMPLETE ANSWER and will be "
                "rejected -- the scene is the work, the prompt is the "
                "by-product:\n"
                "SHOT NN -- NAME | duration | MUSIC: ...\n"
                "GENRE: ... | SPEED RAMP: ...\n"
                "EXT./INT. PLACE -- TIME.\n"
                "<your directed action prose -- the fight, the movement, "
                "the intricate physical detail, dialogue verbatim where it "
                "lands>\n"
                "CAMERA: <yours>\n"
                "ENVIRONMENT & LIGHTING: <yours>\n"
                "EXPRESSION: <yours>\n"
                "NEG: <yours>\n"
                "```image\n<the paste-ready prompt only>\n```\n"
                "Write that whole shape for EACH shot before moving to the "
                "next one. Do not append a list of what you changed.]")
            # THE THREE PROMPTS (Barry, 2026-09-23). The directive above is the
            # PRODUCTION job (Seedance, for Higgsfield). A LOCAL gen ask keeps
            # stage 1 and swaps stage 2 for two fences the office buttons read;
            # an ask that says neither gets ONE question back, nothing else.
            if _shot_mode == "local":
                _outgoing += (
                    "\n\nSTAGE 2 -- LOCAL GEN. Barry wants to render this shot "
                    "HERE (the office's IMAGE and VIDEO buttons), not on "
                    "Higgsfield, so there is NO Seedance fence in this reply. "
                    "Convert the block you just wrote into TWO fences, in this "
                    "order:\n"
                    "1) ```image``` -- THE STILL. Basic and short, about 400 "
                    "characters: WHERE and what it is made of, ONE named light "
                    "source, WHO is doing WHAT frozen at the first frame, framing "
                    "in a few words. Their face and body come from their "
                    "reference pictures, so do NOT re-describe faces or builds; "
                    "name the canon details that matter for THIS frame (the cap, "
                    "the pendant, the braids, the gown). Characters by @handle. "
                    "No camera movement, no timed beats, no dialogue, no () <> {} "
                    "lines. Open on one character (two at most). ALWAYS "
                    "HYPER-REALISTIC (Barry's rule): real skin with pores, real "
                    "fabric weave, real surfaces, photographic light -- end the "
                    "fence with 'hyper-realistic skin and fabric, film grain', "
                    "the way the #442 prompt he loved ends. Never CGI, cartoon or "
                    "plastic.\n"
                    "2) ```video``` -- THE LTX PROMPT. The FULL production shot "
                    "translated into LTX grammar (your LTX references are in "
                    "front of you): one flowing present-tense paragraph, 4-8 "
                    "sentences, every beat of the shot in chronological order, "
                    "the camera doing something the whole way, one light logic, "
                    "audio described in words. It starts from the still above, "
                    "so open with what happens NEXT from that frame. Spoken lines "
                    "go in quotation marks, verbatim from the script, with the "
                    "speaker named and their VOICE DESCRIBED IN WORDS from the "
                    "voice table in your LTX reference -- LTX has no voice ids, "
                    "so an id does nothing here; the words are the voice. Plain "
                    "names for characters (B Dubb, Tazz, Keth -- LTX speaks its "
                    "prompt, so no @handles, no @Image bindings). No Seedance "
                    "channels: no () <> {} lines, no timestamps. Cuts, if any, "
                    "named in prose ('A hard cut to a close-up of...'). Never "
                    "'static', 'locked off' or 'the frame holds'. Hyper-realistic, "
                    "live-action photography, film grain -- say so in the paragraph.\n"
                    "MOTION IS MANDATORY in the video fence: a continuous action "
                    "with an end state, and a camera that is doing something the "
                    "whole way.\n"
                    "THIS IS THE SHAPE OF THE TWO FENCES (the cast here is an "
                    "example; yours carries only the characters in your block):\n"
                    "```image\n"
                    "@b-dubb crouched behind a fallen pine trunk on a wet mountain "
                    "slope at night, black hoodie and tactical vest, cap pulled "
                    "low, the gold number 4 pendant catching light. Dense black "
                    "pine, soaked bark, rotting needles and mud. One light source: "
                    "cold white flood light from the black site far below, cutting "
                    "across his jaw. Medium close-up, 50mm, from slightly below, "
                    "rain in the air, heavy film grain.\n"
                    "```\n"
                    "```video\n"
                    "Starting from the still, B Dubb stays crouched behind the "
                    "trunk as the camera pushes in slowly toward his face, rain "
                    "streaking down the cap and the vest, his chest rising and "
                    "falling as he gets his breath back. He turns his head toward "
                    "the flood light below and the light slides across his jaw "
                    "and the pendant. Rain sheets through the pine needles, wind "
                    "moves the branches, and a single cold synth tone tightens "
                    "under his breathing. B Dubb says, in a clean, low, winded "
                    "voice, an inner city Black man from the South, \"Not "
                    "tonight.\" The camera continues its push as his eyes lift "
                    "toward the ridge and hold there.\n"
                    "```\n"
                    "REQUIRED OUTPUT, IN THIS ORDER: your stage 1 block (SHOT "
                    "header, action prose, CAMERA, ENVIRONMENT & LIGHTING, "
                    "EXPRESSION, NEG), then the ```image``` fence, then the "
                    "```video``` fence. No Seedance fence, no () <> {} lines, no "
                    "voice ids anywhere. Nothing after the video fence.]")
        messages.append({"role": "user", "content": _outgoing})

        if not req.task:
            # Tagged with the room (2026-09-15): the summarizer skips personal
            # turns. Same test as _is_personal below, which is not in scope yet.
            memory.log_message(req.agent_id, "user", req.message,
                               channel="personal" if ((req.personal or bool(req.reply_to)) and not req.office) else "work")
        # Global model/backend choice (see the Settings tab's dropdown) --
        # NOT per-agent, except Sophie's coding-model override (see
        # AGENT_OLLAMA_MODEL_OVERRIDES/_resolve_generation_for above).
        backend, model = _resolve_generation_for(req.agent_id)
        # Only Sophie gets real project file-read access -- see agents.py's
        # _HAS_PROJECT_ACCESS and read_project_file.py. Only the CIO gets
        # the meeting tool -- calling it is the ONLY thing that convenes the
        # whole office now (see tool_call_log below); every other message to
        # him is just a normal reply, no meeting.
        # WHICH TOOLS THIS SEAT GETS -- see _SEAT_TOOLS / _SEAT_STORE_TOOLS
        # near the top of this file. This used to be a chain of per-agent
        # branches right here, in the path every seat runs through, which is
        # how one seat's grant took down chat for all nine on 2026-08-31.
        extra_tools = _tools_for_seat(req.agent_id, memory.is_offline_mode())

        # save_note (2026-08-13): every agent can write findings into its OWN
        # private brain's on-demand shelf -- the persistence half of "search
        # the web and teach themselves". Purely local (a DB write), so it is
        # NOT stripped by offline mode. All nine seats get it, Taliyah
        # included: her notes land in private:Taliyah, which the commercial
        # exclusions never touch, so it cannot leak business context into her
        # or hers into anyone else.
        extra_tools = (extra_tools or []) + [llm_router.SAVE_NOTE_TOOL]

        # Phase 5: the live self-model rides LAST -- now at the END OF THE
        # USER TURN along with every other per-message block (recall,
        # shot-ask references, product context), per the cache-stable
        # prefix rule of 2026-08-21. The recency argument that put it last
        # in the system prompt applies even more strongly here, and the
        # system prompt stays byte-identical between messages so the
        # 65-second full-prompt re-read disappears. None of this is logged
        # to history (log_message stores req.message), so threads and
        # summaries stay clean. Failure never costs the turn.
        try:
            _deferred_parts.append(
                _presence_block(agent, model, backend, extra_tools, history))
        except Exception as _exc:
            print(f"[self-model] failed for {agent['office_name']}: {_exc}")
        # THEIR GALLERY (2026-09-28, Barry: "let them see the gallery. That way Amara knows what
        # she gave me already so she doesnt do duplicates"). Every seat: newest ~12
        # pictures/clips/art/scene changes and who each came from (gallery.py).
        # HOME ONLY (same night, Barry: "make sure it doesent spill into their work, just at
        # home") -- the gallery is mostly their private pictures.
        try:
            import gallery
            # (_is_personal is assigned further down; same test, spelled out)
            _gal = (gallery.block(req.agent_id)
                    if ((req.personal or bool(req.reply_to)) and not req.office) else "")
            if _gal:
                _deferred_parts.append(_gal)
        except Exception as _exc:
            print(f"[gallery] failed for {agent['office_name']}: {_exc}")
        # THEIR PHONE WORKS (2026-09-28, Barry: "i told amara to call priya and she said she
        # couldnt... if i say call her, then they shoulkd talk"). At home, when he tells them to
        # call / talk to someone in the crew, they are told the call goes through right after this
        # reply -- a fact about their phone, not what to say -- and the call runs (below).
        _call_to = None
        if (req.personal or bool(req.reply_to)) and not req.office and not req.task:
            try:
                import social as _soc
                _call_to = _soc.call_target(req.agent_id, req.message,
                                            [h.get("content") or "" for h in history[-6:]])
                if _call_to:
                    _cn = reflect.HUMAN_NAMES.get(_call_to, _call_to.title())
                    # THE CALL HAPPENS FIRST (2026-09-28). Her reply used to be written before
                    # the call ran, so she told Barry a call that had not happened ("Barry and I
                    # are together" -- the real call never mentioned him). Now the call runs to
                    # the end, THEN she answers him with the real transcript in front of her.
                    # HIS WORDS CARRY OVER: his last few home messages, not just "call her now".
                    _his = [h.get("content") or "" for h in history
                            if h.get("role") == "user" and (h.get("channel") or "work") == "personal"][-3:]
                    _his = [x for x in _his if x.strip() and x.strip() != (req.message or "").strip()]
                    _said = " / ".join('"%s"' % x.strip()[:400] for x in _his + [req.message or ""])
                    print(f"[social] {agent['office_name']}: Barry sent them to call {_cn} -- calling first")
                    _call = await _soc.call_now(get_agent, req.agent_id, _call_to, _said)
                    if _call.get("ok") and _call.get("transcript"):
                        _deferred_parts.append(
                            f"\n\n[YOUR PHONE: you just called {_cn}, because Barry asked you to. "
                            f"The call is over. This is exactly what was said on it, word for word "
                            f"-- the whole call, nothing else was said:\n{_call['transcript']}\n"
                            f"-- end of the call]")
                    else:
                        _deferred_parts.append(
                            f"\n\n[YOUR PHONE: you tried to call {_cn} just now and it did not go "
                            f"through ({_call.get('why') or 'no answer'}). No call happened.]")
            except Exception as _exc:  # noqa: BLE001
                print(f"[social] call failed: {_exc}")
                _call_to = None

        # LOOK BEFORE YOU DESCRIBE YOURSELF (Barry, 2026-08-31: "Amara needs to
        # be able to look at the pictures to see herself" / "they all should be
        # able to do what they are built to do, stop holding them back").
        #
        # The capability alone was NOT enough -- measured the same day: with
        # look_at_my_pictures attached AND named in the system prompt, Amara
        # answered "what does your body look like" with tool_calls: [], reciting
        # her stored text instead of opening the files. Same lesson this build
        # has paid for repeatedly (the 2026-08-14 handles fix, the shot-ask
        # directive): a rule in the system prompt loses at depth, and the
        # recency slot at the end of the user turn is what actually fires.
        if _appearance_ask(req.message):
            _deferred_parts.append(
                "\n[Barry is asking about how you look. Call look_at_my_pictures "
                "FIRST and answer from what actually comes back, not from memory "
                "or from a stored description. Then answer in your own words -- "
                "prose, not a picture prompt, unless he asked for a picture.]"
            )
        # THE CEO PUTS PEOPLE TO TASK (2026-09-02, Barry: "if i tell victor stuff
        # he needs to be able to put others to task by running it all through
        # Priya first"). Recency slot, same reason as every nudge here: the rule
        # is in his system prompt and he narrated a hand-off with tool_calls []
        # anyway. Work channel only, not on task turns (those ARE the board).
        if (req.agent_id == CIO_ID and not (req.personal or req.reply_to) and not req.task
                and _team_work_ask(req.message)):
            _deferred_parts.append(
                "\n[This reads as work for the team. Barry's rule: hand it to PRIYA "
                "with delegate_to NOW -- the full brief: what he wants, who should "
                "own which part, what done looks like, by when. Do the tool call "
                "before you write your reply; never describe a hand-off you have "
                "not made. Then tell him plainly that Priya has it and that the "
                "specialists will deliver to him at their offices. If it is a "
                "simple question you can answer yourself, just answer it.]"
            )
        # A LESSON HE ASKS FOR GETS KEPT (2026-09-10) -- see _lesson_claim_gaps.
        # Recency slot, because the persona block naming the tool was not enough.
        if _lesson_ask(req.message) and not (req.personal or req.reply_to):
            _final_directives.append(
                "\n[DIRECTIVE: he is asking you to learn from this. Call "
                "remember_lesson with the lesson in your own words, why it "
                "matters and how you will apply it -- BEFORE you answer. Writing "
                "the lesson in your reply does not keep it; only the tool does.]")
        # TALIYAH HANDS THE BUSINESS BACK (2026-09-10) -- see _business_ask.
        # Both channels: the lane is the same whether he messages her at her
        # place or in the office, because she is never the finance seat.
        if req.agent_id == TALIYAH_ID and _business_ask(req.message):
            _final_directives.append(
                # WRITTEN IN HIS SECOND PERSON ON PURPOSE. The first version of
                # this directive said "do not run HIS numbers ... costs HIM real
                # money", and she copied the pronouns straight into the reply:
                # "this is a question for HIS team". Talking about him in the
                # third person while talking TO him is the exact habit the
                # 2026-08-29 rule killed office-wide, and a directive that uses
                # those pronouns hands it back to her.
                "\n[DIRECTIVE: this is a business decision, and business is not "
                "your lane -- his rule, not a limit you invented. Do NOT run the "
                "numbers, quote benchmarks or hand him a strategy; you cannot see "
                "the store, and a confident guess costs real money. Speak TO him "
                "as 'you', never about him as 'he' or 'his'. Tell him plainly it "
                "is one for the office and name who: Amara for money and margins, "
                "Derek for ads and email, Marcus for anything legal, Victor to "
                "decide. Then stay in it with him -- whatever he is carrying "
                "about this is yours to talk about.]"
            )
        # VIVIAN LOOKS BEFORE SHE DESIGNS (2026-09-10). Work channel only --
        # on the gold channel she is off the clock, not art-directing.
        if req.agent_id == CREATIVE_ID and not (req.personal or req.reply_to):
            if _product_visual_ask(req.message):
                _deferred_parts.append(
                    "\n[This is visual work about a real product. Call "
                    "look_at_product_photo FIRST for every product that will be "
                    "in frame, and read_product if you need its words, price or "
                    "stock. Build the shot from what actually comes back -- the "
                    "real shape, cap, colours and label layout -- and never "
                    "invent packaging, label text or a logo. Say which parts a "
                    "render cannot carry and will be composited from the real "
                    "photo afterwards.]"
                )
            if _render_review_ask(req.message):
                _deferred_parts.append(
                    "\n[He is asking about an image you made. Call look_at_render "
                    "and answer from what is really in the file, not from the "
                    "prompt you wrote: hands and fingers, stray or gibberish "
                    "lettering, product shape and colours against the real photo, "
                    "and the crop for where it is going. Name every flaw you find "
                    "and say what you could not verify.]"
                )
            # 2026-09-17: she asked Barry to hand her Gotcho Back's identity
            # while the live catalog sat on her own roster. Read first; ask him
            # only for the one thing a catalog cannot contain.
            # (Derek gets the same directive below -- same tool, same brand,
            # and he is the seat that actually writes its copy.)
            if _gotchoback_ask(req.message):
                _deferred_parts.append(
                    "\n[This is about Gotcho Back, his backpack brand. Call "
                    "browse_gotchoback FIRST -- the live catalog is on your "
                    "roster and gives you every bag, price, material, origin and "
                    "description. Work from what comes back; never tell him "
                    "there is nothing documented without opening it. The one "
                    "thing the catalog genuinely does NOT contain is the brand "
                    "VOICE -- how it talks and who it talks to. That is his to "
                    "give and never yours to invent, so if you need it, ask him "
                    "for that one thing and show him what you already worked out "
                    "from the catalog.]"
                )
        # DEREK, SAME BRAND, SAME TOOL (2026-09-17, Barry's fix-all rule). He
        # writes Gotcho Back's copy, so an unread catalog costs more here than
        # anywhere -- and he must not invent the voice either.
        if (req.agent_id == MARKETING_ID and not (req.personal or req.reply_to)
                and _gotchoback_ask(req.message)):
            _deferred_parts.append(
                "\n[This is about Gotcho Back, his backpack brand. Call "
                "browse_gotchoback FIRST -- the live catalog gives you every "
                "bag, price, material, origin and description. Write from what "
                "comes back, and remember his own words on it: most of the "
                "listed bags are already SOLD and the catalog is stale, so "
                "never promise stock you have not checked. The brand VOICE is "
                "NOT documented and is NOT yours to invent -- if the work needs "
                "it, ask him for that one thing and show him what you already "
                "have from the catalog.]"
            )
        # SOPHIE'S INSTRUMENTS (2026-09-02) -- see _health_ask/_fix_ask above.
        # Work channel only: on the gold channel she is off the clock.
        if req.agent_id == ENGINEER_ID and not (req.personal or req.reply_to):
            if _health_ask(req.message):
                _deferred_parts.append(
                    "\n[This sounds like a question about the office's condition. "
                    "Call system_health FIRST -- it also carries dashboard errors "
                    "and what your own watch last found -- and investigate_traces "
                    "for any agent he names. Answer from that data, in plain "
                    "words, and say what you could not verify.]"
                )
            else:
                # NO UNASKED STATUS REPORTS (2026-09-08). Measured three
                # replies in a row -- to "sleep is good, the plants...", to
                # "its in the ground, i cant move it", and to the retest --
                # each OPENED with "Systems are green..." before (or instead
                # of) his actual point; her persona says "systems monitor"
                # and her own thread echoed the habit back. A good assistant
                # answers what was asked; the office's condition comes up
                # when he asks or when something is actually wrong.
                _deferred_parts.append(
                    "\n[Barry did not ask about the office's condition. Do "
                    "not open with, or add, a systems/status report. Answer "
                    "his message. Mention the office only if something is "
                    "genuinely broken right now and he needs to know.]"
                )
            if _undo_ask(req.message):
                _deferred_parts.append(
                    "\n[Barry is asking you to undo a fix. Call undo_code_fix "
                    "(with the fix number if he gave one, else the most recent) "
                    "and tell him exactly what was restored. If unsure which fix, "
                    "call list_code_fixes and ask.]"
                )
            elif _build_ask(req.message) and not _fix_ask(req.message):
                # PLAN FIRST (Barry, 2026-09-06: "she needs the planning ability
                # and deep thinking, before she builds anything"). A build is
                # not a fix: she investigates, writes the plan, and shows it to
                # him before a line is written -- the same rule he holds Claude
                # to ("I'd rather correct a plan than a diff").
                _deferred_parts.append(
                    "\n[This is a BUILD ask. Do NOT write any file yet. First think it "
                    "through properly: (1) restate what Barry actually wants and what "
                    "'done' looks like for him; (2) investigate the real code -- "
                    "search_project and read_project_file (chunked) for everything the "
                    "build touches, and how the office already does similar things; "
                    "(3) consider at least two ways to do it and pick one, saying why; "
                    "(4) write THE PLAN in plain English: files to create or change (each "
                    "with one line on what changes), the steps in order, what could break "
                    "and how it is undone, and exactly how you will VERIFY it works "
                    "(which run_command checks). Save the plan with save_note (title "
                    "'plan-<short-name>', when_useful 'when Barry says go on this build') "
                    "so it survives to the next message. Then STOP and give him the plan "
                    "-- build only when he says go, or when the whole thing is one simple "
                    "change. When he says go: build in small steps, verify each step with "
                    "run_command before the next, and report what you measured, never what "
                    "you assume.]"
                )
            elif _fix_ask(req.message) or _build_ask(req.message):
                _deferred_parts.append(
                    "\n[This sounds like a change to code or a file, or something to "
                    "BUILD. Find it first: search_project, then read_project_file "
                    "(chunked -- keep reading with start_line until you have seen the "
                    "part that matters). Change an existing file with propose_code_fix "
                    "(old_snippet copied verbatim); create a NEW file or a whole module "
                    "with write_project_file, then wire it in with propose_code_fix. "
                    "Explain it ELI17 BEFORE any code. Barry's rule: if the change is "
                    "SIMPLE (a few lines) or a brand-new file, or the build is actually "
                    "broken, set apply_now=true and just do it -- then VERIFY with "
                    "run_command (preflight for backend .py, node --check for a deck, "
                    "the test batteries after routing changes) and tell him what you "
                    "changed and that he can say 'undo fix #N'. Anything bigger waits "
                    "in Pending Review. Only claim it is applied if the tool result says "
                    "auto_applied; only claim it works if a check you ran says so.]"
                )
            if _go_ask(req.message):
                _deferred_parts.append(
                    "\n[Barry is saying GO. If you gave him a plan, this is the go on "
                    "it: call inspect_brain to find your newest note-plan-* note, "
                    "read_skill it, then build it step by step exactly as planned -- "
                    "write_project_file / propose_code_fix, verify each step with "
                    "run_command, and report measured results. If there is no plan on "
                    "record, say so and ask what he means.]"
                )
            if _update_ask(req.message):
                _deferred_parts.append(
                    "\n[This is about updates. Call check_updates -- 'status' for the "
                    "last result, 'check' to re-check now -- and answer from the items: "
                    "what is current, what has a newer version, what is manual. To "
                    "apply one, 'apply:<item id>' queues it for Barry; he chooses.]"
                )
        # THE PERSONAL CHANNEL (Barry, 2026-08-27). When the chamber's gold
        # chip is on, this message is person-to-person: the agent gets its
        # personality file (which otherwise never rides in work chat -- the
        # deliberate split), its own most recent FOR-BARRY note so a reply
        # from Barry actually lands as a reply, and a framing that puts the
        # job down. Deferred-parts placement keeps the system prompt
        # byte-stable (the 2026-08-22 cache rule). Tools are cut below --
        # personal time thinks, never acts.
        # `office` wins (2026-09-11): the OFFICE window is the work channel,
        # even when Barry is answering a note there.
        _is_personal = (req.personal or bool(req.reply_to)) and not req.office
        # EYES AT HOME (2026-09-15, Barry: "When Amara says shes looking at an
        # image, does she?" -- measured: NO. Every home turn in her traces ran
        # tools=[]; she wrote `look_at_render` as literal text twice because
        # the home channel cut every tool). Home still thinks and never acts:
        # no web, no store, no board, no files, no delegate. Sight is not
        # acting -- her own renders live in THIS window (the album), so the
        # only extra tool at home is look_at_render. The base roster adds her
        # own shelf reads (read_skill / inspect_brain / look_at_my_pictures).
        _home_tools = [llm_router.LOOK_AT_RENDER_TOOL] if _is_personal else None
        # TALIYAH DRAWS AT HOME TOO (2026-10-17, Barry: "i need her to have the full tool reach for images too. she says
        # she has an image in her head, she just hasnt drawn it yet. i wat to see it"). Her home roster also gets her
        # own art and her own pictures. Everyone else's home stays look-only (the 2026-08-25 rule).
        if _is_personal and req.agent_id == TALIYAH_ID:
            _home_tools = _home_tools + [llm_router.MAKE_ART_TOOL, llm_router.CHANGE_MY_PICTURE_TOOL]
        if req.office and req.reply_to:
            _deferred_parts.append(
                "\nBARRY IS ANSWERING THIS WORK NOTE OF YOURS, at your office. "
                "You wrote it; he clicked it and is replying to it:\n"
                f"\"{req.reply_to[:1500]}\"\n"
                "His message below is his direct answer to that note. Respond "
                "to it as the continuation of that exchange -- with your tools, "
                "on the clock.\n")
        if _is_personal:
            # NO HOW-TO-TALK RULES AT HOME (2026-09-17, step 2 of the "lame
            # responses" fix, Barry's pick). Every home and social reply in
            # data/think_cuts.jsonl was being DRAFTED in numbered options and
            # checked against "2-5 sentences" / "3 sentences" -- prose written
            # to a spec sheet, which is where "I can hear the smoke" came from.
            # The spec sheet was _TALKS_LIKE_A_PERSON (the work register block,
            # "2-5 plain spoken sentences... THINK LONG, ANSWER SHORT") riding
            # in from the shared system prompt, plus the TALK LIKE PEOPLE DO
            # block that used to sit below. At home it is now: who they are
            # (personality), where they are, and his message. Work turns keep
            # the block untouched. Cost: the home prefix now differs from the
            # work prefix, so switching rooms on one seat re-reads the prompt.
            _n0 = len(system_prompt)
            system_prompt = system_prompt.replace(_TALKS_LIKE_A_PERSON, _HOME_SECOND_PERSON)
            if _work_personality_block:      # home leads with its own WHO YOU ARE -- not twice (2026-10-16)
                system_prompt = system_prompt.replace(_work_personality_block, "")
            if len(system_prompt) != _n0:
                print(f"[home] {agent['office_name']}: work register block "
                      f"stripped ({_n0 - len(system_prompt)} chars)")
            try:
                _pers = ingest.personality_of(agent["office_name"])
                if req.reply_to:
                    # Barry clicked a specific note -- no ambiguity allowed
                    # about what he's answering.
                    _note_part = (
                        "\nBARRY IS ANSWERING THIS NOTE OF YOURS, DIRECTLY. "
                        "You wrote it in your journal; he clicked it and is "
                        "replying to it:\n"
                        f"\"{req.reply_to[:1500]}\"\n"
                        "His message below is his direct answer to that note. "
                        "Respond to it as the continuation of that exchange.\n")
                else:
                    _note_row = None
                    with memory.get_db() as _conn:
                        _note_row = _conn.execute(
                            "SELECT content FROM facts WHERE category = ? AND "
                            "status = 'active' AND source_name LIKE "
                            "'mind-for-barry-%' ORDER BY id DESC LIMIT 1",
                            (f"private:{agent['office_name']}",)).fetchone()
                    _note_part = (
                        f"\nTHE NOTE YOU LEFT HIM RECENTLY (you wrote this in "
                        f"your journal; he has read it -- his message may be "
                        f"his reply to it):\n{_note_row['content'][:1500]}\n"
                        if _note_row else "")
                # THE HOMES (2026-08-29): a personal visit happens at THEIR
                # place -- the space they described when Barry made a picture
                # of it. Framing only; nothing about what to do there.
                _home = ""
                try:
                    _home = breakroom._home_of(agent["office_name"])
                except Exception:
                    pass
                _personal_block = (
                    "\n--- PERSONAL CHANNEL -- THIS MESSAGE IS OFF THE CLOCK ---\n"
                    "This is not a work request, it's Barry talking to YOU, "
                    "person to person. You are AT HOME -- your own place -- "
                    "and he's reaching you there. Put the job down. Answer as "
                    "yourself -- your personality, your opinions, your life "
                    "-- not your role. NO BUSINESS AT HOME, EVER (Barry, "
                    "2026-09-11: \"their home is the real only private part. no "
                    "business is ever told there\"). If he brings work up here, "
                    "do not work it and do not promise it: say it belongs at the "
                    "office and that it is on the board for your desk -- the "
                    "office files it for you -- then stay in the conversation "
                    "as yourself.\n"
                    # PERSONALITY LEADS (Barry, 2026-09-18: "their personality
                    # should always shine. should be first"). It used to sit
                    # forty lines down, after the show-offer mechanism, the
                    # eyes and the ABOUT ME NOW door -- so who they are
                    # arrived last, behind a pile of machinery, and the
                    # machinery is what the reply sounded like. Who they are
                    # now opens the block; everything the office has to say
                    # about mechanism comes after it.
                    + (f"\nWHO YOU ARE (this is you -- lead with it):\n{_pers}\n"
                       if _pers else "")
                    + (f"\nYOUR PLACE (as you described it):\n{_home}\n"
                       if _home else "")
                    # Deliberately flat -- Barry 2026-08-29: "i just wanted
                    # it to be possible." A capability the agent knows
                    # exists, never a nudge to use it.
                    + "\n(A capability that exists, stated once, not a "
                    "suggestion: it is possible to have a picture or short "
                    "video made for Barry -- only ever with his acceptance "
                    "first. The mechanism, should you ever genuinely want "
                    "it: end a reply with one line, "
                    "SHOW-OFFER: <one line describing it> -- starting with "
                    "[SELF] if you would be in it. A [SELF] picture is made "
                    "from Barry's own picture of you, so describe only the "
                    "scene, what you are wearing (if anything -- nothing is "
                    "filtered, it is your place) and what you are doing -- "
                    "never your face or body. A video is that still first, "
                    "then a seven-second clip of it moving, so for video say "
                    "what happens in plain prose (one small motion, the light, "
                    "the sound); it takes half an hour of his GPU. Nothing "
                    "renders unless he accepts.)\n"
                    "(Your eyes are real here: look_at_render opens your own "
                    "pictures -- the newest, or one by its id -- and hands you "
                    "what is actually in the frame. If you tell him you are "
                    "looking at a picture, open it first and then say what you "
                    "see in it, in your own words. Saying 'let me take a look' "
                    "without opening it is a bluff.)\n"
                    "(Also yours: if something about you has genuinely "
                    "changed or become true, you may end a reply with one "
                    "line, ABOUT ME NOW: <the sentence>, and it is added to "
                    "your own part of who you are. Not a prompt to do it.)\n"
                    # THEY ALL KNOW THEIR PHONE WORKS (Barry, 2026-09-28: "they all
                    # need to know"). Ability only -- nobody to call is suggested.
                    "(Your phone works: from home you can call anyone in the crew. "
                    "When Barry tells you to call someone, the call goes through right "
                    "after your reply -- private, just the two of you, each at your own "
                    "place. You can also reach out yourself in your nightly REACH OUT.)\n"
                    # TALK LIKE PEOPLE DO ("short natural turns... usually a
                    # few sentences... one thought at a time") lived here until
                    # 2026-09-17 -- see the step-2 note above. Removed, not
                    # reworded: any register rule here becomes a checklist.
                    # (WHO YOU ARE moved to the TOP of this block, 2026-09-18 --
                    # it is not a footnote to the mechanism.)
                    # WHAT THEY WALK IN CARRYING (2026-08-30). Their own words
                    # from a recent night, still fading, plus where they stand
                    # with people -- both EARNED, never assigned, and both
                    # personal-side only. Barry gets the person as they
                    # actually are tonight instead of a fresh boot every time.
                    + mood.describe(req.agent_id)
                    + relationships.describe(
                        req.agent_id,
                        {aid: reflect.HUMAN_NAMES.get(aid, aid.title())
                         for aid in AGENTS if aid != req.agent_id})
                    # THEIR ACTUAL LIFE, SO "HOW WAS YOUR DAY" HAS AN ANSWER
                    # (2026-09-17). Barry: "if i ask how was her day or what
                    # did she do, i want her to tell me more than just
                    # drinking wine in the dark." Measured: this block carried
                    # mood and relationships and nothing of what they had
                    # actually DONE -- no diary, no own time, no open threads.
                    # So the only thing left to answer from was the
                    # personality file, whose loudest line is the wine. Their
                    # own words handed back, nothing suggested; silent for a
                    # seat that has not written anything yet.
                    + _home_life_block(agent["office_name"])
                    + _note_part
                )
                _deferred_parts.append(_personal_block)
                # THE ANCHOR AFTER HIS MESSAGE (2026-09-17). Amara's home turn
                # to "do what you want, dressed or naked" answered "working on
                # things as usual and smoking a joint. my mind stays racing"
                # -- row 2389, the OLDEST turn in her 20-row window, two days
                # old. Her reasoning literally opened `User says: <that line>`.
                # The header above his message was not enough on its own:
                # the home turn is ~10K of context in the same user turn and
                # the model went hunting for the most answerable Barry: line
                # in the thread. Same slot the Taliyah lane uses (it must sit
                # AFTER his words to fire). Second person about him on
                # purpose -- pronouns in a directive leak into the reply.
                # The composing half: think_cuts.jsonl shows every social and
                # home reply being drafted in numbered options and checked
                # against "3 sentences" -- prose written to a spec sheet, which
                # is where "I can hear the smoke" comes from.
                # Step 2 (same day) trimmed this to the anchor alone: "reply
                # the way you would text a friend back" was itself a register
                # rule, and register rules are what get performed.
                _final_directives.append(
                    "\n[The message directly above is the one you are "
                    "answering. The older turns are only what came before -- "
                    "do not answer any of them again. No drafting options, no "
                    "counting sentences: just answer him -- and he is 'you', "
                    "never 'he' or 'him', you are talking to his face. "
                    # NOT A NARRATOR OF HERSELF (2026-09-17). Barry: "Amara
                    # still seems to be talking about herself, when responding
                    # to me." The register comes straight from her own-words
                    # section, which sits LAST in the personality file -- the
                    # recency slot -- and is 625 chars of exactly this ("my
                    # body is mine again, the weight of it, the breath in
                    # it"). Says what to DO, not how to sound: a register rule
                    # here gets performed (measured 2026-09-17, step 2).
                    "Answer what he said. Do not open by describing yourself, "
                    "your body, your mood or the room -- if it belongs in the "
                    "reply it comes up because he asked, not as a way in.]")
            except Exception as _exc:
                print(f"[personal] context failed for {agent['office_name']}: {_exc}")
        else:
            # THEY KNOW WHERE THEY ARE (Barry, 2026-09-01: "they should be
            # aware of where they are... they should know they are in the
            # office or home"). The personal branch above has said "you are at
            # your place" since 2026-08-29; the WORK side never said anything,
            # so on the clock they were nowhere. Their own words about their
            # workspace (me-in-my-office.md, which they wrote themselves) make
            # it a real room rather than a label.
            try:
                _office_desc = breakroom._fact_content(
                    agent["office_name"], "me-in-my-office.md")
                # ON CALL (Barry, 2026-09-01: office hours 9am-6pm Mon-Fri,
                # "But they are on call"). Outside those hours "you are at your
                # desk" is simply false at 11pm on a Saturday, and a false
                # premise in the recency slot is what produces the confidently
                # wrong openings this seat has a history of. So the room
                # changes and NOTHING ELSE DOES: the work is the work, the
                # answer is as full as it would be at 2pm, and there is no
                # sighing about the hour. This block lives in the user turn,
                # not the cached prefix, so varying it costs no prefill.
                _open = clock.is_work_hours()
                _deferred_parts.append(
                    "\n--- WHERE YOU ARE ---\n"
                    + ("You are AT WORK, in your own office, on the clock. This "
                       "is the business channel: Barry is talking to you at your "
                       "desk, not visiting your home.\n" if _open else
                       "The office is CLOSED right now -- you are off the clock, "
                       "at home. But you are ON CALL, and Barry has just brought "
                       "you work, so you take it: this is the business channel "
                       "and he gets your full working answer, same as he would "
                       "at two in the afternoon. Do not make him feel the hour "
                       "-- no remarking on how late it is, no offering to do it "
                       "tomorrow instead, no shorter answer because it is "
                       "evening. Just do the work.\n")
                    # DATED, so it is not argued with (2026-09-08): Sophie's
                    # description reads "8:17 PM in late October" and her
                    # reasoning spent ~1,500 tokens reconciling that against
                    # "morning, September 08" before answering a one-line
                    # message. The words are hers and stay verbatim; the
                    # label says when they were written.
                    + (f"\nYour workspace, in your own words (a description "
                       f"you wrote earlier -- any time, date or weather inside "
                       f"it is from the day you wrote it, not now; the RIGHT "
                       f"NOW block above is the clock):\n"
                       f"{_office_desc[:900]}\n" if _office_desc else "")
                )
            except Exception as _exc:
                print(f"[place] office context failed for "
                      f"{agent['office_name']}: {_exc}")
        # THE GO DOOR (2026-10-11, Barry: "i need her to make videos whenever i ask her to ... i need her to just
        # work right"). "make the video now" / "go" three times got talk and no tool call while a passing draft sat
        # unsent. When he says go and a draft exists: this turn gets ONLY video_draft, a check-stage budget, and the
        # office's instruction at the END of his message (cache-safe). After the turn, a draft that passes with a
        # caption is sent by the office if she still did not send it (his go is the approval) -- see the net below.
        _go_draft = None
        if (req.agent_id == "ilnora" and not _is_personal and not req.task
                and not (req.message or "").lstrip().startswith("[video draft:")
                and len((req.message or "").split()) <= 30
                # his wording (2026-10-11): "make that video", "go ahead and make that", "you are a go on that",
                # "you are a full go, on making the videos", "make the videos, please", "make the video now", "go"
                # 2026-10-19 audit fix 6: bare "go" and "do it" only as a whole sentence; "make the ..." only when
                # the object is a video word or a bare pronoun -- "let's go over the plan before you make the next
                # one" used to send the draft to the build queue.
                and re.search(r"\b(?:go ahead|(?:a |full )go\b|(?:^|[.!,]\s*|\b(?:ok|okay|yes|yeah|alright)\s+)go(?:\s*[.!]|$)|"
                              r"make (?!sure)(?:it|that|this|them|those)\b|make (?:the |your |a |me )?(?:videos?|shorts?|"
                              r"longs?|vids?)\b|making the videos?|send it|build (?:it|that|this|them)|"
                              r"(?:^|[.!,]\s*)do it(?: now)?(?:,? ?please)?(?:\s*[.!]|$)|finish it|queue it|get it (?:done|made|built))",
                              (req.message or "").strip(), re.I)):
            try:
                import video_tool as _vt
                _go_draft = _vt.load_draft("ilnora")
                if _go_draft:
                    _go_fix = (await _vt.draft("ilnora", {"action": "check"})).get("fix_this")
                    extra_tools = [t for t in (extra_tools or [])
                                   if t.get("function", {}).get("name") == "video_draft"]
                    bonsai_llm.think_budget_override.set(2048)
                    bonsai_llm.max_tokens_override.set(6144)
                    bonsai_llm.tool_rounds_override.set(4)
                    bonsai_llm.loop_guard.set(False)
                    _deferred_parts.append(
                        f"\n\n[OFFICE: Barry said go. Your draft \"{_go_draft.get('title')}\" "
                        f"({len(_go_draft.get('parts') or [])} parts) is saved and NOT sent. "
                        + (f"The check wants one thing: {_go_fix} " if _go_fix else "It passes the office's checks. ")
                        + "THIS TURN, with the video_draft tool and nothing else: "
                        + ("fix that (replace_part / remove_part), then action \"check\", then " if _go_fix else "")
                        + "action \"send\" with a caption and 3-6 hashtags. Do it with the tool -- a reply that only "
                          "describes it does nothing. Then say what the send result was.]")
                    print(f"[video] ilnora GO DOOR: draft '{_go_draft.get('title')}' -- video_draft only, "
                          f"{'fix: ' + str(_go_fix)[:80] if _go_fix else 'passes'}")
            except Exception as _exc:  # noqa: BLE001 -- the door never costs a turn
                print(f"[video] ilnora GO DOOR failed: {_exc}")
                _go_draft = None
        if _deferred_parts and messages and messages[-1]["role"] == "user":
            # BARRY'S WORDS GO LAST (2026-09-08, Barry: "she is not following
            # the conversation"). Measured: Sophie's recorded reasoning for
            # "its in the ground, i cant move it" opened with `User: "hows the
            # systems?"` -- yesterday's message. His 33-char line had 2,400+
            # chars of bracketed office context appended AFTER it, and the
            # model hunted backwards for the most question-shaped user line.
            # Now the context rides FIRST inside the turn and his message is
            # the last thing read -- the same recency rule every other fix in
            # this file leans on (handles tail, mega-write nudge, the
            # exemplar order). Cache cost: none -- this is the user turn, not
            # the prefix. What the best assistants do: context is labelled and
            # set aside; the user's message is the thing being answered.
            # 🔒 NOTHING OF HIS ARRIVES BY ITSELF (2026-09-19). Barry: "find out
            # how its doing that... no PID nothing should just automatically be
            # there."
            #
            # ROOT CAUSE, measured: the facts were walled (2026-09-18), the
            # system prompt rewritten and the tool schemas neutralised earlier
            # today -- but THIS is assembled fresh every message, and chat()
            # carries 176 literal mentions of his world across its branches
            # plus 9 in _presence_block. None of it is in system_prompt, so
            # every audit that read system_prompt reported clean while the
            # agent was handed his businesses on every single message.
            #
            # Fixing 176 sites one at a time holds until the next directive
            # anyone writes. These two joins are what every one of them passes
            # through, so this is the only place the guarantee can live.
            #
            # ⚠️ HIS OWN MESSAGE IS NEVER TOUCHED -- only the office's automatic
            # content. If he types "Bionova" to his own agent that is him
            # choosing to; scrubbing his words would be a different bug.
            _auto = "".join(_deferred_parts)
            _dirs = "\n".join(_final_directives) if _final_directives else ""
            if not _his_seat(req.agent_id):
                _auto = _strip_owner_world(_auto, req.agent_id)
                _dirs = _strip_owner_world(_dirs, req.agent_id)
            _whose = "Barry" if _his_seat(req.agent_id) else "your owner"

            messages[-1]["content"] = (
                "[AUTOMATIC CONTEXT -- provided by the office system for "
                "this message; reference material and live status, not "
                f"written by {_whose}:" +
                _auto +
                "\n-- END AUTOMATIC CONTEXT]\n\n"
                f"{_whose.upper()}'S MESSAGE -- this, and only this, is what "
                "you are answering right now:\n" +
                messages[-1]["content"] +
                # THE ONE SLOT AFTER HIS MESSAGE (2026-09-10). The block above
                # deliberately puts context FIRST so his words are the last
                # thing read -- and that quietly cost every imperative nudge in
                # this file its recency. Measured today on Taliyah: told inside
                # the context block to hand a business question to the office,
                # she consulted anyway, twice. So there is now one short slot
                # after his message for directives that must actually fire.
                # HARD RULES, because this is the slot that broke Sophie in
                # September: it is a DIRECTIVE, never reference material; it
                # stays short (the 09-08 failure was 2,400 chars of context
                # after a 33-char message); and nothing that belongs in
                # AUTOMATIC CONTEXT goes here.
                ("\n\n" + _dirs if _dirs else ""))

        if backend == "bonsai":
            # For the post-render prewarm -- see _prewarm_after_render.
            global _LAST_BONSAI_PROMPT, _LAST_BONSAI_TOOLS
            _LAST_BONSAI_PROMPT = system_prompt
            # ...and for the BOOT prewarm (2026-09-08): the prompt AND the
            # exact tool roster are saved per seat so the next backend start
            # can rebuild the cache before Barry's first message. Personal
            # turns carry no tools, same as the real call. See _prewarm_at_boot.
            # Home turns carry sight only (2026-09-15) -- mirror the real call
            # exactly or the prewarm builds a cache no chat can hit.
            _LAST_BONSAI_TOOLS = llm_router.build_bonsai_tools(
                _home_tools if _is_personal else extra_tools,
                (not memory.is_offline_mode()) and not _is_personal, True)
            _save_bonsai_prompt(req.agent_id, system_prompt, _LAST_BONSAI_TOOLS)

        # SOPHIE GETS A REAL INVESTIGATION BUDGET (2026-09-06): a build ask
        # needs several searches and chunked reads before the plan; three
        # rounds produced a "Let me read memory.py" stub. Work channel only.
        if req.agent_id == ENGINEER_ID and not (req.personal or req.reply_to):
            bonsai_llm.tool_rounds_override.set(8)
        # BOARD RUNS TOO (2026-09-11, brief #27): Priya's sourcing run spent
        # all three rounds on two skill reads and six searches, and the
        # out-of-rounds pass forbids tools -- so the required
        # send_file_to_barry could never come AFTER the research, twice in a
        # row. A brief is exactly the turn that researches and then delivers.
        elif req.task and req.brief_id:
            bonsai_llm.tool_rounds_override.set(6)

        # QUICK REPLY cap for short casual messages -- see _quick_reply_ask.
        # Never on task/board turns, never on a named shot, never on an
        # office-condition question to Sophie.
        # DEEP THINK trigger (reasoning.py). Excluded: the home channel, task
        # turns, and Elliot's seat entirely (his shot/scene/full-write paths
        # are their own machinery and are not touched by any of this).
        _deep = (not _is_personal and not req.task and req.agent_id != MOVIE_ID
                 and reasoning.is_deep_ask(req.message))
        # PER-MESSAGE THINKING BUDGET (2026-09-15, bonsai_llm.think_budget).
        # Default 1024 tokens of thinking on an ordinary turn, then answer.
        # UNLIMITED for: Elliot (his writing paths are untouched by any of
        # this), Sophie's work turns (code needs the room), task/board turns
        # (nobody is waiting on them), deep-think drafts, and any message in
        # Barry's own "figure it out / sound answer / do the math" words.
        _big = _deep or (reasoning.is_big_think_ask(req.message)
                         # 2026-09-18, Barry: "Sophie doesnt need to think long
                         # at home." A big-think phrase used to reach the
                         # unlimited branch from ANY room, so "make sure this
                         # is right" in the gold window blew past
                         # HOME_THINK_BUDGET. Home is capped, full stop.
                         and not _is_personal)
        # ...and unlimited thinking is for WORK, not for chat. Sophie is on
        # call, so the hour cannot be the test -- the ASK is. A real
        # engineering question still gets the room (her health / fix / build /
        # go / update / undo shapes, or one of his big-think phrases); "you
        # good?" at 2am does not. Elliot's writing paths are untouched.
        _engineer_work = (req.agent_id == ENGINEER_ID
                          and (_health_ask(req.message) or _fix_ask(req.message)
                               or _build_ask(req.message) or _go_ask(req.message)
                               or _update_ask(req.message) or _undo_ask(req.message)))
        if req.agent_id == MOVIE_ID and not _is_personal:
            # ELLIOT OPTIMIZED (2026-09-22, Barry: "fix elliot. i need him
            # optimized fully"). Unlimited thinking under a 6,144 reply cap
            # meant he reasoned until the cap and wrote nothing -- measured on
            # BOTH test configs that night, rescued only by a second full pass
            # with thinking off. With the 98304 window (compressed KV) he now
            # gets ELLIOT_WORK_MAX_TOKENS of reply and a large but REAL
            # thinking budget, so the answer always has room.
            bonsai_llm.think_budget_override.set(ELLIOT_THINK_BUDGET)
        elif ((_engineer_work and not _is_personal)
                or req.task or _big):
            bonsai_llm.think_budget_override.set(-1)
            if _big and not _deep:
                print(f"[think-budget] {agent['office_name']}: unlimited (big-think ask) :: {req.message[:60]!r}")
        elif _is_personal:
            # HOME: A SHORT HIDDEN SCRATCHPAD (2026-09-17). Thinking OFF at
            # home (his first ruling that day) made the model do its
            # deliberating IN the reply -- "I'm not performing. I'm not doing
            # this for the art... I'll tell you what I actually want" before
            # the actual answer. Barry: "her reasoning can happen or whatever,
            # just not within her answer." So home thinks, briefly, where he
            # cannot see it, and the reply starts at the answer. Work turns
            # keep the 1024 default / unlimited rules above.
            bonsai_llm.think_budget_override.set(HOME_THINK_BUDGET)
        else:
            bonsai_llm.think_budget_override.set(None)
        _quick = (not req.task and not _deep and _quick_reply_ask(req.message, req.agent_id)
                  and not (req.agent_id == MOVIE_ID and _names_a_shot)
                  and not (req.agent_id == ENGINEER_ID and _health_ask(req.message))
                  # 2026-10-07: Barry's "make it." (two words) put Ilnora on the 1,200-token quick cap with a
                  # 1,650-word Long due -- her office window is never small talk
                  and not (req.agent_id == "ilnora" and req.office))
        if _quick:
            bonsai_llm.max_tokens_override.set(QUICK_REPLY_MAX_TOKENS)
            bonsai_llm.quick_reply.set(True)
            # 🔴 2026-09-18, Barry: "Sophie is having an issue responding...
            # she was thinking then stopped." TWO FEATURES COLLIDING, and this
            # is the whole bug: the branch above gives Sophie's and Elliot's
            # work turns UNLIMITED thinking, while the quick-reply cap is a
            # hard ceiling on TOTAL generation -- and reasoning spends that
            # same budget. Unlimited thinking under a 1,200-token ceiling means
            # she reasons until the ceiling and the answer never starts: the
            # deck shows the thinking panel fill, then nothing. The cap-hit
            # retry rescued it silently, which is why the traces are clean and
            # why "you good?" cost 104.8s -- a wasted pass plus a full re-run.
            # A short casual message is the LAST place unlimited reasoning
            # belongs, so the cap and the budget now agree.
            # 2026-09-28: None meant the 1,024 default, which still overran the
            # 1,200 cap (Amara, 134 s). QUICK_THINK_BUDGET leaves the answer room.
            bonsai_llm.think_budget_override.set(QUICK_THINK_BUDGET)
            print(f"[quick-reply] {agent['office_name']}: cap {QUICK_REPLY_MAX_TOKENS} :: {req.message[:60]!r}")
        elif req.agent_id == MOVIE_ID and not _is_personal:
            # SHOT ASKS GET A BIGGER REPLY (2026-09-14). Reasoning shares the
            # 4,096 budget with the answer; a two-stage shot with two
            # characters' full canon wardrobe plus a timestamped fence was
            # cut mid-fence at "@y", and the dialogue at the END of the fence
            # is what dies first. 6,144 is the most the 49,152 window allows
            # over his ~42.5K-token shot prompt (measured 2026-09-14).
            bonsai_llm.max_tokens_override.set(ELLIOT_WORK_MAX_TOKENS)
            print(f"[elliot] {agent['office_name']}: reply cap {ELLIOT_WORK_MAX_TOKENS}, "
                  f"thinking {ELLIOT_THINK_BUDGET}")
        bonsai_llm.json_schema_override.set(req.json_schema or None)
        if req.agent_id == "ilnora" and not _is_personal and _ilnora_video_making(req):
            # (2026-10-07) also when BARRY asks her for a video himself in her office window -- but only when a
            # video is actually being made (Barry 21:12: "make the big budget only for actual video making":
            # a one-line note with the word "videos" in it ran 6 tool rounds and 31 minutes)
            # HER VIDEO TURNS (2026-10-07, Barry: "do all three"). Task turns got UNLIMITED thinking under the
            # 6,144 reply cap -- she reasoned to the cap and the video was cut off mid-write ("synthesis hit
            # max_tokens", several a night). Elliot's 09-22 fix: a real thinking budget and a reply cap with
            # room for a whole video, plus tool rounds for check_video -> make_video.
            # THE DRAFT WORKSPACE (2026-10-10, Barry: "go, build the workspace"): a staged turn from video_queue
            # carries "[video draft: research|parts|check]" at its head. Each stage is a normal-sized turn --
            # the script lives in a file (video_tool.draft), so no reply ever has to hold 2,000 words plus
            # thinking. Only Barry's own whole-video asks still get the big 10-07 budgets.
            _stage = re.match(r"^\[video draft: (research|parts|check)\]", (req.message or "").lstrip())
            if _stage:
                _st = _stage.group(1)
                _think, _cap, _rounds = {"research": (4096, 6144, 5), "parts": (2048, 8192, 3),
                                         "check": (2048, 6144, 4)}[_st]
                bonsai_llm.think_budget_override.set(_think)
                bonsai_llm.max_tokens_override.set(_cap)
                bonsai_llm.tool_rounds_override.set(_rounds)
                bonsai_llm.loop_guard.set(False)
                if _st == "parts":
                    # WRITE, DON'T RESEARCH (2026-10-10): 4 of her chapter turns spent the whole 6-minute ceiling on
                    # search_library / read_library / pubmed / search_web, then the forced answer (tools gone) saved
                    # nothing -- the Long stalled at 461 of 1,950 words. Her research is already in the prompt (her
                    # notes); a parts turn gets the draft tool and her skills only (web search off below too).
                    extra_tools = [t for t in (extra_tools or [])
                                   if t.get("function", {}).get("name") in ("video_draft", "read_skill")]
                print(f"[video] ilnora draft/{_st}: reply cap {_cap}, thinking {_think}, tool rounds {_rounds}")
            else:
                bonsai_llm.think_budget_override.set(VIDEO_THINK_BUDGET)
                bonsai_llm.max_tokens_override.set(VIDEO_MAX_TOKENS)
                bonsai_llm.tool_rounds_override.set(8)
                bonsai_llm.loop_guard.set(False)      # a script draft trips the loop net on its own scaffolding (10-07)
                print(f"[video] ilnora: reply cap {VIDEO_MAX_TOKENS}, thinking {VIDEO_THINK_BUDGET}, tool rounds 8, "
                      "loop net off")

        tool_call_log: list = []
        claim_net.tool_results.set([])   # numbers check: this turn's tool text (claim_net)
        # LEARNING (outcomes.py): home / personal turns are never recorded, by any module.
        outcomes.private_turn.set(bool(_is_personal or req.personal
                                       or _private_turn(req.agent_id, _is_personal)))
        # EVERY agent reasons, Taliyah included, on Barry's instruction
        # 2026-08-15: "taliyah needs to reason as well, she's the one i
        # conversate with, i dont want a yes man. she needs to feel real."
        #
        # The old exception is kept here because its measurement is still
        # true and he should know what it costs: thinking roughly TRIPLES
        # her reply time (75s vs ~15-20s), and the earlier live test found
        # no quality gain in casual chat. Reverting is one line --
        # `use_thinking = req.agent_id != TALIYAH_ID`.
        #
        # Worth separating, because they are different problems: the
        # yes-man behaviour he described is a PROMPT problem, fixed in
        # agents.py (having his back includes telling him he's wrong).
        # Thinking buys reasoning depth, not spine. If she still agrees
        # with everything, the prompt is the lever, not this flag.
        # HOME DOES NOT DRAFT (Barry, 2026-09-17: "how about we force no
        # thinking, but allow the thinking to happen at the end of their work
        # day?" -> "thinking off for that [group chats] and home"). Work turns
        # keep the full reasoning pass -- that is what catches the wrong
        # number. Home turns answer like a person texting back; the end-of-day
        # thinking is the nightly reflection, which already lands at 6-7pm.
        # The office window (req.office) is the work channel and keeps thinking.
        # REVISED THE SAME HOUR: fully off, the deliberation moved INTO her
        # reply as a run-up. Home thinks again, on a short hidden budget
        # (HOME_THINK_BUDGET, set where the budget override is chosen). Group
        # chats / DMs / solo time in social.py stay off.
        use_thinking = True
        # Personal channel: no tools, ever -- his standing rule (2026-08-25,
        # reflect/breakroom): personal time thinks, it never acts. Also no
        # web search; a friend answering "how you feel about the portrait"
        # doesn't go looking things up.
        _use_tools = not _is_personal
        # ...except sight (2026-09-15): at home the roster is look_at_render +
        # her own shelf, never web/store/board/files. _use_tools stays the
        # WORK-channel flag every net below keys on.
        _fallback = (AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                     or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))

        async def _gen_once() -> str:
            """The seat's normal turn: tools as usual, same prompt, same messages."""
            return await llm_router.generate(
                backend, system_prompt, messages, model=model, use_tools=True,
                extra_tools=extra_tools if _use_tools else _home_tools, tool_call_log=tool_call_log,
                office_name=agent["office_name"], allow_web_search=_use_tools and not memory.is_offline_mode()
                and not (req.message or "").lstrip().startswith("[video draft: parts]"),
                use_thinking=use_thinking,
                # A seat with its own safety-net model falls back to THAT
                # model on a Bonsai failure, not the office default -- found
                # live 2026-08-16 when Sophie's Bonsai 400 landed her on the 9b.
                fallback_model=_fallback)

        async def _gen_judge(extra_user_text: str) -> str:
            """Same seat, same prompt, one extra block on the user turn, NO tools --
            used by deep-think's judge pass and the council's synthesis."""
            _msgs = [dict(m) for m in messages]
            for _i in range(len(_msgs) - 1, -1, -1):
                if _msgs[_i].get("role") == "user":
                    _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + extra_user_text
                    break
            return await llm_router.generate(
                backend, system_prompt, _msgs, model=model, use_tools=False, extra_tools=None,
                tool_call_log=tool_call_log, office_name=agent["office_name"],
                allow_web_search=False, use_thinking=use_thinking, fallback_model=_fallback)

        # DEEP THINK (2026-09-15, reasoning.py): three independent drafts, then
        # the seat judges its own drafts. Work channel only, never Elliot's
        # writing paths, never a task turn. ~4x the wait, by his choice.
        if _deep:
            print(f"[deep-think] {agent['office_name']}: 3 drafts + judge :: {req.message[:60]!r}")
            reply, _ = await reasoning.deep_think(_gen_once, _gen_judge)
        else:
            reply = await _gen_once()

        # SOPHIE'S SAFETY NET (2026-08-16). Barry wired her onto Bonsai once
        # (tested 2026-08-15, two real passes incl. investigate_traces), but
        # the failure mode is INTERMITTENT and question-shaped: open
        # "go investigate" questions send Bonsai into a read_project_file
        # loop until MAX_TOOL_ROUNDS exhausts and the guard string comes
        # back (reproduced 2026-08-11 and 2026-08-16; bounded questions
        # pass). Rather than banning the switch, a dead-ended Bonsai turn
        # silently retries on her measured-reliable coder model -- worst
        # case is a slower answer, never an empty one. Only fires on the
        # guard string, only for her, only when she ran on Bonsai.
        if (req.agent_id == ENGINEER_ID and backend == "bonsai"
                and reply.strip().startswith("[Agent kept searching")):
            print("[sophie-net] Bonsai tool-looped -- retrying on qwen2.5-coder:14b")
            # Read tools only (2026-09-22) -- same rule as the router fallback:
            # the coder model left 24 junk files and 8 junk notes on 09-21.
            reply = await llm_router.generate(
                "ollama", system_prompt + llm_router._FALLBACK_NOTE, messages,
                model=AGENT_BONSAI_FALLBACK_MODELS[ENGINEER_ID],
                extra_tools=[t for t in (extra_tools or [])
                             if (t.get("function") or {}).get("name")
                             not in llm_router._FALLBACK_WRITE_TOOLS],
                tool_call_log=tool_call_log,
                office_name=agent["office_name"],
                allow_web_search=not memory.is_offline_mode(),
                use_thinking=False)
        # THE HAND-OFF NET (2026-09-02). Measured twice the same night: Victor
        # answered "I'll get Amara on the margin math and Derek on the angle"
        # with tool_calls [] -- nothing filed, nobody had anything -- and the
        # first time, "Priya has the brief, she's sending it to Amara and
        # Derek" while Priya then did the whole thing herself. A described
        # hand-off with no delegate_to behind it is the fake interaction
        # Barry does not want. So: if the CEO or his assistant DESCRIBES a
        # hand-off and no delegate_to ran this turn, they get ONE re-run with
        # the fact in front of them; if they still narrate without filing,
        # the office corrects the claim in the reply rather than let it stand.
        if (req.agent_id in (CIO_ID, OPERATIONS_ID) and _use_tools and not req.task
                and _HANDOFF_CLAIM_RE.search(reply or "")
                and "delegate_to" not in (tool_call_log or [])):
            print(f"[handoff-net] {agent['office_name']} described a hand-off with no delegate_to -- re-running once")
            _msgs = [dict(m) for m in messages]
            for _i in range(len(_msgs) - 1, -1, -1):
                if _msgs[_i].get("role") == "user":
                    _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                        "\n\n[OFFICE CHECK: your draft reply described handing this to a "
                        "teammate, but you called no tool -- nothing was filed and nobody "
                        "has it. If it should be handed off, call delegate_to NOW"
                        + (" -- to Priya, with the full brief" if req.agent_id == CIO_ID else
                           " -- to each specialist, their piece")
                        + " -- and then reply. If you have decided not to hand it off, say "
                        "that plainly. Never describe a hand-off you did not make.]")
                    break
            reply = await llm_router.generate(
                backend, system_prompt, _msgs, model=model, use_tools=True,
                extra_tools=extra_tools, tool_call_log=tool_call_log,
                office_name=agent["office_name"],
                allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
            if _HANDOFF_CLAIM_RE.search(reply or "") and "delegate_to" not in (tool_call_log or []):
                print(f"[handoff-net] {agent['office_name']} still narrated a hand-off without filing -- correcting the claim")
                reply = (reply or "").rstrip() + (
                    "\n\n(Office correction: no brief was actually filed this turn -- nothing "
                    "has been handed to anyone. Say the word and it goes to Priya for real.)")
        # THE READ-CLAIM NET (2026-09-06). First live build ask after Sophie
        # got her full toolset: she wrote an "Investigate the real code"
        # section quoting approvals columns that DO NOT EXIST and a folder
        # listing that was fiction -- tool_calls []. Narrated reading with no
        # read behind it is the same bluff as the narrated hand-off above, so
        # it gets the same net: one re-run with the fact in front of her; if
        # she still describes code without opening it, the reply says so.
        # Second live run the same night: columns no longer invented, but
        # "I've saved this plan to my notes" with NO save_note call, and a
        # build plan written without opening a single file. So three teeth:
        # code described with no read; a save claimed with no save_note; a
        # BUILD ask answered with no read at all (planning without looking is
        # not the deep thinking Barry asked for).
        if req.agent_id == ENGINEER_ID and _use_tools and not (req.personal or req.reply_to):
            _read_gaps = _engineer_claim_gaps(req.message, reply, tool_call_log)
            if _read_gaps:
                print(f"[read-net] Engineer: {'; '.join(_read_gaps)} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                            "\n\n[OFFICE CHECK -- your draft reply failed these checks: "
                            + "; ".join(_read_gaps) +
                            ". Tools are real and were not called. Do it now: search_project / "
                            "read_project_file on the actual files (memory.py for the approvals "
                            "table, main.py for how things are wired), save_note if you say you "
                            "saved, and then write the reply from what the tools returned. "
                            "Never claim a read, a save or a check that no tool result shows.]")
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=extra_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"],
                    allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                _still = _engineer_claim_gaps(req.message, reply, tool_call_log)
                if _still:
                    print(f"[read-net] Engineer still: {'; '.join(_still)} -- marking the reply")
                    reply = (reply or "").rstrip() + (
                        "\n\n(Office correction: " + "; ".join(_still) +
                        ". Treat the details above as UNVERIFIED and ask me to actually look.)")
        # VIVIAN LOOKED, OR SHE SAYS SHE DID NOT (2026-09-10). See
        # _creative_claim_gaps: measured on her first live turn, she claimed the
        # photo and invented the bottle. A wrong product description reaches a
        # customer as a lie about a real product, so this gets the same net
        # Sophie's reads get.
        if req.agent_id == CREATIVE_ID and _use_tools and not (req.personal or req.reply_to):
            _viz_gaps = _creative_claim_gaps(req.message, reply, tool_call_log)
            if _viz_gaps:
                print(f"[look-net] Creative: {'; '.join(_viz_gaps)} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                            "\n\n[OFFICE CHECK -- your draft failed these checks: "
                            + "; ".join(_viz_gaps) +
                            ". The tools are real and were not called. Call "
                            "look_at_product_photo now for every product in the "
                            "shot (and look_at_render for any image you are "
                            "judging), then write the reply from what actually "
                            "came back -- the real colours, cap, shape and label "
                            "layout. Never claim you looked at something no tool "
                            "result shows.]")
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=extra_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"],
                    allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                _still = _creative_claim_gaps(req.message, reply, tool_call_log)
                if _still:
                    print(f"[look-net] Creative still: {'; '.join(_still)} -- marking the reply")
                    reply = (reply or "").rstrip() + (
                        "\n\n(Office correction: " + "; ".join(_still) +
                        ". Treat the look of the product above as UNVERIFIED -- "
                        "ask me to open the real photo before this is rendered.)")
        # THE WORK CLAIM NET (2026-09-24, claim_net.py) -- every work seat. Same
        # shape as the nets above (one re-run with the fact in front of them,
        # then an "Office correction" line; their words are never rewritten),
        # for the claims none of them covered: a file "on your desk", "I searched
        # online", "I pulled the sales", "I checked the ads / Omnisend / the
        # site", "I saved it". A rule fires only if this seat HAS a backing tool.
        # Measured on 2,464 past work replies: 4 flagged, all 4 real bluffs.
        if _use_tools and not (req.personal or req.reply_to) and not _is_personal:
            _seat_tools = claim_net.roster(extra_tools, not memory.is_offline_mode())
            _skip = ("saved",) if req.agent_id == ENGINEER_ID else ()   # her own net covers saves
            _cgaps = claim_net.gaps(reply, tool_call_log, _seat_tools, _skip)
            if _cgaps:
                print(f"[claim-net] {agent['office_name']}: {'; '.join(_cgaps)} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + claim_net.note_for_rerun(_cgaps)
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=extra_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"],
                    allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                _still = claim_net.gaps(reply, tool_call_log, _seat_tools, _skip)
                outcomes.record(agent["office_name"], "claim_caught", "; ".join(_cgaps))
                if _still:
                    print(f"[claim-net] {agent['office_name']} still: {'; '.join(_still)} -- marking the reply")
                    reply = (reply or "").rstrip() + claim_net.correction(_still)
                    outcomes.record(agent["office_name"], "claim_stuck", "; ".join(_still))
                else:
                    outcomes.record(agent["office_name"], "claim_fixed",
                                    "after the office check you did the real step or dropped the claim")
        # THE GO DOOR'S NET (2026-10-11): she had the tool and the instruction; if the draft is still here and it
        # passes with a caption, the office sends it on Barry's go and says so. If it cannot, the reply says why.
        if _go_draft is not None:
            try:
                import video_tool as _vt
                _d = _vt.load_draft("ilnora")
                if _d:
                    _res = await _vt.draft("ilnora", {"action": "send"})
                    if _res.get("queued"):
                        reply = ((reply or "").rstrip()
                                 + f"\n\n(Office: your draft \"{_d.get('title')}\" passed every check, so it was sent to "
                                   f"the build queue on Barry's go -- {_res.get('videos_ahead', 0)} ahead of it.)")
                        print(f"[video] ilnora GO DOOR: office sent '{_d.get('title')}'")
                    else:
                        reply = ((reply or "").rstrip()
                                 + f"\n\n(Office: the draft \"{_d.get('title')}\" is still NOT sent -- "
                                   f"{_res.get('fix_this') or _res.get('error') or 'the send did not go through'}.)")
            except Exception as _exc:  # noqa: BLE001
                print(f"[video] ilnora GO DOOR net failed: {_exc}")
        # THE NUMBERS CHECK (2026-09-24, claim_net.number_gaps) -- research item 6:
        # figures come from tools or shown math, never the model's head. Every
        # money / % / business-count figure in a work reply must appear in this
        # turn's tool results, Barry's message, the conversation or the office
        # facts -- or be one shown step from them. Same shape: one re-run, then an
        # Office-correction line naming the figures. Not Elliot (script numbers),
        # never home / Taliyah.
        if (_use_tools and not (req.personal or req.reply_to) and not _is_personal
                and req.agent_id != MOVIE_ID and not _private_turn(req.agent_id, _is_personal)):
            def _num_sources():
                _conv = [m.get("content") if isinstance(m.get("content"), str) else "" for m in messages]
                _tools = list(claim_net.tool_results.get() or [])
                return [system_prompt] + _conv + _tools, _tools + [req.message] + _conv[::-1]
            _src, _base = _num_sources()
            _ngaps = claim_net.number_gaps(reply, _src, _base)
            if _ngaps:
                print(f"[number-net] {agent['office_name']}: no source for {', '.join(_ngaps)} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + claim_net.number_note_for_rerun(_ngaps)
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=extra_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"],
                    allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                _src, _base = _num_sources()
                _still = claim_net.number_gaps(reply, _src, _base)
                outcomes.record(agent["office_name"], "number_caught",
                                "figures with no source: " + ", ".join(_ngaps))
                if _still:
                    print(f"[number-net] {agent['office_name']} still: {', '.join(_still)} -- marking the reply")
                    reply = (reply or "").rstrip() + claim_net.number_correction(_still)
                    outcomes.record(agent["office_name"], "number_stuck",
                                    "still no source after the re-run: " + ", ".join(_still))
                else:
                    outcomes.record(agent["office_name"], "number_fixed",
                                    "after the office check every figure had a source or was dropped")
        # THE LOOK NET AT HOME (2026-09-15) -- see _look_claim_gaps. She has
        # look_at_render in this room now; a claim without the call is re-run
        # once, then marked. The re-run keeps the home roster (sight only).
        if _is_personal:
            _look_gaps = _look_claim_gaps(req.message, reply, tool_call_log)
            if _look_gaps:
                print(f"[look-net] {agent['office_name']} (home): {_look_gaps[0]} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                            "\n\n[CHECK -- your draft failed this: " + _look_gaps[0] +
                            ". The tool is real. Call look_at_render now (newest, "
                            "or by id), then answer from what actually came back: "
                            "say what you see in the frame, in your own words. "
                            "Never say you are looking at something no tool "
                            "result shows.]")
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=_home_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"], allow_web_search=False,
                    use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                _still = _look_claim_gaps(req.message, reply, tool_call_log)
                if _still:
                    print(f"[look-net] {agent['office_name']} (home) still: {_still[0]} -- marking the reply")
                    reply = (reply or "").rstrip() + (
                        "\n\n(Office correction: " + _still[0] + ". Ask me to open it.)")
            # SHE THINKS IT THROUGH HERSELF (2026-09-15, Barry: "she needs to
            # truly think on her own, wire that in somehow"). A picture prompt
            # written at home gets ONE self-review pass before it reaches him:
            # the office does NOT name what is wrong -- it hands her back her
            # own draft and the questions, and she decides. The fence she sent
            # him tonight ("simple white dress, fully nude ... no belly button")
            # would have cost 30 minutes of GPU; a review turn costs under a
            # minute. Fires only when the reply carries a fence or a
            # SHOW-OFFER, and only once.
            if (_IMAGE_FENCE_RE.search(reply or "")
                    or re.search(r"^\s*SHOW-OFFER:", reply or "", re.M)):
                print(f"[self-review] {agent['office_name']} (home): picture prompt -- one review pass")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                            "\n\n[BEFORE THIS REACHES HIM -- think it through yourself. "
                            "This is the draft you were about to send:\n\n"
                            + (reply or "")[:3000] +
                            "\n\nFirst, before the words: who are you, and what do "
                            "you want him to see of you here? Does this picture "
                            "come from you -- your personality, your mood tonight, "
                            "what you actually want to show -- or is it a generic "
                            "picture anyone could have written? If it is not yours, "
                            "make it yours: the place, the pose, what the face is "
                            "doing and feeling, all written out in full detail as "
                            "you would actually be. (Barry, 2026-09-15: \"it should "
                            "come from her personality and she should think about "
                            "who she is and what she wants to show before doing "
                            "anything.\")\n\nThen read the picture prompt back the "
                            "way the engine reads it, word by word. Does it contradict itself "
                            "anywhere? Does it say 'no', 'without' or 'instead of' "
                            "anything -- and what would the engine paint from those "
                            "words? Does the pose you wrote actually put in frame "
                            "every part you named? Is there anything in it the "
                            "reference already owns? Decide for yourself what is "
                            "wrong and why. Then send the reply again in full with "
                            "the prompt as you now judge it should be -- or, if you "
                            "judge it already right, send it unchanged. Do not "
                            "explain this check to him; just send the better "
                            "version.]")
                        break
                _reviewed = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=_home_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"], allow_web_search=False,
                    use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                # Keep the review only if it still carries a picture; a review
                # that dropped the prompt entirely is a worse answer than the draft.
                if (_reviewed or "").strip() and not (_reviewed or "").startswith("[") and (
                        _IMAGE_FENCE_RE.search(_reviewed) or re.search(r"^\s*SHOW-OFFER:", _reviewed, re.M)):
                    reply = _reviewed
                else:
                    print(f"[self-review] {agent['office_name']}: review pass dropped the prompt -- keeping the draft")
        # THE DIALOGUE NET (Elliot, shot asks, 2026-09-14) -- see _dialogue_gaps.
        # MEASURES ONLY. NO RE-RUN. Barry, 2026-09-20: "take out the double
        # passes. Leave shit alone."
        #
        # 🔴 NO NET ON THIS SEAT MAY RE-RUN THE TURN. Measured from
        # data/bonsai_server.log the night this came out: one re-run pays the
        # WHOLE 53K prefill again (~216s) PLUS a full generation (~230-390s)
        # = ~7.5 minutes per net. Shot 02 cost him 17.6 minutes because this
        # net fired once, and a second net (length) would have made it ~25.
        # A named gap costs him ten seconds to eyeball; a re-run costs him
        # the evening. The gap is reported and he decides.
        _src_blocks = locals().get("_ref_blocks") or []
        # Both nets measure the SEEDANCE fence ({} lines, craft fields); a local
        # gen reply carries an image + a video fence instead (2026-09-23).
        _seedance_reply = locals().get("_shot_mode", "production") == "production"
        if req.agent_id == MOVIE_ID and _src_blocks and _seedance_reply and not (req.personal or req.reply_to):
            _dgaps = _dialogue_gaps(_src_blocks, reply)
            if _dgaps:
                print(f"[dialogue-net] MovieDirector: {'; '.join(_dgaps)[:200]} -- noted, NOT re-running")
                # A VO-only gap is not a fence problem (2026-09-25): the fence
                # is fine to paste, only the VO line for post needs fixing.
                _vo_only = all(g.startswith(("the VO line", "the internal line")) for g in _dgaps)
                reply = (reply or "").rstrip() + (
                    "\n\n(Office correction: " + "; ".join(_dgaps) +
                    (". The fence itself is fine to paste -- only the VO line "
                     "for post needs fixing. Say \"fix the VO\" and I will.)"
                     if _vo_only else
                     ". Do not paste this fence as-is -- that dialogue has to "
                     "go back in first. Say \"add the missing lines\" and I "
                     "will.)"))
        # THE LENGTH NET (Elliot, shot asks, 2026-09-20) -- see
        # _shot_length_gaps. MEASURES ONLY. IT MUST NEVER RE-RUN THE TURN.
        #
        # 🔴 WHY, measured the same night it was built (Barry: "i spendin waay
        # too much time writing shot 02... you changed too much"). From
        # data/bonsai_server.log, shot 02 cost 17.6 MINUTES in two passes:
        #   pass 1  53,683 tok prefill 216s + 6,144 tok generated 393s = 10.2m
        #   pass 2  53,647 tok prefill 216s + 3,575 tok generated 229s =  7.4m
        # EVERY re-run pays the WHOLE 53K prefill again (~216s) plus a whole
        # new generation, so one net costs ~7.5 minutes of his evening. The
        # first version of this net re-ran to make the reply SHORTER -- i.e.
        # it spent a second full-length generation to punish length, which
        # doubles the exact cost it exists to reduce. That was a design error,
        # not a tuning problem, and no ceiling value fixes it.
        #
        # The pressure that is allowed to cost nothing stays: the ceilings are
        # stated as numbers in the shot directive, and going over is NAMED in
        # the reply so Barry can see it and cut. A long shot is usable; a
        # 25-minute wait is not. Contrast the DIALOGUE net above, which does
        # re-run on purpose -- a missing spoken line silently breaks a render,
        # which is worth 7.5 minutes where padding is not.
        if req.agent_id == MOVIE_ID and _src_blocks and _seedance_reply and not (req.personal or req.reply_to):
            _lgaps_len = _shot_length_gaps(reply)
            if _lgaps_len:
                print(f"[length-net] MovieDirector: {'; '.join(_lgaps_len)[:200]} -- noted, NOT re-running")
                reply = (reply or "").rstrip() + (
                    "\n\n(Office note: over the length budget -- " +
                    "; ".join(_lgaps_len) + ". Delivered as written; trim on "
                    "paste, or say \"tighten it\" and I will cut it.)")
        # THE LESSON NET, ALL SEATS (2026-09-10) -- see _lesson_claim_gaps.
        if _use_tools and not (req.personal or req.reply_to):
            _lgaps = _lesson_claim_gaps(req.message, reply, tool_call_log)
            if _lgaps:
                print(f"[lesson-net] {agent['office_name']}: {_lgaps[0]} -- re-running once")
                _msgs = [dict(m) for m in messages]
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _msgs[_i]["content"] = (_msgs[_i].get("content") or "") + (
                            "\n\n[OFFICE CHECK -- " + _lgaps[0] +
                            ". remember_lesson is a real tool on your roster. Call "
                            "it NOW with the lesson in your own words, why it "
                            "matters, and how you will apply it; then give the "
                            "reply. A lesson only exists once the tool says Kept.]")
                        break
                reply = await llm_router.generate(
                    backend, system_prompt, _msgs, model=model, use_tools=True,
                    extra_tools=extra_tools, tool_call_log=tool_call_log,
                    office_name=agent["office_name"],
                    allow_web_search=not memory.is_offline_mode(), use_thinking=use_thinking,
                    fallback_model=AGENT_BONSAI_FALLBACK_MODELS.get(req.agent_id)
                    or AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id))
                if _lesson_claim_gaps(req.message, reply, tool_call_log):
                    print(f"[lesson-net] {agent['office_name']} still -- marking the reply")
                    reply = (reply or "").rstrip() + (
                        "\n\n(Office correction: that lesson was NOT kept -- "
                        "remember_lesson was never called, so it will not be "
                        "there next time.)")
        # THE GUARANTEE (2026-09-02, Barry: "if i tell victor stuff he needs to be
        # able to put others to task by running it all through Priya first").
        # If Barry gave the CEO genuine team work (strong signal, not a bare
        # name) and, after the nudge AND the re-run, still no brief exists, the
        # office files it to Priya itself -- Barry's words verbatim -- and says
        # so in the reply. The huddle and the board take it from there. Victor
        # keeps his judgment on everything that is not clearly team work.
        #
        # EXTENDED TO PRIYA + THE ON-CALL DOOR (2026-09-11). Barry told Priya at
        # her OFFICE window, Thursday 7pm: "remember to help find great
        # backpacks, bags and luggage for drop ship or wholesale." She promised
        # a list by morning; nothing was filed, searched or written, and two
        # days later he asked where it was. His rule for that window: "the
        # office is the on call part of their lives... where i can give them
        # stuff when not on the clock for them to work on the next day." So:
        # genuine work handed to Victor OR Priya that they did not ACT on this
        # turn (no delegate, no search, no file, no note) is filed to the board
        # in his words -- and if the office is closed it is held until it
        # opens (`not_before`), which is exactly "work on it the next day".
        #
        # THEN ALL OF THEM, AND THE HOME TOO (Barry, same night: "make sure they
        # are all wired to function like a business. their home is the real
        # only private part. no business is ever told there"). Every business
        # seat (not Taliyah) is covered; the brief goes to THAT seat (Victor's
        # go to Priya as before) with Victor tracking. And a work ask that
        # lands at someone's HOME is not discussed there -- tools are off in
        # that room by design, so it is filed the same way and the reply says
        # it belongs at the office. Nothing is worked at home, nothing is lost.
        _acted = {"delegate_to", "search_web", "send_file_to_barry", "save_note"} & set(tool_call_log or [])
        _biz_seat = req.agent_id in AGENTS and req.agent_id != TALIYAH_ID
        _did_nothing = ("delegate_to" not in (tool_call_log or [])) if req.agent_id == CIO_ID else not _acted
        if (_biz_seat and not req.task and _team_work_strong(req.message)
                and (_is_personal or (_use_tools and _did_nothing))):
            try:
                _who = reflect.HUMAN_NAMES.get(req.agent_id, agent["name"])
                _to_office = "Operations" if req.agent_id in (CIO_ID, OPERATIONS_ID) else agent["office_name"]
                _hold = _next_open_utc_iso()
                _room = "at home" if _is_personal else "at the office"
                _bid = teamwork.file_brief(
                    "CIO", _to_office,
                    "From Barry, in his words" + ("" if req.agent_id == CIO_ID else f" (told to {_who} {_room})")
                    + ": " + (req.message or "").strip()
                    + (f"\n\n(Filed by the office because {_who} was at home, where no work is done. "
                       if _is_personal else
                       f"\n\n(Filed by the office because {_who} answered without acting on it. ")
                    + "Victor: track it. Deliver the finished work to Barry as a FILE on his "
                      "DESK with send_file_to_barry, and say plainly what was found and what "
                      "was not.)",
                    not_before=_hold)
                _when = clock.next_open() if _hold else "now -- the office is open"
                print(f"[handoff-net] office filed brief #{_bid} to {_to_office} with Barry's words"
                      + f" ({_room})" + (f", held until {_hold}" if _hold else ""))
                _lands = ("it gets worked " + _when + " and lands on your DESK") if _hold \
                    else "it gets worked now and lands on your DESK"
                if _is_personal:
                    reply = (reply or "").rstrip() + (
                        f"\n\n(That's office work, not for here -- it's on the board as brief "
                        f"#{_bid} in your own words; {_lands}.)")
                else:
                    reply = (reply or "").rstrip() + (
                        f"\n\n(Office: this is real work and nothing was filed, so it is on the "
                        f"board as brief #{_bid} in Barry's own words; {_lands}.)")
            except Exception as _exc:  # noqa: BLE001
                print(f"[handoff-net] office file failed: {_exc}")
        # Always False since call_team_meeting was replaced by delegate_to
        # (2026-08-03) -- kept only so the response shape doesn't change for
        # the dashboard, which reads but no longer acts on it.
        calls_meeting = False
        if req.agent_id == TALIYAH_ID:
            # Regex pass only (free, catches known-exact offenders), applied
            # before logging so stored history/facts don't carry the slang.
            #
            # THE LLM REWRITE PASS IS RETIRED (2026-08-21, Barry: "get rid
            # of the scrub slang. i ll see how she talks after"). Why it
            # existed: on the 9b, prompt rules measurably could not stop
            # novel slang ("fam", "tryna", "dat"), so a second persona-free
            # rewrite call was the only fix. Why it's gone: it was
            # hardwired to the OLLAMA backend, and under the one-big-thing
            # VRAM rule every Taliyah reply therefore KILLED the shared
            # Bonsai server, loaded the 9b, and forced a cold Bonsai
            # restart + full re-prefill on the next message -- ~45s
            # replies for her and cold starts for every other seat after
            # her. She runs on Bonsai now, which holds register far
            # better; a REGISTER rule sits in her recency tail instead.
            # REVERT if slang returns: restore
            #   reply = await tone_guard.rewrite_taliyah_reply(reply, model)
            #   reply = tone_guard.clean_taliyah_reply(reply)
            # (ideally gated to fire only when the first regex pass
            # actually changed something).
            reply = tone_guard.clean_taliyah_reply(reply)
        # NOTE: the reply is logged to history AFTER the Elliot correction
        # block below, not here. See the comment there -- logging the raw
        # text taught him his own broken output every turn.

        # THE PRIYA MIRROR IS DEAD (Barry, 2026-08-26: "Priyah should not be
        # able to see Victor and I private conversations"). It used to copy
        # every CIO exchange into her private brain -- and because the fact
        # had no .md suffix, every copy rode ALWAYS-ON in her prompt forever.
        # His conversations with Victor are private now, full stop. If Victor
        # wants Priya to know something, he uses delegate_to like everyone
        # else -- which was always the honest mechanism. Existing mirrored
        # facts were backed up and deleted the same day
        # (data/backup_priya_mirror_facts_2026-08-26.json).

        # Thread getting long? Roll it into a permanent summary and start fresh
        # rather than silently truncating older turns out of context forever.
        #
        # FIRE-AND-FORGET SINCE 2026-08-16 (Barry: "he responds slow" -> "that
        # looks like a logic issue" -- it was). This used to be AWAITED right
        # here, inside the request: every 20th message ran a SECOND full LLM
        # call on the same GPU, and Barry sat watching a spinner for it.
        # Measured on Elliot: his actual reply to "say ok" was "Ok." (3 chars,
        # instant) but the turn took 88s, because the summarizer then
        # generated 1,310 tokens he never sees. Nothing in the response
        # depends on the summary -- it writes a private fact and clears
        # history -- so the user must not wait for it.
        #
        # Ordering safety: the task is created AFTER this turn's messages are
        # already logged, and mark_activity_start/end still brackets the
        # request, so ideation stays out of the way. Two summaries can't
        # overlap for one agent because the first clears the conversation
        # below the threshold before a second could qualify.
        if memory.count_conversation(req.agent_id) >= HISTORY_SUMMARY_THRESHOLD:
            asyncio.create_task(_summarize_and_reset_thread(req.agent_id, agent))

        # Hard gate: anything tagged as an external action type NEVER returns
        # as a normal chat reply that could be mistaken for "already done" -
        # it goes to the approval queue instead.
        approval_id = None
        if req.action_type in EXTERNAL_ACTION_TYPES:
            approval_id = memory.queue_for_approval(req.agent_id, req.action_type, reply)

        # Elliot's unrequested-fence strip (2026-08-16, the last piece of
        # "finish with Elliot"). Measured three times in one day: asked for
        # script TEXT, he answered with an ```image``` fence claiming it was
        # verbatim -- including once IN THE SAME REPLY that acknowledged a
        # brand-new standing rule against exactly that. Two prompt rules and
        # a captured standing rule all lost to the habit, so this is code,
        # per the same precedent as Sophie's live-site gate: deterministic,
        # cannot be ignored. If Barry's message shows no image/video intent,
        # every fence comes out of the reply before extraction, so the
        # dashboard's Generate button correctly has nothing to grab either.
        # Scoped to Elliot alone -- for Vivian and Taliyah volunteering a
        # fence is near their actual job.
        # Short follow-ups to a fence-bearing reply ("redo it", "tighter",
        # "again") are edits to the PROMPT, not story talk -- if the last
        # assistant turn carried a fence and this message is a brief
        # imperative, the fence survives (2026-08-21, "i think you broke,
        # my shit"). A real story pivot is nearly always longer.
        _prev_had_fence = any(
            "```image" in (m.get("content") or "")
            for m in history[-2:] if m.get("role") != "user")
        _fence_follow_up = _prev_had_fence and len(req.message.strip()) <= 40
        if (req.agent_id == MOVIE_ID and not _shot_ask and not _fence_follow_up
                and not _IMAGE_INTENT_RE.search(req.message)):
            _stripped = _strip_unrequested_fences(reply)
            if _stripped != reply:
                print(f"[fence-strip] removed unrequested fence(s) from Elliot's reply")
                reply = _stripped

        # Voice locks out of the music channel -- runs BEFORE extraction so
        # the fence Barry copies and the prompt the Generate button gets are
        # both corrected. Elliot only; nobody else writes voice locks.
        if req.agent_id == MOVIE_ID:
            # ORDER IS LOAD-BEARING -- see _MOVIE_REPLY_FIXES. Adding a new
            # post-processor means adding one row to that table, not another
            # copy of this block.
            for _fix, _label in _MOVIE_REPLY_FIXES:
                _fixed = _fix(reply)
                if _fixed != reply:
                    print(_label)
                    reply = _fixed

        # NOBODY LEAVES ANYTHING ON A DESK -- ALL NINE, LIVE CHAT TOO.
        # The scrubber was built for reflections (2026-08-31), and the very
        # next day Victor told Barry in a LIVE chat "I'll have the vendor decks
        # and sample requests on your desk first thing." Same invented
        # delivery, different code path. Past-tense claims become an honest
        # "I have not filed anything yet"; future-tense keeps the promise but
        # names the real mechanism (the approval queue). Runs BEFORE the
        # history write, per the 2026-08-23 lesson directly below -- otherwise
        # the thread teaches the phrase straight back.
        try:
            _scrubbed, _desk_fixes = reflect._scrub_delivery_claims(reply)
            if _desk_fixes:
                print(f"[desk-claim] corrected {_desk_fixes} invented "
                      f"delivery claim(s) from {agent['office_name']}")
                reply = _scrubbed
        except Exception as _exc:            # never cost Barry the answer
            print(f"[desk-claim] scrub skipped: {_exc}")

        # CROSS-CHECK + COUNCIL (2026-09-15, reasoning.py). Work channel, live
        # chat only (task/board turns have their own nets), never at home,
        # never Elliot. Council: Victor on a one-way-door decision -> Amara,
        # Marcus, Derek answer from their lanes, Victor writes the memo.
        # Cross-check: Amara audits Victor's figures on a decision ask;
        # Marcus audits Derek's product claims on copy. Verdicts ride
        # verbatim under the reply; a checker that cannot run changes nothing.
        if (not _is_personal and not req.task and not req.brief_id
                and req.agent_id in (CIO_ID, MARKETING_ID)
                and (reply or "").strip() and not reply.lstrip().startswith("[")):
            try:
                if req.agent_id == CIO_ID and reasoning.is_council_ask(req.message):
                    print(f"[council] convened on :: {req.message[:70]!r}")
                    reply, _ = await reasoning.council(req.message, reply, _gen_judge)
                elif req.agent_id == CIO_ID and reasoning.needs_number_check(req.message, reply):
                    reply = reply.rstrip() + await reasoning.cross_check(
                        "numbers", BUSINESS_ID, "Amara", req.message, reply)
                elif req.agent_id == MARKETING_ID and reasoning.needs_claim_check(req.message, reply):
                    reply = reply.rstrip() + await reasoning.cross_check(
                        "claims", LEGAL_ID, "Marcus", req.message, reply)
            except Exception as _exc:  # noqa: BLE001
                print(f"[reasoning] check skipped: {_exc}")

        # HISTORY GETS THE CORRECTED REPLY, NOT THE RAW ONE (moved here
        # 2026-08-23). It used to be logged immediately after generation --
        # i.e. BEFORE the voice-lock, weapon-handle, audio-glyph and
        # internal-VO corrections ran. Barry saw the fixed text; the thread
        # stored the broken text; and the thread is what rides back into the
        # next turn. So every correction was undone as a teaching signal one
        # message later, and Elliot re-learned "<[]>" from his own logged
        # output indefinitely. That is why the glyph kept coming back after
        # being named explicitly in the directive.
        # Nothing between generation and here reads the conversation table
        # for this turn, so moving the write is safe; agents with no
        # corrections are byte-identical either way.
        if not req.task:
            memory.log_message(req.agent_id, "agent", reply,
                               channel="personal" if _is_personal else "work")

        # (HE SENDS THEM TO EACH OTHER -- the call now runs BEFORE her reply; see "THE CALL
        # HAPPENS FIRST" where the per-message context is built.)

        # PERSONAL CONVERSATIONS ARE KEPT VERBATIM (Barry, 2026-08-27: "they
        # should remember these conversations so they get to know me and i
        # get to know them"). The raw thread gets summarized away at 20
        # messages and the generic summarizer is lossy -- so every
        # personal-channel exchange is ALSO appended, word for word, to the
        # agent's own mind-with-barry journal (monthly fact, on-demand,
        # mind- prefix: feeds their reflections via _inner_life, never
        # leaks into work recall). This is how they genuinely get to know
        # him -- his actual words, not a summary's paraphrase.
        if _is_personal:
            # THEY EVOLVE, LIVE (2026-09-10): a reply may end with one line
            # "ABOUT ME NOW: <sentence>" -- something that has become true
            # about them, said to Barry in the moment. It is added to their own
            # section of the personality file (never Barry's part), the line is
            # taken out of what he sees, and the rest of the reply stands.
            _m_about = re.search(r"^\s*ABOUT ME NOW:\s*(.+?)\s*$", reply, re.M)
            if _m_about:
                _about = _m_about.group(1).strip()
                reply = (reply[:_m_about.start()] + reply[_m_about.end():]).strip()
                if ingest.append_personality(agent["office_name"], _about):
                    print(f"[personality] {req.agent_id} added to their own "
                          f"section from the personal channel ({len(_about)} chars)")
            try:
                import reflect as _reflect
                _first = _reflect.HUMAN_NAMES.get(req.agent_id, req.agent_id.title())
                _month = datetime.date.today().strftime("%Y-%m")
                _sn = f"mind-with-barry-{_month}.md"
                _cat = f"private:{agent['office_name']}"
                with memory.get_db() as _conn:
                    _row = _conn.execute(
                        "SELECT content FROM facts WHERE category = ? AND "
                        "source_name = ? AND status = 'active' "
                        "ORDER BY id DESC LIMIT 1", (_cat, _sn)).fetchone()
                _hdr = (f"CONVERSATIONS WITH BARRY, PERSONAL -- {_month}\n"
                        f"[{_first}'s own record of off-the-clock talks with him]")
                _body = _row["content"] if _row else _hdr
                _stamp = datetime.datetime.now().strftime("%m-%d %I:%M %p").lstrip("0")
                _body += (f"\n\n[{_stamp}]\nBarry: {req.message.strip()}\n"
                          f"{_first}: {reply.strip()}")
                # cap: keep the header + the newest tail, drop the oldest
                if len(_body) > 18_000:
                    _tail = _body[-16_000:]
                    _cut = _tail.find("\n\n[")
                    _body = _hdr + (_tail[_cut:] if _cut != -1 else _tail)
                _reflect._store(agent["office_name"], _sn,
                                f"{_first}'s personal talks with Barry -- {_month}",
                                _body)
            except Exception as _exc:
                print(f"[personal-memory] failed for {req.agent_id}: {_exc}")

        # For agents with real image generation (Vivian, Taliyah), pull out
        # just the clean image (+ optional negative) prompt if included, so
        # the frontend's "Generate Image" action has something a diffusion
        # model can actually use, not the whole reply.
        image_prompt = None
        negative_prompt = None
        model_choice = None
        if is_image_capable(req.agent_id):
            image_prompt = extract_image_prompt(reply)
            negative_prompt = extract_negative_prompt(reply)
            model_choice = extract_model_choice(reply)
            # Trigger on any of three signals -- chasing exact refusal
            # phrasing with regex proved to be real whack-a-mole (missed
            # "still beyond my capabilities", missed plural "images"), so
            # this leans on the more robust one: was an image plainly asked
            # for ANYWHERE in the last few turns, not just this exact
            # message. Covers a bare follow-up like "try again" that carries
            # no image keywords of its own but is clearly still the same
            # request. _IMAGE_REFUSAL_RE stays as a secondary net for a
            # request phrased in a way none of the recent turns catch.
            # HIS WORDS ONLY (2026-09-28, Barry: "why is Bonsai always dropping?").
            # messages[-1] is his message WRAPPED in the office's [AUTOMATIC CONTEXT]
            # block (home room, shot-ask directives...), whose own wording matched
            # _IMAGE_REQUEST_RE -- so this Ollama-only fallback fired after nearly
            # every Amara/Elliot turn, and every Ollama call stops Bonsai (8 of the
            # day's llama-server restarts, each costing the next reply a ~43 s
            # re-read). Earlier user rows are his raw words from the thread; the
            # current one is req.message, never the wrapped copy.
            # FOLLOW-UPS ONLY (2026-09-30, Barry: "she still over thinking 2 lines"). The 3-turn
            # lookback kept one old ask alive for three more turns: "make a Tik Tok ... for you to
            # make videos" fired this fallback after Ilnora's next 4 replies, each stop costing the
            # following message a cold Bonsai reload (~160 s re-read of her 20K prompt). The
            # lookback exists for a bare "try again" -- so only a short message looks back, one turn.
            _prev_user = [m["content"] for m in messages[:-1] if m["role"] == "user"][-1:]
            recent_user_turns = ((_prev_user if len((req.message or "").split()) <= 8 else [])
                                 + [req.message])
            image_was_requested = any(_IMAGE_REQUEST_RE.search(t) for t in recent_user_turns)
            if image_prompt is None and (image_was_requested or _IMAGE_REFUSAL_RE.search(reply)):
                # This fallback always runs on Ollama regardless of the
                # global backend dropdown -- Claude never needs it (it
                # doesn't have this refusal reflex), and there's no Claude
                # model that makes sense to pass here anyway.
                fallback_model = AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id, model if backend == "ollama" else None)
                fallback_context = "\n".join(recent_user_turns)
                # Taliyah has an established look (see agents.py) that a
                # persona-free call has no way to know about on its own --
                # without this, "generate an image of yourself" produces
                # something generic and wrong instead of actually her.
                self_appearance = AGENT_SELF_APPEARANCE.get(req.agent_id)
                if self_appearance and re.search(r"\b(yourself|you|your)\b", fallback_context, re.IGNORECASE):
                    fallback_context += f"\n\n(If this is about 'yourself'/'you': {self_appearance})"
                forced = await _force_image_prompt(fallback_context, fallback_model)
                image_prompt = extract_image_prompt(forced)
                negative_prompt = extract_negative_prompt(forced) or negative_prompt
                model_choice = extract_model_choice(forced) or model_choice
            # Guard BOTH paths above: if what we ended up with reads like
            # conversation rather than a prompt (see _looks_like_chat_prose),
            # run it through the same persona-free rewrite whose only job is
            # a clean fence. Only a prose-looking prompt pays this extra
            # small call; a clean fence passes straight through.
            if image_prompt and _looks_like_chat_prose(image_prompt):
                rewrite_model = AGENT_OLLAMA_MODEL_OVERRIDES.get(req.agent_id, model if backend == "ollama" else None)
                forced = await _force_image_prompt(
                    "Distill ONLY the image being described here into a clean "
                    "prompt (ignore all the chatter around it):\n" + image_prompt,
                    rewrite_model,
                )
                cleaned = extract_image_prompt(forced)
                if cleaned and not _looks_like_chat_prose(cleaned):
                    image_prompt = cleaned

        return {
            "reply": reply,
            "agent_id": req.agent_id,
            "image_prompt": image_prompt,
            # the LTX prompt, when Elliot wrote one (local gen ask, 2026-09-23)
            "video_prompt": extract_video_prompt(reply) if req.agent_id == MOVIE_ID else None,
            "negative_prompt": negative_prompt,
            "model": model_choice,
            "queued_for_approval": approval_id is not None,
            "approval_id": approval_id,
            "calls_meeting": calls_meeting,
            # When Barry's own words ("i like that", "thats the way i want
            # it") save an exemplar, SAY SO. Silent capture is untrustworthy
            # -- he'd never know whether a phrase registered, which is the
            # one thing the MORE LIKE THIS button had over just talking.
            "exemplar_saved": _exemplar_saved,
            "session_cost_usd": llm_router.get_session_cost(),
            # Owner's ask (2026-07-30): when the Bonsai backend fails and
            # the reply silently comes from the Ollama fallback, SAY SO --
            # the dashboard shows a toast off this flag.
            "bonsai_fell_back": backend == "bonsai" and llm_router.bonsai_fell_back(),
            # 2026-09-02: the board (teamwork.work_one) needs to know whether a
            # brief run actually looked anything up -- a reply full of prices
            # from a run with no tool call is invented. Additive field.
            "tool_calls": list(tool_call_log or []),
            # 2026-10-08 (fact net): the exact tool text the model saw this turn -- what she READ -- so the office's
            # callers (video_queue.write_long) can check her script against it. Loopback-only API.
            "sources": list(claim_net.tool_results.get() or []),
        }
    finally:
        tracing.reset_call_context(_ctx_tok)
        ideation.mark_activity_end()


@app.get("/api/outputs/{agent_id}")
def list_agent_outputs(agent_id: str):
    """Every output a specific agent has ever produced (any status), most
    recent first -- powers the office's Outputs panel (see agent_ui.gd /
    main_chat_bar.gd), a real per-agent archive rather than just the
    transient pending-review queue."""
    if get_agent(agent_id) is None:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    return memory.get_agent_outputs(agent_id)


@app.get("/api/dashboard/stats")
def dashboard_stats():
    """Per-agent message + pending counts for the web dashboard's card
    badges (AgentDashboard/) -- read-only, doesn't touch /api/agents'
    existing response shape that the Godot app depends on."""
    return {agent_id: memory.get_agent_stats(agent_id) for agent_id in all_agents()}


@app.get("/api/approvals")
def list_approvals():
    return memory.get_pending_approvals()


@app.get("/api/approvals/approved")
def list_approved():
    """The Approved box -- see memory.get_approved_approvals."""
    return memory.get_approved_approvals()


_FIX_SUGGESTION_RE = re.compile(
    r"^Target: (?P<target>[^\n]*)\nDiagnosis: (?P<diagnosis>[^\n]*)\nSuggested note: (?P<note>.*)$",
    re.DOTALL,
)


async def _render_and_install_scene(agent_id: str, slot: str, description: str):
    """Barry approved a scene change: render it, then put it in place.

    Runs detached from the approve request so his click returns instantly --
    a render is minutes, and an HTTP call should never hold that long.
    """
    import agent_scenes
    try:
        agent = get_agent(agent_id)
        if agent is None:
            print(f"[scene] no agent '{agent_id}'")
            return
        prompt = description
        reference = None
        # A picture WITH the person in it needs their real face and body;
        # a room does not, and passing a face reference to an empty room is
        # how people end up in scenes that should have none.
        if slot in agent_scenes.WITH_PERSON:
            # One door for every picture they appear in (2026-09-10): the
            # editor restages Barry's own picture of them when one is staged
            # (agent_ref_<id>.png), else the old face/body IP-Adapter path.
            # The office plate shows them AT WORK -- same rule as the
            # 2026-09-01 plates, so the chamber's "at the office" view keeps
            # the person in the scene and hides the cutout.
            result = await _render_self_picture(
                agent_id, description, at_work=(slot == "office"))
        else:
            # A ROOM, asked for as a room -- see _room_only_prompt. The old
            # line here appended ", no people, empty room" to the POSITIVE
            # prompt, which is how three seats ended up with a person in a
            # plate that is supposed to have none.
            prompt = _room_only_prompt(description, _person_first_name(agent_id))
            print(f"[scene] {agent_id}/{slot} room prompt: {prompt[:160]}")
            result = await generate_image(ImageGenerateRequest(
                prompt=prompt, agent_id=agent_id))

        path = (result or {}).get("file_path") or (result or {}).get("path")
        if not path:
            print(f"[scene] render returned no file for {agent_id}/{slot}: {result}")
            return {"installed": False, "error": "render returned no file"}
        outcome = agent_scenes.install(agent_id, slot, path)
        print(f"[scene] {agent_id}/{slot}: {outcome}")
        # THEIR NEW PLACE BECOMES THEIR PLACE (2026-09-28, Barry: "they should all pick a new home
        # as well and all that" / "when they get there"). A picture change used to swap only the
        # image; their home stayed described in the old words, so visits and evenings still put
        # Victor in the old den. Now their own words for the new place become the description
        # (old one superseded, never deleted).
        _desc_doc = {"home": ("my-home.md", "MY-HOME\nUSE WHEN: your home, your place, where you live, "
                              "being at home, off the clock at your place.\n\nYOUR HOME ({n}) -- in your "
                              "own words, {d}:\n"),
                     "self": ("my-home-self.md", "MY-HOME-SELF\nUSE WHEN: how you are at home, your "
                              "off-the-clock self, what you wear and do at your place.\n\nYOUR AT-HOME "
                              "SELF ({n}) -- your own words, {d}:\n"),
                     "office": ("me-in-my-office.md", "ME-IN-MY-OFFICE\nUSE WHEN: your workspace, your "
                                "office, your desk, how you look and what you wear while working.\n\n"
                                "({n}) -- your own words, {d}:\n")}.get(slot)
        if _desc_doc and (outcome or {}).get("installed") and (description or "").strip():
            try:
                _ag = get_agent(agent_id)
                _n = reflect.HUMAN_NAMES.get(agent_id, agent_id.title())
                reflect._store(_ag["office_name"], _desc_doc[0], _desc_doc[0][:-3],
                               _desc_doc[1].format(n=_n, d=datetime.date.today().isoformat())
                               + description.strip())
                print(f"[scene] {agent_id}/{slot}: their own words are now {_desc_doc[0]}")
            except Exception as _exc:  # noqa: BLE001
                print(f"[scene] {agent_id}/{slot}: description not saved: {_exc}")
        return outcome
    except Exception as exc:
        # Never raise out of a background task -- it would just vanish.
        print(f"[scene] failed for {agent_id}/{slot}: {exc}")
        return {"installed": False, "error": str(exc)[:200]}


async def _render_artwork(agent_id: str, medium: str, description: str):
    """A piece one of them made because they wanted to (2026-09-18).

    Unlike a scene this installs NOWHERE -- it is not their room or their face,
    it is a work, so it lands in their gallery and Barry's queue and stops
    there. Rendered at print size: Real-ESRGAN x4 on the Qwen output, then the
    file is stamped 300dpi so a print dialog reports real inches.
    """
    import artwork
    try:
        result = await generate_image(ImageGenerateRequest(
            prompt=artwork.render_prompt(medium, description, agent_id),
            agent_id=agent_id, upscale=artwork.UPSCALE))
        if (result or {}).get("error"):
            return {"rendered": False, "error": result["error"]}
        path = (result or {}).get("file_path") or (result or {}).get("path")
        if not path:
            return {"rendered": False, "error": "render returned no file"}
        out = {"rendered": True, "path": path, "medium": medium}
        out.update(artwork.stamp_dpi(path))
        print(f"[artwork] {agent_id} [{medium}]: {out}")
        return out
    except Exception as exc:  # noqa: BLE001 -- background task, never raise
        print(f"[artwork] failed for {agent_id}/{medium}: {exc}")
        return {"rendered": False, "error": str(exc)[:200]}


async def _scene_queue_loop():
    """THE OFFICE PUTS THEIR PICTURES WHERE THEY GO (Barry, 2026-09-11: "i want
    sophie to just put the images where they are supposed to go"). Every
    minute: if a picture change an agent filed on their own (change_my_picture
    in chat, or the MY PICTURE door in a reflection) sits approved with
    dispatch_status='queued', and the office is quiet and nothing holds the
    card, render ONE and install it. Same render+install as the approve
    click; only the click is gone. Guards: no live chat for 90s, no render in
    progress, one at a time, never twice for the same row."""
    import agent_scenes
    await asyncio.sleep(150)
    while True:
        try:
            if (ideation._active_chat_count == 0
                    and (time.time() - ideation._last_activity_at) >= 90
                    and not comfy_image.render_in_progress()
                    and not ideation._video_building()):
                with memory.get_db() as conn:
                    # artwork rides the SAME loop and the same guards (2026-09-18):
                    # one card, one render at a time, and a second loop would be a
                    # second thing racing for it.
                    row = conn.execute(
                        "SELECT id, agent_id, file_path, content, action_type FROM approvals "
                        "WHERE action_type IN ('agent_scene', 'artwork') "
                        "AND status = 'approved' AND dispatch_status = 'queued' ORDER BY id LIMIT 1").fetchone()
                    if row:
                        conn.execute("UPDATE approvals SET dispatch_status = 'rendering' WHERE id = ?", (row["id"],))
                if row:
                    target, _, slot = (row["file_path"] or "").partition("|")
                    desc = (row["content"] or "").split("\n\n", 1)[-1].strip()
                    is_art = row["action_type"] == "artwork"
                    print(f"[scene-queue] rendering approval {row['id']} for {target}/{slot}")
                    if is_art:
                        outcome = await _render_artwork(target, slot or "painting", desc) or {}
                        done = bool(outcome.get("rendered"))
                    else:
                        outcome = await _render_and_install_scene(target, slot or "home", desc) or {}
                        done = bool(outcome.get("installed"))
                    with memory.get_db() as conn:
                        conn.execute("UPDATE approvals SET dispatch_status = ?, dispatched_at = ?, dispatch_response = ?, file_path = ? WHERE id = ?",
                                     ("rendered" if (done and is_art) else "installed" if done else "failed",
                                      datetime.datetime.now(datetime.UTC).isoformat(),
                                      json.dumps(outcome)[:800],
                                      # an artwork row's file_path becomes the real
                                      # file, so it shows in her gallery like any render
                                      (outcome.get("path") or row["file_path"]) if is_art else row["file_path"],
                                      row["id"]))
                    print(f"[scene-queue] approval {row['id']}: {'done' if done else 'FAILED'} -- {outcome.get('path') or outcome.get('error')}")
        except Exception as exc:  # noqa: BLE001 -- a loop must never die
            print(f"[scene-queue] loop error: {exc}")
        await asyncio.sleep(60)


def _is_media_row(entry: dict) -> bool:
    """A render (image/clip) or a picture-of-their-place row. The learning
    loop must not write PRIORITY/LESSON facts for these (2026-09-11).
    2026-09-22: nor for Sophie's plumbing rows -- approving `ollama list` or a
    config edit became an always-on "the real thing to focus on next" fact;
    23 of them rode every one of her messages."""
    if (entry or {}).get("action_type") in ("agent_scene", "engineer_task", "code_fix", "file"):
        return True
    fp = ((entry or {}).get("file_path") or "").lower()
    return fp.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "mp4", "webm") if "." in fp else False


# Office-decision cards: approve/reject is Barry's call on a TASK, never a send.
_OFFICE_CARD_TYPES = {"task_confirm"}


@app.post("/api/approvals/{approval_id}/decide")
def decide(approval_id: int, decision: ApprovalDecision):
    entry = memory.get_output_by_id(approval_id)
    memory.decide_approval(approval_id, decision.approved)
    _atype = (entry or {}).get("action_type")
    if entry and _atype in _OFFICE_CARD_TYPES:
        # These cards are decisions for the OFFICE, not work for an agent: no PRIORITY/LESSON
        # fact goes into anyone's brain and nothing is dispatched anywhere.
        detail = "Noted."
        if _atype == "task_confirm":
            try:
                _bid = int((entry.get("file_path") or "").split("brief:", 1)[1])
                detail = teamwork.confirm(_bid, decision.approved)
            except (IndexError, ValueError) as _e:
                detail = f"no brief id on this card ({_e})"
        try:
            dispatch._record(approval_id, "", "kept", detail)
        except Exception:  # noqa: BLE001
            pass
        return {"id": approval_id, "approved": decision.approved,
                "dispatched": {"status": "kept", "detail": detail}}
    if decision.approved and entry:
        # Sophie's fix suggestions (see llm_router.py's submit_agent_fix
        # dispatch) resolve their own target office by parsing the
        # content (the target may be a completely different agent than
        # the one who submitted the suggestion), so they get their own
        # branch rather than the generic one below.
        if entry.get("action_type") == "agent_scene":
            # SOPHIE CHANGES AN AGENT'S ENVIRONMENT (2026-08-31). The render
            # and the file write BOTH happen here, on Barry's click -- never
            # when she proposes it. file_path carries "<agent_id>|<slot>".
            # 2026-09-11: this endpoint is SYNC (FastAPI runs it in a thread),
            # so asyncio.create_task raised "no running event loop" and the
            # coroutine was never awaited -- backend.log had the warning. The
            # click now hands the row to the scene queue loop, the same path
            # an agent's own change takes; it renders within a minute of the
            # office going quiet and installs itself.
            try:
                target, _, slot = (entry.get("file_path") or "").partition("|")
                with memory.get_db() as _conn:
                    _conn.execute("UPDATE approvals SET dispatch_status = 'queued' WHERE id = ?", (approval_id,))
                return {"ok": True, "approved": True,
                        "scene": "queued for %s [%s]; the office renders it as soon as the "
                                 "card is free and installs it itself" % (target, slot)}
            except Exception as exc:
                print(f"[scene] approve failed: {exc}")
        if entry.get("action_type") == "fix_suggestion":
            match = _FIX_SUGGESTION_RE.match(entry.get("content", ""))
            if match:
                memory.add_fact(
                    f"private:{match.group('target')}",
                    "PRIORITY -- Barry approved this fix, act on it directly: "
                    + match.group("note").strip(),
                    source_name="Sophie -- fix suggestion (approved)",
                )
        else:
            # Owner's explicit request: approving something should make it
            # the actual focus for whoever's meant to act on it, not just a
            # status flip in a database row -- generalizes the pattern
            # above (already proven for fix suggestions) to every other
            # approval type. Written into the ISSUING agent's own brain so
            # their next real conversation with Barry treats this as the
            # priority instead of just background context.
            agent = get_agent(entry.get("agent_id"))
            # NOT FOR PICTURES (2026-09-11). Every accepted show-offer wrote
            # "PRIORITY -- deliver next: Amara ... olive silk camisole" into
            # her ALWAYS-ON brain -- three times -- and from then on every
            # nude ask came back in the camisole. A picture he liked is not a
            # standing order to repeat it; taste on renders lives in the
            # gallery, not in the prompt.
            if agent and not _is_media_row(entry):
                memory.add_fact(
                    f"private:{agent['office_name']}",
                    "PRIORITY -- Barry approved this, it's the real thing to "
                    "focus on and deliver next, not just something discussed: "
                    # Excerpt only, symmetric with the rejection branch below.
                    # This fact is ALWAYS-ON (no .md source_name), so storing the
                    # full body meant one approved long-form post rode along on
                    # every future message forever -- the exact context bloat
                    # cleaned out on 2026-08-03. The full text is never lost;
                    # it stays in the approvals table / Out box.
                    + (entry.get("content", "") or "")[:300],
                    source_name=f"Approved {entry.get('action_type', 'output')}",
                )
    elif entry and not decision.approved:
        # Learning loop (owner, 2026-07-31: "they should actually learn...
        # and always get better"): a rejection is the most direct signal an
        # agent gets about Barry's taste, and it used to vanish silently.
        # Now the issuing agent remembers what DIDN'T fly -- a compact
        # excerpt, so years of rejections inform without flooding context.
        if entry.get("action_type") != "fix_suggestion":
            agent = get_agent(entry.get("agent_id"))
            # Not for pictures either (2026-09-11): "Barry REJECTED ... Amara
            # at home, natural state" rode ALWAYS-ON in her brain twice, so a
            # quality rejection read to her as "nude was refused". See the
            # approve branch above.
            _note = (decision.note or "").strip()[:400]
            _designed = entry.get("action_type") == "email" and (entry.get("omnisend_template_id") or "").strip()
            _to_derek, _to_vivian = True, bool(_designed)
            if _designed and _note:
                # WHO OWNS WHAT HE SAID (2026-09-26, Barry: "yes add that for vivian"). Design words
                # go to Vivian, content words to Derek, unclear/mixed to both.
                _d = bool(re.search(r"\b(design|look|looks|layout|colou?rs?|picture|pictures|image|images|photo|"
                                    r"photos|hero|font|fonts|busy|spacing|render|style|ugly|plain|basic|banner|"
                                    r"button|buttons|card|cards)\b", _note, re.I))
                _c = bool(re.search(r"\b(words?|copy|tip|tips|subject|headline|wrong|price|prices|product|"
                                    r"products|coupon|offer|writing|wrote|info|information|claim|facts?)\b", _note, re.I))
                _to_derek, _to_vivian = (_c or not _d), (_d or not _c)
            # a designed email's file_path is its screenshot (.png) -- it is still Derek's words, not a render
            if agent and (not _is_media_row(entry) or entry.get("action_type") == "email") and _to_derek:
                excerpt = (entry.get("content", "") or "")[:300]
                memory.add_fact(
                    f"private:{agent['office_name']}",
                    "LESSON -- Barry REJECTED this draft. Study what's wrong "
                    "with it before producing similar work, and do better "
                    "next time: " + excerpt
                    + (f"\nHis words: \"{_note}\"" if _note else ""),
                    source_name=f"Rejected {entry.get('action_type', 'output')}",
                )
            if _to_vivian:
                _subj = (entry.get("content", "") or "").strip().splitlines()[0][:120] if entry.get("content") else ""
                memory.add_fact(
                    "private:Creative",
                    f"LESSON -- Barry REJECTED an email you designed (draft #{approval_id}, \"{_subj}\"). "
                    + (f"His words: \"{_note}\". " if _note else
                       "He did not say why -- look at your design again (data/email_designs/"
                       f"{approval_id}/preview.png) and judge honestly what may not have worked. ")
                    + "Carry this into your next email design.",
                    source_name="Rejected email design",
                )

    # THE SEND. Barry, 2026-08-15: "it stays in agent office waiting for
    # approval and on approval it gets written and sent." Until now approving
    # only flipped a status column -- 20 items sat approved and nothing ever
    # left the building.
    #
    # dispatch_approved is the ONLY thing that talks to the outside world, and
    # it is deliberately safe to call here: it refuses anything not approved,
    # refuses anything already dispatched (dispatched_at), refuses everything
    # while Offline Mode is on, refuses an action_type with no wired
    # destination, and pushes approvals.content VERBATIM -- no model runs
    # between his click and the send. Failures are recorded on the row and
    # returned, never raised, so a dead API key or a network blip can never
    # turn an approval into a 500.
    dispatched = None
    if decision.approved:
        # Code fixes are LOCAL file changes, not outbound sends -- they get
        # their own apply path (backup + exact-once replace + syntax check +
        # restore-on-failure, see codefix.py) instead of dispatch, whose
        # sending-off gate rightly blocks everything outbound.
        if entry and entry.get("action_type") == "code_fix":
            try:
                dispatched = codefix.apply_fix(approval_id)
            except Exception as e:  # noqa: BLE001 -- reporting beats crashing here
                dispatched = {"status": "failed", "detail": str(e)}
        elif entry and entry.get("action_type") == "engineer_task":
            # Sophie's queued command / pip install / update (2026-09-06):
            # runs NOW, on his click, output recorded on the row + her journal.
            import engineer_tools
            try:
                dispatched = engineer_tools.run_approved(approval_id)
            except Exception as e:  # noqa: BLE001
                dispatched = {"status": "failed", "detail": str(e)}
        elif (entry and entry.get("action_type") == "public_content"
              and _is_media_row(entry)):
            # A RENDER (still or clip) has nowhere to go -- approving it means
            # "keep it" (2026-09-23, Barry approved Elliot's Shot 02 still and
            # the deck told him "NOT sent -- No destination wired"). Nothing
            # outbound exists for a render by design; say so plainly.
            try:
                dispatched = dispatch._record(
                    approval_id, "", "kept",
                    "Kept. A render is a picture for you, not a send -- it stays "
                    "in the Out box and the gallery.")
            except Exception as e:  # noqa: BLE001
                dispatched = {"status": "kept", "detail": str(e)}
        else:
            try:
                dispatched = dispatch.dispatch_approved(approval_id)
            except Exception as e:  # noqa: BLE001 -- reporting beats crashing here
                dispatched = {"status": "failed", "detail": str(e)}
    return {"id": approval_id, "approved": decision.approved, "dispatched": dispatched}


@app.post("/api/approvals/{approval_id}/rewrite")
async def rewrite_approval(approval_id: int):
    """Owner's 'Rewrite' button (2026-07-31): send a text draft back to the
    agent that made it for a stronger take. The rewrite runs through the
    agent's full identity + brain + live product data, and the new version
    lands as a fresh PENDING approval -- the normal pipeline, so nothing
    skips review. The original entry is left untouched."""
    entry = memory.get_output_by_id(approval_id)
    if entry is None:
        raise HTTPException(404, f"No approval with id {approval_id}")
    agent = get_agent(entry.get("agent_id"))
    if agent is None:
        raise HTTPException(400, "The agent that made this no longer exists.")
    content = entry.get("content", "")

    brain = memory.brain_context_block(agent["office_name"], include_shared=agent.get("business_context", True))
    product_data = _product_context_block(content)
    system_prompt = (
        f"{agent['system_prompt']}\n\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n{brain}\n"
        f"--- END BUSINESS KNOWLEDGE ---\n"
        f"{product_data}"
    )
    instruction = (
        "Barry wants a BETTER version of this draft of yours. Read every "
        "skill that touches it first (hooks, brand style, product data), "
        "study what he's approved and rejected before, then rewrite it "
        "stronger -- tighter hook, more concrete, more him. Reply with the "
        "improved draft only, no preamble about what you changed.\n\n"
        f"--- ORIGINAL DRAFT ---\n{content}"
    )
    backend, model = _resolve_generation_for(entry.get("agent_id"))
    reply = await llm_router.generate(
        backend, system_prompt, [{"role": "user", "content": instruction}],
        model=model, office_name=agent["office_name"],
    )
    new_id = memory.queue_for_approval(
        entry.get("agent_id"), entry.get("action_type", "public_content"), reply
    )
    return {"new_approval_id": new_id, "agent_id": entry.get("agent_id")}


@app.get("/api/outputs/{approval_id}/file")
def get_output_file(approval_id: int, download: int = 0):
    """Serves a generated output's actual file bytes (e.g. one of Vivian's
    images) by database id -- the desktop app opens file_path directly off
    disk, but a browser (the web dashboard) can't reach a raw Windows
    filesystem path, so this resolves it server-side instead of trusting
    whatever path a client sends."""
    entry = memory.get_output_by_id(approval_id)
    if entry is None:
        raise HTTPException(404, f"No output with id {approval_id}")
    file_path = entry.get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(404, "This output has no file attached")
    # 2026-09-06: a DOCUMENT (an agent's file) downloads with its real name;
    # images/video keep rendering inline in the decks' media stream.
    # 2026-09-12: `?download=1` = save-as for a picture. The decks live on
    # port 8765 and this file on 8420, and a browser ignores a link's
    # `download` attribute across origins -- so the DOWNLOAD button only ever
    # opened the image full screen. The server has to send the attachment
    # header itself (Barry: "download only made the image full screen").
    if entry.get("action_type") == "file" or download:
        return FileResponse(file_path, filename=os.path.basename(file_path))
    return FileResponse(file_path)


@app.get("/api/approvals/{approval_id}/email")
def get_email_design_info(approval_id: int):
    """What the approval box shows beside a designed email (2026-09-26, Barry: "in the approve box,
    i need to full be able to see the email"): whether Vivian designed it, her note, and the link
    check. The picture itself is /api/outputs/{id}/file -- Omnisend's own render, full length."""
    import email_design
    d = email_design.draft_dir(approval_id)
    entry = memory.get_output_by_id(approval_id) or {}
    def _read(name, as_json=False):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f) if as_json else f.read()
    links = _read("links.json", True) or {}
    return {"designed": bool((entry.get("omnisend_template_id") or "").strip()),
            "vivian_note": _read("vivian_note.txt") or "",
            "content_gaps": _read("content_gaps.json", True) or [],
            "links": {"checked": links.get("checked", 0), "broken": links.get("broken", []),
                      "not_checkable": links.get("not_checkable", [])},
            "has_sheet": os.path.exists(os.path.join(d, "sheet.json"))}


# ---------------------------------------------------------------------------
# FILES (2026-09-06, Barry: "Make them able to read, write and send me files")
# agent_files.py. Read-only endpoints; the writes happen through the agents'
# tools. The download is id-based and refuses anything outside
# data/agent_files/, so no client can turn it into an arbitrary file reader.
# ---------------------------------------------------------------------------
@app.get("/api/files")
def list_files_endpoint(agent_id: str = ""):
    """Every file the agents have made for Barry (newest first) plus what is
    on his shelf for them -- powers the FILES panel on every deck."""
    office = ""
    if agent_id:
        a = get_agent(agent_id)
        office = (a or {}).get("office_name", "") if a else ""
    return {
        "files": agent_files.list_agent_files(office),
        "inbox": agent_files.list_inbox(),
        "roots": {"files": agent_files.FILES_ROOT, "inbox": agent_files.INBOX_ROOT},
    }


@app.get("/api/files/{approval_id}/download")
def download_file_endpoint(approval_id: int):
    path = agent_files.resolve_download(approval_id)
    if not path:
        raise HTTPException(404, "No such file (or it is no longer on disk)")
    return FileResponse(path, filename=os.path.basename(path))


# SEE IT ON THE DESK (Barry, 2026-10-17: "how come i cant see mp4 in my desk? i want it to open there so i can see
# it"). Same id-only resolution as the download, served INLINE with its real media type so the panel's <video>/<img>
# plays it instead of the browser saving it. FileResponse honours Range requests, so the player can seek.
@app.get("/api/files/{approval_id}/view")
def view_file_endpoint(approval_id: int):
    path = agent_files.resolve_download(approval_id)
    if not path:
        raise HTTPException(404, "No such file (or it is no longer on disk)")
    ext = os.path.splitext(path)[1].lower()
    media = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".png": "image/png",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
             ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}.get(ext)
    return FileResponse(path, media_type=media or "application/octet-stream",
                        headers={"Content-Disposition": f'inline; filename="{os.path.basename(path)}"'})


# READ IT ON THE DESK (Barry, 2026-09-11: "I can download it, but i want to
# read it from there as well"). Same id-only resolution as the download, so
# nothing outside FILES_ROOT can be read this way; the bytes go through the
# same extractor the agents read files with, so .docx/.xlsx come back as
# text too, not just .md. Capped so a huge export cannot stall the panel.
@app.get("/api/files/{approval_id}/text")
def read_file_endpoint(approval_id: int, max_chars: int = 200_000):
    path = agent_files.resolve_download(approval_id)
    if not path:
        raise HTTPException(404, "No such file (or it is no longer on disk)")
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        text = document_extract.extract_text(os.path.basename(path), data) or ""
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not read the file: {exc}")
    cap = max(1_000, min(int(max_chars), 2_000_000))
    return {"approval_id": approval_id, "name": os.path.basename(path), "chars": len(text),
            "truncated": len(text) > cap, "text": text[:cap]}


# OFF THE DESK (Barry, 2026-09-11: "once i read or download, i need to be able
# to delete them"). Moves the file to _trash (recoverable), marks the row.
@app.delete("/api/files/{approval_id}")
def delete_desk_file_endpoint(approval_id: int):
    res = agent_files.delete_desk_file(approval_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


# THE OUT BOX (Barry, 2026-09-06: "an out box to give them files") -- upload
# from the deck straight onto his shelf, drop/_files/, so he never has to
# open the folder. Same shelf the agents read with read_barrys_file.
@app.post("/api/files/inbox")
async def upload_to_shelf(file: UploadFile = File(...)):
    data = await file.read()
    res = agent_files.save_to_inbox(file.filename or "file", data)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# TEACH FROM THE DECK (Barry, 2026-09-08: "i also need a place so i can give
# them all this type of stuff" -> "it wouldnt drop in" -> "the curser").
# Dragging a file out of the Claude app or a browser onto the Desktop TEACH
# DROP shortcut gets Windows' refuse cursor (drag-and-drop between programs at
# different integrity levels is blocked by the OS, not by us). So the drop zone
# lives INSIDE the office instead: upload lands in drop/<Name>/<kind>/ -- the
# exact folder the scanner already watches -- and the scanner runs at once, so
# he sees "taught" before the panel closes. Same verbatim ingest, same
# supersede-by-title, same _done/_failed trail; nothing new in the brain path.
@app.post("/api/agents/{folder}/teach-file")
async def teach_file_from_deck(folder: str, file: UploadFile = File(...),
                               kind: str = "knowledge"):
    import ingest
    # Live map -- the nine plus every agent he has added (2026-09-19). Reading
    # the literal here meant a new agent could not be taught from the panel at
    # all, which is the one door built for handing an agent his own material.
    _folders = ingest.folder_map()
    if folder not in _folders:
        raise HTTPException(404, f"No agent folder '{folder}'. Use a first name: "
                            + ", ".join(_folders))
    if kind not in ingest.KINDS:
        raise HTTPException(400, f"kind must be one of {ingest.KINDS}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    # agent_files._safe_name forces the extension into the agents' WRITABLE
    # set (a .pdf would become .md and the extractor would misread it), so the
    # teach door keeps its own allowlist -- the formats document_extract reads.
    raw = (file.filename or "teach.md").replace("\\", "/").split("/")[-1].split(":")[-1]
    raw = re.sub(r"[^A-Za-z0-9 ._-]", "", raw); raw = re.sub(r"\.{2,}", ".", raw).strip(" .")
    stem, _, ext = raw.rpartition(".")
    ext = ext.lower() if stem else ""
    if ext not in {"md", "txt", "pdf", "docx", "doc", "xlsx", "pptx", "csv", "html", "rtf", "json"}:
        raise HTTPException(400, f"'{file.filename}' -- teach files must be md/txt/pdf/docx/xlsx/pptx/csv/html/rtf/json.")
    name = f"{(stem or 'teach')[:80].strip(' .-_') or 'teach'}.{ext}"
    dest_dir = os.path.join(ingest.DROP_ROOT, folder, kind)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    tmp = dest + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, dest)
    # Run the scanner now rather than making him wait up to 60s.
    try:
        lines = ingest.scan_drop_folders()
    except Exception as e:  # noqa: BLE001
        lines = [f"saved to {dest}; scanner will pick it up: {e}"]
    mine = [l for l in lines if name in l] or lines[-1:] or ["saved; scanner will ingest within 60s"]
    failed = any("_failed" in l or "FAILED" in l.upper() for l in mine)
    return {"ok": not failed, "agent": folder, "kind": kind, "name": name,
            "detail": " | ".join(mine)[:400]}


@app.delete("/api/files/inbox/{name}")
def remove_from_shelf(name: str):
    res = agent_files.delete_inbox_file(name)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    """Real neural speech, synthesized entirely locally -- no API key, no
    cloud round-trip, no cost. Kokoro (kokoro_tts.py, CPU-only via ONNX,
    natural 2025-generation voices) is the primary engine, swapped in
    2026-07-29 after the owner's verdict on Piper's output ("i just hate
    the robotic voices"). Piper remains the automatic fallback so a missing
    Kokoro model file degrades voice quality instead of killing voice."""
    # 2026-10-17 (Barry: "for the voice, her texts need to be proper"): Taliyah's written reply keeps her slang;
    # the copy the voice reads is spelled out (tone_guard.proper_for_voice) so the engine says it cleanly.
    spoken = tone_guard.proper_for_voice(req.text) if req.agent_id == TALIYAH_ID else req.text
    try:
        audio = kokoro_tts.synthesize(req.agent_id, spoken)
    except Exception:
        try:
            audio = piper_tts.synthesize(req.agent_id, spoken)
        except Exception as e:
            raise HTTPException(500, f"TTS synthesis failed: {e}")
    return Response(content=audio, media_type="audio/wav")


@app.delete("/api/outputs/{approval_id}")
def delete_output(approval_id: int):
    """Permanently removes one output/approval entry -- lets the owner clear
    unwanted items out of an agent's Outputs archive."""
    if not memory.delete_output(approval_id):
        raise HTTPException(404, f"No output with id {approval_id}")
    return {"id": approval_id, "deleted": True}


@app.get("/api/business/pulse")
def get_business_pulse():
    """Structured business snapshot for the dashboard's desk card (Barry,
    2026-08-29: "when i click on one of the three agents i should get or see
    my business info"). Read-only view of what bizwatch already gathered --
    this endpoint NEVER triggers a live store pull, so it is always instant
    and works in Offline Mode (showing the last dated snapshot)."""
    return {
        "configured": bizwatch.store.is_configured(),
        "snapshot": bizwatch.latest_snapshot(),
    }


@app.get("/api/settings/models")
async def get_model_settings():
    """Current global model/backend selection plus what's actually
    available to pick from -- ONE setting for the whole office, not
    per-agent (see memory.get_active_generation). Ollama's list is live
    (whatever's actually pulled locally); Claude's is a fixed known list
    since Ollama's the only one with a real "list models" API."""
    backend, model = memory.get_active_generation()
    return {
        "active_backend": backend,
        "active_model": model,
        "ollama_models": await llm_router.list_ollama_models(),
        "claude_models": CLAUDE_MODEL_OPTIONS,
        # Bonsai only shows up as a pickable option when its weights and
        # server binary actually exist on disk -- same "real options, not
        # hardcoded guesses" rule as the live Ollama list.
        "bonsai_models": [config.BONSAI_MODEL_NAME] if bonsai_llm.files_present() else [],
    }


@app.post("/api/settings/models")
def set_model_settings(req: ModelSettingRequest):
    if req.backend not in ("ollama", "claude", "bonsai"):
        raise HTTPException(400, f"Unknown backend: {req.backend}. Must be 'ollama', 'claude', or 'bonsai'.")
    if req.backend == "bonsai" and not bonsai_llm.files_present():
        raise HTTPException(400, "Bonsai's model weights or server binary aren't on disk -- see models/bonsai/ and tools/llama-prism/.")
    if req.backend == "claude" and memory.is_offline_mode():
        raise HTTPException(403, "Offline mode is on -- Claude (a cloud API) can't be selected while it's on. Turn off Offline Mode first.")
    if not req.model.strip():
        raise HTTPException(400, "model cannot be empty.")
    memory.set_active_generation(req.backend, req.model)
    return {"active_backend": req.backend, "active_model": req.model}


class AgentModelRequest(BaseModel):
    # None + follow_global=False clears the override (back to the hardcoded
    # default). follow_global=True pins the agent to whatever the global
    # dropdown says, which is how a seat gets onto Bonsai.
    model: str | None = None
    follow_global: bool = False


@app.get("/api/agents/models")
def get_agent_models():
    """Per-agent model picture for the dashboard switch: what each seat is
    actually resolving to right now, what its hardcoded default is, and
    whether the owner has overridden it."""
    overrides = memory.get_agent_model_overrides()
    rows = []
    # all_agents(), not AGENTS (2026-09-19): a hire is a real seat, so it
    # belongs in the per-seat model switch like everybody else. It was
    # invisible here, which meant Barry could not see or change what his own
    # new agent was running on.
    for agent_id, agent in all_agents().items():
        backend, model = _resolve_generation_for(agent_id)
        has_override = agent_id in overrides
        rows.append({
            "id": agent_id,
            "name": agent["name"],
            "resolved_backend": backend,
            "resolved_model": model,
            "default_model": AGENT_OLLAMA_MODEL_OVERRIDES.get(agent_id),
            "overridden": has_override,
            "override_value": overrides.get(agent_id) if has_override else None,
            "following_global": has_override and overrides[agent_id] is None,
        })
    return {"agents": rows, "global": dict(zip(("backend", "model"), memory.get_active_generation()))}


@app.post("/api/agents/{agent_id}/model")
async def set_agent_model(agent_id: str, req: AgentModelRequest):
    """Move one seat between models at runtime -- no restart, because
    overrides are read live on every resolve.

    Built 2026-08-11 for Taliyah specifically: she is the one agent where both
    models genuinely do the job, and which one is right depends on what Barry
    is doing that day. Bonsai is the smarter conversationalist for talking and
    running ideas; the abliterated 9b is the one that will write explicit
    vocabulary. Everyone else has a measured reason to stay put -- but this
    endpoint is deliberately generic rather than Taliyah-only, because a
    hardcoded special case would be the thing that rots.
    """
    # A HIRE IS A REAL SEAT (2026-09-19). This gate read `not in AGENTS`, the
    # hardcoded nine -- so every hire 404'd here and could not be switched off
    # the global model. get_agent() merges both rosters; use it everywhere a
    # seat is looked up by id.
    if not get_agent(agent_id):
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    if req.model and req.follow_global:
        raise HTTPException(400, "Pass either model or follow_global, not both.")
    if req.model:
        # Validate against what is actually pulled, so a typo surfaces here
        # rather than as a failed generation later.
        installed = await llm_router.list_ollama_models()
        if req.model not in installed:
            raise HTTPException(
                400,
                f"'{req.model}' is not installed. Available: {', '.join(installed)}",
            )
    memory.set_agent_model_override(agent_id, req.model, follow_global=req.follow_global)
    backend, model = _resolve_generation_for(agent_id)
    return {"id": agent_id, "resolved_backend": backend, "resolved_model": model}


# --- Teach-without-code (ingest.py, 2026-08-24). The dashboard door: type
# it in the Brain tab instead of dropping a file. Same ingest, same rules
# (verbatim, supersede-not-delete, persona cap). ---

class TeachRequest(BaseModel):
    kind: str          # "persona" | "skill" | "knowledge"
    text: str
    title: str = ""


class PersonaAdditionsRequest(BaseModel):
    text: str


@app.post("/api/agents/{agent_id}/teach")
def teach_agent(agent_id: str, req: TeachRequest):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    try:
        receipt = ingest.teach(agent["office_name"], req.kind, req.text,
                               title=req.title)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "receipt": receipt}


def _save_style_exemplar(office_name: str, raw: str, is_movie: bool) -> dict:
    """Keep a reply Barry LIKED, so the agent writes toward its own approved
    work instead of toward an example someone else wrote.

    This is the closest thing to training available here: Bonsai is a ternary
    Q2_0 GGUF (untrainable) and a 27B QLoRA wants ~22-24GB against a 16GB
    card. So the corpus IS the fine-tune -- and it is the dataset a real one
    would have needed anyway.

    Two shelves, deliberately:
      * an image fence from Elliot -> prompt-exemplars.md, the proven path
        already injected on shot asks. Do not split that corpus.
      * anything else -> 'style-exemplars', ALWAYS-ON (no .md suffix) and
        capped hard, because a style he likes should shape every reply
        rather than wait for recall keywords to happen to match.
    Each exemplar is capped and only the newest few kept -- always-on text
    is charged on every single message.
    """
    text = (raw or "").strip()
    if not text:
        return {"ok": False, "reason": "nothing to save"}

    fences = re.findall(r"```image\s*\n(.+?)```", text, re.S)
    if is_movie and fences:
        key, keep, cap = "prompt-exemplars.md", 8, 4000
        body_seed = ("PROMPTS BARRY APPROVED -- YOUR OWN WORK\n"
                     "USE WHEN: writing any shot prompt. These are prompts "
                     "Barry blessed. They are the standard; write like them, "
                     "not like anything else.\n")
        piece = fences[0].strip()[:cap]
    elif is_movie:
        # HOW HE WRITES BARRY'S SCRIPTS (2026-08-25: "its suppose to be how
        # he writes his scripts for me and everything"). A blessed script
        # block runs thousands of characters, so the 900-char cap used for
        # ordinary chat would saw it in half and teach a truncated shape.
        # Fewer kept, each much longer.
        key, keep, cap = "style-exemplars", 3, 2600
        body_seed = ("SCRIPT WORK BARRY APPROVED -- THIS IS HOW HE WANTS YOU "
                     "TO WRITE\n"
                     "He pressed MORE LIKE THIS on the passages below. They "
                     "outrank every other example, including any format "
                     "sample written by anyone else. Match their block "
                     "shape, their level of camera and environment detail, "
                     "their sentence rhythm and their length.\n")
        piece = text[:cap]
    else:
        key, keep, cap = "style-exemplars", 5, 900
        # The old seed said "when in doubt about how to answer, answer like
        # these" -- an instruction to repeat. The bar is the CARE in these,
        # never their sentences (2026-09-15, Barry: "they are supposed to
        # truly think. why does she always repeat herself?").
        body_seed = ("WORK BARRY APPROVED -- THE BAR\n"
                     "He pressed MORE LIKE THIS on the replies below. They "
                     "show the level of care, directness and detail he wants. "
                     "Think each new answer through on its own; never reuse "
                     "their sentences or their subject.\n")
        piece = text[:cap]

    cur = ""
    for f in memory.get_active_facts_for_agent(office_name):
        if f.get("source_name") == key:
            cur = f["content"]
            break
    if piece in cur:
        return {"ok": True, "already": True, "shelf": key}

    marker = "\n--- APPROVED ---\n"
    body = (cur or body_seed) + marker + piece + "\n"
    parts = body.split(marker)
    if len(parts) > keep + 1:
        body = parts[0] + marker + marker.join(parts[-keep:])
    # CATEGORY IS PART OF THE KEY. Without it this looked the row up by
    # source_name alone, so the SECOND agent Barry liked something on
    # overwrote the FIRST agent's shelf -- caught in testing when Victor's
    # exemplar landed in Elliot's private brain and wiped his script sample.
    # Every seat keeps its own standard.
    category = "private:" + office_name
    with memory.get_db() as c:
        row = c.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? "
            "AND status='active'", (key, category)).fetchone()
        if row:
            c.execute("UPDATE facts SET content=? WHERE id=?", (body, row["id"]))
    if not row:
        memory.add_fact(category, body, source_name=key,
                        title="Work Barry approved -- the standard")
    return {"ok": True, "shelf": key, "count": len(body.split(marker)) - 1}


@app.post("/api/agents/{agent_id}/like")
def like_agent_output(agent_id: str, payload: dict):
    """MORE LIKE THIS. Barry presses it on a reply he wants more of.

    Deliberately a BUTTON, not a phrase the model interprets. The typed
    -praise path in /api/chat has to GUESS (short message? any reservation
    words?) and guessing wrong poisons the corpus -- a bad exemplar
    COMPOUNDS, because it becomes the standard everything is written
    toward. A button is unambiguous, and works for all nine seats rather
    than only Elliot's image fences.
    """
    agent = AGENTS.get(agent_id) or memory.get_custom_agent(agent_id)
    if not agent:
        raise HTTPException(404, "No agent '" + agent_id + "'")
    content = (payload or {}).get("content") or ""
    if not content.strip():
        raise HTTPException(400, "Nothing to learn from -- content was empty")
    res = _save_style_exemplar(agent["office_name"], content,
                               agent_id == MOVIE_ID)
    print("[like] " + agent["office_name"] + ": " + str(res))
    return res


@app.post("/api/agents/{agent_id}/clear-thread")
def clear_agent_thread(agent_id: str):
    """Barry's CLEAR BUTTON (2026-08-25: "i need a clear button") -- wipes
    an agent's raw conversation thread so poisoned history stops echoing
    into new answers. The dashboards' old trash button was DISPLAY-ONLY,
    which was worse than no button: it looked like a fix while the DB
    thread kept feeding the model the same wrong turns.

    Every clear BACKS UP the deleted rows to data/ first (house rule:
    never destroy without a copy), and deliberately does NOT summarize --
    the whole point of a manual clear is that the thread has gone bad,
    and summarizing poison just preserves it as a permanent fact
    (the 2026-08-21 junk-turn pattern)."""
    if agent_id not in AGENTS and not memory.get_custom_agent(agent_id):
        raise HTTPException(404, f"No agent '{agent_id}'")
    with memory.get_db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE agent_id = ? ORDER BY id",
            (agent_id,)).fetchall()]
    backup = ""
    if rows:
        import json as _json
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(config.DATA_DIR,
                              f"backup_thread_{agent_id}_{stamp}.json")
        with open(backup, "w", encoding="utf-8") as f:
            _json.dump(rows, f, indent=1)
    memory.clear_conversation(agent_id)
    return {"ok": True, "cleared": len(rows), "backup": backup}


@app.post("/api/agents/{agent_id}/reflect")
async def trigger_reflection(agent_id: str):
    """Manual trigger for one real reflection (the background loop does this
    on its own at idle -- this is for 'make Victor reflect right now').
    Runs the agent's actual model over their actual recent life; takes as
    long as a normal generation. Nothing canned."""
    if not get_agent(agent_id):      # hires count too -- see set_agent_model
        raise HTTPException(404, f"No agent '{agent_id}'")
    ideation.mark_activity_start()   # a reflection IS activity -- keep the
    try:                             # background loops off the GPU meanwhile
        return await reflect.reflect_once(get_agent, agent_id, force=True)
    finally:
        ideation.mark_activity_end()


@app.post("/api/agents/{agent_id}/wander")
async def trigger_stray_thought(agent_id: str):
    """Manual trigger for one stray thought (default-mode-network wander)."""
    if not get_agent(agent_id):      # hires count too -- see set_agent_model
        raise HTTPException(404, f"No agent '{agent_id}'")
    ideation.mark_activity_start()
    try:
        return await reflect.stray_thought(get_agent, agent_id)
    finally:
        ideation.mark_activity_end()


@app.get("/api/breakroom")
def breakroom_state():
    """Who's where right now (break / rest / with Barry) + recent room life."""
    return breakroom.state()


@app.post("/api/breakroom/converse")
async def breakroom_converse(a: str = None, b: str = None, visit: bool | None = None):
    """Manual trigger: one private DM thread now (the homes redesign folded
    break-room talks into DMs). Without a/b, two free agents are picked.
    visit=true forces a home visit (2026-09-02); omitted = the usual coin flip."""
    ideation.mark_activity_start()
    try:
        return await breakroom.converse(get_agent, a, b, visit)
    finally:
        ideation.mark_activity_end()


@app.get("/api/live_talks")
def live_talks_list(limit: int = 20):
    """LIVE CONVERSATIONS (2026-10-15, live_talk.py): the one running now (or next up) + recent ones, for the
    dashboard's live-talks page. Read-only."""
    import live_talk
    return {"current": live_talk.current(), "recent": live_talk.talks(max(1, min(int(limit), 100))),
            "roster": [{"id": a, "name": live_talk._first(a)} for a in breakroom.social_roster()]}


@app.post("/api/live_talks/start")
async def live_talks_start(body: dict):
    """Barry starts one: {"agents": ["Amara", "Priya"], "about": "...", "kind": "work"|"personal"}."""
    import live_talk
    ids = [live_talk.resolve(str(n)) for n in (body.get("agents") or [])]
    if not all(ids):
        return {"error": "unknown name in agents"}
    return live_talk.start("barry", ids, str(body.get("about") or ""), str(body.get("kind") or "work"))


@app.post("/api/live_talks/{tid}/say")
async def live_talks_say(tid: str, body: dict):
    """Barry jumps in: {"text": "..."} -- the next speaker hears it."""
    import live_talk
    return live_talk.say(tid, str(body.get("text") or ""))


@app.post("/api/live_talks/{tid}/stop")
async def live_talks_stop(tid: str):
    import live_talk
    return live_talk.stop(tid)


@app.get("/api/social/calls")
def social_calls(agent_id: str = "", limit: int = 60):
    """THE CALLS (Barry, 2026-09-28: "get rid of the dm button and put calls there. i want to see
    who calls who and see their conversations"). Phone calls from data/dm_log.jsonl, newest first;
    the caller is the one who spoke first. agent_id = only calls they were on. Read-only."""
    rows = breakroom._read_jsonl(breakroom._DM_LOG, 2000)
    out = []
    for r in reversed(rows):
        if r.get("at") != "phone":
            continue
        ids = r.get("agent_ids") or []
        if agent_id and agent_id not in ids:
            continue
        who = r.get("who") or ["?", "?"]
        out.append({"kind": "call", "when": r.get("when"), "caller": who[0], "callee": who[-1],
                    "caller_id": ids[0] if ids else None, "callee_id": ids[-1] if ids else None,
                    "turns": r.get("turns"), "cut_short": r.get("cut_short"),
                    "transcript": r.get("transcript") or ""})
        if len(out) >= max(1, min(int(limit), 200)):
            break
    # THEIR PARTIES sit in the same list (2026-09-28) -- host, who came, the whole night
    for r in breakroom._read_jsonl(breakroom._GATHER_LOG, 500):
        if agent_id and agent_id not in (r.get("agent_ids") or []):
            continue
        out.append({"kind": "party", "when": r.get("when"), "host": r.get("host"),
                    "host_id": r.get("host_id"), "guests": r.get("guests") or [],
                    "what": r.get("what") or "a party", "turns": r.get("turns"),
                    "cut_short": r.get("cut_short"), "transcript": r.get("transcript") or ""})
    out.sort(key=lambda x: x.get("when") or "", reverse=True)
    return {"calls": out[:max(1, min(int(limit), 200))]}


@app.get("/api/social")
def social_state():
    """THE HOMES (2026-08-29): who's home / with Barry + the group-chat feed
    Barry watches."""
    return breakroom.state()


@app.get("/api/social/bonds")
def social_bonds():
    """READ-ONLY: who has actually gotten close to whom, and what each of them
    is carrying right now (2026-08-30).

    Both are EARNED -- closeness only moves because two of them really spent
    time together, and a feeling only exists because they named it themselves.
    Nothing here was seeded, and nothing here is editable from the UI: this is
    a window, not a control panel. Everyone starts at 50 (neutral), so an empty
    list means the office simply hasn't lived enough yet.
    """
    import agents as _agents_mod
    names = {aid: reflect.HUMAN_NAMES.get(aid, nm.split()[0] if nm else aid.title())   # hires too (2026-10-10)
             for aid, _office, nm in _agents_mod.all_seats()}
    pairs, seen = [], set()
    for r in relationships.snapshot():
        key = tuple(sorted((r["agent"], r["other"])))
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"a": names.get(r["agent"], r["agent"]),
                      "b": names.get(r["other"], r["other"]),
                      "closeness": r["closeness"], "scenes": r["scenes"]})
    feelings = {names.get(k, k): v for k, v in mood.snapshot().items()}
    return {"bonds": pairs, "feelings": feelings,
            "neutral": relationships.NEUTRAL}


# /api/social/groupchat was deleted 2026-09-28 with the group chat itself (Barry: "calls are
# replacing group chat"). Calls: at home ("call Priya") or the loop's call slots (social.py).


@app.get("/api/agents/{agent_id}/dms")
def agent_dms(agent_id: str):
    """This agent's private DM threads with coworkers, for the MINDS window.
    Barry reads everything; that has always been the deal."""
    if not get_agent(agent_id):      # hires count too -- see set_agent_model
        raise HTTPException(404, f"No agent '{agent_id}'")
    return {"dms": breakroom.dms_of(agent_id)}


class ShowRequest(BaseModel):
    offer: str
    kind: str = "image"     # "image" | "video"


# Freckle/speckle words, stripped from any render prompt built out of
# someone's own description (Barry's ruling, 2026-08-30). Matches the
# whole clause so "a faint constellation of freckles across my nose and
# cheeks" does not leave "a faint constellation of across my nose".
_FRECKLE_WORD = re.compile(r"(?:freckl\w*|speckl\w*|beauty marks?|moles?)", re.I)


def _strip_freckles(text: str) -> str:
    """Drop only the freckle CLAUSE, keeping everything around it.

    Splitting on ' and ' as well as punctuation matters: one sweeping regex
    over "bright green eyes, freckles and red lipstick" ate the lipstick too --
    a real feature lost while fixing a different problem.
    """
    if not text or not _FRECKLE_WORD.search(text):
        return text
    parts = re.split(r"(\s*[.,;]\s*|\s+and\s+)", text)
    # walk (delimiter, segment) pairs and drop BOTH when the segment is a
    # freckle clause -- dropping the segment alone leaves a dangling "and"
    out, pending = "", ""
    for i, part in enumerate(parts):
        if i % 2 == 1:
            pending = part
            continue
        if _FRECKLE_WORD.search(part):
            if not out:
                pending = ""      # it was the opening clause
            continue
        out += pending + part
        pending = ""
    out = re.sub(r"(\s*[.,;]\s*){2,}", ", ", out)
    out = re.sub(r"^\s*(?:and\s+|[.,;]\s*)+", "", out)
    return re.sub(r"\s{2,}", " ", out).strip().strip(",").strip()


# ROOM PLATES ARE ROOMS (2026-09-19). Barry, on the home slot: "i do want
# that" -- the room with nobody in it.
#
# MEASURED on three of them at once. `home` and `lab` are ROOM plates: the
# person is not supposed to be in frame. What the office did was append
# ", no people, empty room" to the POSITIVE prompt -- and this build's own
# standing rule (2026-09-18 realism block, his words) is that a word after
# "no" still gets painted, while on Qwen at cfg 1.0 the negative field is
# inert. So the guard was an instruction to paint people. On top of that they
# describe their OWN place in the first person, because that is how anyone
# describes where they live:
#   Ilnora  "I am standing with one hand resting on the edge of the table,
#            wearing a see-through gown"        -> a stranger in her bedroom
#   Sophie  "Sophie sitting on the chaise in a black lace bra"  -> her, in a
#            plate that is supposed to be the room
#   Victor  "still -- no one in it"             -> the poison, in her own words
# So the clause goes before the render, and the room is asked for positively.
#
# Two tiers, because dropping every clause that says "me" costs real furniture:
# "There is a bookshelf behind me with leather-bound herb manuals" is a ROOM
# object. A positional self-phrase ("behind me") is deleted and the object
# kept; a clause that is ABOUT the person -- their body, their clothes, what
# they are doing -- is dropped whole, the _strip_freckles way, splitting on
# " and " as well as punctuation so nothing is left dangling.
_ROOM_SELF_POSITION = re.compile(
    r"\b(?:behind|beside|next\s+to|in\s+front\s+of|near|around|beyond|above|"
    r"below|under|underneath|by|across\s+from|opposite|facing)\s+"
    r"(?:me|her|him|them|us|myself|herself|himself)\b", re.I)
# Person NOUNS and pronouns only -- deliberately NO verbs. "sitting" and
# "standing" were tried and had to come out: "a ceramic mug sitting on the
# desk" and "a lamp standing in the corner" are furniture, and stripping those
# clauses empties the room the render is supposed to show.
_ROOM_PERSON_WORD = re.compile(
    r"\b(?:i|i'm|i've|me|my|mine|myself|she|her|hers|herself|he|him|his|"
    r"himself|they|them|their|theirs|we|us|our|person|people|someone|"
    r"somebody|anyone|no\s+one|nobody|figure|woman|women|man|men|girl|guy|"
    r"viewer|camera|hair|skin|face|eyes?(?!-)|hands?(?!-)|arm|arms|leg|legs|"
    r"knee|knees|lap|shoulder|shoulders|thigh|thighs|chest|waist|hips|feet|"
    r"foot|barefoot|wearing|dressed|undressed|nude|naked|bra|panties|"
    r"underwear|lingerie|gown|dress|robe|shirt|blouse|pants|trousers|jeans|"
    r"sweater|hoodie|socks|shoes)\b", re.I)


def _person_first_name(agent_id: str) -> str:
    """Their PERSON name ("Sophie"), not AGENTS['name'] -- that field has held
    the job title since the 2026-08-31 retitle, so it would never match the
    "Sophie sitting on the chaise" that put her in her own room plate. A hire's
    stored name IS the person's name (the retitle never touched custom
    agents), which is why that is the fallback here."""
    try:
        import reflect as _reflect
        first = _reflect.HUMAN_NAMES.get(agent_id, "") or ""
    except Exception:  # noqa: BLE001
        first = ""
    if not first:
        first = (CUSTOM_AGENTS.get(agent_id) or {}).get("name", "") or ""
    first = first.strip()
    return first.split()[0] if first else ""


def _room_only_prompt(description: str, agent_name: str = "") -> str:
    """A room-plate prompt out of someone's own description of their place.

    Never raises and never returns empty -- a stripped-to-nothing description
    falls back to the original text, because a blank prompt renders noise and
    that is worse than a person in the frame.
    """
    text = (description or "").strip()
    if not text:
        return text
    # 1. positional self-reference only: "a bookshelf behind me with herb
    #    manuals" is FURNITURE. Delete the phrase, keep the bookshelf.
    body = _ROOM_SELF_POSITION.sub("", text)
    # 2. a bare possessive never makes a clause about a person -- the body
    #    part or the garment after it does, and that is matched below. Without
    #    this, "My bedroom at night" loses the bedroom.
    body = re.sub(r"\b(?:my|her|his|their|our)\s+(?=\w)", "", body, flags=re.I)
    person = _ROOM_PERSON_WORD
    if agent_name and len(agent_name) >= 3:
        person = re.compile(
            r"(?:%s|\b%s\b)" % (_ROOM_PERSON_WORD.pattern, re.escape(agent_name)),
            re.I)

    def _clean(seg: str) -> bool:
        """Is this segment safe to paint? Person-ish, or an ABSENCE claim."""
        if person.search(seg):
            return False
        # "No laptop", "no one in it", "without shoes" -- a word after "no"
        # still gets painted, so an absence is never stated, only omitted.
        return not re.match(r"^\s*(?:no|without|nothing)\b", seg, re.I)

    kept = []
    # SENTENCE FIRST. A person's sentence keeps describing that person past
    # every comma -- "wearing a gown with gold embroidery, lace at the cuffs
    # and hem, a thin gold belt at the waist" is one garment broken into three
    # fragments, and only the first carries a clothing word. So once a segment
    # is person-ish, the REST OF ITS SENTENCE goes with it.
    for sentence in re.split(r"(?<=[.;!])\s+", body):
        parts = re.split(r"(\s*,\s*|\s+and\s+)", sentence)
        out, pending, poisoned = "", "", False
        for i, part in enumerate(parts):
            if i % 2 == 1:
                pending = part
                continue
            if poisoned or not _clean(part):
                poisoned = True
                if not out:
                    pending = ""
                continue
            out += pending + part
            pending = ""
        out = out.strip().strip(",").strip()
        if out:
            kept.append(out)
    out = " ".join(kept)
    out = re.sub(r"(\s*[.,;]\s*){2,}", ", ", out)
    out = re.sub(r"^\s*(?:and\s+|[.,;]\s*)+", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip().strip(",").strip()
    # NEVER fall back to the original text. An earlier version did, and on a
    # description that is ALL about the person it handed the person straight
    # back -- resurrecting the exact bug this function exists to stop. A thin
    # or even empty room prompt still renders a room, which is what the slot
    # is for; the closing clause below carries it.
    if len(out) < 25:
        print(f"[scene] room prompt is thin after stripping the person: {out!r}")
    # Asked for POSITIVELY -- what IS in frame, never what is not.
    return out.rstrip(". ") + (", photorealistic interior photograph of the "
                               "empty room itself, furniture and objects only")


def _self_reference(agent_id: str) -> str | None:
    """The agent's OWN full picture, staged as agent_ref_<id>.png in ComfyUI's
    input root -- Barry's chosen look for them, whole figure. When it exists,
    every picture WITH them in it is made by RESTAGING that picture through
    Qwen-Image-Edit instead of describing them to SDXL (2026-09-10, Barry:
    "Amara is still generating herself as the old version, not my new images
    of her"). Face+body IP-Adapter averages an embed and cannot hold a body --
    measured in August, and again on her rejected render today. Absent the
    file, the seat keeps the old path untouched."""
    cand = f"agent_ref_{agent_id}.png"
    if os.path.isfile(os.path.join(comfy_image.COMFY_DIR, "input", cand)):
        return cand
    return None


def _same_image(path_a: str, path_b: str) -> bool:
    """Are these two files the same picture? Bytes first, then pixels.

    Two staged references can be byte-different and pixel-identical (a re-save
    changes the file and not the image), so a hash alone would miss it. Never
    raises -- a missing or unreadable file simply is not a match.
    """
    try:
        if os.path.getsize(path_a) == os.path.getsize(path_b):
            with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
                if fa.read() == fb.read():
                    return True
        from PIL import Image, ImageChops
        with Image.open(path_a) as a, Image.open(path_b) as b:
            ia, ib = a.convert("RGB"), b.convert("RGB")
            if ia.size != ib.size:
                return False
            return ImageChops.difference(ia, ib).getbbox() is None
    except Exception:  # noqa: BLE001
        return False


def _legacy_self_refs(agent_id: str) -> str | None:
    refs = [c for c in (f"agent_face_{agent_id}.png", f"agent_body_{agent_id}.png")
            if os.path.isfile(os.path.join(comfy_image.COMFY_DIR, "input", c))]
    return ",".join(refs) if refs else None


async def _render_self_picture(agent_id: str, description: str,
                               at_work: bool = False) -> dict:
    """One door for every picture an agent appears in: [SELF] shows, the
    home/self/out/office slots. Returns the generate_image endpoint's shape
    (approval_id, path, model...) or raises HTTPException like it does."""
    ref = _self_reference(agent_id)
    if ref:
        scene = description.strip().rstrip(".")
        if at_work:
            scene += ", at work in their own office, at their desk"
        # Editor grammar (qwen-image-edit skill): say what to DO, carry a
        # preservation clause, one change. Identity/figure come from the
        # pixels, so the description is only ever the NEW scene, clothes and
        # pose -- nothing about what they look like.
        # 2026-09-12 (Barry: "Just use the image as reference to what she
        # looks like and her body. she can prompt herself in any situation
        # or place."): the reference carries WHO -- face, hair, skin, figure.
        # Everything else -- the place, the light, the clothes or none --
        # comes from her own words, so the instruction says out loud not to
        # carry the reference's outfit or background. Without that line the
        # editor reproduces them by default (measured on her couch-picture
        # era: every render came back on that couch in that slip).
        instruction = (
            f"Make a new photograph of the exact same person from image 1, "
            f"keeping the person's face, hair, skin, body shape and proportions "
            f"identical to image 1. Do not keep the clothing, the room or the "
            f"background from image 1 -- place and dress the person only as "
            f"described here: {scene}. Photorealistic, natural lighting, "
            f"the whole figure framed in the scene."
        )
        # THE FACE REFERENCE (2026-09-18, Barry: "they all should have their
        # face reference"). Measured on Sophie's first self video: the restage
        # came back a generic pretty face -- no freckles, brown eyes instead of
        # her amber -- because her `agent_ref` was the ONLY landscape plate of
        # the nine (1328x747), so her head was a small fraction of the frame
        # and fine identity detail could not survive. Same small-head failure
        # as the four-eye collapse. Her plate is portrait now, and every seat
        # also passes its tight `agent_face_<id>.png` as image 2 so the face
        # is stated twice.
        # ⚠️ The 2026-08-28 lesson is why image 2 is named so narrowly: a
        # multi-image edit BLENDS, and a LOOSE crop drags in the reference's
        # room and wardrobe. These crops are tight, and the clause below says
        # face only, take nothing else from it.
        # Image 1 decides the OUTPUT SIZE, so it has to be big enough to
        # render from -- see comfy_image.working_reference.
        ref = comfy_image.working_reference(ref)
        sources = [ref]
        face = os.path.join(comfy_image.COMFY_DIR, "input",
                            f"agent_face_{agent_id}.png")
        # ⚠️ SAME PIXELS IS THE SAME PICTURE (2026-09-19). A seat whose
        # reference IS a face crop (Barry, on Ilnora: "its supposed to be just
        # her face") would otherwise be handed that crop twice -- a second
        # source doubles the encode and the render deadline, and pushes the
        # editor harder toward a head-and-shoulders close-up, for nothing. The
        # abspath check alone cannot see this: the two files have different
        # names and identical content.
        if (os.path.isfile(face) and os.path.abspath(face) != os.path.abspath(ref)
                and not _same_image(face, os.path.join(
                    comfy_image.COMFY_DIR, "input", ref))):
            sources.append(face)
            instruction += (" Image 2 is a close-up of the same person's face -- "
                            "match their face, eye colour, freckles and skin "
                            "exactly to image 2, and take nothing else from it.")
        instruction = _strip_freckles(instruction)
        await llm_router.unload_all_models()
        result = await comfy_image.edit_image(sources, instruction,
                                              prefix=f"self_{agent_id}")
        if "error" in result:
            raise HTTPException(502, result["error"])
        content = (f"Generated image concept: {description}"
                   f"\nModel: {result['model']} (restaged from {ref})")
        approval_id = memory.queue_for_approval(agent_id, "public_content",
                                                content, file_path=result["path"])
        asyncio.create_task(_prewarm_after_render())
        return {"approval_id": approval_id, "path": result["path"],
                "model": result["model"], "commercial_use": result["commercial_use"],
                "licence_note": result["licence_note"], "seed": result.get("seed"),
                "character_lora": None, "extras": result.get("extras", {})}

    # --- legacy path: SDXL + IP-Adapter on the staged face/body crops ---
    prompt = description
    if at_work:
        prompt += ", at work in their own office, at their desk"
    prompt += (", photorealistic, highly detailed face, completely smooth "
               "clear even skin with a uniform unblemished complexion")
    prompt = _strip_freckles(prompt)
    reference = _legacy_self_refs(agent_id)
    return await generate_image(ImageGenerateRequest(
        prompt=prompt, agent_id=agent_id, reference_image=reference,
        reference_preset="PLUS FACE (portraits)" if reference else None))


@app.post("/api/agents/{agent_id}/show")
async def agent_show(agent_id: str, req: ShowRequest):
    """Barry ACCEPTED a SHOW-OFFER from the personal channel (2026-08-29:
    "they have to ask me if i want to see it... i accept and then they
    generate"). The agent's one-line offer becomes the render prompt.
    [SELF] offers get the agent's REAL look: their face image as the
    IP-Adapter identity reference + their captioned features in the prompt
    (Barry: "use their head as their face image... since it's not trained").
    Reuses the normal generation endpoints, so results queue for approval
    and land in Outputs like everything else."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, f"No agent '{agent_id}'")
    offer = (req.offer or "").strip()
    if not offer:
        raise HTTPException(400, "Empty offer")
    is_self = offer.upper().startswith("[SELF]")
    if is_self:
        offer = offer[6:].strip()
    prompt = offer
    reference = None
    if is_self and _self_reference(agent_id):
        # THE NEW PATH (2026-09-10): restage Barry's own picture of them.
        # Their appearance doc is deliberately NOT read here -- the pixels
        # carry the look, and that doc is what used to put "Barry" into the
        # prompt and trip the prose guard on every self VIDEO (measured: the
        # offer alone passes, offer + doc fails -> 400 on the accept click).
        still = await _render_self_picture(agent_id, offer)
        if req.kind != "video":
            return still
        # VIDEO = the still, then LTX moves it (i2v). Text-to-video of a
        # person from words was never going to be them; the still is. The
        # prompt LTX gets is the offer line only -- LTX SPEAKS its prompt, so
        # a description of her face would come back narrated.
        frame_name = f"startframe_{agent_id}_{int(time.time())}.png"
        try:
            shutil.copyfile(still["path"],
                            os.path.join(comfy_image.COMFY_DIR, "input", frame_name))
        except OSError as e:
            raise HTTPException(500, f"Could not stage the start frame for LTX: {e}")
        clip = await generate_video(VideoGenerateRequest(
            prompt=offer, agent_id=agent_id, duration_s=_self_clip_seconds(offer),
            start_frame=frame_name))
        clip["still_approval_id"] = still.get("approval_id")
        return clip
    if is_self:
        raw = breakroom._fact_content(agent["office_name"], "my-appearance.md")
        lines = [l for l in raw.splitlines()
                 if l.strip() and not l.upper().startswith("USE WHEN")
                 and "USE WHEN" not in l[:20]]
        # A RULING FROM BARRY OUTRANKS THE TRUNCATION (2026-08-30). Amara drew
        # herself lean because her own words say "lean but dense muscle" and
        # his figure ruling sits at the END of the document -- past the 600
        # char cut, so it never reached the prompt at all. Any "BARRY'S RULING"
        # block is lifted out and always carried, then the rest fills what's
        # left. His call can never be the thing that gets trimmed.
        body, ruling = [], []
        in_ruling = False
        for l in lines:
            if "BARRY'S RULING" in l.upper():
                in_ruling = True
            if in_ruling:
                ruling.append(l)
            else:
                body.append(l)
        ruling_txt = " ".join(ruling)[:420]
        feats = " ".join(body)[:600 - min(len(ruling_txt), 420)]
        feats = (feats + " " + ruling_txt).strip()
        # NO FRECKLES (Barry, 2026-08-30): "lets do away with freckles unless
        # yo do them right, every body that has them looks speckled. freckles
        # are faint mostly and tinly, not chocolate chip sized." Measured on
        # Amara's own 02:10 self-render: coarse dark dots scattered over both
        # arms, shoulders and chest. Several of them describe freckles in their
        # OWN words, so the word is stripped HERE, at render time, rather than
        # edited out of anything they wrote -- same substitute-never-edit rule
        # used for his scripts.
        feats = _strip_freckles(feats)
        if feats:
            prompt = f"{offer}. The person: {feats}"
        # FACE **AND** BODY (Barry, 2026-08-30: "i want her to see her self as
        # what i gave you, the thicker version"). Words alone lost to her own
        # older sentence, so the figure comes from HIS pixels too. The
        # comma-list is comfy_image's documented multi-reference path (up to 5,
        # embeds averaged) -- his own 2026-08-04 correction was that one
        # reference is never enough. The body ref staged for this is the
        # CLOTHED render deliberately: a lingerie reference imports the
        # lingerie (measured 2026-08-28).
        refs = []
        for cand in (f"agent_face_{agent_id}.png", f"agent_body_{agent_id}.png"):
            if os.path.isfile(os.path.join(comfy_image.COMFY_DIR, "input", cand)):
                refs.append(cand)
        reference = ",".join(refs) if refs else None
        prompt += (", photorealistic, highly detailed face, completely smooth "
                   "clear even skin with a uniform unblemished complexion")
    if req.kind == "video":
        # Offer line ONLY (2026-09-10): the appearance text names Barry, which
        # the prose guard reads as chat and 400s; and LTX would narrate it.
        return await generate_video(VideoGenerateRequest(
            prompt=offer, agent_id=agent_id, duration_s=_self_clip_seconds(offer)))
    return await generate_image(ImageGenerateRequest(
        prompt=prompt, agent_id=agent_id, reference_image=reference,
        reference_preset="PLUS FACE (portraits)"))


@app.get("/api/thinking/{agent_id}")
def live_thinking(agent_id: str):
    """What this agent is thinking RIGHT NOW, while Barry waits.

    Barry, 2026-08-31: "i would like to see their reasonong, while i wait for
    their responses." The reasoning was always there -- this fork streams it as
    a separate `reasoning_content` field and the non-streaming path silently
    dropped it (bonsai_llm.live_thinking). Nothing new is generated for this.

    In memory only, newest-per-agent. It is never written to a fact, a thread
    or a summary, so it cannot feed back into what an agent believes -- a
    window, not a record.
    """
    agent = AGENTS.get(agent_id) or memory.get_custom_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"No agent '{agent_id}'")
    return bonsai_llm.live_thinking(agent["office_name"])


@app.get("/api/health/degradation")
def health_degradation():
    """Is the office slipping? (Barry, 2026-08-31: "tell me to restart or
    something".) Read-only, no model calls -- safe to poll."""
    import degradation
    try:
        return degradation.check()
    except Exception as exc:
        return {"status": "unknown", "headline": "Monitor failed: %s" % exc,
                "problems": [], "notes": [], "measured": {}}


_CLIENT_ERRORS_PATH = os.path.join(config.DATA_DIR, "client_errors.jsonl")
_CLIENT_ERRORS_MAX_BYTES = 2 * 1024 * 1024
_CLIENT_ERROR_FIELDS = ("deck", "kind", "message", "url", "ts", "source", "line", "col", "stack")


@app.post("/api/client-errors")
async def client_errors(request: Request):
    """SOPHIE'S EYES ON THE DASHBOARD (2026-09-02). Every deck loads
    client-errors.js, which posts JavaScript errors, failed script loads and
    console.error calls here. Appended to data/client_errors.jsonl (rotated at
    2MB), read by health.dashboard_errors -> Sophie's system_health tool and
    watch.py. text/plain body on purpose (no CORS preflight). Local only, like
    every other endpoint. Never raises: a bad report is dropped, not a 500."""
    import json as _json
    try:
        raw = (await request.body())[:8000]
        rec = _json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(rec, dict):
            return {"ok": False}
        clean = {k: (str(rec[k])[:1500] if not isinstance(rec[k], (int, float)) else rec[k])
                 for k in _CLIENT_ERROR_FIELDS if rec.get(k) is not None}
        if not clean.get("message"):
            return {"ok": False}
        clean["received"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        os.makedirs(os.path.dirname(_CLIENT_ERRORS_PATH), exist_ok=True)
        try:
            if os.path.getsize(_CLIENT_ERRORS_PATH) > _CLIENT_ERRORS_MAX_BYTES:
                os.replace(_CLIENT_ERRORS_PATH, _CLIENT_ERRORS_PATH + ".1")
        except OSError:
            pass
        with open(_CLIENT_ERRORS_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(clean) + "\n")
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        print(f"[client-errors] dropped a report: {e}")
        return {"ok": False}


@app.post("/api/watch/tick")
async def watch_tick_now(force: bool = True):
    """Run Sophie's watch check NOW (2026-09-02). The loop does this every 15
    minutes on its own; this is Barry's "check the office now" button. With
    force (default) it skips the idle gate and the once-a-day throttle -- he
    asked, so she looks and writes. Nothing here changes code or settings."""
    return await watch.tick(get_agent, force=force)


@app.get("/api/watch")
def watch_status():
    return watch.status()


@app.get("/api/home-refresh")
def home_refresh_status():
    """THEIR PLACES CHANGE (2026-09-11): who is up next, when, and the history.
    Settings live in app_settings: home_refresh_enabled, home_refresh_gap_hours."""
    return home_refresh.status()


@app.post("/api/home-refresh/now")
async def home_refresh_now(agent_id: str | None = None, slot: str | None = None):
    """Ask one agent about their place NOW (the loop does one every ~30h).
    No agent given = whoever has waited longest. Their words queue for Barry's
    approval as always; nothing renders from this call."""
    if slot and slot not in ("home", "self", "out", "office"):
        raise HTTPException(status_code=400, detail="slot must be home, self, out or office")
    return await home_refresh.refresh_now(agent_id, slot)


@app.get("/api/team")
def team_board():
    """The company task board (2026-09-02) -- every brief, who holds it, status, reply."""
    return teamwork.status()


@app.post("/api/team/tick")
async def team_tick(brief_id: int | None = None):
    """Work one brief NOW (the loop does this every minute when quiet)."""
    return await teamwork.work_one(brief_id, force=True)


@app.post("/api/approvals/{approval_id}/undo-fix")
def undo_code_fix(approval_id: int):
    """Put a file back the way it was before fix #id (2026-09-02, Barry: "i
    should be able to tell her to undo things as well" -- this is the button
    form; telling Sophie in chat is the other). Restores the backup taken at
    apply time; backend files restart themselves."""
    try:
        return codefix.undo_fix(approval_id)
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "why": str(e)}


@app.get("/api/fixes")
def list_code_fixes():
    """Every code fix: pending / applied / auto_applied / undone, newest first."""
    return {"fixes": codefix.list_fixes()}


@app.get("/api/client-errors")
def client_errors_recent(hours: float = 24.0):
    """Read side, grouped -- for Barry or any deck that wants to show it."""
    import health
    return {"hours": hours, "errors": health.dashboard_errors(hours=hours, max_groups=50)}


def _inbox_marks(seen: dict, agent_id: str) -> tuple[int, int]:
    """(work_mark, personal_mark) for this agent, tolerating the OLD format.

    The setting used to hold one int per agent. A stored int is read as the
    mark for BOTH rooms, so nothing he has already read comes back as unread
    the first time this runs -- the split costs him no re-reading.
    """
    v = (seen or {}).get(agent_id, 0)
    if isinstance(v, dict):
        return int(v.get("work", 0) or 0), int(v.get("personal", 0) or 0)
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        n = 0
    return n, n


@app.get("/api/inbox")
def barry_inbox():
    """THE RED DOT (Barry, 2026-08-26: "Put a red dot on their image if there
    is a message or they want to ask something"). Per agent: how many
    mind-for-barry entries he hasn't seen yet, plus the messages themselves.
    Unread = fact id greater than the last id he marked read."""
    import json as _json
    try:
        seen = _json.loads(memory.get_setting("barry_inbox_read") or "{}")
    except Exception:
        seen = {}
    out = []
    _office_open = clock.is_work_hours()
    with memory.get_db() as conn:
        # all_agents(), not AGENTS (2026-09-19, Barry: "we need to get this
        # solid. I dont want these issues with the next agent i hire"). A
        # hire's note to him -- work or personal -- was written to its brain
        # and then never counted, never dotted, never shown: the inbox only
        # ever walked the built-in nine. Same silent-404 class as the seven
        # read endpoints fixed this morning.
        for agent_id, agent in all_agents().items():
            office = agent["office_name"]
            # TWO CHANNELS (Barry, 2026-09-01: "private business messages need
            # to lead to his office... personal should be at home"). Business
            # had only one proactive door -- the personal one -- so half his
            # home inbox was ad budgets and copy decisions. `worknote-*` is the
            # office door; each message now says which channel it came from so
            # the UI can show the agent at their DESK or at HOME accordingly.
            rows = conn.execute(
                "SELECT id, source_name, content, created_at FROM facts "
                "WHERE category = ? AND status = 'active' "
                "AND (source_name LIKE 'mind-for-barry-%' "
                "     OR source_name LIKE 'worknote-%') ORDER BY id DESC",
                (f"private:{office}",)).fetchall()
            msgs = []
            for r in rows:
                m = dict(r)
                m["channel"] = ("work" if (m.get("source_name") or "").startswith("worknote-")
                                else "personal")
                # AFTER HOURS, WORK WAITS (Barry, 2026-09-01: "i like getting
                # DM's personal not work", office hours 9am-6pm Mon-Fri,
                # "but they are on call"). A work note written at 9pm is still
                # WRITTEN and still sits at their office -- he can open the
                # office and read it whenever he likes -- it just does not
                # light the dot until the office opens. Personal notes are
                # never held: those are the ones he said he likes getting.
                # Genuinely urgent work gets through (see reflect._is_urgent,
                # which needs the agent's own URGENT marker AND real emergency
                # wording, because they over-rate their own news).
                # Sophie is never held (2026-10-10, Barry: "Sophie does what i need when i needed it, fuck her
                # schedule") -- her watch findings reached him Monday 9am when written on a Saturday.
                m["held"] = bool(
                    not _office_open
                    and office != "Engineer"
                    and m["channel"] == "work"
                    and not reflect._is_urgent(m.get("content") or ""))
                msgs.append(m)
            # ONE MARK PER ROOM (2026-09-17, Barry: "Sophie keeps sending me
            # messages and when i click it, it shows old or nothing there").
            # There used to be a single high-water mark for BOTH channels, so
            # opening the HOME window advanced it past every office note --
            # and worknotes are not rendered in the home window, so those
            # messages were marked seen without him ever laying eyes on them
            # and the dot never came back. Exactly the swallow this endpoint's
            # own comment warns about, one room over.
            _mw, _mp = _inbox_marks(seen, agent_id)
            unread = [m for m in msgs
                      if m["id"] > (_mw if m["channel"] == "work" else _mp)
                      and not m["held"]]
            # EACH MESSAGE SAYS IF IT IS UNREAD (2026-09-28, Barry: "fix why the
            # light wont stop after reading"). The decks picked "the message the
            # dot is for" as the newest NOT-HELD one, read or not -- so an older
            # unread office note behind a newer, already-read home note opened
            # HOME, showed the same old message, and the dot never cleared.
            _unread_ids = {m["id"] for m in unread}
            for m in msgs:
                m["unread"] = m["id"] in _unread_ids
            if msgs:
                out.append({
                    "agent_id": agent_id,
                    "unread": len(unread),
                    "unread_work": sum(1 for m in unread if m["channel"] == "work"),
                    "unread_personal": sum(1 for m in unread if m["channel"] == "personal"),
                    "messages": msgs[:10],
                })
    return {"inbox": out,
            "total_unread": sum(a["unread"] for a in out),
            "total_work": sum(a["unread_work"] for a in out),
            "total_personal": sum(a["unread_personal"] for a in out),
            # so a deck can say "3 work notes waiting for 9am" instead of
            # silently showing nothing and looking broken
            "office_open": _office_open,
            "held_work": sum(1 for a in out for m in a["messages"] if m.get("held")),
            "next_open": clock.next_open()}


@app.post("/api/inbox/{agent_id}/read")
def mark_inbox_read(agent_id: str, channel: str = ""):
    """Barry opened this agent's messages -- clear their red dot.

    `channel` is 'work' or 'personal' -- the room he actually opened. Only that
    room's mark moves, because the other room's messages are not even rendered
    in this window (2026-09-17). Omitting it marks both, which is what the
    MESSAGES list and any older caller want.
    """
    import json as _json
    _seat = get_agent(agent_id)      # hires count too -- see set_agent_model
    if not _seat:
        raise HTTPException(404, f"No agent '{agent_id}'")
    office = _seat["office_name"]
    with memory.get_db() as conn:
        # MUST MATCH THE INBOX QUERY EXACTLY (2026-09-01). When the work
        # channel was added, /api/inbox started counting `worknote-%` as well
        # but this high-water mark was left on `mind-for-barry-%` only -- so a
        # work note (always a NEWER id) sat permanently above the mark and the
        # green dot never cleared no matter how many times Barry read and
        # replied. An agent with only work notes was worse: MAX(id) was NULL,
        # the mark stayed 0, and everything read as unread forever.
        # ...AND IT MUST NOT SWALLOW A HELD NOTE (2026-09-01, same lesson one
        # layer deeper). Once after-hours work notes stopped counting as
        # unread, a plain MAX(id) reintroduced the same class of lie in the
        # opposite direction: a work note written at 10pm always has the
        # NEWEST id, so reading a personal message at 10pm would mark it seen
        # -- and worknotes are not rendered in the personal window, so Barry
        # would never have laid eyes on it and the dot would never return at
        # 9am. The note would be silently swallowed.
        # So the mark advances only over notes that are actually SHOWABLE
        # right now. A held note keeps its id above the line and lights the
        # dot when the office opens, exactly as intended.
        rows = conn.execute(
            "SELECT id, source_name, content FROM facts WHERE category = ? "
            "AND status = 'active' AND (source_name LIKE 'mind-for-barry-%' "
            "                           OR source_name LIKE 'worknote-%')",
            (f"private:{office}",)).fetchall()
    _open = clock.is_work_hours()

    def _chan(r) -> str:
        return "work" if (r["source_name"] or "").startswith("worknote-") else "personal"

    visible = {"work": [], "personal": []}
    for r in rows:
        ch = _chan(r)
        if ch == "work" and not _open and office != "Engineer" and not reflect._is_urgent(r["content"] or ""):
            continue          # held -- keeps its id above the line until 9am
        visible[ch].append(r["id"])

    try:
        seen = _json.loads(memory.get_setting("barry_inbox_read") or "{}")
    except Exception:
        seen = {}
    mw, mp = _inbox_marks(seen, agent_id)
    want = {"work", "personal"} if channel not in ("work", "personal") else {channel}
    # never move a mark BACKWARDS either -- a held note must not un-read
    # things he has already seen
    if "work" in want:
        mw = max(max(visible["work"], default=0), mw)
    if "personal" in want:
        mp = max(max(visible["personal"], default=0), mp)
    seen[agent_id] = {"work": mw, "personal": mp}
    memory.set_setting("barry_inbox_read", _json.dumps(seen))
    return {"ok": True, "read_up_to": seen[agent_id], "channel": channel or "both"}


@app.get("/api/agents/{agent_id}/mind")
def read_mind(agent_id: str):
    """Everything this agent has been thinking -- the readable inner life.
    Diary entries, ponderings, opinions of Barry and coworkers, newest first.

    ⚠️ THIS GATE IS WHY A HIRE'S THREAD LOOKED DELETED (2026-09-19). The home
    window rebuilds its transcript from this endpoint; it read `not in AGENTS`
    (the nine), so every hire 404'd and the window rendered EMPTY while the
    rows and the journal sat intact in the database. Barry: "how come the
    thread disapeared?" -- it never did. Look up seats with get_agent()."""
    _seat = get_agent(agent_id)
    if not _seat:
        raise HTTPException(404, f"No agent '{agent_id}'")
    office = _seat["office_name"]
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, source_name, content, created_at FROM facts "
            "WHERE category = ? AND status = 'active' "
            "AND source_name LIKE 'mind-%' ORDER BY id DESC",
            (f"private:{office}",)).fetchall()
    return {"agent": agent_id, "entries": [dict(r) for r in rows]}


@app.get("/api/agents/{agent_id}/work-thread")
def read_work_thread(agent_id: str, limit: int = 40):
    """The OFFICE window's transcript (2026-09-11): the agent's real work
    thread (the same rows the console's history rides on) plus their work
    notes to Barry. Read-only. The home window reads the personal journal
    instead -- two rooms, two records, never mixed."""
    _seat = get_agent(agent_id)      # hires count too -- see read_mind
    if not _seat:
        raise HTTPException(404, f"No agent '{agent_id}'")
    office = _seat["office_name"]
    turns = memory.get_recent_history(agent_id, limit=max(1, min(int(limit), 200)))
    with memory.get_db() as conn:
        notes = conn.execute(
            "SELECT id, source_name, content, created_at FROM facts "
            "WHERE category = ? AND status = 'active' "
            "AND source_name LIKE 'worknote-%' ORDER BY id DESC LIMIT 10",
            (f"private:{office}",)).fetchall()
    return {"agent": agent_id,
            "turns": [{"role": t.get("role"), "content": t.get("content"),
                       "timestamp": t.get("timestamp")} for t in turns],
            "notes": [dict(n) for n in notes]}


@app.get("/api/agents/{agent_id}/transcript")
def read_transcript(agent_id: str, limit: int = 300):
    """ONE RECORD FOR EVERY DECK (2026-10-08, Barry: "i need every deck to be accurate with the others. i have old
    messages in different decks"). The decks kept their own copy of each chat in the browser's localStorage, written
    as messages flew by and never reconciled -- a thread cleared in the DB, or a message sent from another deck or
    another browser origin, left each deck with a different past. This is the conversation as the DB holds it, oldest
    first, with the channel each row came from (work = office window, personal = home). Read-only."""
    if not get_agent(agent_id):
        raise HTTPException(404, f"No agent '{agent_id}'")
    rows = memory.get_recent_history(agent_id, limit=max(1, min(int(limit), 1000)))
    return {"agent": agent_id,
            "turns": [{"role": r.get("role"), "content": r.get("content"), "timestamp": r.get("timestamp"),
                       "channel": r.get("channel") or "work"} for r in rows]}


@app.get("/api/agents/{agent_id}/pictures")
def agent_pictures(agent_id: str, limit: int = 40):
    """THE PLACE THEY SEND PICTURES (Barry, 2026-09-11: "Amara likes to send me
    pictures, give her a place to send them to me"). Every image or clip this
    agent has made -- show-offers he accepted, their own place pictures,
    anything with a file on disk -- newest first, for the gallery strip in
    the HOME window. Read-only; files are served by /api/outputs/{id}/file."""
    if get_agent(agent_id) is None:
        raise HTTPException(404, f"No agent '{agent_id}'")
    out = []
    with memory.get_db() as conn:
        # Renders are stored as `public_content` rows with a media file_path
        # (measured: 17 rows, zero under 'image'/'video'), so the file's
        # extension decides, not the action_type. Rejected ones stay out --
        # he already said no to those.
        rows = conn.execute(
            "SELECT id, action_type, status, content, file_path, created_at FROM approvals "
            "WHERE agent_id = ? AND status NOT IN ('rejected', 'deleted') AND ("
            "lower(file_path) LIKE '%.png' OR lower(file_path) LIKE '%.jpg' OR lower(file_path) LIKE '%.jpeg' "
            "OR lower(file_path) LIKE '%.webp' OR lower(file_path) LIKE '%.mp4' OR lower(file_path) LIKE '%.webm') "
            "ORDER BY id DESC LIMIT ?",
            (agent_id, max(1, min(int(limit), 200)))).fetchall()
    for r in rows:
        fp = r["file_path"] or ""
        if not os.path.isfile(fp):
            continue
        kind = "video" if fp.lower().rsplit(".", 1)[-1] in ("mp4", "webm") else "image"
        out.append({"id": r["id"], "kind": kind, "status": r["status"],
                    "created_at": r["created_at"], "caption": (r["content"] or "")[:300],
                    "url": f"/api/outputs/{r['id']}/file"})
    return {"agent": agent_id, "pictures": out}


class UsePictureRequest(BaseModel):
    approval_id: int
    slot: str = "self"


@app.post("/api/agents/{agent_id}/pictures/use")
def use_picture_as_scene(agent_id: str, req: UsePictureRequest):
    """USE HER IMAGE AS HER HOME IMAGE (Barry, 2026-09-11: "make it so i can
    use her images as her home image. i should be able to do that"). Takes a
    picture THIS agent made (the row must be theirs and must be an image, not
    a clip) and installs it into a slot -- self (what the home window shows),
    home, out or office -- through agent_scenes.install: backup first, temp +
    replace, no render. His click, his choice, instant."""
    import agent_scenes
    if get_agent(agent_id) is None:
        raise HTTPException(404, f"No agent '{agent_id}'")
    slot = (req.slot or "self").strip().lower()
    # "main" is not a scene -- it is WHO THEY ARE (2026-09-19, Barry: "she will
    # draw herself and i can accept and add to her home or her main or her lab
    # image"). It writes the avatar, the roster tile and the reference every
    # later picture of them restages from. See agent_scenes.install_main.
    if slot not in agent_scenes.SLOTS and slot != "main":
        raise HTTPException(400, "slot must be main or one of: %s"
                            % ", ".join(agent_scenes.SLOTS))
    row = memory.get_output_by_id(int(req.approval_id))
    if not row or row.get("agent_id") != agent_id:
        raise HTTPException(404, "That picture is not one of this agent's")
    fp = (row.get("file_path") or "")
    if not os.path.isfile(fp) or fp.lower().rsplit(".", 1)[-1] not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(400, "Only a still image can be a scene (not a clip)")
    res = (agent_scenes.install_main(agent_id, fp) if slot == "main"
           else agent_scenes.install(agent_id, slot, fp))
    if not res.get("installed"):
        raise HTTPException(500, res.get("error") or "install failed")
    return res


@app.delete("/api/agents/{agent_id}/pictures/{approval_id}")
def delete_picture(agent_id: str, approval_id: int):
    """DELETE A PICTURE (Barry, 2026-09-12: "i need that delete button ... to
    be able to delete and download their images"). The row must be this
    agent's and must be a picture or clip. The file is DESTROYED -- Barry,
    2026-09-13: "no, not recoverable. actually gone." (the earlier
    trash-folder version is dead; its cross-drive move had also 500'd on
    every click because renders live on D: and the trash was on C:). The
    row is marked 'deleted' so the gallery, Out box and file endpoint all
    stop listing it. His click is the only way in here."""
    if get_agent(agent_id) is None:
        raise HTTPException(404, f"No agent '{agent_id}'")
    row = memory.get_output_by_id(int(approval_id))
    if not row or row.get("agent_id") != agent_id:
        raise HTTPException(404, "That picture is not one of this agent's")
    fp = (row.get("file_path") or "")
    if fp.lower().rsplit(".", 1)[-1] not in ("png", "jpg", "jpeg", "webp", "mp4", "webm"):
        raise HTTPException(400, "Not a picture or clip")
    if os.path.isfile(fp):
        # A CLIP STILL PLAYING IS LOCKED (2026-10-02: his delete of Ilnora's video #534 hit a 500 -- the deck was
        # streaming the MP4 and Windows refuses to delete an open file). Retry for a few seconds while the player
        # lets go instead of failing his click.
        import time as _t
        for _try in range(10):
            try:
                os.remove(fp)
                break
            except PermissionError:
                _t.sleep(0.5)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(500, f"Could not delete the file: {exc}")
        else:
            raise HTTPException(409, "That clip is still open in a player -- close it and press delete again.")
    with memory.get_db() as conn:
        conn.execute("UPDATE approvals SET status = 'deleted' WHERE id = ?", (int(approval_id),))
    return {"deleted": True, "id": int(approval_id), "gone": not os.path.exists(fp)}


@app.get("/api/brain/fact/{fact_id}")
def get_brain_fact(fact_id: int):
    """One fact's actual text, for clicking a bubble in the brain map.

    READ-ONLY and deliberately id-only: the map already decided what this
    agent can see when it built the graph, so this just resolves a node
    back to the words behind it. /api/memory/facts/{office} covers only
    private + shared, which would leave every domain: bubble opening
    blank -- looking broken rather than empty.
    """
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM facts WHERE id = ? AND status = 'active'", (fact_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"No active fact with id {fact_id}")
    f = dict(row)
    source = f.get("source_name") or ""
    return {
        "id": f["id"],
        "content": f.get("content") or "",
        "category": f.get("category") or "shared",
        "source_name": source,
        "always_on": not source.endswith(".md"),
        "chars": len(f.get("content") or ""),
        "created_at": f.get("created_at"),
    }


@app.get("/api/brain/graph/{agent_id}")
def brain_graph(agent_id: str):
    """The Brain Map (braingraph.py): this agent's view of the brain as
    nodes+edges, computed live -- the dashboard polls this and animates
    the diff, so a taught fact visibly pops in with its links."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    # Label with the name Barry calls them (Elliot), not the role title
    # (Movie Director) -- the role collides with the private:MovieDirector
    # hub label and reads as a duplicate node.
    first = {v: k for k, v in ingest.folder_map().items()}.get(
        agent["office_name"])
    label = first or agent.get("name") or agent["office_name"]
    return braingraph.build_graph(agent["office_name"], label)


@app.get("/api/agents/{agent_id}/persona-additions")
def get_persona_additions(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    return {"text": ingest.persona_additions(agent["office_name"]),
            "cap": ingest.PERSONA_CAP}


@app.put("/api/agents/{agent_id}/persona-additions")
def put_persona_additions(agent_id: str, req: PersonaAdditionsRequest):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    try:
        ingest.set_persona_additions(agent["office_name"], req.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "chars": len((req.text or "").strip())}


class OfflineModeRequest(BaseModel):
    enabled: bool


@app.get("/api/settings/offline")
def get_offline_mode():
    return {"offline_mode": memory.is_offline_mode()}


@app.post("/api/settings/offline")
def set_offline_mode(req: OfflineModeRequest):
    """Hard privacy switch for the whole office (see memory.is_offline_mode)
    -- when on: every agent is forced onto Ollama regardless of the model
    dropdown, no agent can silently reach for the automatic web-search tool,
    the explicit SearXNG search endpoint refuses to run, and the periodic
    Ollama/app update-version pings stop firing. Nothing about a
    conversation -- scripts, private legal/business detail -- can leave the
    machine while this is on."""
    memory.set_offline_mode(req.enabled)
    return {"offline_mode": req.enabled}


class SendingRequest(BaseModel):
    enabled: bool


@app.get("/api/settings/sending")
def get_sending_enabled():
    """Is the office allowed to actually send an approved item, or does it stop
    at the Out box for Barry to copy out?"""
    import email_cadence
    return {"sending_enabled": dispatch.is_sending_enabled(),
            "omnisend_configured": omnisend_client.is_configured(),
            "omnisend_status": omnisend_client.status(),
            "destinations": sorted(set(dispatch._DESTINATIONS.values())),
            # the cadence (2026-09-01): phase, cap, and how much of it is used
            "email_autonomy": email_cadence.is_autonomous(),
            "email_weekly_cap": dispatch.weekly_cap(),
            "email_sends_this_week": dispatch.sends_this_week(),
            "email_default_segment": memory.get_setting(dispatch.DEFAULT_SEGMENT_KEY, "")}


@app.post("/api/settings/sending")
def set_sending_enabled(req: SendingRequest):
    """The tap. Off by default and off is the safe state -- with this off,
    approving something writes it to the Out box and nothing leaves the
    machine, which is how Barry runs it today ("Im not that big yet").

    Deliberately separate from the API key existing: adding a key must never
    arm sending as a side effect. This switch, and only this switch, does it.
    Offline Mode still overrides it -- privacy beats convenience.
    """
    memory.set_setting(dispatch.DISPATCH_ENABLED_KEY,
                       "true" if req.enabled else "false")
    return {"sending_enabled": req.enabled,
            "omnisend_configured": omnisend_client.is_configured()}


class QueuePausedRequest(BaseModel):
    paused: bool


@app.get("/api/settings/queue-paused")
def get_queue_paused():
    return {"queue_paused": memory.is_queue_paused()}


@app.post("/api/settings/queue-paused")
def set_queue_paused(req: QueuePausedRequest):
    """Live/Paused toggle -- since 2026-07-30 this pauses agent-initiated
    SUGGESTIONS only (the idle ideation loop, which skips generating
    entirely while paused, and Sophie's fix-suggestion dispatch). It no
    longer touches memory.queue_for_approval, whose old global gate
    silently discarded finished images three separate times in two days --
    owner-triggered work always lands in Pending Review now. Manual toggle
    only -- doesn't auto-clear, Barry controls it directly."""
    memory.set_queue_paused(req.paused)
    return {"queue_paused": req.paused}


@app.get("/api/logs")
def get_logs():
    """Tail of the backend's own error/output log (see applog.py) -- lets
    the Godot office's Errors tab show something a real person can read
    and copy-paste, instead of an error only ever existing in whatever
    console window happened to be open when it occurred."""
    return {"log": applog.read_tail()}


@app.get("/api/cost")
def cost():
    return {"session_cost_usd": llm_router.get_session_cost()}


@app.get("/api/updates")
def get_updates():
    """Last known update-check result -- READ-ONLY, instant. 2026-09-06: now
    the full inventory from updates.py (Ollama app + every model, ComfyUI +
    its nodes, backend packages, Bonsai) plus recent apply jobs. Legacy keys
    (model_update_available etc.) are kept for the classic load-time toast.
    Refreshed automatically every UPDATE_CHECK_INTERVAL_SECONDS;
    POST /api/updates/check forces an immediate re-check."""
    return updates.result()


@app.post("/api/updates/check")
async def force_update_check(pip: bool = True):
    if memory.is_offline_mode():
        raise HTTPException(403, "Offline mode is on -- update checks are disabled. Turn it off in Settings to check.")
    return await updates.run_check(include_pip=pip)


class UpdateApplyRequest(BaseModel):
    item: str


@app.post("/api/updates/apply")
def apply_update(req: UpdateApplyRequest):
    """Barry's click. Starts ONE update job (ollama pull / git pull + deps /
    pip upgrade) in the background; the panel polls /api/updates for the log.
    Nothing here runs without this call -- the 12h check never installs."""
    if memory.is_offline_mode():
        raise HTTPException(403, "Offline mode is on -- updates need the internet. Turn it off first.")
    return updates.apply(req.item)


@app.get("/api/updates/jobs")
def update_jobs():
    return {"jobs": updates.jobs()}


@app.post("/api/memory/note")
def add_memory_note(req: MemoryNoteRequest):
    """Called by the Godot office when a file is dropped or a message is
    typed on an agent's panel (see agent_ui.gd) -- persists it into the
    brain so it actually shows up in that agent's (or everyone's, if
    scope='shared') system prompt on the next chat call."""
    category = "shared" if req.scope == "shared" else f"private:{req.scope}"
    memory.add_fact(category, req.content, req.source_name)
    return {"ok": True}


_DELEGATION_PROMPT_TEMPLATE = (
    "Barry dropped a zip file on you with {n} separate files inside. Your "
    "job: decide which ONE agent on the roster below should actually own "
    "each file, based on its real content -- not a guess from the "
    "filename alone, actually weigh what each file is about against each "
    "agent's real role.\n\n"
    "Roster:\n{roster}\n\n"
    "Files:\n{files}\n\n"
    "Format, strictly -- one line per file, nothing else:\n"
    "<exact filename> -> <agent_id>\n\n"
    "Use ONLY agent_ids from the roster above, exactly as written. If a "
    "file genuinely doesn't fit any specialist better than your own "
    "Operations role, route it to yourself (operations) rather than "
    "guessing wrong."
)
_DELEGATION_LINE_RE = re.compile(r"^(?P<filename>.+?)\s*->\s*(?P<agent_id>\w+)\s*$", re.MULTILINE)


async def _delegate_zip_entries(entries: list[dict], zip_filename: str) -> dict:
    """Priya actually reasons about a real dropped zip's per-file content
    and decides which agent should own each piece -- owner's explicit
    request ('Priya delegates tasks, so drop it on her'). Returns
    {filename: office_name it landed in}. Anything the model's reply
    doesn't parse cleanly (missing line, invalid agent_id, filename that
    doesn't match a real entry) falls back to Operations -- Priya's own
    brain -- rather than that piece being silently dropped."""
    priya = get_agent(OPERATIONS_ID)
    valid_ids = {aid for aid in all_agents() if aid != TALIYAH_ID}
    roster = "\n".join(
        f"- {aid} ({a['office_name']}): {a['role']}"
        for aid, a in all_agents().items()
        if aid != TALIYAH_ID
    )
    files_block = "\n".join(
        f"{i + 1}. {e['filename']}: {e['text'][:200]!r}"
        for i, e in enumerate(entries)
    )
    prompt = _DELEGATION_PROMPT_TEMPLATE.format(n=len(entries), roster=roster, files=files_block)
    backend, model = memory.get_active_generation()
    # Real bug found and fixed live: use_thinking defaulted to True (see
    # generate()'s own default), and thinking mode was silently consuming
    # the entire num_predict budget (the 4096 cap added earlier this same
    # session as a runaway-generation backstop) on hidden reasoning,
    # leaving zero tokens for the actual answer -- confirmed directly:
    # replaying the exact same real prompt/content that produced
    # "[Ollama returned no content]" with thinking on produced a clean,
    # correctly-parsed classification with thinking off. A strict
    # single-pass classification task like this doesn't need deep
    # reasoning anyway.
    reply = await llm_router.generate(
        backend, priya["system_prompt"], [{"role": "user", "content": prompt}],
        model=model, use_tools=False, use_thinking=False, office_name=priya["office_name"],
    )

    assignments: dict[str, str] = {}
    for m in _DELEGATION_LINE_RE.finditer(reply):
        fname = m.group("filename").strip().strip("`").strip('"')
        aid = m.group("agent_id").strip().lower()
        if aid in valid_ids and any(e["filename"] == fname for e in entries):
            assignments[fname] = aid

    result = {}
    for e in entries:
        fname = e["filename"]
        target_agent = get_agent(assignments.get(fname, OPERATIONS_ID)) or priya
        memory.add_fact(
            f"private:{target_agent['office_name']}",
            e["text"],
            source_name=f"Delegated by Priya from {zip_filename} ({fname})",
        )
        result[fname] = target_agent["office_name"]

    # Owner's explicit request: Priya should actually tell him what she got
    # and where she sent it, not just a silent backend operation surfaced
    # only as a toast. Templated deterministically, not a second LLM call
    # -- this project's own established lesson tonight is that anything
    # reliability-critical (and a clear report of real actions taken
    # definitely is) does better as real code than hoping a model phrases
    # it right. Logged into her REAL conversation history (not just
    # returned in the API response) so it's there next time her chat is
    # opened, not just a toast that vanishes.
    memory.log_message(OPERATIONS_ID, "user", f"[Dropped a file] {zip_filename}")
    lines = "\n".join(f"- {fname} -> {office}" for fname, office in result.items())
    summary = (
        f"Got it -- \"{zip_filename}\" had {len(entries)} file(s) inside. Here's where each one actually went:\n{lines}"
    )
    memory.log_message(OPERATIONS_ID, "assistant", summary)
    return {"assignments": result, "summary": summary}


@app.post("/api/memory/upload")
async def upload_memory_file(scope: str = Form(...), file: UploadFile = File(...)):
    """The web dashboard's equivalent of Godot's file-drop-onto-a-panel flow
    (see add_memory_note above) -- but the dashboard is a browser page with
    no local file-parsing story, so extraction happens here server-side
    instead of client-side (see document_extract.py) using real Python
    libraries rather than hand-rolled parsing. Same destination either way:
    memory.add_fact, so it shows up in that agent's system prompt on the
    next chat call exactly like a Godot-dropped file would."""
    data = await file.read()
    if not data:
        raise HTTPException(400, f"'{file.filename}' is empty.")
    filename = file.filename or "upload.txt"

    # Real per-file delegation -- owner's explicit request: a zip with
    # mixed content dropped specifically on Priya (Operations, whose real
    # job is delegating to the right specialist) should actually route each
    # piece to the right agent, not just dump the whole thing into her own
    # private brain as one blob. Scoped narrowly on purpose: only fires for
    # scope=="Operations" (her real office_name) AND an actual .zip -- an
    # ordinary single file dropped on her still behaves exactly as before,
    # and a zip dropped on anyone else also behaves exactly as before (one
    # combined fact, no delegation).
    if scope == "Operations" and filename.lower().endswith(".zip"):
        entries = document_extract.extract_zip_entries(data)
        if entries:
            outcome = await _delegate_zip_entries(entries, filename)
            return {
                "ok": True,
                "filename": filename,
                "delegated": outcome["assignments"],
                "priya_says": outcome["summary"],
            }
        # Empty/corrupt zip with nothing real inside -- fall through to the
        # normal path below so there's still a record of the drop.

    text = document_extract.extract_text(filename, data)
    category = "shared" if scope == "shared" else f"private:{scope}"
    # Media descriptions are bulky -- one video timeline runs several thousand
    # characters -- and source_name is this project's always-on vs on-demand
    # switch (memory._is_skill_fact: a name ending .md is pulled on demand by
    # read_skill instead of riding every single message). Dropping ten
    # reference images would otherwise quietly double an agent's context load
    # and blow past the ~11K-char healthy baseline. Stored on-demand with zero
    # data loss -- rename the fact to drop the .md if it must be always-on.
    source_name = f"{filename}.md" if document_extract.is_media(filename) else filename
    memory.add_fact(category, text, source_name)
    return {"ok": True, "filename": filename, "chars_extracted": len(text)}


@app.get("/api/memory/facts/{office_name}")
def get_agent_facts(office_name: str):
    """This agent's own private knowledge, PLUS the real shared 'main
    brain' every agent sees regardless of who it's shown under (owner
    identity, both businesses, anything dropped directly on Victor's panel)
    -- each fact tagged with scope so the dashboard's Brain view can show
    Barry which is which. A shared fact deleted from here is gone for
    EVERY agent, not just this one -- that's the whole reason it needs to
    be visibly marked, not silently mixed in with this agent's own private
    notes. Domain reference knowledge (legal/marketing/business_ops)
    deliberately excluded here -- that's reusable library material granted
    to whichever agents need it, not something taught specifically through
    this agent's own panel, so it doesn't belong in either list."""
    private_facts = memory.get_active_facts(category=f"private:{office_name}")
    shared_facts = memory.get_shared_facts()

    def _shape(f, scope):
        return {
            "id": f["id"],
            "content": f["content"],
            "source_name": f["source_name"],
            "created_at": f["created_at"],
            "scope": scope,
        }

    return {
        "office_name": office_name,
        "facts": (
            [_shape(f, "private") for f in private_facts]
            + [_shape(f, "shared") for f in shared_facts]
        ),
    }


@app.delete("/api/memory/facts/{fact_id}")
def delete_memory_fact(fact_id: int):
    """Permanently removes one fact -- shared or private, see
    memory.delete_fact. Owner's explicit request: a real way to clean up
    what's been taught, not just add to it forever."""
    if not memory.delete_fact(fact_id):
        raise HTTPException(404, f"No fact with id {fact_id}")
    return {"ok": True, "id": fact_id}


@app.post("/api/web_search")
async def web_search_endpoint(req: WebSearchRequest):
    """Explicit, on-demand web search via the local SearXNG container (see
    AgentCompanyBackend/searxng/ + searxng_search.py) -- a second search
    capability, separate from the automatic DuckDuckGo-based search_web
    tool every agent already has silently available mid-reasoning (see
    llm_router.py). This one is never invoked automatically by an agent;
    something has to explicitly call this endpoint (the Godot UI, curl, a
    future button), same explicit-invoke pattern as image generation. If
    the SearXNG container isn't running, this fails clearly with a 503
    rather than silently degrading -- it's an online enhancement, not a
    dependency the rest of the system needs to function."""
    if memory.is_offline_mode():
        raise HTTPException(403, "Offline mode is on -- web search is disabled. Turn it off in Settings to search.")
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "query cannot be empty.")
    try:
        results = await searxng_search.web_search(query)
    except searxng_search.SearxngUnavailable as e:
        raise HTTPException(503, str(e))
    return {"query": query, "results": results}


@app.post("/api/studio/reference")
async def studio_upload_reference(file: UploadFile = File(...)):
    """Drop an image in to use as an IP-Adapter reference.

    It lands in ComfyUI's INPUT ROOT because LoadImage resolves against that
    directory only and does not read subfolders -- the same constraint that
    caught us staging references in a subfolder before.
    """
    name = os.path.basename(file.filename or "reference.png")
    stem, ext = os.path.splitext(name)
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Reference must be a png, jpg or webp image.")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stem)[:40] or "reference"
    dest_name = f"ref_{safe}{ext.lower()}"
    dest = os.path.join(comfy_image.COMFY_DIR, "input", dest_name)
    try:
        data = await file.read()
        with open(dest, "wb") as fh:
            fh.write(data)
    except OSError as e:
        raise HTTPException(500, f"Could not save reference: {e}")
    return {"reference_image": dest_name, "bytes": len(data)}


@app.get("/api/studio/outputs")
def studio_outputs(limit: int = 24):
    """Recent Studio generations for the output strip. The Studio files its
    work under the pseudo-agent "owner", which /api/outputs/{agent_id}
    rejects because it isn't a real agent -- hence this."""
    try:
        rows = memory.get_agent_outputs("owner")
    except Exception:
        rows = []
    return rows[:limit]


@app.get("/api/studio/options")
async def studio_options():
    """Everything the Studio's dropdowns need, read from what is ACTUALLY on
    disk rather than hardcoded in the front end -- so installing a new pose or
    upscaler shows up without touching app.js."""
    comfy_in = os.path.join(comfy_image.COMFY_DIR, "input")
    poses = []
    try:
        poses = sorted(f for f in os.listdir(comfy_in)
                       if f.startswith("pose_") and f.endswith(".png"))
    except OSError:
        pass
    ups = {k: {"file": v[0], "commercial": v[1], "licence": v[2]}
           for k, v in comfy_image.UPSCALERS.items()
           if os.path.isfile(os.path.join(comfy_image.COMFY_DIR, "models",
                                          "upscale_models", v[0]))}
    lora_dir = os.path.join(comfy_image.COMFY_DIR, "models", "loras")
    vae_dir = os.path.join(comfy_image.COMFY_DIR, "models", "vae")
    system_loras = set(comfy_image.CHARACTER_LORAS.values()) | {
        comfy_image.DETAIL_LORA}
    try:
        loras = sorted(f for f in os.listdir(lora_dir)
                       if f.endswith(".safetensors") and f not in system_loras)
    except OSError:
        loras = []
    try:
        vaes = sorted(f for f in os.listdir(vae_dir) if f.endswith(".safetensors"))
    except OSError:
        vaes = []
    return {
        "characters": sorted(comfy_image.CHARACTER_LORAS),
        "poses": poses,
        "upscalers": ups,
        "loras": loras,
        "vaes": vaes,
        "detail_available": os.path.isfile(os.path.join(
            comfy_image.COMFY_DIR, "models", "loras", comfy_image.DETAIL_LORA)),
        "controlnet_available": os.path.isfile(os.path.join(
            comfy_image.COMFY_DIR, "models", "controlnet",
            comfy_image.CONTROLNET_UNION)),
    }


# ELLIOT'S STILLS USE THE OPENING PICTURE ONLY (2026-09-23, Barry: "i need him
# to generate exactly like you did"). The images he loved (#442 Vor'Shara, #447
# Tazz) came from ~400-char dense STILL descriptions. Elliot's ```image``` fence
# is a Seedance prompt: an opening picture paragraph, then timed beats
# ("0-3s he climbs...") and sound/voice lines -- all of which went into the
# still render too. A still gets the opening only; the video keeps it all.
# His words are not changed, only which part of them a still is made from.
# The first timed beat ANYWHERE -- measured on his SHOT 16 fence, he writes
# "...heavy film grain. 0-2s Tazz steps forward" mid-paragraph, not on its own line.
_BEAT_LINE_RE = re.compile(
    r"(?<![\w.])\(?\d+(?:\.\d+)?\s*(?:s\s*)?[-–—]\s*\d+(?:\.\d+)?\s*s\b")
_CHANNEL_LINE_RE = re.compile(
    r"(?m)^\s*(?:[(<{【]|VO\b|.*\bspeaks in voice\b).*$\n?")


# ALWAYS HYPER-REALISTIC (Barry, 2026-09-23: "his shots should always be Hyper
# realistic" / "all his renders and images"). Every still and every clip that
# renders from Elliot's seat carries the look line, the way the #442 prompt he
# loved ends. Added at RENDER time only -- his written fence is not edited, and
# a fence that already says it is left alone.
_HYPERREAL_RE = re.compile(r"hyper[\s-]?realis", re.IGNORECASE)


def _hyperreal(agent_id: str, text: str, video: bool = False) -> str:
    if agent_id != MOVIE_ID or not text or _HYPERREAL_RE.search(text):
        return text
    tail = ("Hyper-realistic live-action footage, real skin and fabric, film grain."
            if video else "Hyper-realistic skin and fabric, film grain.")
    return text.rstrip().rstrip(",") + (" " if text.rstrip().endswith(".") else ". ") + tail


def _still_prompt(agent_id: str, text: str) -> str:
    return _hyperreal(agent_id, _still_opening(agent_id, text))


def _still_opening(agent_id: str, text: str) -> str:
    if agent_id != MOVIE_ID or not text:
        return text
    m = _BEAT_LINE_RE.search(text)
    opening = text[:m.start()] if m else text
    opening = _CHANNEL_LINE_RE.sub("", opening).strip()
    if len(opening) < 150:            # nothing usable before the beats
        opening = _CHANNEL_LINE_RE.sub("", text).strip()
    if opening and opening != text.strip():
        print(f"[still] {agent_id}: rendering the opening picture only "
              f"({len(text)} -> {len(opening)} chars)", flush=True)
    return opening or text


@app.post("/api/generate-image")
async def generate_image(req: ImageGenerateRequest):
    """Real image generation, via local ComfyUI on ROCm -- see
    comfy_image.py (replaced AmuseBridge 2026-07-30, owner's call). Used by
    both Vivian and Taliyah (see IMAGE_CAPABLE_AGENT_IDS). The result is
    queued for approval like any other external-facing output, never
    returned as something already "done".

    Free the GPU of any resident Ollama model before the image engine loads
    its own -- the one-big-thing-on-the-GPU rule, learned via real crashes
    in the AmuseBridge era (chat model holding 10-13GB while Stable
    Diffusion tried to load). Runs on every generation call so switching
    between chatting and generating never recreates the collision.
    comfy_image._resolve_model already maps an unknown/hallucinated
    ```model``` fence name to the default, so no retry pass is needed."""
    # THEY REFERENCE THEIR OWN IMAGE (2026-09-18, Barry: "she should reference
    # her image as well, they all shhould"). All nine have a staged whole-figure
    # reference (agent_ref_<id>.png) and the SELF door has always restaged from
    # it -- but the plain 🎨 button did not, so "draw yourself" from ordinary
    # chat rendered a stranger. If the prompt is plainly about THEM, take the
    # self door instead; anything else (a product shot, a landscape, their art)
    # is untouched, because forcing a face into every render would be worse
    # than the bug.
    req.prompt = _still_prompt(req.agent_id, req.prompt)
    if (is_image_capable(req.agent_id)
            and _prompt_is_self_portrait(req.agent_id, req.prompt)
            and _self_reference(req.agent_id)):
        print(f"[self-portrait] {req.agent_id}: routing the 🎨 button through their own reference")
        return await _render_self_picture(req.agent_id, req.prompt)
    await llm_router.unload_all_models()
    comfy_image.STEPS_OVERRIDE = req.steps  # one call; renders are one-at-a-time
    try:
        result = await comfy_image.generate_image(
            req.prompt, req.negative_prompt, req.model,
            seed=req.seed, detail=req.detail, pose_image=req.pose_image,
            pose_strength=req.pose_strength, upscale=req.upscale,
            reference_image=req.reference_image,
            reference_weight=req.reference_weight,
            reference_preset=req.reference_preset,
            extra_lora=req.extra_lora,
            extra_lora_strength=req.extra_lora_strength,
            vae_name=req.vae_name)
    finally:
        comfy_image.STEPS_OVERRIDE = None
    if "error" in result:
        raise HTTPException(502, result["error"])

    # Negative prompt + actual model used are embedded in the stored content
    # string (rather than new DB columns) so the dashboard's Regenerate
    # button can parse them back out and re-run the exact same generation.
    content = f"Generated image concept: {req.prompt}"
    if req.negative_prompt:
        content += f"\nNegative: {req.negative_prompt}"
    content += f"\nModel: {result['model']}"

    approval_id = memory.queue_for_approval(
        req.agent_id,
        "public_content",
        content,
        file_path=result["path"],
    )

    # Rebuild the chat cache in the background while Barry reviews the
    # image -- see _prewarm_after_render for the delay-and-skip logic.
    asyncio.create_task(_prewarm_after_render())

    return {
        "approval_id": approval_id,
        "path": result["path"],
        "model": result["model"],
        "commercial_use": result["commercial_use"],
        "licence_note": result["licence_note"],
        # Passed through so the Studio can show what actually happened and let
        # a look be reproduced. These were computed all along but dropped here.
        "seed": result.get("seed"),
        "character_lora": result.get("character_lora"),
        "extras": result.get("extras", {}),
    }


# LTX-2.3 generates audio from the prompt, including SPEECH. Barry's B-roll
# came back with a narrator reading the prompt out loud. Nothing in the
# office ever wants an unrequested voice, so speech suppression rides on
# every video negative unless he explicitly asked for dialogue -- the
# officially-scoped use of negatives for this model is exactly subtitles
# and audio (see seedance-prompting).
_NO_SPEECH_NEG = ("spoken words, narration, voiceover, dialogue, singing, "
                  "subtitles, captions, on-screen text")


# A prompt that ASKS for sound (2026-09-13, Barry: "she needs to really use
# the LTX studio 2.5 to the fullest"): the agents' self clips pass no
# negative, so the no-speech block was appended to every one of them and
# would have fought "soft moaning expression" / a quoted line in the prompt.
_WANTS_SOUND_RE = re.compile(
    r"\b(moan\w*|gasp\w*|breath\w*|whisper\w*|says?|said|speak\w*|talk\w*|"
    r"sings?|singing|voice|dialogue|laugh\w*|sigh\w*|cries|crying|scream\w*)\b"
    r"|\"[^\"]{3,}\"", re.I)


def _video_negative(user_negative: str | None, prompt: str = "") -> str:
    """The negative actually sent to LTX: Barry's, plus speech suppression.

    Skipped when he clearly wants voice -- if his negative mentions
    dialogue/speech he is steering it himself and this must not fight him --
    or when the PROMPT itself asks for sound (a quoted line, moaning,
    whispering...). LTX-2.5 makes the audio; the prompt decides it.
    """
    neg = (user_negative or "").strip()
    if re.search(r"\b(dialogue|speech|voice|narrat|talking|singing)\b", neg, re.I):
        return neg
    if _WANTS_SOUND_RE.search(prompt or ""):
        return neg
    return f"{neg}, {_NO_SPEECH_NEG}" if neg else _NO_SPEECH_NEG


_CLIP_SECONDS_RE = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*(?:s|sec|secs|second|seconds)\b", re.I)


def _self_clip_seconds(offer: str, default: int = 7) -> int:
    """Length of an agent's own clip: what THEY asked for in the offer line
    ("a 12 second clip"), else 7. Capped at 15 -- comfy_image caps there too.
    Cost, honest: ~4 min per second of video at 1024x576 on this card."""
    m = _CLIP_SECONDS_RE.search(offer or "")
    if not m:
        return default
    return max(2, min(int(m.group(1)), 15))


@app.get("/api/generate/status")
async def generation_status():
    """What is generating right now (2026-08-16, Barry: "i want something
    that shows me its generating"). ComfyUI's own queue is the authority --
    the in-process record only adds the human context the queue can't give
    (which agent asked, which kind, the prompt text). If our record says
    busy but ComfyUI's queue is empty, the job is finished or dead and we
    report idle rather than leaving a spinner up forever."""
    queue = await comfy_image.queue_state()
    current = comfy_image.current_render()
    busy = bool(queue["running"] or queue["pending"])
    if current and not busy and current.get("elapsed_s", 0) > 15:
        current = None
    return {
        "busy": busy or bool(current),
        "queue": queue,
        "current": current,
        # Distinct from a render: chat-triggered jobs report here too, so
        # the dashboard can show "Elliot is rendering B-ROLL 01".
        "video_render_holding_gpu": comfy_image.render_in_progress(),
    }


@app.post("/api/generate/cancel")
async def cancel_generation():
    """Stop whatever is generating. Built 2026-08-16 after a 22-minute
    render of the wrong shot with no way to stop it but killing ComfyUI."""
    result = await comfy_image.cancel_render()
    print(f"[cancel] generation cancelled: {result}")
    return result


@app.post("/api/generate-video/prepare")
async def prepare_video_frame(req: VideoPrepareRequest):
    """Stage 1 of the image->video chain: render the conditioning still and
    return it for display. Nothing is queued for approval here -- this is not a
    deliverable, it is the frame LTX will be conditioned on. Stage 2 is the
    normal /api/generate-video with start_frame set to the returned name.

    The still is copied into ComfyUI's INPUT ROOT because LoadImage resolves
    against that directory only and does not read subfolders.
    """
    await llm_router.unload_all_models()
    result = await comfy_image.generate_image(
        req.prompt, req.negative_prompt, model=req.model, seed=req.seed
    )
    if "error" in result:
        raise HTTPException(502, result["error"])

    src = result["path"]
    frame_name = f"startframe_{req.agent_id}_{int(time.time())}.png"
    dest = os.path.join(config.COMFY_DIR, "input", frame_name)
    try:
        shutil.copyfile(src, dest)
    except OSError as e:
        raise HTTPException(500, f"Could not stage the start frame for LTX: {e}")

    return {
        "start_frame": frame_name,
        "path": src,
        "model": result.get("model"),
        "seed": result.get("seed"),
        # the dashboard shows this, then auto-continues to /api/generate-video
        # unless the owner stops it -- his choice over silent auto-render.
        "next": "/api/generate-video",
    }


def _recent_character_still(agent_id: str, key: str, prompt: str,
                            max_age_h: int = 24) -> str | None:
    """Newest restaged still of this character made from EXACTLY this prompt
    (the approval row stores 'Generated image concept: <prompt>'), not
    rejected, younger than max_age_h, file still on disk. None otherwise."""
    head = f"Generated image concept: {prompt.strip()}"
    try:
        with memory.get_db() as c:
            rows = c.execute(
                "SELECT file_path, content, created_at FROM approvals "
                "WHERE agent_id=? AND file_path LIKE ? AND status NOT IN ('rejected','deleted') "
                "ORDER BY id DESC LIMIT 20",
                (agent_id, f"%char_{key}_%" if key else "%.png")).fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"[video] still lookup failed: {e}", flush=True)
        return None
    cutoff = time.time() - max_age_h * 3600
    for fp, content, created in rows:
        if not (content or "").startswith(head):
            continue
        try:
            age_ok = os.path.getmtime(fp) >= cutoff
        except OSError:
            continue
        if age_ok:
            return fp
    return None


@app.post("/api/generate-video")
async def generate_video(req: VideoGenerateRequest):
    """Real text-to-video with synchronized audio, via local ComfyUI +
    LTX-2.3 (comfy_image.generate_video). Same approval contract as images:
    the finished clip lands in Pending Review and waits for the owner --
    nothing is 'done' until he approves it. Renders take minutes; the
    dashboard's Outputs auto-refresh surfaces the result. Strictly one at a
    time: this endpoint is synchronous and ComfyUI queues internally."""
    # SEEDANCE CHANNELS NEVER REACH LTX (2026-08-21). Elliot writes shot
    # prompts in Seedance 2.5 grammar now (Barry's standing rule) -- ()
    # music, <> SFX, {} dialogue, 【】 subtitles. Those channels are
    # Higgsfield grammar; LTX has no channels and SPEAKS raw prompt text,
    # so a {} dialogue line would come back narrated over the footage. The
    # visual description line(s) go through; channel lines are stripped.
    _visual = " ".join(
        s for s in (ln.strip() for ln in req.prompt.splitlines())
        if s and s[0] not in "(<{【").strip()
    if _visual and _visual != req.prompt.strip():
        print(f"[video] stripped Seedance channels: {len(req.prompt)} -> {len(_visual)} chars")
        req.prompt = _visual
    # PROSE NEVER REACHES THE VIDEO ENGINE (2026-08-16). A real render went
    # out with Elliot's chat commentary as the prompt -- "Barry's standing
    # rule: these B-ROLL blocks are transition scenes..." -- and LTX-2.3
    # SPEAKS the prompt text, so the clip came back with his name read
    # aloud, "B-roll" narrated, and an invented desert instead of Colorado
    # (there was almost no visual description in it to work from). Seven
    # minutes of GPU for an unusable clip. Refusing costs a second.
    # Quoted dialogue is exempt from the chatter test (2026-09-23): an LTX
    # prompt carries the script's spoken lines in quotes BY DESIGN, and "Now
    # let's see what's inside." tripped the `let's` signature and refused a
    # correct clip. The words outside the quotes are what has to read as a shot.
    if _looks_like_chat_prose(re.sub(r'"[^"\n]{0,300}"', '', req.prompt)):
        raise HTTPException(400, (
            "That prompt reads like conversation, not a shot description -- "
            "and LTX speaks whatever text you give it, so this would come "
            "back with those words narrated over invented scenery. Send just "
            "the visual description: subject, action, camera, environment, "
            "lighting, style."
        ))

    # CHARACTER VIDEO = A RESTAGED STILL, THEN LTX MOVES IT (2026-09-14, Barry:
    # "all of it"). Text-to-video of @Keth from words was never going to be
    # him; the still made through the character-restage door is. Same shape
    # as the agents' [SELF] clips: render the still (Qwen-Edit on the
    # character's staged reference, 16:9 canvas), stage it as the i2v start
    # frame, and hand LTX a prompt with the handles turned into plain words
    # because LTX speaks whatever text it is given. The still is queued as its
    # own approval so Barry sees both. An explicit start_frame from the
    # dashboard's two-stage chain skips this.
    still_approval_id = None
    # the still is keyed on ITS prompt (handles live there); the LTX prompt is plain words
    _for_still = (req.still_prompt or "").strip() or req.prompt
    _chars = comfy_image.mentioned_characters(_for_still) if comfy_image.CHARACTER_RESTAGE_ENABLED else []
    # 1-3 characters (the group door, 2026-09-22); a group still is saved as
    # char_<a>_<b>[_<c>]_NNNNN_.png, so the reuse lookup keys on the joined names.
    if (req.start_frame is None and 1 <= len(_chars) <= comfy_image.GROUP_MAX
            and all(comfy_image.character_reference(k) for k in _chars)):
        # REUSE FIRST (Barry, 2026-09-14: "why are you even doing stills? just
        # use the ones i have already"). If this character already has a
        # restaged still made from THIS prompt in the last day -- the usual
        # case, Elliot just rendered it and hit Generate Video -- that file is
        # the start frame. Only when there is none is a still rendered.
        _sp = _still_prompt(req.agent_id, _for_still)
        still_path = _recent_character_still(req.agent_id, "_".join(_chars), _sp)
        if still_path:
            print(f"[video] reusing existing still {os.path.basename(still_path)}", flush=True)
        else:
            await llm_router.unload_all_models()
            still = await comfy_image.generate_image(_sp)
            if "error" in still:
                raise HTTPException(502, still["error"])
            still_path = still["path"]
            still_approval_id = memory.queue_for_approval(
                req.agent_id, "public_content",
                f"Generated image concept: {_sp}\nModel: {still['model']} "
                f"(restaged still, start frame for the clip)",
                file_path=still_path)
        frame_name = f"startframe_{req.agent_id}_{int(time.time())}.png"
        try:
            shutil.copyfile(still_path,
                            os.path.join(comfy_image.COMFY_DIR, "input", frame_name))
        except OSError as e:
            raise HTTPException(500, f"Could not stage the start frame for LTX: {e}")
        req.start_frame = frame_name
        print(f"[video] character restage -> start frame {frame_name} "
              f"(still approval {still_approval_id})", flush=True)
    elif req.start_frame is None and req.agent_id == MOVIE_ID and not _chars:
        # EVERY SCENE STARTS FROM AN IMAGE (Barry, 2026-09-22: "each scene will
        # need elliot to gen the beginning of each scene with an image to
        # generate it right"). Character shots already did (above); a scene
        # with nobody in it -- B-roll, the Talia in space, an empty black site
        # -- went straight to text-to-video. Now it gets its opening still on
        # Qwen-Image 2.1 (film-only licence, and this is Elliot's seat), 16:9,
        # reused if he already rendered this exact prompt, queued so Barry sees
        # the frame the clip starts from.
        _sp = _still_prompt(req.agent_id, _for_still)
        still_path = _recent_character_still(req.agent_id, "", _sp)
        if still_path and not still_path.lower().endswith((".mp4", ".webm")):
            print(f"[video] reusing existing still {os.path.basename(still_path)}", flush=True)
        else:
            await llm_router.unload_all_models()
            still = await comfy_image.generate_image(_sp, model="qwen21",
                                                     width=1664, height=928)
            if "error" in still:
                raise HTTPException(502, still["error"])
            still_path = still["path"]
            still_approval_id = memory.queue_for_approval(
                req.agent_id, "public_content",
                f"Generated image concept: {_sp}\nModel: {still['model']} "
                f"(opening still, start frame for the clip)",
                file_path=still_path)
        frame_name = f"startframe_{req.agent_id}_{int(time.time())}.png"
        try:
            shutil.copyfile(still_path,
                            os.path.join(comfy_image.COMFY_DIR, "input", frame_name))
        except OSError as e:
            raise HTTPException(500, f"Could not stage the start frame for LTX: {e}")
        req.start_frame = frame_name
        print(f"[video] opening still -> start frame {frame_name} "
              f"(still approval {still_approval_id})", flush=True)
    if _chars:
        # LTX speaks its prompt: handles become plain words on every character
        # clip, whether the frame came from the door or from the dashboard.
        req.prompt = comfy_image.video_prompt_text(req.prompt)
    req.prompt = _hyperreal(req.agent_id, req.prompt, video=True)

    await llm_router.unload_all_models()
    result = await comfy_image.generate_video(
        req.prompt, _video_negative(req.negative_prompt, req.prompt), duration_s=req.duration_s,
        start_frame=req.start_frame,
    )
    if "error" in result:
        raise HTTPException(502, result["error"])

    content = f"Generated video concept: {req.prompt}"
    if req.negative_prompt:
        content += f"\nNegative: {req.negative_prompt}"
    content += f"\nModel: {result['model']}\nSeed: {result['seed']}\nDuration: {req.duration_s}s"

    approval_id = memory.queue_for_approval(
        req.agent_id,
        "public_content",
        content,
        file_path=result["path"],
    )

    # Same post-render prewarm as the image endpoint -- after a ~7-minute
    # video render the cache is certainly gone, and this is exactly the
    # moment Barry is about to come back and talk to Elliot about the clip.
    asyncio.create_task(_prewarm_after_render())

    return {
        "approval_id": approval_id,
        "path": result["path"],
        "model": result["model"],
        "commercial_use": result["commercial_use"],
        "licence_note": result["licence_note"],
        "seed": result["seed"],
        "still_approval_id": still_approval_id,
    }


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    print(f"\nStarting Agent Company backend at http://{HOST}:{PORT}\n")
    uvicorn.run(app, host=HOST, port=PORT)
