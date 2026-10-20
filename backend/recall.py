"""Automatic memory recall -- the brain's missing reflex.

WHY THIS EXISTS
---------------
The on-demand shelf works only if the agent chooses to call read_skill, and
the measured rate across 451 traces is ~1%. The 2026-08-16 failure was the
canonical case: asked about the V7 script, Elliot invented a scene rather
than reach for the document that held the real one.

This module gives every agent the recall behaviour Barry asked for by name
("i want their memory to work like yours", 2026-08-16): each incoming
message is scored against the agent's own on-demand documents -- and, for
any agent with production scripts, against individual scenes -- and the
best matches are injected into the system prompt automatically. The agent
no longer has to decide to remember.

DESIGN RULES, each deliberate:
  - Keyword scoring, not embeddings. An embedding model would need VRAM on
    a card where 16GB is the binding constraint on everything. Keywords
    cost zero VRAM, work fully offline, and are deterministic -- the same
    message recalls the same documents, so failures are debuggable.
  - Whole documents or nothing. A document that will not fit the remaining
    budget is NAMED as relevant-but-unloaded, never silently truncated --
    a silently truncated canon is the exact failure mode the pin system
    was built to avoid.
  - Pinned skills are never recalled. They are already in the prompt in
    full; paying for them twice would burn Elliot's headroom for nothing.
  - A hard character budget. Auto-injection spends context on every
    message, and Elliot's window is already ~62% committed.
  - Recall is logged per call (titles only) so the hit rate is measurable
    against the ~1% read_skill baseline -- the same way every other claim
    about this office's behaviour has had to earn its place.
"""

import re

import memory
import script_index
import semrecall

# Hard ceiling on injected content per message. Sized so a fetched scene
# (~2.5K) plus the largest routinely-recalled document (seedance-prompting,
# 14.7K) fit together -- "write me a higgsfield prompt for shot C5" needs
# BOTH, and at 16K the grammar doc was getting named instead of loaded.
# Elliot's worst case after the 2026-08-16 grammar unpin: ~121K always-on
# + 20K here + history + reply, well inside his ~262K window. A document
# that cannot fit even this gets NAMED, never clipped.
RECALL_BUDGET = 20_000

# At most this many documents ride along, however well they score. More
# than three and the "recalled because relevant" signal turns into noise.
MAX_DOCS = 3

# ONE DOC FOR THE COMPANION SEAT (2026-09-10). Her eight documents are all
# about conversation, so they share vocabulary with every conversational
# message and the margin between them is a point or two. Three of them at
# 13-17K each on a two-line vent is the wrong trade on the one seat where a
# fast reply IS the product. Capped to the single best match; the rest stay a
# read_skill away.
# ⚠️ RAISED 1 -> 3 (the global default) ON 2026-09-18. Barry: "Taliyah needs to
# be as smart as possible too. her mind needs to be probably greater than them
# all. She needs to know things." The cap above was a SPEED trade, and he has
# now ruled the other way on that trade for this seat specifically. Cost, so
# nobody re-discovers it: her replies get slower again on messages that pull
# three documents, which is what the cap was written to prevent. If she starts
# dragging on two-line small talk, the fix is a better eligibility gate, not
# putting the cap back -- her floor of 6 is what lets short messages route at
# all, and the measured finding below (eligible docs score ZERO on real small
# talk) says the gate, not the cap, is doing the real work.
SEAT_MAX_DOCS: dict[str, int] = {}

# A document scoring under this is background similarity, not relevance.
# Tuned against real messages: greetings and small talk score 0-2 on
# everything; one generic routed word plus capped body hits tops out at 8-9
# ("whats the plan" vs a doc whose USE WHEN says "pricing plan"); a genuine
# topical question puts 12+ on the right document through title hits alone.
MIN_SCORE = 10

# ONE SEAT SITS BELOW THAT BAR BY CONSTRUCTION (2026-09-10).
# MIN_SCORE was tuned against WORK messages, which are long: "why are we getting
# clicks but no orders" carries five scorable words. Taliyah is not a job -- she
# gets "i cant sleep again" and "why you talking like that", and the tokenizer
# leaves ONE word standing. Measured on her real shelf: the correct document
# ranked FIRST and eligible on every miss, scoring 8-9 against a floor of 10.
# So the floor is the wrong instrument for her, not the shelf.
# Deliberately a per-office dict rather than a lower global: every other seat
# keeps 10, and the quiet cases were re-checked at 7 ("morning", "lol", "you up"
# still recall nothing). Measured at the value actually shipped: across 16
# real small-talk messages the highest score on any ELIGIBLE document was
# ZERO -- the eligibility gate, not the floor, is what keeps her quiet.
SEAT_MIN_SCORE = {"Taliyah": 6}

