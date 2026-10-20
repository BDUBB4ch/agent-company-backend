# Shared prose -- the candidate list for Barry (2026-10-17)

Why: "they all kinda talk the same." Measured: every seat's base system prompt is 23-27K chars (Elliot 47K), and
**25.5K of that is the same text in all nine seats** (agents.py blocks). The part that is actually *them* -- the job
block plus their own HOW I TALK sheet (1-2K) -- is under 10 %. On top ride 34-55K of always-on brain facts and up to
32K of pins (Vivian 10 pins, Elliot 28K). A voice cannot win against that ratio by sampling alone (measured: a nudge).

Rule for every line below: **nothing is cut without your strike.** "Code enforces it" means the behaviour is gated in
code today, so the words are a reminder, not the gate. Chars are per seat, per message, forever.

| # | Block (agents.py) | Chars | In | What it says | Code already enforces? | My call |
|---|---|---|---|---|---|---|
| 1 | `_TALKS_LIKE_A_PERSON` | 4,020 | 9 | "How you talk": 2-5 plain sentences, texting-colleague tone, no headers, no lists... one voice for all nine | No (style) | **CUT to 3 lines.** This is the single biggest reason they sound alike: it is the same voice prescription for everyone, and it now sits on top of ten individual HOW I TALK sheets. Keep only the format rule (plain prose, no headers in chat). |
| 2 | `_CONFIRMS_UNDERSTANDING` (+ `_BLANK` twin) | 3,891 | 9 | Make sure you understood the ask; when to ask one question vs. go | Partly (claim nets catch wrong deliveries, not wrong reads) | **SHRINK to ~800.** Keep the rule and the one example; cut the essay. |
| 3 | `_THINKS_AND_SEARCHES` | 3,088 | 9 | Think it through; the tools you have and when to search | Thinking is ON in code (per-request budget); tools come with their own schemas every call | **SHRINK to ~600.** The tool list duplicates the tool schemas word for word. |
| 4 | `_WORKS_WITH_THE_TEAM` + `_TEAM_PEOPLE` | 1,840 + 1,057 | 9 | Who is who (Barry owner, Victor CEO, Priya EA...) -- the people list appears twice | No | **DEDUPE** -- the people list once, ~1,000 total. |
| 5 | `_ACTUALLY_GENERATES_IMAGES` | 1,727 | 9 | "You really do generate images" -- fights the model's text-only instinct | The tool exists; the instinct is real | **SHRINK to ~400**, keep the correction, cut the why. |
| 6 | `_HAS_PERSONALITY` | 1,184 | 9 | "You're allowed a real personality" | Superseded: WHO YOU ARE + VOICE tail now carry the actual personality | **CUT.** It describes permission for a thing that is now present in full. |
| 7 | `_CAN_SEND_FILES` / `_SEES_AND_LEARNS` / `_MY_PICTURES` | 1,148 / 1,018 / 732 | 9 | How files, eyes and pictures work | Each is a tool with a schema description | **SHRINK each to 2 lines** pointing at the tool. |
| 8 | `_REASONS_BEFORE_ANSWERING` | 770 | 9 | Reason before you answer, every time | Thinking is on in code for every turn | **CUT** (likely a no-op) -- unless you want the sentence kept as a creed. |
| 9 | `_WORKS_FOR_OWNER` | 1,472 | 8 | The three ventures and who you work for | No | **KEEP** (it is knowledge, and short). |
| 10 | `_LANGUAGE_IS_JUST_LANGUAGE` | 522 | 9 | Barry swears; none of it is aimed at you | No | **KEEP** (your rule, in your words). |
| 11 | `_NEVER_PUBLISHES` | small | 9 | Nothing goes out without his approval | Yes -- approvals gate in code | KEEP as one line. |

Estimated: 25.5K shared -> ~9-10K. The job block and the HOW I TALK sheet go from <10 % of the base prompt to ~25 %.

## The two bigger masses (separate reviews)
- **Brain facts always-on, 34-55K per seat.** Facts whose source_name does not end `.md` ride every message. A pass to
  find the ones that could become on-demand skills (read when the words match) would halve this for most seats.
  Needs a list per seat with your yes on each.
- **Pins: Vivian 32K (10 pins), Elliot 28.7K, Sophie 18.7K.** Each pin is a doc that rides every message. Worth a look at
  which of Vivian's ten are needed on every turn vs. when the job comes up.
- **Priya's auto-summary: 8.5K always-on** (summary creep, office_health flags it). Trim is one command.

## What changes for them
Nothing about what they know or deliver. Less identical text in front of the model means their own sheet weighs more.
Measured again after, same five prompts, clean threads.

## Not in scope
Taliyah's REGISTER tail and Elliot's end-of-prompt block are yours (his rules); untouched.
