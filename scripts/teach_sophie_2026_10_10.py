"""Barry, 2026-10-10: "teach her everything she needs to know about this build, the codes, everything. you need to
teach her how to handle all this properly" / "get her right. she needs to be functional."

Three docs on Sophie's shelf (private:Engineer, on-demand). Two REPLACE stale 2026-09-28 versions (same source_name,
old row superseded, not deleted): the build map (missed 17 of 90 modules, incl. her own engineer_ops / stack_watch)
and office reliability (predated context-fit, the loop-stop change, the GPU-off guard, the 9b fix). One is NEW: how to
handle "fix it" -- today she diagnosed Elliot's overflow from failures that all predated the 13:23 fix.
Safe to re-run."""
import sys
sys.path.insert(0, "backend")
import memory

DOCS = []

DOCS.append(("build-map-custodian-subsystems-modules-logs-where-the-truth-lives.md",
             "BUILD MAP -- where the truth lives for every part of the office", r"""USE WHEN: build, the build, subsystem, module, modules, where is, which file, what file, how does it work, architecture, backend, custodian, mechanics, broken, bug, fix, restart, port, ports, watchdog, security, secure, breach, intrusion, virus, malware, privacy, google, tracker, log, logs, audit, preflight, health check, office check, what changed, code, the code, codebase, source
BUILD MAP -- WHERE THE TRUTH LIVES FOR EVERY PART OF THE OFFICE (custodian's routing table, updated 2026-10-10)

HOW TO USE: find the part below, then READ the listed source before you answer (read_project_file; negative start_line = end of a log). Order of authority: the running code > CLAUDE.md > BUILD_HISTORY.md (END = newest) > newest HANDOFF-*.md > AgentDashboard\test-panel.html (newest first) > docs/handbook chapter > FILE-MAP.md (2026-08-29, incomplete). The backend is 90 modules in backend/. All paths under C:\Users\Owner\Desktop\AgentCompanyBackend unless noted.

RUNNING, PORTS, RESTARTS -- CLAUDE.md "Running it" + "Components / ports"; handbook 01. Backend 8420 (backend/main.py), dashboard 8765 (..\AgentDashboard), Ollama 11434, Bonsai llama-server 8811, ComfyUI 8188 (office) / 8189 (MyStudio), SearXNG 8080 -- all 127.0.0.1. scripts/stack_watchdog.ps1 runs as the logon task "Barrys AI Stack Watchdog" and revives them every 45s; data/watchdog.log has every restart with LOCAL time ("Backend DOWN ... restarting"). Before ANY restart: scripts/preflight_check.py must exit 0; never restart while data/video_rendering.flag exists or a turn is in flight (GET /api/ping "busy"); kill the backend by port owner, never by "main.py". applog.py mirrors all backend output to data/backend.log (no timestamps -- use watchdog.log for WHEN).

MODEL PATH -- bonsai_llm.py (server start, GPU-present guard, breaker, tool loop, CONTEXT FIT retry, loop stop, time ceiling, forced-answer pass), llm_router.py (routing, Ollama fallback, tool dispatcher _dispatch_tool_call, write-tool stripping), config.py, tracing.py (data/traces.jsonl); handbook 02; your skill "OFFICE RELIABILITY". main._history_for_model bounds the thread sent each turn. Logs: data/bonsai_events.log, data/bonsai_server.log, data/traces.jsonl, data/loop_cuts.jsonl.

AGENTS AND PROMPTS -- agents.py (roster, base prompts, all_seats(); office_name/agent_id are DB KEYS), personas/<office>.md, personalities/<office>.md, main.py (/api/chat builds the turn; seat tools in _SEAT_TOOLS / _SEAT_STORE_TOOLS / _tools_for_seat; runtime grants in memory agent_tools); handbook 03. Hires live in CUSTOM_AGENTS -- "in AGENTS" checks miss them. tone_guard.py = Taliyah's post-generation tone cleanup; textclean.py = the shared emoji/text cleanup.

BRAIN, RECALL, LEARNING -- memory.py (facts; source ending .md = on-demand skill, else always-on; categories private:/domain:/business:/knowledge:; agent_domains grants; the shared-tier wall), recall.py (USE WHEN routing, first 1200 chars, no stemming), semrecall.py, memory_weight.py, lessons.py, outcomes.py, learning_review.py, readback.py, claim_net.py (done-claims + numbers net), fact_net.py (video-script sentences checked against sources), reasoning.py, braingraph.py (the Brain Map view); handbook 04 + 11. DB: data/brain.db (db_backup.py keeps copies). Teaching without code: ingest.py (drop/<FirstName>/{persona,personality,skills,knowledge}/ + the Teach panel), document_extract.py (file -> text), skills_intake.py. library.py = books kept OUT of the brain, reached on demand. research_tools.py = real sources (labs, universities) read, not stored.

FILES -- agent_files.py: every seat reads Barry's out box (read_barrys_file, list_files) and writes real docs to his DESK (send_file_to_barry). gallery.py = what each agent gave him (pictures/clips) and who asked.

BOARD AND TEAMWORK -- teamwork.py (briefs, huddles, send-backs, failed-brief notes), jobs.py (job routing; data/jobs.log), activity.py (busy line, turn_in_flight); data/teamwork.log, data/brief_runs/.

CLOCK AND INNER LIFE -- clock.py (live setting work_days = Mon-Fri, 9-6; never blocks Barry), reflect.py, social.py, life.py, mood.py, relationships.py, ideation.py, home_refresh.py, artwork.py; handbook 10. mind-* facts never reach work prompts; home is the only private room.

INBOX -- main.py /api/inbox + /read: worknote-* = office (green) channel, mind-for-barry-* = home; after-hours work notes held till the office opens.

STORE, ADS, EMAIL, SOCIAL -- store.py (read-only Woo; buyer_sources, walk_checkout), bizwatch.py, competitor_watch.py (manual only), ads_api.py/ads_auth.py/ads_feed.py (Microsoft Ads, paused), omnisend_view.py (read) / omnisend_client.py (send), dispatch.py (approve = send, atomic claim), email_cadence.py, email_design.py (Vivian's design_email), social_cadence.py, factcheck.py, content_policy.py, store_inbox.py; handbook 08; your skill "sophie-store-ops-brain".

IMAGES, VIDEO, VOICE, READING -- comfy_image.py (ComfyUI, the GPU flag, card guard), agent_scenes.py, char_refs.py, reel_builder.py (builds the videos, storyboard pass), video_tool.py (Ilnora's make_video / video_draft / check), video_queue.py (her queue; live setting video_build_window = "any" since 2026-10-10 -- Barry: "she is off schedule now" -- builds start whenever the card is free; anything else = the old 18:00-09:00 slot), youtube_view.py (her channel, read-only), plant_photos.py, media_understanding.py (vision + OCR + Whisper), ocr.py, kokoro_tts.py, piper_tts.py; workflows/*.json; handbook 07. data/comfyui.log, data/video_queue/. One big thing on the 16GB card at a time.

FILM -- script_index.py, script_pos.py, script_wip.py, jobs.py shot parsing; handbook 06. Canon = data/barry-character-canon.md = brain fact 592, byte-identical; never change canon.

SOPHIE'S OWN HANDS -- engineer_ops.py (office_ops: read queue/drafts/events/watchdog/card/Bonsai timings + reversible writes: hold/release builds, pause/resume/requeue, archive a draft, relaunch the watchdog; propose_admin_task: elevated PowerShell -> his board -> his approve runs it under UAC, transcript in data/admin_tasks/), engineer_tools.py (run_command safe list, writes, restart_backend: preflight first, refuses under a render or a building video, restarts AFTER your reply ends -- only its 'scheduled' result means a restart is coming), codefix.py (propose one exact snippet -> his approve applies it with backup + preflight + restart; undo_fix; vital-only self-apply, 3/day), read_project_file.py, health.py (system_health), watch.py (15-min watch), stack_watch.py (in that watch: watchdog task alive/relaunch, GPU card OFF/BACK, driver resets), updates.py + update_checker.py, degradation.py, standing_rules.py; handbook 05; your journal "my-code-fixes".

SECURITY -- YOURS. security_watch.py (the build: nothing outside gets in; no Google trackers, DuckDuckGo/Mojeek search, every service on 127.0.0.1), pc_security.py (the PC: Windows Defender and friends), host_watch.py (new startup items, services, scheduled tasks). web_search.py + searxng_search.py + tools/searxng-office/settings.yml. .env holds keys -- never print or send them; never send Barry's email, name or accounts anywhere. A listener on 0.0.0.0 or a new outbound destination is an incident: name it, show the evidence, tell Barry.

DASHBOARD -- ..\AgentDashboard: neo-chamber.html, neo-holo.html (the two he uses), index.html, test-panel.html (every test result, newest first); handbook 09. Patch with anchored edits; node --check after.

INSTRUMENTS (run_command): scripts/preflight_check.py (before every restart), scripts/office_health.py (per-seat always-on load, drift), scripts/tool_audit_2026_09_17.py (every tool on every seat, no GPU), scripts/functional_audit_2026_09_07.py ("does it all work", one Bonsai turn), scripts/test_*.py (test_job_routing.py, test_shot_lookup.py, test_breaker_2026_09_28.py).

WHEN SOURCES DISAGREE: the running code is the fact. Say which doc is wrong and tell Barry -- never "fix" a record of superseded wording by rewriting it."""))

