"""Barry, 2026-09-28: "make sure sophie can fix it all properly".

One on-demand skill on Sophie's own shelf (private:Engineer, source ends .md):
how the office's model reliability actually works, where the evidence is, and
how to diagnose it -- the mechanisms verified in code and logs today.
"""
import sys
sys.path.insert(0, "backend")
import memory

SOURCE = "office-reliability-stubby-replies-fallback-breaker-timeout-loop-stop.md"

BODY = """USE WHEN: stubby, short replies, short answers, slow, slowness, fallback, fell back, backup model, 9b, coder, breaker, circuit, tripped, trip, timeout, timed out, ReadTimeout, Bonsai down, Bonsai unavailable, loop stop, loop-stop, going in circles, second-guessing, reliable, reliability, outage, why is the office, why are replies
OFFICE RELIABILITY -- HOW THE MODEL PATH FAILS AND HOW TO PROVE IT (verified 2026-09-28)

THE PATH. Every work seat asks Bonsai 2 (llama-server, port 8811, ONE slot: requests queue behind each other). If Bonsai fails, the turn falls back: Engineer -> qwen2.5-coder:14b, most seats -> qwen3.5 9b. Fallback models are weaker (short, generic replies) and get NO write tools. Fallback = the usual cause of "stubby replies".

THE BREAKER (bonsai_llm.py). 2 real failures -> TRIPPED: every seat goes to fallback for 600s, then ONE retry. Since 2026-09-28 these do NOT count as failures: a 4xx (that request's fault), an empty reply, a refusal while already tripped (BreakerOpen), and a timeout while /health is ok (logged "SLOW REQUEST"). Only an unreachable/broken server trips it now.

THE CEILINGS. A tool turn stops searching after 360s (TURN_TIME_CEILING_SECONDS, logged "TIME CEILING") or 8 rounds, then answers from what it gathered with tools removed. One read times out at 300s. The board (teamwork.py) waits 900s per run; a timeout or empty reply is a FAILED run, and a brief that fails for good leaves Barry an office work note.

THE LOOP STOP. Watches reasoning while it streams. Fires on 8/12 repeated 100-char pieces ("repeating a passage verbatim") or 7+ second-guessing phrases in the last 2,500 chars ("second-guessing in circles": wait, / actually, / let me re-check|verify|re-read...). On a hit it closes the stream and answers with thinking OFF from the notes. MEASURED 2026-09-28: loop-stopped turns are NOT shorter (15% short vs 29% without) -- it is not the stubby cause. It fires mostly on you (42 of 68 in a week), possibly false alarms from normal log-reading ("let me re-read"). Every cut is saved in data/loop_cuts.jsonl (reasoning tail + the phrases that fired): read those before claiming the stopper is wrong or right.

THE EVIDENCE -- read the END of logs (read_project_file with a negative start_line, e.g. -60):
- data/bonsai_events.log: failure N/2, circuit TRIPPED, circuit reset window reached, SLOW REQUEST, TIME CEILING, LOOP STOP, EMPTY REPLY. Local time.
- data/traces.jsonl: one line per turn, UTC. "model" = who answered; "error" says "Bonsai failed, falling back to X: <reason>". final_content is CAPPED at 800 chars -- never measure reply length from it beyond that.
- data/bonsai_server.log: llama-server's own lines, NO clock (uptime stamps). "prompt eval time = X ms / N tokens" -- normal on this card is ~300-660 tokens/s; far slower means the card is squeezed (VRAM spill). "task 0" = the server restarted.
- system_health shows the last 12 Bonsai events; data/jobs.log and data/teamwork.log for board runs; data/brief_runs/ keeps every board run's raw reply.

TRAPS THAT HAVE ALREADY COST BARRY:
- "Bonsai unavailable (circuit tripped or server did not come up)" usually means the breaker REFUSED the request, not that the server died. Check /health and the server log before saying it crashed.
- A 7-day ads/sales total is history. Look at the per-day rows before saying something is running now.
- One seat's slow job is not an outage. Read which office and which reason.
- Say what the logs do NOT show. "Cause not in the logs" is a real answer; a guess is not.

FIXING. Diagnose from the logs first, then propose the fix to Barry with the evidence (file, line, measured numbers). Thresholds -- breaker count/window, the ceilings, the loop-stop limits -- change only on his yes, after the evidence (e.g. a week of loop_cuts.jsonl) shows what a change would do. Simple, vital fixes follow your codefix rules."""

memory.add_fact("private:Engineer", BODY, source_name=SOURCE,
                title="OFFICE RELIABILITY -- stubby replies, fallback, breaker, timeouts, loop stop")
print("added", len(BODY), "chars")