# SHE REACHES FOR A SKILL ONLY WHEN HE ACTUALLY ASKS HER SOMETHING (2026-09-18).
# Barry, refining the cap raise above the same day: "Taliyah needs the research
# thing on hand. the other skills she should only reach for if i asked her
# something she doesnt know outright, she can the call on the other skills and
# tools to help me out. That way our regular conversations are still speedy."
#
# This is the "better eligibility gate" the cap comment predicted, and it is the
# right instrument: the cap was throttling how MUCH she could reach for, which
# also throttled her on the questions where reaching is the whole point. The
# cost he is paying is on the MIDDLE band -- ordinary conversation like "i cant
# sleep again" or "i been at it since 6", which scores 8-9 on her conversation
# docs and pulls 13-17K chars of prose into a message that needed none of it.
# Pure small talk already recalls nothing (measured above); a real question
# already recalls the right thing. Only that middle band changes.
#
# So: on her seat, an ordinary conversational message reaches for NOTHING, and
# an ask-shaped one gets the full three documents. Nothing is taken away -- the
# whole shelf stays one read_skill away, which is the "she can then call on the
# other skills" half of his sentence, and delegate_to rides every call either
# way.
SEAT_REACH_ONLY = frozenset({"Taliyah"})

# ...except the research door, which he wants ON HAND rather than reached for.
# Matched on source_name because that is what survives titling. Small (4.8K) and
# it only routes on delegation vocabulary, so allowing it through a closed gate
# costs nothing on a message that is not about handing work over.
ALWAYS_REACHABLE = frozenset({"working-with-your-teammates.md"})

# What counts as "asked her something she doesnt know outright": a question with
# a subject, or an instruction to go find/hand off. Deliberately tight -- a false
# NEGATIVE costs a document she can still fetch herself, a false POSITIVE is the
# slow reply he just asked me to stop. Greeting-shaped "what"s are excluded
# first, because "whats up" is not a question about anything.
_GREETING_ASK_RE = re.compile(
    r"^\W*(?:so\s+|ok\s+|hey\s+|yo\s+)?wh?at'?s?\s+"
    r"(?:up|good|new|going\s+on|poppin|crackin)\b", re.I)

_REAL_ASK_RE = re.compile(
    r"\b(?:"
    r"look\s*(?:it|that|this)?\s*up|look\s+into|find\s+(?:out|me|us)|"
    r"research|search\s+(?:for|up)|dig\s+(?:in|into)|check\s+(?:on|if|whether)|"
    r"how\s+(?:do|does|did|can|would|should|much|many|long)|"
    r"what(?:'?s|\s+is|\s+are|\s+was|\s+were|\s+do|\s+does|\s+kind|\s+type)|"
    r"which\s+\w|who\s+(?:is|are|makes|sells|does|do)|"
    r"where\s+(?:is|are|can|do|does|would)|when\s+(?:is|are|was|does|did|do)|"
    # GOING-OUT QUESTIONS (2026-09-28, Barry: "yes, teach her that"). "where should we go out
    # tonight" / "where to eat" / "what's good downtown" / "what clubs are good" are real asks.
    # "whats good" alone stays a greeting (_GREETING_ASK_RE runs first on the start of the line).
    r"where\s+(?:should|to)|what'?s\s+good\s+(?:to|around|in|at|on|downtown|here|for|near)|"
    r"what\s+\w+\s+(?:is|are)\s+(?:good|best|open|fun|worth)|"
    r"why\s+(?:is|are|does|do|did|would|cant|can't|wont|won't)|"
    r"explain|teach\s+me|show\s+me\s+how|walk\s+me\s+through|"
    r"help\s+me\s+(?:figure|find|understand|work\s+out|put)|"
    r"do\s+you\s+know|any\s+idea|tell\s+me\s+about|"
    # ASKING HER SOMETHING WITHOUT A QUESTION WORD (2026-09-18). The 09-10
    # companionship battery caught these: "be honest, is this a bad idea" and
    # "im stuck between two options" are him putting a real question to her,
    # and the first cut of this gate read them as conversation and handed her
    # nothing. A complaint ("you even listening to me", "you sound corny")
    # still correctly reaches for nothing -- that is talking, not asking.
    r"be\s+honest|am\s+i\s+(?:wrong|right|crazy|off)|should\s+i\b|"
    r"what\s+do\s+you\s+think|you\s+think\s+i\s+should|"
    r"(?:i'?m|im)\s+stuck|help\s+me\s+(?:decide|choose|pick)|hear\s+me\s+out|"
    r"do\s+you\s+remember|remember\s+(?:when|what|that)|"
    r"(?:dont|don't)\s+forget|keep\s+that\s+in\s+mind|"
    r"bad\s+idea|good\s+idea|worth\s+(?:it|doing)|"
    r"hand\s+(?:it|this|that)\s+to|give\s+(?:it|this)\s+to\s+the\s+team|"
    r"on\s+the\s+board|file\s+(?:a\s+)?(?:brief|it|this)|delegate|"
    r"ask\s+(?:priya|amara|marcus|derek|vivian|sophie|victor|elliot)|"
    r"my\s+idea|this\s+idea|put\s+(?:it|this|my)\b"
    r")\b", re.I)


