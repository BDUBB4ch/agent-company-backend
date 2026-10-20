# PLAN — The Brain Graph (per-agent associative brain, job-scoped regions)

**Status: PLANNED, NOT APPROVED FOR BUILD. Barry gives the ok phase by phase.**
Designed 2026-08-23/24 in conversation. Goal is SPEED, not smarter models:
speed = fewer tokens arriving per message + known addresses instead of re-reading.
Proof already exists in this build: Elliot's task-scoped prompt (220K → 45K chars,
152s → 57s) and the anchors card (canon 100K unpinned, 21.5K card pinned).
This plan generalizes those two hand-built wins to all nine agents.

## The shape (agreed with Barry)

- **The job picks the region.** Each agent has 3-5 named jobs; each job maps to a
  region = exactly the docs/chunks/pins that job needs. Agent's only decision is
  naming the job (a 5-way classification a 27B does reliably); the harness fetches.
- **The agent you're with files what you hand it.** Drop a doc on Derek →
  Derek reads it ONCE at intake, distills, files, writes the USE WHEN line.
  The conversation already answered "who is this for." If it doesn't fit his seat,
  he says so instead of filing it wrong.
- **The brain links it mechanically.** Shared entities + shared category = edges.
  No model involved. Category grants already share it to every agent with access.
- **Priya is the librarian, on idle.** Duplicates, contradictions, orphans, stale
  routing lines → proposals into the approval queue. Never writes directly.
- **Wiki = the Brain tab.** Same store. Map view is a toggle next to the list, not
  a replacement. One graph, per-agent views (existing private/domain/shared tiers).
- **Distill other people's material, never Barry's.** Third-party (videos, books,
  articles) compiles down to hard points — the thing, what it does, how to do it,
  numbers WITH their conditions. His scripts/canon are verbatim-only, always
  (2026-08-08 rule; anchors card precedent = extraction, never summary).
- **Supersede, never delete.** Raw transcripts/sources stay as on-demand `.md`
  (zero context cost) so distilled points stay auditable.

## Phases, in build order (speed first)

