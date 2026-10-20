# Doors and gates on the chat path -- audit (2026-10-19)

Reading audit, no code changed. A **door** answers, queues, or rewrites before the model; a **gate** decides which seat or channel reaches a door, a tool, or a net. Every condition below is quoted from the code as it stands after the 2026-10-19 fix that moved the whole-script door back under Elliot. Grades: **WRONG SEAT** (a seat can reach another seat's door), **LOOSE TRIGGER** (ordinary language fires it), **ORDER** (shadowed branch or gate mismatch), **NONE**. Fixes are one-line descriptions, never code.

Channel vocabulary used throughout: the chat decides "home" once, at `main.py:6480`: `_is_personal = (req.personal or bool(req.reply_to)) and not req.office`. Task turns (`req.task`) are the office talking (video queue, board, cadence).

## A. backend/main.py -- doors that answer or rewrite before the model

**1. Script bookmark** -- `main.py:4370`, triggers in `script_pos.py:30-43`.
Trigger: `WHERE_RE` ("where are we", "what shot are we on"...), `PREV_RE`, `NEXT_RE` = `next shot|next one|keep going|carry on|continue|the one after|what's next|moving on|on to the next|^next$`.
Gate: `req.agent_id == MOVIE_ID and not req.personal`.
Does: a "where" ask returns the bookmark text with no model, logging user + role `assistant`, `jobs.log(... "script_position")`; "next"/"prev" rewrites `req.message = f"{req.message} -- that is {label}"` so the whole shot machinery fires.
RISK: **LOOSE TRIGGER.** "Continue the outline you were giving me on EP2" or "where are we on the EP2 budget" become a named-shot ask or a bookmark reply. Fix: anchor `continue|carry on|moving on` to a whole-message match like `^next$` already is, and require `shot|block|script` within `WHERE_RE`.

**2. Ilnora's ask door** -- `main.py:4402-4430`.
Trigger: `\b(?:make|do|create|write|produce|get me|give me|need(?: you to make)?|want)\b[^.?!\n]{0,40}?\b(a couple of|a few|another|one|an|a|1|2|two|3|three|4|four|5|five|some|more)\b[^.?!\n]{0,30}?\b(videos?|shorts?|longs?|long videos?|long forms?|vids?)\b`, no saved draft, message <= 60 words.
Gate: `req.agent_id == "ilnora" and not req.personal and not req.task`.
Does: `asyncio.create_task(_vq.barry_asked(_n, _form, _ask))` (holds builds 120 min per video, runs N writing turns, queues builds), logs an "(Office) Ilnora is on it" line as role `assistant`, returns without the model.
RISK: **LOOSE TRIGGER.** The verb and the count word may sit 40 characters apart and the sentence may be a question: "write a caption to go with the video", "did you make a video today?", "do a quick fix on the short" all queue a build. Also the gate ignores `req.reply_to` (a click-reply to her note is home elsewhere). Fix: require the count word within three characters of the verb, refuse messages ending in `?`, and gate on the `_is_personal` test rather than `req.personal` alone.

**3. Whole-script / verbatim door** -- `main.py:4433`, logic `main.py:3054`, regexes `3021-3050`.
Trigger, in order: file export (`_SCRIPT_FILE_RE` + `_SCRIPT_MENTION_RE`), whole document (`_SCRIPT_WHOLE_RE` = `\b(whole|entire|full|complete)\s+(script|episode|thing)\b|\ball of it\b|\bstart to finish\b`), then strong (`as is|verbatim|word for word|exactly|as written`) or weak (`what happens|show me|read me|give me|see`...) asks; each `and not _SCRIPT_CREATIVE_RE`.
Gate: `req.agent_id == MOVIE_ID and not req.personal`.
Does: serves DB text verbatim (the full script is ~125K chars), logs user + role `assistant`, `jobs.log(... "factual_script")`, returns.
RISK: **LOOSE TRIGGER** (now Elliot-only, so no longer wrong-seat). "I watched the whole thing last night, loved it" serves the entire script into his thread, and that text rides in his next twenty turns of history. **ORDER** against `jobs.py:51` `_MEGA_WRITE_RE`: "I want the whole script in production format" has no creative word, so the verbatim door wins and the rewrite pass never runs. Fix: require `_SCRIPT_MENTION_RE` beside `all of it|whole thing|start to finish`, and add `production|format` to `_SCRIPT_CREATIVE_RE`.

**4. Standing-rule capture** -- `main.py:4477`, patterns `standing_rules.py:40-62`.
Trigger: any of `from now on`, `every time`, `going forward`, `remember to`, `remember:`, `i('ve| have)? (already )?told you`, `how many times (do|must|have) i`, `stop \w+ing`, `don't ... (again|anymore)`, `(always|never) (be|use|...)`; message <= 500 chars.
Gate: `None if req.task else standing_rules.capture(...)` -- every seat, both channels, Taliyah included.
Does: writes the message verbatim as an ALWAYS-ON fact "STANDING RULE from Barry" in that seat's private brain.
RISK: **LOOSE TRIGGER** at home. "Remember to eat something tonight" or "stop worrying about it" in Amara's home window becomes a permanent rule charged on every one of her work messages. Fix: skip when `_is_personal` is true (compute it before this point) and require a second-person object after `stop \w+ing`.

**5. Exemplar by praise** -- `main.py:4641-4683`, saver `main.py:8666`.
Trigger: `_explicit` (`save it|bless|lock it in|add it to your examples`) or `_praise` (`perfect|nailed it|that's it|exactly|i like that|love it|keep it|that works|approved?|more like this`...) with `len(_m) <= 60`, and no `_reservation` (`but|except|change|instead|fix|redo|tweak|less|more of`).
Gate: `_home_turn = req.personal and not req.office` skips; everything else saves. Note `req.reply_to` is not consulted here.
Does: saves the previous non-user history row as an exemplar -- Elliot's image fence to `prompt-exemplars.md`, any other seat to `style-exemplars`, an ALWAYS-ON fact (3 kept, 2,600 chars each).
RISK: **LOOSE TRIGGER** and **ORDER.** "Approved" typed to Derek about an email makes that reply his permanent style. Worse: doors 1-3 log their office text as role `assistant`, the model path logs role `agent` (`main.py:7702`), and this door takes "the last row whose role != user" -- so "perfect" right after the ask door saves "(Office) Ilnora is on it..." as Ilnora's style exemplar. Fix: skip rows whose role is `assistant` (or log door lines under a distinct role such as `office`), and use the `_is_personal` test.

**6. HOME ONLY strip** -- `main.py:4572`, `_without_home` at `2831`, `_HOME_LIFE_RE` at `2815` = `\b(at home|home|homes|gowns?|under ?wear|underwear|see[- ]through|lingerie)\b`.
Gate: `if req.agent_id != TALIYAH_ID` -- applied to the personality file on every turn; home re-adds the full file later.
Does: hides any `#` section whose heading contains "home only", and deletes every sentence matching the regex.
RISK: **LOOSE TRIGGER.** Bare `home|homes` cuts ordinary biography at work: "I grew up in a home with six kids." or "I work from home on Fridays." vanish from the voice sheet. Fix: keep the heading rule and drop the bare `home|homes` alternates (leave `at home`).

**7. Jobs router** -- `jobs.py:130`, regexes `51-73`; consumers `main.py:5078-5365` and `5564-6096`.
Trigger: `_MEGA_WRITE_RE` = `\b(entire|whole|full|complete)\b.{0,40}\b(rewrite|script|episode|production)\b|...`; `_NAMES_A_SHOT_RE` = `\b(?:shots?|b-?rolls?|scenes?)\s*#?\s*(?:[a-z]?\d+[a-z]?|\b[a-h]\b)`; shot-word + `give|write|direct`; `_PROMPT_RE` + `_GENERATION_RE` (`writ\w*`).
Gate: `if agent_id != movie_id: return Job("chat", ...)` -- every non-Elliot seat is "chat", so the un-gated `if _shot_ask:` block at `main.py:5225` is Elliot-only in effect.
Does: mega_write rebuilds the system prompt task-scoped with recall off (`5395`); shot_prompt reads scene blocks, moves the bookmark (`5259`, `5283`), injects the Seedance doc and skills, appends the two-stage directive, raises the reply cap, arms the dialogue and length nets.
RISK: **LOOSE TRIGGER.** "I shot a few clips at the grow today" is SHOT A (shot job, recall off). "Did you see the full episode of that show" is a mega-write pass. "That prompt you wrote yesterday was great" is a shot ask with the Act One treatment injected. Fix: require a digit or `#` for the bare-letter form (allow a letter only after `scene`), require `rewrite|write|convert` in `_MEGA_WRITE_RE` instead of bare `script|episode`, and make the prompt rule need an imperative verb (`write|give|make`) rather than any `writ\w*`.

**8. Shot output mode** -- `main.py:1117`. `_SHOT_HIGGS_RE` wins, else `_SHOT_LOCAL_RE` (`gen|render|make|image|video|here|local...`), else production. Only consulted when `_shot_ask`. RISK: **NONE.**

**9. Work nudges and nets share a mismatched channel test** -- nudges `main.py:6270-6475`; nets `7143` (Sophie read-net), `7177` (Vivian look-net), `7216` (claim net), `7269` (numbers), `7404/7440` (Elliot dialogue/length), `7449` (lesson net).
Gate on all of them: `not (req.personal or req.reply_to)` (some add `and not _is_personal`). The channel decision itself is `(req.personal or bool(req.reply_to)) and not req.office`.
Does: nudges append directive text only; nets re-run once and append "(Office correction: ...)".
RISK: **ORDER.** A reply to a WORK note in the office window (`req.office` true, `req.reply_to` set) is a tools-on work turn that gets no work nudge and no work net: Priya can claim "I searched online" there with nothing behind it and nothing corrects it. Fix: compute `_is_personal` once at the top of the `try` and replace every `not (req.personal or req.reply_to)` with `not _is_personal`.

**10. Ilnora's go door and its net** -- `main.py:6737-6775`, net `7243-7260`.
Trigger: `\b(?:go ahead|(?:a |full )go\b|go\b|make (?!sure)(?:it|that|this|them|those|the|your|a |me )|making the videos?|send it|build (?:it|that|this|them)|do it|finish it|queue it|get it (?:done|made|built))`, message <= 30 words, a saved draft exists.
Gate: `req.agent_id == "ilnora" and not _is_personal and not req.task and not ...startswith("[video draft:")`.
Does: cuts her roster to `video_draft`, sets budgets, appends the OFFICE instruction; after the turn, if the draft still exists, the office itself calls `draft("ilnora", {"action": "send"})` and a passing draft with a caption is queued to build.
RISK: **LOOSE TRIGGER.** `go\b`, `do it`, `make the` match mid-sentence: "let's go over the plan before you make the next one" sends the draft to the build queue on his behalf. Fix: anchor the bare words the way `_GO_ASK_RE` (`main.py:1601`) does (whole message = go/do it/make it), keeping only "make that/the video" as a mid-sentence form.

**11. Hand-off guarantee** -- `main.py:7507-7542`, regex `_TEAM_WORK_STRONG_RE` at `1528`.
Trigger: `put the team on|...|\b(?:get|have|put)\s+(?:me|us)\s+(?:a|an|the|some)\b|i (need|want) a (read|report|plan...)|by (tomorrow|monday...)|help (me|us) (figure|work|plan|get|find|source|track)|(find|research|look (for|into)|compare...) ... (suppliers?|products?|leads?|bags|quotes?...)`.
Gate: `_biz_seat and not req.task and _team_work_strong(req.message) and (_is_personal or (_use_tools and _did_nothing))`, where `_biz_seat = req.agent_id in AGENTS and req.agent_id != TALIYAH_ID` (Ilnora is not in `AGENTS`, so excluded).
Does: `teamwork.file_brief("CIO", <seat or Operations>, "From Barry, in his words ...")`, held until opening hours, and appends "(That's office work ...)" or "(Office: ... brief #N)".
RISK: **LOOSE TRIGGER.** At home, "get me a glass of water" or "help me find my keys" to Amara files a brief on the BusinessOps board with Victor tracking. At work, "compare the two leads you mentioned" to Marcus, answered from context with no tool, files a brief too. Fix: at home require the business-noun alternative only (drop bare `get me a`); at work treat "answered without a promise" (`_HANDOFF_CLAIM_RE` false) as acting.

**12. Home phone call** -- `main.py:6227-6262`, trigger `social.py:266 call_target`.
Trigger: a send verb within 40 chars of a crew first name, or `(call|phone|ring|talk to|tell|hit up) (her|him|them)` resolved to the most recently named crew member.
Gate: `(req.personal or bool(req.reply_to)) and not req.office and not req.task`.
Does: runs a full two-agent call on the GPU before her reply and pastes the transcript into her context.
RISK: **LOOSE TRIGGER**, low cost. "Tell her I said hi" or "you should talk to him about it" runs the call. Fix: require the verb at sentence start.

**13. Praise/approval, council, image fallback, approval queue** -- `7605` queues any `req.action_type in EXTERNAL_ACTION_TYPES` (NONE). Council `7674`: `agent in (CIO_ID, MARKETING_ID)` and `is_council_ask` = `COUNCIL_WORD_RE` or (`ONE_WAY_RE` and `DECISION_RE`), `reasoning.py:63-70`. RISK: **LOOSE TRIGGER** -- `launch(?:ing)? (the|a|our)|hire|exclusive` plus `go ahead|recommend` means "should we go ahead and launch the fall email?" convenes three extra Bonsai turns. Fix: require `COUNCIL_WORD_RE` or the money/lease/loan alternatives, not `launch|hire` alone. Elliot's fence strip (`7629`), `_MOVIE_REPLY_FIXES` (`7639`), desk-claim scrub (`7655`), ABOUT ME NOW (`7724`): **NONE.**

## B. backend/llm_router.py -- tool rosters and dispatch

**14. Seat rosters** -- `main.py:568` `_SEAT_TOOLS`, `711` `_SEAT_STORE_TOOLS` (offline-stripped), `781 _tools_for_seat` plus runtime grants `memory.get_agent_tools` minus `_TOOL_GRANT_DENY` (`885`: run_command, restart_backend, write/propose/undo fixes, install_skill, onboard, accept_host_changes, grant_tools, update_business_brain, script blocks). Hires get delegate/team_status (`main.py:170-184`) and `neutral_tools`. Ilnora's video tools are not in code; they arrive by grant. Home turns get `[LOOK_AT_RENDER_TOOL]` only (Taliyah also art). RISK: **NONE.**

**15. Word-gated tools** -- script save/delete `llm_router:2513` (`approved?|save|keep (it|them...)|lock ... in|store|cut\b|delete\b|remove\b|drop ...` in `current_user_message`, office must be MovieDirector), grant_tools `2143` (`grant|give \w+ the tool|tools?\b.{0,20}\b(to|for)\b|kit ... out|revoke`), onboard `2165`, accept_host_changes `2190`, undo `2904`, security scan `2921`.
RISK: **LOOSE TRIGGER**, double-gated by the model having to call the tool. "Which tools do you have for that?" opens grant_tools; "save your energy, just read me shot 4" opens a script save. On task turns `current_user_message` is the OFFICE's brief text, which routinely contains "save"/"cut". Fix: drop the `tools ... to/for` alternative; set `current_user_message` to empty when `req.task`.

**16. Ollama fallback keeps write tools** -- `llm_router:3609` `_FALLBACK_WRITE_TOOLS`, applied at `3758`; Sophie's loop net `main.py:7077` uses the same set.
The set omits `video_draft`, `make_video`, `check_video`, `product_video`, `cad_generate`, `office_ops`, `propose_admin_task`, `design_email`, `grant_tools`.
RISK: **WRONG SEAT** (wrong model). CLAUDE.md's rule is "the Ollama fallback gets NO write tools", but when Bonsai fails the 9b can queue a video build, hold or release builds, relaunch the watchdog, propose an admin task, grant tools, or push an Omnisend template. Fix: add those names to `_FALLBACK_WRITE_TOOLS`, or derive the set from a per-tool `writes` flag so a new tool cannot be missed.

## C. backend/video_tool.py / video_queue.py

**17. Draft actions** -- `video_tool.py:303 draft`. `start` refuses a title overlapping a made or queued one (8+ chars either way); `send` requires a caption, runs `check`, then `start()` -> `video_queue.enqueue`. `check_only` (`445`): same-fingerprint refusal and one check per request (contextvar, fresh per HTTP request). RISK: **NONE.**

**18. Check send-backs** -- `video_tool.py:540`. In order: medical words in her on-camera `shot` (`_MEDICAL`, line 37), more than one outfit (`_GARMENTS`, 40, includes `top|tank|tee`), redo title, made-title overlap, plant reuse against made jobs, 35% shingle overlap, repeated parts, sentence said twice (>= 0.6), Long under 1,310 words, blank picture (<= 2 words), unnamed plant when a picture uses `herb|plant|leaf|leaves|flower|...|root|bark`.
RISK: **LOOSE TRIGGER**, cost one check turn. "show: the old root cellar door" or "a bark-brown table" demands a scientific name. Fix: drop `root|bark|bush|vine` from the plant-word list (they name places and colours).

**19. The office's own turns** -- `video_queue.py:596 _ask` posts `{"task": True, "personal": False}` to `/api/chat`; `barry_asked` (`1121`) and `make_one` (`1052`); `write_long_draft` (`819`) sends `[video draft: research|parts|check]`.
In main: `history = []`, nothing logged, standing rules off, ask and go doors off (`not req.task`), `_ilnora_video_making` true, stage budgets at `6964`, the parts stage trims tools to `video_draft, read_skill` with web off. `barry_asked` logs "(Office) Video i of n ..." as role `assistant` (see door 5).
RISK: **NONE** beyond door 5's role problem. `drain_tick` (`551`) never builds under a turn in flight.

## D. backend/recall.py, claim_net.py, tone_guard.py, dispatch.py

**20. Recall direct doors** -- `recall.py:355`. Scene labels (`_SCENE_REF_RE`, 195), explicit dates, opening/ending asks (419: an `open|start|begin|end...` word plus `episode|script|film|movie|scene|story|act`), word-matched scenes, workflow phrases (474), then scoring (`MIN_SCORE 10`, Taliyah 6 with `SEAT_REACH_ONLY`). Every door reads through `script_index.read_scene(office_name, ...)` and the seat's own shelf, so a seat without scripts gets nothing. `mind-`/`worknote-` excluded. RISK: **NONE** cross-seat; prompt-space only.

**21. Claim net** -- `claim_net.py:20-100 RULES`, `gaps` at 107, main gate `7216` (`_use_tools and not (req.personal or req.reply_to) and not _is_personal`; Sophie skips `saved`). A rule applies only when the seat holds a backing tool. Numbers (`211`): every `$`, `%` (not 0/100) and count > 10 must be in the system prompt, conversation, tool text, or one shown step; Elliot and Taliyah exempt. Words never rewritten. RISK: **NONE** cross-seat. Note: a Legal "15% restocking fee is typical" is flagged unsourced by design.

**22. Tone guard** -- `tone_guard.py:70 clean_taliyah_reply`, called `main.py:7565`, gate `req.agent_id == TALIYAH_ID`, both channels, before the reply is logged.
Does: strips emoji; deletes `sweetie|sweetheart|boo|chief|partner|boss` anywhere; replaces whole tokens `esp|u|ur|r|w/|tryna|dat`.
RISK: **LOOSE TRIGGER.** "My business partner" becomes "my business"; "the boss said" becomes "the said"; "the U.S." becomes "the you.S."; "Toys R Us" becomes "Toys are Us". Fix: anchor nicknames to address position (sentence start or after a comma, followed by punctuation) and skip `u|r` when followed by `.`.

**23. Dispatch** -- `dispatch.py:266`. Gate order: `dispatch_enabled` setting, status `approved`, `dispatched_at` empty, offline mode, destination (`_DESTINATIONS = {"email": "omnisend"}` only), dry run, Omnisend configured, fact-check banner and `factcheck.check_email`, weekly cap, atomic `sending` claim, then `_send_email` (link check, price re-check, test-send path). Callers: `main.py:8247` after the decide route's card/scene/engineer/media branches, and `email_cadence.py:377` only `if is_autonomous() and designed` (setting default `"false"`). RISK: **NONE.** Note only: with no default segment set, `_send_email` falls to Omnisend's "everyone".

## What a human should test

Office window unless stated; the expected sign is in brackets.

1. **Elliot:** "I watched the whole thing last night, loved it." [the full script, no model; `jobs.log` says `factual_script`] -- door 3.
2. **Elliot:** "continue the outline you were giving me for EP2" [a Seedance shot block for the bookmarked next shot] -- door 1.
3. **Ilnora, no draft saved:** "write a caption to go with the video you sent me" [instant "(Office) Ilnora is on it: 1 video"; a build queues] -- door 2.
4. **Ilnora, with a saved draft:** "let's go over the plan before you make the next one" [reply ends "(Office: your draft ... was sent to the build queue on Barry's go)"] -- door 10.
5. **Amara, gold home window:** "remember to eat something tonight" [a STANDING RULE appears in her Brain tab] -- door 4.
6. **Amara, home:** "get me a glass of water lol" [reply ends "(That's office work ... brief #N)"; a BusinessOps brief on the board] -- door 11.
7. **Ilnora:** right after test 3's office line, type "perfect" [`style-exemplars` fact now holds the office line] -- door 5.
8. **Priya, office window, click one of her WORK notes and reply:** "did you search online for those suppliers?" [if she claims a search with no `search_web` in the trace, no "(Office correction" follows] -- door 9.
9. **Taliyah:** "say this back to me exactly: my partner and the boss flew to the U.S." [reply reads "my and the flew to the you.S."] -- door 22.
10. **Ilnora, with a passing draft, after stopping llama-server so the 9b answers:** "make the video now" [the trace shows `video_draft` offered and callable on the fallback] -- door 16.

Two more if time allows: **Elliot** "I shot a few clips at the grow today" (`jobs.log` shows `shot_prompt`, door 7) and **Victor** "should we go ahead and launch the fall email?" (three council turns, door 13).