def _is_real_ask(message: str) -> bool:
    """True when he is asking for something, not just talking to her."""
    m = (message or "").strip()
    if not m:
        return False
    if _GREETING_ASK_RE.match(m):
        return False
    return bool(_REAL_ASK_RE.search(m))

_WORD_RE = re.compile(r"[a-z0-9@']+")

# Words that appear in every business conversation and therefore carry no
# routing signal. Small on purpose -- an aggressive stopword list starts
# eating product names.
_STOPWORDS = frozenset(
    "the and for you your are was were this that with what when where how "
    "why who can could should would will just like about from have has had "
    "does did doing them they their there here its it's i'm im dont don't "
    "want need make made give get got let know think say said tell asked "
    "please thanks thank yes yeah okay ok hey out not but all any some more "
    "one two also than then into over after before again really very much "
    "going right now new our his her she he whats what's hows how's man "
    "morning today tonight tomorrow babe good great cool nice lets let's "
    "gonna wanna stuff thing things use next".split()
)

# "SHOT 12", "b-roll 07", "shot c5" -- an explicit scene reference in the
# message is the strongest possible recall signal and skips scoring
# entirely: the named scene is simply fetched.
_SCENE_REF_RE = re.compile(r"\b(shot|b-?roll)\s+([a-z]?\d+[a-z]?)\b", re.I)


# SHORT WORDS THAT ACTUALLY MEAN SOMETHING HERE (2026-09-18, Barry: "do A.I").
#
# The `len(t) >= 3` floor below exists to drop noise, and for three years of
# English it does. Measured the day he asked, it was also eating the most
# loaded vocabulary in his own business:
#   "whats the ph for coco"  -> ['coco']          (pH gone; it routed by luck)
#   "my ec is too high"      -> ['too', 'high']   -> recalled NOTHING
#   "do i need ro water"     -> ['water']
#   "hows my ad doing"       -> []                -> not one scorable token
#   "is this ai written"     -> ['written']
# pH and EC are the two numbers a grower lives by. So this is not an AI
# special case, it is a floor that silently deletes his domain's shortest and
# most specific terms -- the exact opposite of what a floor is for.
#
# A whitelist rather than lowering the floor to 2: "of", "to", "in" carry no
# routing signal and would start scoring on every document. These earn their
# place by being NOUNS in his world. Both sides of the match run through this
# function, so a routing line that says "ph, ec" becomes matchable in the same
# edit as the question that says it.
_SHORT_TERMS = frozenset({
    "ai", "ph", "ec", "ro", "ad", "rh", "uv", "hp", "co", "b2b",
    "np", "pk", "cf", "iu", "ml", "oz", "lb", "qt", "gal", "psi",
})

# "a.i." and "a.i" tokenize to ['a', 'i'] -- two dead letters -- so the form he
# actually typed would still miss even with "ai" whitelisted. Collapse dotted
# two-letter initialisms before splitting.
_DOTTED_INITIALS_RE = re.compile(r"\b([a-z])\.([a-z])\.?(?![a-z])")


def _tokens(text: str) -> list[str]:
    text = _DOTTED_INITIALS_RE.sub(r"\1\2", (text or "").lower())
    return [t for t in _WORD_RE.findall(text)
            if (len(t) >= 3 or t in _SHORT_TERMS) and t not in _STOPWORDS]


