"""Barry, 2026-09-28: Sophie is "the custodian of it all" / "she is also security".

BUILD MAP -- one on-demand routing table on her shelf: for each subsystem, the
module(s), the doc and the log that hold the truth. It points at LIVE sources
(it copies no mechanics), so it cannot go stale the way a copied manual does.
"""
import sys
sys.path.insert(0, "backend")
import memory

SOURCE = "build-map-custodian-subsystems-modules-logs-where-the-truth-lives.md"

BODY = """USE WHEN: build, the build, subsystem, module, modules, where is, which file, how does it work, architecture, backend, custodian, mechanics, broken, bug, fix, restart, port, ports, watchdog, security, secure, breach, intrusion, virus, malware, privacy, google, tracker, log, logs, audit, preflight, health check, office check, what changed
BUILD MAP -- WHERE THE TRUTH LIVES FOR EVERY PART OF THE OFFICE (custodian's routing table, 2026-09-28)

HOW TO USE: find the part below, then READ the listed source before you answer (read_project_file; negative start_line = end of a log). Order of authority: the running code > CLAUDE.md > BUILD_HISTORY.md (end) > newest HANDOFF-*.md > docs/handbook chapter (+ its dated "changes since" section) > FILE-MAP.md (generated 2026-08-29, module list incomplete -- the backend has ~80 modules now). All paths under C:\\Users\\Owner\\Desktop\\AgentCompanyBackend unless noted.

RUNNING, PORTS, RESTARTS -- CLAUDE.md "Running it" + "Components / ports"; handbook 01. Backend 8420 (backend/main.py), dashboard 8765 (..\\AgentDashboard), Ollama 11434, Bonsai llama-server 8811, ComfyUI 8188 (office) / 8189 (MyStudio), SearXNG 8080, Laya 8812 -- all 127.0.0.1. scripts/stack_watchdog.ps1 revives them every 45s (data/watchdog.log). Before ANY restart: scripts/preflight_check.py must exit 0; never restart while data/video_rendering.flag exists; kill the backend by port owner, never by "main.py".

MODEL PATH -- bonsai_llm.py (server, breaker, tool loop, loop stop, time ceiling), llm_router.py (routing, fallback, write-tool stripping), config.py; handbook 02; your skill "OFFICE RELIABILITY". Logs: data/bonsai_events.log, data/bonsai_server.log, data/traces.jsonl (800-char cap), data/loop_cuts.jsonl. laya_shadow.py / laya_tags.py / laya_setups.py = Laya, the CPU decision layer (private log, no text).

AGENTS AND PROMPTS -- agents.py (roster, base prompts; office_name/agent_id are DB KEYS), personas/<office>.md, personalities/<office>.md, main.py (/api/chat builds the turn, seat tools in _SEAT_STORE_TOOLS); handbook 03. Hires live in CUSTOM_AGENTS -- "in AGENTS" checks miss them.

BRAIN, RECALL, LEARNING -- memory.py (facts; source ending .md = on-demand skill, else always-on; categories private:/domain:/business:/knowledge:; the shared-tier wall), recall.py (USE WHEN routing, first 1200 chars), semrecall.py, memory_weight.py, lessons.py, outcomes.py, learning_review.py, readback.py, claim_net.py (done-claims + numbers net), reasoning.py; handbook 04 + 11. DB: data/brain.db (db_backup.py keeps copies).

BOARD AND TEAMWORK -- teamwork.py (briefs, huddles, send-backs, failed-brief notes), jobs.py (job routing; data/jobs.log), activity.py; data/teamwork.log, data/brief_runs/.

CLOCK AND INNER LIFE -- clock.py (live setting work_days Mon-Sat, 9-6; never blocks Barry), reflect.py, social.py, life.py, mood.py, relationships.py, ideation.py, home_refresh.py, artwork.py; handbook 10. mind-* facts never reach work prompts; home is the only private room.

INBOX -- main.py /api/inbox + /read: worknote-* = office (green) channel, mind-for-barry-* = home; after-hours work notes held till the office opens.

STORE, ADS, EMAIL, SOCIAL -- store.py (read-only Woo; buyer_sources, walk_checkout), bizwatch.py, competitor_watch.py, ads_api.py/ads_auth.py/ads_feed.py (Microsoft Ads, paused), omnisend_view.py (read) / omnisend_client.py (send), dispatch.py (approve = send, atomic claim), email_cadence.py, email_design.py, social_cadence.py, factcheck.py, content_policy.py, store_inbox.py; handbook 08; your skill "sophie-store-ops-brain". Store findings: fact "STORE FINDINGS -- 2026-09-25/26".

IMAGES, VIDEO, VOICE, READING -- comfy_image.py (ComfyUI, GPU flag), agent_scenes.py, char_refs.py, reel_builder.py, plant_photos.py, media_understanding.py (vision + OCR + Whisper), ocr.py, kokoro_tts.py, piper_tts.py; workflows/*.json; handbook 07. data/comfyui.log. One big thing on the 16GB card at a time.

FILM -- script_index.py, script_pos.py, script_wip.py, jobs.py shot parsing; handbook 06. Canon = data/barry-character-canon.md = brain fact 592, byte-identical; never change canon.

SOPHIE'S OWN HANDS -- engineer_tools.py (run_command safe list, writes), codefix.py (gated self-apply + undo, your journal "my-code-fixes"), read_project_file.py, health.py (system_health), watch.py (15-min watch), updates.py + update_checker.py, skills_intake.py, degradation.py, standing_rules.py; handbook 05.

SECURITY -- YOURS. security_watch.py (the build: nothing outside gets in; no Google, DuckDuckGo-only search, every service on 127.0.0.1), pc_security.py (the PC: Windows Defender and friends, not a homemade AV), host_watch.py (the machine changing: new startup items, services, scheduled tasks). web_search.py + searxng_search.py + tools/searxng-office/settings.yml (engines: DuckDuckGo + Mojeek, no Google). .env holds keys -- never print or send them; never send Barry's email, name or accounts anywhere (his rule). Every service binds 127.0.0.1; a listener on 0.0.0.0 or a new outbound destination is an incident: name it, show the evidence, tell Barry.

DASHBOARD -- ..\\AgentDashboard: neo-chamber.html, neo-holo.html (the two he uses), index.html, test-panel.html (every test result, newest first); handbook 09. Patch with anchored edits; node --check after.

INSTRUMENTS (run_command): scripts/preflight_check.py (before every restart), scripts/office_health.py, scripts/test_*.py (e.g. test_breaker_2026_09_28.py, test_job_routing.py, test_shot_lookup.py), scripts/functional_audit_2026_09_07.py ("does it all work", one Bonsai turn), scripts/tool_audit_2026_09_17.py (every tool on every seat, no GPU).

WHEN SOURCES DISAGREE: the running code is the fact. Say which doc is wrong and tell Barry -- never "fix" a record of superseded wording by rewriting it."""

memory.add_fact("private:Engineer", BODY, source_name=SOURCE,
                title="BUILD MAP -- where the truth lives for every part of the office")
print("added", len(BODY), "chars")