### Phase 1 — Job table + regions (Elliot first)
**STEP 1 BUILT 2026-08-24** (Barry's "yep p.1"): `backend/jobs.py` = the declared
job table + detection (regexes moved verbatim) + `data/jobs.log`; main.py wired;
parity 22/22 (`scripts/test_job_routing.py`); verified live. Step 2 (region specs
consolidated into the table, per-job pins) NOT built — needs his next ok.
Latent miss FIXED same session (Barry: "write should be to elliot") — writ\w*
is a generation word now; recorded as an INTENDED divergence in the battery.
Step 2 candidate from Barry: a `story_write` job ("make him a writer so he can
put the story together") — long-form-story-writing.md already exists on-demand;
the job would pull it + treatment/WIP material deterministically.
The biggest speed win and the working prototype already exists as scattered
if-branches in main.py (mega-write, shot-ask, verbatim gate, brainstorm-vs-write).
- New `backend/jobs.py`: per-agent job definitions — name, triggers, region spec
  (per-JOB pins instead of per-agent pins, categories, chunk refs, tail blocks).
- Region assembled when the JOB changes, not per message — **sticky, so the
  prompt prefix stays byte-stable and the prompt cache holds** (the 65s→11s
  lesson; a per-message region would silently undo it).
- **Always a default region** — never "no region" (the _shot_ask ghost's damage
  was falling through to plain chat).
- **Every routing decision logged** (`[job]` lines). Optional: model also names
  the job; disagreement with the trigger is logged — the instrument that would
  have caught the ghost in a day instead of weeks.
- Rollout: Elliot only. His four branches become the first table entries. All
  other agents keep the current path untouched until his side is measured.
- Payoff: pin-budget pressure mostly disappears (pins become per-job; seedance
  rides only on prompt jobs, anchors only on writing jobs).
- Verify: `prompt eval time` in bonsai server log; region contents per job;
  re-test with Barry's REAL phrasings ("Shots 2 and 3, please").

### Phase 2 — Intake addressing
- Upload while chatting with agent X → intake pass: X reads once, produces
  title, filing category, USE WHEN line, entity links, and (third-party only)
  distilled hard points. Numbers keep their conditions or don't get kept
  (the "40% yield" trap Marcus flagged).
- Wrong-fit rule: agent refuses to file what doesn't belong to its seat.
- Raw source → on-demand `.md`; distilled points → the active fact.
- Files: main.py upload endpoint, memory.py, small intake module.

### Phase 3 — Chunking (sections as retrieval units)
- Generalize the script_index pattern: heading-based sections of large `.md`
  facts become addressable chunks; retrieval serves sections, not whole docs.
- Kills the "named but never injected" failure (31.9K V8 fact vs 20K budget →
  Elliot invented a fence-crash).

### Phase 4 — Graph substrate
- New tables `nodes` / `edges` in brain.db — **additive; facts table untouched;
  fully derived and rebuildable by script** (delete and regenerate, no data loss).
- Edge builders, no LLM: filed-under (category column), sees (existing grant
  logic), mentions (handle/entity roster regex), links (`[[wikilink]]` support
  in fact text), appears-in (entities × script blocks).
- similar-to (embeddings) is DEFERRED — see guardrails.

### Phase 5 — Recall v2: spreading activation
- recall.py gains a graph scorer: entities named in the message light up,
  activation spreads ~2 hops with decay, top results within budget.
- **Inspectable by design**: every injection logs its path ("in because you
  named @Keth and it links to @Keth") — unlike a cosine score.
- Per-agent flag; Elliot first; keyword path stays as the fallback.

### Phase 6 — YouTube / transcript ingestion
- yt-dlp subtitle pull (text-only, no video download); Whisper CPU fallback
  when no subs. Blocked by Offline Mode like search/store tools.
- Output goes through Phase 2 intake like any other drop.
- New dependency (yt-dlp) — flag to Barry at build time.

### Phase 7 — Priya the librarian (ponder)
- Idle-gated (`ideation._active_chat_count == 0`, same as the summarizer),
  heavily throttled. Finds: near-duplicate facts, contradicting rulings,
  orphaned docs (no agent sees it, nothing links it), missing links, stale
  USE WHENs. **Proposals → approval queue only. Never writes to the brain,
  never touches canon.** (2026-08-08: a stronger model than Bonsai authored
  canon unsupervised and it took backups to undo.)

### Phase 8 — Brain Map view (dashboard tab)
**BUILT 2026-08-24 (pulled forward on Barry's ask, v1):** braingraph.py +
/api/brain/graph/{agent_id} + brainmap.js (List/Map toggle, canvas, live
4s-poll diff animation — new facts pop in, links flash, deletions fade).
Verified live in-browser. NOT yet in v1: image nodes (faces/product photos),
region lighting on jobs, click-through wiki panel — the items below stay open.
- Map/List toggle in the Brain view, per-agent. Canvas force layout, no
  framework, no CDN, offline — dashboard house style.
- Nodes sized by char count (context weight VISIBLE — the 220K word-salad
  state would have looked wrong before it read wrong). Image nodes where a
  reference exists (Higgsfield character refs, the 118 product photos in
  data/product-images/); labeled dots otherwise. Hover isolates neighbors.
  Click → wiki panel: doc rendered, backlinks, who sees it, always-on vs
  on-demand, supersede chain. **Last job's region lights up** — the router
  made visible. Read-only in v1.

## Hard guardrails (all paid for already)

1. Canon and Barry's scripts: verbatim only, never distilled, never auto-edited.
2. Regions sticky per job — never per-message (cache stability).
3. Always a default region; every route logged; misroutes visible, not silent.
4. Additive everywhere: new tables/modules, existing recall path stays until an
   agent is explicitly flipped; one agent at a time, Elliot first.
5. All agent-initiated structure changes → approval queue.
6. **No Ollama calls in the retrieval path** — an embedding call via Ollama trips
   `_unload_models()` and kills the Bonsai server (the Taliyah tone-guard bug).
   Embeddings, if ever added, run in-process CPU (onnxruntime — already installed)
   or via llama-embedding.exe (already on disk). Deferred from v1 entirely:
   spreading activation first; add vectors only if measured misses justify it.
7. Measure before/after: office_health.py, bonsai log prefill counts, recall hit
   quality on real asks. No phase ships on "it ran."

## Open questions for Barry (before the relevant phase)

1. Phase 1: keep the optional model-names-the-job second opinion, or regex-only?
2. Phase 6: yt-dlp dependency + online-only ok?
3. Phase 8: any nodes he wants imaged that lack references?
4. Post-v1: embeddings for similar-to edges — only if spreading activation
   measurably misses ("hurt"/"wounds" class). Decision deferred.
