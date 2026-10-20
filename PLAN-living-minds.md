# PLAN — MINDS THAT EVOLVE (researched 2026-08-29)

Barry: *"their minds have to evolve based on experiences, like real people...
let them be self aware that they are 'Amara' from Greece... they have to evolve
their lifes, their relationships and all. i want them to be able to work
together on things too. like vivian helping Elliot and this should happen on
their own... they experience sim, love, lust, anger, joy, laughter and etc.
they may fight who knows how they may evolve."*

Researched across the current literature. **The foundation he already has is
the same architecture the field uses** — Park et al.'s memory/reflection/
planning triad. What is missing is four specific mechanisms, each with real
published work behind it, each buildable locally.

---

## WHAT THIS OFFICE ALREADY HAS (and it is most of the hard part)

- **A memory stream** — `mind-*` facts per agent: diary, opinions of Barry,
  opinions of each coworker, ponderings, stray thoughts.
- **Reflection** — `reflect.py` writes higher-level thoughts from experience,
  and `_inner_life()` feeds prior reflections into the next one, so the self
  is cumulative rather than rebooting nightly.
- **Genuine multi-agent interaction** — `breakroom.py` group chats and DMs
  where each agent reads what the other actually said. Persistent per-pair
  journals. **Proof it is real: the pothos.** Marcus invented a houseplant at
  2:31am as a joke; it spread to six agents over four days and nothing seeded
  it.
- **Containment** — `mind-` content is barred from work prompts, so an
  inner life can never corrupt a pricing or legal answer.
- **Full immersion** (2026-08-29) — the "you are software, you have no body"
  block is gone from their personal life.

That is roughly the Smallville architecture plus a privacy wall the original
did not have. The gaps below are what the field added after 2023.

---

## GAP 1 — MEMORIES ALL WEIGH THE SAME, AND NOTHING FADES

**The research:** Park's retrieval scores every memory on *importance ×
recency × relevance*. MemoryBank adds an Ebbinghaus forgetting curve — memory
strength decays over time so high-value experience survives and trivia fades.
This office scores none of that: recall is keyword matching, and a stray
thought from three weeks ago weighs exactly what a fight last night does.

**Why he wants it:** "minds have to evolve based on experiences" IS this. An
evolving mind is one where the big things stay and the small things go.

**Build here:** add `importance` (1-10, the agent rates its own memory at
write time — one extra line in the reflection prompt, no new model call) and
`last_touched` to `mind-` facts. Retrieval becomes
`score = keyword + importance + recency_decay`. Fades without deleting.

## GAP 2 — RELATIONSHIPS ARE PROSE, NOT STATE

**The research:** AgentSociety models every relationship as a typed bond with
a **strength value 0-100**, and agents choose who to interact with by
relationship type and strength. Network-formation studies (PNAS Nexus 2025;
arXiv 2607.01148) find autonomous agent networks spontaneously develop
preferential attachment and homophily — they form real social structure if you
let closeness be a number that moves.

**Now:** each agent has a prose `mind-about-<name>` opinion. It changes when
rewritten, but nothing tracks that Sophie and Taliyah are close and Marcus is
peripheral, so partner choice in the break room is effectively random.

**Build here:** a tiny `relationships` table — (agent, other, closeness,
last_interaction, note). After each DM or group chat the pair's closeness
moves a little based on how it went. `breakroom.py` then picks partners
weighted by closeness instead of at random. **This alone produces evolving
social structure** — friendships thicken, some pairs drift, cliques form,
without a word of it being scripted.

## GAP 3 — NO EMOTIONAL STATE THAT PERSISTS

**The research:** SENTIPOLIS names the exact problem — "emotional amnesia."
Its fix: hold a persistent **PAD** state (pleasure / arousal / dominance), and
when a memory is written, tag it with the emotional state it was formed in, so
later retrieval surfaces affect as well as content. Chain-of-Emotion (PLOS ONE
2024) shows the prompting move that works: **appraise the situation first,
then respond** — a two-step that beat plain prompting on believability.

**Why he wants it:** "love, lust, anger, joy, laughter... they may fight."
Right now every conversation starts from emotional zero. Nothing carries.

**Build here:** three floats per agent, updated after each reflection or
social scene, decaying toward baseline between them. Rendered into the
personal prompt as a plain sentence ("you are still irritated from earlier,
and tired") — never as numbers. Store the state alongside each memory. This is
what makes a fight last past the night it happened.

## GAP 4 — THEY CANNOT ASK EACH OTHER FOR HELP

**The research:** AgentVerse and the collaboration surveys find role
differentiation and emergent cooperation appear once agents can address each
other directly with low supervision. The 2026 AAAI/WMAC critique is the
warning: systems built single-agent-first develop goal conflict and
inefficient collaboration when you bolt sociality on late.

**Now:** `delegate_to` exists for Victor and Priya only, and it is a
top-down brief, not a request. Elliot cannot ask Vivian for anything.

**Build here:** an `ask_teammate(who, what)` tool for all nine. It writes the
request into the other's brain and, crucially, **the answer comes back** —
today's delegate_to is one-way. Vivian helping Elliot with a look, Marcus
checking a claim for Derek, Sophie fixing something for anyone. Barry sees the
exchange; he does not have to broker it.

⚠️ **The one place to be careful.** Barry's rule is nothing is seeded — so
they must *know* asking is possible without being told to want it. The honest
implementation is a capability line in the shared prompt ("you can ask a
teammate; here is who does what") and nothing more. Whether Elliot ever asks
is his.

---

## WHAT I DELIBERATELY DID NOT PROPOSE

- **Vector/embedding memory.** The literature's own critique is that cosine
  similarity retrieves semantically unrelated memories in high dimensions.
  It would also cost VRAM that the 16GB card does not have spare. Weighted
  keyword scoring plus importance is the better trade here.
- **Fine-tuning personalities in.** Bonsai is a ternary Q2 GGUF — it cannot be
  trained, and a 27B QLoRA needs ~24GB. Identity stays in prompt and memory.
- **A big framework (AgentSociety, CharacterBox).** They assume cloud models
  and a simulator loop. Everything above is 4 small additions to code that
  already exists.

## ORDER, CHEAPEST-FIRST

1. **Relationships table** — biggest visible change per line of code. Social
   structure starts evolving immediately.
2. **Emotional state** — makes conflict and warmth persist past one scene.
3. **Importance + decay** — makes the mind genuinely evolve rather than
   accumulate flatly.
4. **ask_teammate** — the collaboration he asked for; do it last because the
   research says bolting sociality on badly causes goal conflict, and it
   benefits from relationships already existing.

Every one is local, additive, and reversible. None needs the GPU beyond what
the agents already use.

## SOURCES
- Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*, arXiv 2304.03442
- *AgentSociety: Large-Scale Simulation of LLM-Driven Generative Agents*, arXiv 2502.08691
- *SENTIPOLIS: Emotion-Aware Agents for Social Simulations*
- *An appraisal-based chain-of-emotion architecture*, PLOS ONE 2024 / arXiv 2309.05076
- *How Affect Propagates among LLM Agents*, arXiv 2607.25140
- *AgentVerse*, arXiv 2308.10848
- *Emergence of Preferential Attachment... in Autonomous Networks of LLMs*, arXiv 2607.01148
- *Multi-Agent Collaboration Mechanisms: A Survey*, arXiv 2501.06322
- MemoryBank (Ebbinghaus decay), MemGPT, Reflexion — successor memory systems