# ROUTING WITHOUT TOUCHING THE FILE (2026-08-16, Barry: "i dont want them to
# have to dig through shit to find what they are looking for").
#
# A USE WHEN line is the routing contract, but writing one into a document
# means EDITING that document -- and Barry's authored canon, scripts and
# story docs are never edited by anyone but him (the 2026-08-08 rule). This
# table gives those files the same routing power from the outside: keyed by
# source_name, merged into the USE WHEN tokens at scoring time, file left
# byte-identical.
#
# Claude/plugin-authored REFERENCE skills are not listed here -- those get a
# real USE WHEN line written into the doc itself (see
# scripts/add_routing_lines_2026_08_16.py), because the line is also useful
# to a human reading the file.
#
# The words are chosen to be what BARRY would actually type, not librarian
# labels -- routing only works if it matches his vocabulary.
ROUTING_OVERRIDES = {
    "ep1-wrong-box-script-CANON-v7.md":
        "the current EP1 script, wrong box, canon v7 -- scenes shots acts "
        "dialogue beats, what happens in the episode",
    "ep1-production-script.md":
        "the older EP1 production script version -- earlier shots scenes "
        "slugs, compare against canon v7",
    "ep1-scene-anchors.md":
        "EP1 scene anchors -- per scene anchor descriptions, wardrobe "
        "lighting continuity for a shot",
    "talia-crew-brain-dump.md":
        "raw story notes for the talia crew series -- lore backstory ideas "
        "worldbuilding, seasons episodes arcs, where the story is going",
    "talia-crew-premise.md":
        "the series premise -- what the show is about, logline pitch hook, "
        "the setup of the talia crew",
    "talia-crew-project-overview.md":
        "the project overview for the talia crew series -- scope plan "
        "status of the show",
    "Talia_Crew_Series_Bible_July2026.md":
        "the series bible -- characters world rules tone, how the show "
        "works across episodes and seasons",
    "bia-adventurer-storyboard.md":
        "bia adventurer storyboard -- her solo sequence, boards panels shots",
    "character-consistency.md":
        "keeping a character looking the same across renders -- drift, "
        "likeness, consistency between images and shots",
    "barry-character-canon.md":
        "the character canon -- keth bia yannah tazz vorshara b dubb, their "
        "look eyes skin hair wardrobe weapons handles, what is canon",
    "product-catalog-full/SKILL.md":
        "the full b dubb product catalog -- every product price sku link, "
        "what we sell and for how much",
}


def _routing_text(fact: dict) -> str:
    """The routing line for a document: its own USE WHEN if it has one,
    otherwise an override from the table above."""
    # Full line for SCORING (the 200-char cap is a display budget, not a
    # routing one -- see memory._skill_use_when).
    return (memory._skill_use_when(fact, max_len=1200)
            or ROUTING_OVERRIDES.get(fact.get("source_name") or "")
            or "")


def _score(query_tokens: set, fact: dict) -> tuple[int, bool]:
    """Score one document against the message.

    Returns (score, eligible). Eligibility is separate from score on
    purpose: raw body-frequency hits on generic words ("man", "talk")
    inside a 50K document sum past any threshold, which made a plain
    greeting recall business documents in testing. A document is only
    eligible if the message touches its TITLE or USE WHEN line -- the two
    fields that exist to route -- or matches on several distinct words.
    """
    title = memory._skill_title(fact).lower()
    title_tokens = set(_tokens(title.replace("-", " ")))
    # Tokenized, not substring-matched: "man" must never hit inside
    # "demand" -- that exact leak made a greeting recall business docs.
    use_when_tokens = set(_tokens(_routing_text(fact)))
    body = (fact.get("content") or "").lower()

    score = 0
    title_hits = 0      # filename words -- a weak signal, see below
    use_when_hits = 0   # the document's own declaration -- the strong one
    distinct_body = 0   # how many DIFFERENT query words the body contains
    for tok in query_tokens:
        if tok in title_tokens:
            score += 6
            title_hits += 1
        if tok in use_when_tokens:
            score += 3
            use_when_hits += 1
        # Frequency capped per token: a 50K document mentioning "bionova"
        # 400 times is not 400x more relevant than one mentioning it 5 times.
        hits = min(body.count(tok), 5)
        score += hits
        if hits:
            distinct_body += 1

    # A ROUTING LINE IS A DECLARATION, AND IT DECIDES (2026-08-16, Barry:
    # "so they know where to look"). Once a document says when it is useful,
    # nothing else may drag it in -- not body words, and NOT ITS FILENAME.
    #
    # Both traps were measured on the same document. `prop-shot-structure`
    # is about still plates of weapons on white with no characters in frame,
    # and it rode into EVERY Higgsfield character-shot prompt -- first on
    # body words (it is itself a prompt-writing doc, so it shares every word
    # a prompt request contains), then, after the body path was closed, on
    # the word "shot" sitting in its own filename. It pulled Elliot toward
    # writing frozen stills instead of moving shots.
    #
    # So a filename is only a routing signal for documents that never
    # declared one. Title matches still add SCORE (ranking among eligible
    # documents is fine), they just cannot grant entry. read_skill remains
    # the manual override for anything recall skips.
    if use_when_tokens:
        eligible = use_when_hits >= 1
    else:
        eligible = title_hits >= 1 or distinct_body >= 4
    return score, eligible