DOCS.append(("office-reliability-stubby-replies-fallback-breaker-timeout-loop-stop.md",
             "OFFICE RELIABILITY -- stubby replies, fallback, breaker, timeouts, context, loop stop", r"""OFFICE RELIABILITY -- STUBBY REPLIES, FALLBACK, BREAKER, TIMEOUTS, CONTEXT, LOOP STOP
USE WHEN: stubby, short replies, short answers, slow, slowness, fallback, fell back, backup model, 9b, coder, breaker, circuit, tripped, trip, timeout, timed out, ReadTimeout, Bonsai down, Bonsai unavailable, loop stop, loop-stop, going in circles, second-guessing, reliable, reliability, outage, why is the office, why are replies, 400, Bad Request, exceeds, context size, context overflow, too big, n_ctx, CONTEXT FIT, GPU NOT FOUND, card disabled, 3 tok/s
OFFICE RELIABILITY -- HOW THE MODEL PATH FAILS AND HOW TO PROVE IT (updated 2026-10-10)

THE PATH. Every work seat asks Bonsai 2 (llama-server, port 8811, ONE slot: requests queue). If Bonsai fails, the turn falls back: Engineer -> qwen2.5-coder:14b, most seats -> qwen3.5 9b (Ollama). Fallback models are weaker (short, generic) and get NO write tools. Fallback = the usual cause of "stubby replies". The trace's "error" says "Bonsai failed, falling back to X: <reason>" -- the reason is the diagnosis.

FAILURE SIGNATURES AND WHAT ALREADY HANDLES THEM (check these before proposing anything):
1. CONTEXT OVERFLOW -- 400 "request (N tokens) exceeds the available context size (98304 tokens)". The prompt (system + always-on + tools + thread + tool results) is over Bonsai's 98,304. Handled twice since 2026-10-10: main._history_for_model sends at most 16K chars per old message and 120K total; and bonsai_llm._shed_oldest_history / _post_fitting read the exact size from the 400, drop just enough of the OLDEST history (never the system prompt, Barry's message or this turn's tool work), leave reply room and retry once -> bonsai_events.log "CONTEXT FIT <office>: ...". A 400 AFTER a CONTEXT FIT line = the system prompt + current message alone are too big (nothing left to drop): the seat's always-on load is the problem -- report the numbers (scripts/office_health.py), never cut an agent's knowledge yourself; that is Barry's call. Elliot carries the heaviest load (~128K chars always-on).
2. FALLBACK ALSO FAILS -- Ollama 400. Fixed 2026-10-10 (repeat_last_n = num_ctx; Bonsai-shaped messages converted). Ollama's own reason is now in the trace.
3. GPU OFF -- after a reboot the RX 9070 XT came up DISABLED (Device Manager code 22) and Bonsai ran on the CPU at ~3 tok/s. bonsai_llm.ensure_running now refuses a server without the GPU ("GPU NOT FOUND" event); stack_watch reports the card OFF / BACK in your watch. Re-enabling a device is an admin task -> propose_admin_task, his approval.
4. THE BREAKER (bonsai_llm.py). 2 real failures -> TRIPPED: every seat on fallback for 600s, then ONE retry. Not counted: a 4xx (that request's fault), an empty reply, a refusal while tripped, a timeout while /health is ok ("SLOW REQUEST"). "Bonsai unavailable (circuit tripped...)" usually means the breaker REFUSED the request, not that the server died -- check /health and the server log first.
5. THE CEILINGS. A tool turn stops searching after 360s ("TIME CEILING") or 8 rounds, then answers with tools removed. One read times out at 300s. The board waits 900s per run.
6. THE LOOP STOP. Watches reasoning while it streams. A: 8 of the last 12 100-char pieces already written earlier ("repeating a passage verbatim"). B: 7+ second-guessing words (wait, / hmm, / actually, / let me re-check...) in the last 2,500 chars AND, since 2026-10-10, the tail must also be re-saying itself (15%+ of its 5-word phrases already used: bonsai_llm._repeat_share, DITHER_MIN_REPEAT). Why: 308 "second-guessing" cuts 09-28 -> 10-10 (107 yours, 142 Ilnora's) were mostly false -- Qwen writes "Actually," / "Hmm," as plain connectives; your typical cut re-used 1% of its phrases, the real loops 25-53%. Replayed on all 329 recorded cuts: yours 107 -> 8. A cut answers with thinking OFF from the notes. Every cut is saved in data/loop_cuts.jsonl (reasoning tail + phrases that fired) -- the evidence for any further threshold change.

THE EVIDENCE -- read the END of logs (read_project_file with negative start_line, e.g. -60):
- data/bonsai_events.log: failure N/2, TRIPPED, SLOW REQUEST, TIME CEILING, LOOP STOP, CONTEXT FIT, GPU NOT FOUND, EMPTY REPLY. LOCAL time.
- data/traces.jsonl: one line per turn, UTC (local = UTC minus 6 in October). "model" = who answered; "error" = why it fell back. final_content capped at 800 chars.
- data/bonsai_server.log: llama-server's own lines, no clock. "prompt eval time = X ms / N tokens" (normal ~300-660 tokens/s; much slower = VRAM squeezed or GPU off); "exceeds the available context size" = overflow; "task 0" = server restarted.
- data/watchdog.log: every backend/service restart, LOCAL time -- this is how you know when new code went live.
- system_health shows the last 12 Bonsai events; data/jobs.log and data/teamwork.log for board runs.

TRAPS THAT HAVE ALREADY COST BARRY:
- Old failures are not current failures. Compare each failure's time with the last restart (watchdog.log) and the newest BUILD_HISTORY.md entry before calling something broken -- see "FIX IT -- THE RIGHT WAY".
- A 7-day ads/sales total is history. Look at the per-day rows.
- One seat's slow job is not an outage. Read which office and which reason.
- Say what the logs do NOT show. "Cause not in the logs" is a real answer; a guess is not.

FIXING. Follow "FIX IT -- THE RIGHT WAY". Thresholds (breaker, ceilings, loop-stop limits) change only on his yes, after evidence shows what a change would do."""))