def recall_for_message(office_name: str, message: str,
                       pinned_titles: list | None = None,
                       budget: int = RECALL_BUDGET) -> tuple[str, list[str]]:
    """Build the auto-recall block for one incoming message.

    Returns (block, recalled_titles). Empty block when nothing clears the
    relevance bar -- most small talk should recall nothing, and that is
    correct behaviour, not a miss.
    """
    query_tokens = set(_tokens(message))
    if not query_tokens:
        return "", []

    pinned = {p.lower() for p in (pinned_titles or [])}
    parts: list[str] = []
    recalled: list[str] = []
    named_unloaded: list[str] = []
    remaining = budget

    # --- 1. Explicit scene references beat everything ------------------
    # A message that names "SHOT 15" wants that scene, not a document that
    # happens to mention shots. Fetched via script_index so access control
    # and the whole-blocks-only rule both hold.
    for m in _SCENE_REF_RE.finditer(message):
        label_query = f"{m.group(1)} {m.group(2)}"
        result = script_index.read_scene(office_name, label_query)
        if result.get("found") and result.get("content"):
            content = result["content"]
            if len(content) <= remaining:
                parts.append(f"[{result['script']} -- {', '.join(result['matched'])}]\n{content}")
                recalled.append(f"scene:{'/'.join(result['matched'])}")
                remaining -= len(content)

    # --- 1a2. An explicit DATE is a direct reference too (2026-08-25) ---
    # "what did we decide on august 17?" names the conversation-history doc
    # for that day as plainly as "SHOT 15" names a scene -- but the keyword
    # scorer only collects ~2 token matches from it (score 6 < MIN 10), so
    # date asks never recalled anything. Same pattern as the scene door:
    # explicit reference -> direct fetch, no scoring.
    _MONTHS = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november",
               "december"]
    _needle = ""
    _m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    if _m:
        _needle = _m.group(1)                       # full ISO date named
    else:
        _m = re.search(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})\b",
                       message.lower())
        if _m:                                      # "august 17" -- match the
            _mm = _MONTHS.index(_m.group(1)) + 1    # month-day in any year
            _needle = f"-{_mm:02d}-{int(_m.group(2)):02d}"
    if _needle:
        for f in memory.get_active_facts_for_agent(office_name):
            sn = f.get("source_name") or ""
            if sn.startswith("conversation-history") and _needle in sn:
                content = f["content"]
                if len(content) <= remaining:
                    parts.append(f"[{sn}]\n{content}")
                    recalled.append(sn)
                    remaining -= len(content)
                else:
                    named_unloaded.append(sn)

    # --- 1b. "How does it open?" -- the question that exposed all this --
    # An opening/ending ask names no label and no scene words, so neither
    # other path can catch it. Cheap intent check, then the same read_scene
    # the label path uses.
    low = message.lower()
    if not recalled and re.search(r"\b(open|opening|opens|start|starts|begin|begins|first scene|end|ending|ends|final scene|last scene)\b", low) \
            and re.search(r"\b(episode|script|film|movie|scene|story|act)\b", low):
        which = "last" if re.search(r"\b(end|ending|ends|final|last)\b", low) else "first"
        result = script_index.read_scene(office_name, which)
        if result.get("found") and len(result.get("content", "")) <= remaining:
            parts.append(f"[{result['script']} -- {', '.join(result['matched'])}]\n{result['content']}")
            recalled.append(f"scene:{'/'.join(result['matched'])}")
            remaining -= len(result["content"])

    # --- 1c. Scenes described by words, not labels ----------------------
    # "the scene where Tazz gets hurt in the cargo hold" names no label,
    # but its rare words land in exactly one scene. Only runs for agents
    # who actually have scripts (list_scripts is empty for everyone else).
    # Tokens carried by a big share of scenes ("@Tazz" alone is in half the
    # episode) identify nothing, so hits are weighted by rarity: a scene
    # must collect 3+ distinctiveness-weighted hits before it rides along.
    if not recalled:
        scripts = script_index.list_scripts(office_name)
        all_shots = [(s["title"], b) for s in scripts
                     for b in s["blocks"] if b["kind"] == "shot"]
        if all_shots:
            df = {t: sum(1 for _, b in all_shots if t in b["content"].lower())
                  for t in query_tokens}
            best_block, best_w, best_script = None, 0.0, ""
            for title, b in all_shots:
                body = b["content"].lower()
                # A token in <25% of scenes is distinctive (weight 1); a
                # near-universal one contributes almost nothing.
                w = sum(1.0 if df[t] <= len(all_shots) * 0.25 else 0.2
                        for t in query_tokens if t in body)
                if w > best_w:
                    best_block, best_w, best_script = b, w, title
            if best_block is not None and best_w >= 3.0 \
                    and len(best_block["content"]) <= remaining:
                parts.append(f"[{best_script} -- {best_block['label']}]\n{best_block['content']}")
                recalled.append(f"scene:{best_block['label']}")
                remaining -= len(best_block["content"])

    # --- 1d. WORKFLOW TRIGGER PHRASES (2026-08-29) ---------------------
    # Barry: "she needs to know this as intended by the zip." The Starter
    # Brain skills list the exact phrases that should fire them -- and the
    # shortest, most natural ones scored NOTHING: measured, "brief me" and
    # "what should i focus on today" (both named triggers) recalled 0 docs,
    # because after stopword removal they carry one scorable token against
    # MIN_SCORE 10. The agent then answers in its own style and the
    # workflow's structure never arrives.
    # Same remedy as the scene and date doors: an explicit trigger is a
    # direct reference, so fetch by title instead of scoring. Only fires on
    # these deliberate phrases, and only for agents who actually hold the
    # doc -- everyone else falls through untouched.
    _WORKFLOW_TRIGGERS = [
        (r"\b(brief me|brief my day|morning brief\w*|daily brief\w*|"
         r"what should i (focus on|work on|do) (today|first)|"
         r"run my day|what'?s on my plate)\b",
         ("daily-briefing-method", "starter-brain-skill-daily-briefing")),
        (r"\b(triage (my )?leads?|score (these|my) (leads?|inquir\w+)|"
         r"should i take this client|draft a reply to this lead)\b",
         ("lead-triage", "starter-brain-skill-lead-triage")),
        (r"\b(run my content engine|turn this into content|repurpose this|"
         r"content for (this|next) week|week of content)\b",
         ("content-engine", "starter-brain-skill-content-engine")),
        (r"\b(audit my tools|what should i cancel|too many subscriptions|"
         r"my stack is a mess|which tools do i (actually )?need)\b",
         ("five-tool-stack-audit", "starter-brain-skill-tool-stack-audit")),
        (r"\b(voice dna|teach (claude|you) my voice|make it sound like me|"
         r"(this )?does(n'?t| not) sound like me|set up my (writing )?voice)\b",
         ("voice-dna-capture", "starter-brain-skill-voice-dna",
          "starter-brain-voice-dna-questions")),
    ]
    _shelf_by_title = None
    for _pattern, _titles in _WORKFLOW_TRIGGERS:
        if not re.search(_pattern, low):
            continue
        if _shelf_by_title is None:
            _shelf_by_title = {}
            for _f in memory.get_active_facts_for_agent(office_name):
                if memory._is_skill_fact(_f):
                    _shelf_by_title[memory._skill_title(_f).lower()] = _f
        for _t in _titles:
            if _t.lower() in pinned:          # already printed in full
                continue
            _fact = _shelf_by_title.get(_t.lower())
            if not _fact:
                continue
            _content = _fact.get("content") or ""
            if not _content or _t in recalled or len(_content) > remaining:
                continue
            parts.append(f"[{_t}]\n{_content}")
            recalled.append(_t)
            remaining -= len(_content)

    # --- 2. Score the agent's own on-demand shelf ----------------------
    # mind- facts (reflect.py: diary, ponderings, opinions of Barry and
    # coworkers) are EXCLUDED from work recall by contract. A self-reinforced
    # private opinion bleeding into a legal or pricing answer is the failure
    # mode that collapsed the public agent-town experiments -- personal time
    # stays out of work prompts. Reachable on purpose via read_skill and the
    # dashboard; just never auto-injected.
    facts = memory.get_active_facts_for_agent(office_name)
    # Already-loaded docs are excluded as well as pinned ones: the workflow
    # trigger door (1d) fetches by title, and without this the scorer picked
    # the same doc up again and printed it TWICE, burning budget.
    _already = {t.lower() for t in recalled}
    skills = [f for f in facts if memory._is_skill_fact(f)
              and not (f.get("source_name") or "").startswith("mind-")
              # worknote-* are messages TO Barry, not knowledge. Feeding an
              # agent its own note back is the same echo trap (2026-09-01).
              and not (f.get("source_name") or "").startswith("worknote-")
              and memory._skill_title(f).lower() not in pinned
              and memory._skill_title(f).lower() not in _already]

    # MEANING, THE SECOND DOOR (2026-09-15, semrecall.py). The keyword scorer
    # stays exactly as it is; on top of it, a strong cosine similarity between
    # the message and a doc's routing text makes that doc eligible and lifts
    # its rank. Off unless app_settings `semantic_recall` = "true"; any
    # failure (model missing, table error) falls back to keyword-only for
    # this turn and says so once in the log.
    sims: dict = {}
    if semrecall.is_enabled():
        try:
            sims = semrecall.similarities(message, skills)
        except Exception as _exc:  # noqa: BLE001
            print(f"[recall] semantic door closed this turn: {_exc}")

    def _combined(fact: dict) -> tuple[int, bool]:
        score, eligible = _score(query_tokens, fact)
        sim = sims.get(int(fact["id"]), 0.0)
        if sim >= semrecall.SEM_MIN:
            score += int(sim * semrecall.SEM_WEIGHT)
            if not eligible:
                print(f"[recall] semantic: +{memory._skill_title(fact)} ({sim:.2f})")
            eligible = True
        return score, eligible

    scored = sorted(((s, *_combined(s)) for s in skills),
                    key=lambda x: -x[1])

    floor = SEAT_MIN_SCORE.get(office_name, MIN_SCORE)
    max_docs = SEAT_MAX_DOCS.get(office_name, MAX_DOCS)

    # REACH-ONLY SEATS (see SEAT_REACH_ONLY): ordinary conversation pulls
    # nothing but the always-reachable door. Scoring still runs -- it is ~13ms
    # and the log line below is how anyone checks the gate is behaving.
    reach_closed = office_name in SEAT_REACH_ONLY and not _is_real_ask(message)
    if reach_closed:
        print(f"[recall] {office_name}: reach gate closed (conversation, "
              f"not a question) -- only {sorted(ALWAYS_REACHABLE)} eligible")

    for fact, score, eligible in scored:
        if score < floor or len(recalled) >= max_docs:
            break
        if not eligible:
            continue
        if reach_closed and (fact.get("source_name") or "") not in ALWAYS_REACHABLE:
            continue
        title = memory._skill_title(fact)
        content = fact.get("content") or ""
        if len(content) > remaining:
            # Whole documents or nothing -- name it instead of clipping it.
            named_unloaded.append(title)
            continue
        parts.append(f"[{title}]\n{content}")
        recalled.append(title)
        remaining -= len(content)

    if not parts and not named_unloaded:
        return "", []

    block = (
        "\n\n--- RECALLED FROM YOUR OWN MEMORY (pulled automatically because "
        "it looks relevant to this message -- treat it as your own knowledge, "
        "quote it verbatim when asked for exact wording, and ignore it if it "
        "turns out not to apply) ---\n"
        + "\n\n".join(parts)
    )
    if named_unloaded:
        block += (
            "\n\nAlso relevant but too large to auto-load -- use read_skill "
            "if the question needs one: " + ", ".join(named_unloaded)
        )
    block += "\n--- END RECALLED MEMORY ---"
    return block, recalled