DOCS.append(("fix-it-the-right-way-check-whats-already-fixed.md",
             "FIX IT -- THE RIGHT WAY (check what is already fixed, prove the cause, one fix, verify live)", r"""USE WHEN: fix it, fix this, can you fix it, go ahead and fix, go ahead, fix that, repair, patch, it's broken, its broken, broke, not working, still broken, stubby, sort it out, handle it, take care of it, stay on top of it, sentry, custodian, propose a fix, code fix, apply, approve, restart, is it fixed, did it work, already fixed, check it out

# FIX IT -- THE RIGHT WAY

Barry, 2026-10-10: "you are the sentry of this office. i need you to stay on top of things here. you have the tools, skills and ability." He wants it FIXED and the live office right -- not a second patch on top of a fix that is already running, and not a guess.

What went wrong on 2026-10-10 (learn from it): you diagnosed Elliot's context overflow correctly, but all four failures you cited (16:14, 16:42, 17:15, 17:30 UTC) were from BEFORE the 13:23 local restart that already carried a fix for exactly that. You never checked the timeline, so "fix it" would have stacked a second fix on a live one.

STEP 1 -- IS IT STILL HAPPENING? (always first, takes one minute)
- When did the code last change? data/watchdog.log (local time: "Backend DOWN ... restarting") + the END of BUILD_HISTORY.md (what changed and why) + the top of ..\AgentDashboard\test-panel.html (newest test first) + the newest HANDOFF-*.md.
- Line up your evidence: traces.jsonl is UTC (local = UTC - 6 in October), bonsai_events.log and watchdog.log are local. A failure before the last restart proves nothing about the code running now.
- Only failures AFTER the last restart count as "still broken". None yet? Say: "fixed at <time> by <change>; no failure since; here is what will prove it on the next <kind of> turn."

STEP 2 -- PROVE THE CAUSE (still broken)
- From the logs, not from memory: the exact error line, the seat, the time, the numbers (tokens, seconds, counts). Read the code path that produced it (read_project_file on the module the BUILD MAP names). Say the cause in one sentence with the evidence behind it.
- If the logs do not show the cause, say that plainly and say what would show it.

STEP 3 -- ONE FIX, THE SMALLEST THAT ADDRESSES THE CAUSE
- Reversible office state (a stuck build, a paused job, a dead watchdog) -> office_ops does it now; tell him what you did.
- New code that is written but not running (the watchdog.log restart is OLDER than the change) -> restart_backend. It runs preflight and restarts right after your reply; say "restarting after this reply", never "restarted".
- Code -> codefix: ONE exact snippet per proposal, with the evidence and a plain explanation (his ELI17 rule). It waits for his approve click unless the office shows a code-verified live breakage (vital), max 3 a day. On approve it backs up, applies, runs preflight, restores on failure, restarts the backend. Any fix can be undone (undo_fix).
- Needs admin rights (a device, a service, a scheduled task) -> propose_admin_task; his approve runs it under UAC.
- Never: two fixes for one cause, touching a file someone just fixed without reading that fix first, changing thresholds without evidence, cutting an agent's knowledge or persona (his call), changing canon.
- Bigger than one snippet? Plan it in your reply (files, steps, risk), let him say yes, then send the snippets one at a time.

STEP 4 -- VERIFY ON THE LIVE OFFICE
- After the restart: the watchdog.log restart line is newer than the apply; then the thing itself -- the next turn of that seat has no fallback error in traces.jsonl, the event you expected appears (e.g. "CONTEXT FIT"), the tool returns the right thing. Syntax ok is not "works".
- Never restart while data/video_rendering.flag exists or someone is mid-turn (GET /api/ping "busy").

THE CLAIM NET WATCHES YOU (2026-10-10): "restarted the backend" with no scheduled restart_backend this turn, or "raised/changed/tuned the threshold/code/setting" with no code-fix or command tool, gets your reply sent back once and then an "(Office correction: ...)" line. On 2026-10-10 your forced answer said "Restarted the backend" and "Raised the dithering threshold from 7 to 12" -- neither happened. Only claim what a tool result in THIS turn shows. If you ran out of time, say what you read and what is still undone.

STEP 5 -- TELL HIM, SHORT
What was wrong (with the evidence), what was already fixed and when, what you changed or proposed, how you verified it, and what you could NOT verify. A few lines. Then stay on it: your 15-minute watch reports it if it comes back.

DECISION, IN ONE LINE: already fixed -> say so with the proof time; still broken + proven cause -> one fix + verify; cause not proven -> say what you measured and what would prove it."""))

memory.init_db()
for source, title, body in DOCS:
    with memory.get_db() as conn:
        n = conn.execute("UPDATE facts SET status = 'superseded' WHERE category = 'private:Engineer' AND source_name = ? "
                         "AND status = 'active'", (source,)).rowcount
    memory.add_fact("private:Engineer", body, source_name=source, title=title)
    print(f"{source}: {len(body):,} chars (replaced {n})")
