"""
The brain: a local knowledge base every agent reads from before responding,
and writes to when you correct them or teach them something new.

This is NOT the agents' underlying model getting smarter - it's a set of
notes about your business that get pulled into context automatically. See
README.md for the full explanation if you want it.

Runs on SQLite - a single file on your disk, zero setup, zero cost.

Facts are either shared (category e.g. 'business', 'legal', 'brand_voice',
'product' -- injected into every agent's prompt) or private to one agent
(category 'private:<office_name>', e.g. 'private:Legal' -- injected only
into that agent's prompt). This mirrors the Godot office's own per-agent
drop-zone scoping (see agent_ui.gd / memory_store.gd): a file or note
dropped on Victor/CIO's panel arrives here as 'shared', dropped on any
other agent's panel arrives as 'private:<that office_name>'.
"""
import sqlite3
import json
import os
import re
import datetime
from contextlib import contextmanager
from config import DB_PATH, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def unhire_custom_agent(agent_id: str, office_name: str) -> None:
    """Undo a HALF-BUILT hire. Not a fire button -- a rollback.

    Why it exists (2026-09-19): hire_custom_agent INSERTS, and the prompt build
    that follows it can raise. When it did, the row survived the 500 and the
    panel reported failure -- so Barry pressed the button again and got TWO
    Ilnoras, five seconds apart, from two attempts he was told had both failed.
    Called only from the hire endpoint's own failure path, on an agent that has
    never answered a message."""
    with get_db() as conn:
        conn.execute("DELETE FROM custom_agents WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM agent_domains WHERE office_name = ?", (office_name,))
        try:
            conn.execute("DELETE FROM agent_knows WHERE office_name = ?", (office_name,))
        except sqlite3.OperationalError:
            pass  # table predates nothing that matters here
        conn.execute("DELETE FROM facts WHERE category = ?", (f"private:{office_name}",))


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,          -- shared topic (e.g. 'business') or 'private:<office_name>'
            content TEXT NOT NULL,
            source_name TEXT DEFAULT '',      -- original filename, if this came from a dropped file
            status TEXT DEFAULT 'active',    -- 'active' or 'superseded'
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,              -- 'user' or 'agent'
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            action_type TEXT NOT NULL,       -- e.g. 'social_post', 'email', 'product_update'
            content TEXT NOT NULL,
            file_path TEXT DEFAULT '',        -- set for generated files (e.g. Vivian's images)
            status TEXT DEFAULT 'pending',   -- 'pending', 'approved', 'rejected'
            created_at TEXT NOT NULL,
            decided_at TEXT
        );

        CREATE TABLE IF NOT EXISTS custom_agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            office_name TEXT NOT NULL,
            role TEXT NOT NULL,
            job_description TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_domains (
            office_name TEXT NOT NULL,
            domain TEXT NOT NULL,
            PRIMARY KEY (office_name, domain)
        );

        /* Tools granted to a seat at RUNTIME (2026-09-18, Barry: "Sophie needs
           to be able to give tools too"). Tool rosters otherwise live in code
           (main._SEAT_TOOLS), which means a new agent needing one specialised
           tool needed a code edit and a restart -- and "Sophie gives them their
           skills and tools based on their role" cannot be true if the tools half
           is a source file. This table is the additive half: main._tools_for_seat
           appends whatever is granted here on top of the hardcoded roster.
           Never subtracts -- a code-granted tool cannot be revoked from here, so
           this can only ever widen a seat, never quietly break one. */
        CREATE TABLE IF NOT EXISTS agent_tools (
            office_name TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            granted_at  TEXT,
            granted_why TEXT,
            PRIMARY KEY (office_name, tool_name)
        );

        -- WHAT ONE AGENT KNOWS ABOUT HIS WORLD (2026-09-19). One row per piece
        -- he deliberately ticked; no row means the wall is shut, which is the
        -- default for every new agent. See memory.KNOWS_ABOUT.
        CREATE TABLE IF NOT EXISTS agent_knows (
            office_name TEXT NOT NULL,
            area        TEXT NOT NULL,
            granted_at  TEXT,
            why         TEXT,
            PRIMARY KEY (office_name, area)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        # Migration: business_context didn't exist in custom_agents' original
        # schema -- CREATE TABLE IF NOT EXISTS doesn't add columns to an
        # already-existing table, so this runs every startup and is a no-op
        # once the column is actually there (SQLite has no
        # ADD COLUMN IF NOT EXISTS, hence the try/except).
        try:
            conn.execute(
                "ALTER TABLE custom_agents ADD COLUMN business_context INTEGER NOT NULL DEFAULT 1"
            )
        except sqlite3.OperationalError:
            pass

        # Migration (2026-08-15): the dispatch half of the approval queue.
        # Approving used to only flip a status column -- nothing was ever
        # actually sent anywhere, by design, because no send path existed.
        # Barry's call: "on approval it gets written and sent".
        #   destination       -- where it went ('omnisend', ...); set at dispatch
        #   dispatched_at     -- THE IDEMPOTENCY GUARD. Non-null means it has
        #                        already gone out; a retry, a double-click or a
        #                        re-approval must never send the same item twice.
        #   dispatch_status   -- 'sent' | 'failed' | 'skipped'
        #   dispatch_response -- the provider's own reply (campaign id, or the
        #                        error verbatim) so there is an audit trail of
        #                        what actually left the building.
        #   send_at           -- (2026-09-01, the email cadence) when this
        #                        should actually go out; dispatch turns a
        #                        future value into an Omnisend SCHEDULED send
        #                        so a Saturday email leaves on Saturday with
        #                        the PC off. Past/empty = send on approve.
        #   segment_id        -- audience for this item; empty means dispatch
        #                        falls back to the default segment setting,
        #                        and only then to Omnisend's "all subscribers".
        for col, decl in (
            ("destination", "TEXT DEFAULT ''"),
            ("dispatched_at", "TEXT"),
            ("dispatch_status", "TEXT DEFAULT ''"),
            ("dispatch_response", "TEXT DEFAULT ''"),
            ("send_at", "TEXT DEFAULT ''"),
            ("segment_id", "TEXT DEFAULT ''"),
            # 2026-09-26: Vivian's designed email lives in Omnisend as a DRAFT template
            # (email_design.py); the approve click sends a campaign from THIS template,
            # so what he saw on the card is byte-for-byte what goes out.
            ("omnisend_template_id", "TEXT DEFAULT ''"),
        ):
            try:
                conn.execute(f"ALTER TABLE approvals ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass
        # WHICH ROOM A TURN HAPPENED IN (2026-09-15). Personal (home) turns
        # share this table with work turns, so the thread summarizer rolled
        # Amara's home chat into an always-on WORK fact in the summarizer's
        # third-person voice ("Agent... user... need to verify the render").
        # 'work' | 'personal'; the summarizer skips personal turns -- the
        # mind-with-barry journal already keeps those verbatim.
        try:
            conn.execute("ALTER TABLE conversations ADD COLUMN channel TEXT NOT NULL DEFAULT 'work'")
        except sqlite3.OperationalError:
            pass


# Every always-on fact renders as one bullet in brain_context_block(), so an
# untitled wall of prose gives the model nothing to navigate by -- it has to
# read the whole thing to find out whether it's relevant. Owner's instruction
# (2026-08-07): "organize their brains so everything flows better and easily
# accessible... they need to know how to categorize their info." So every fact
# gets a TITLE line, and it's enforced here rather than at the 11 call sites,
# so any future writer inherits it for free.
_TITLE_ALREADY_THERE = ("PRIORITY", "LESSON", "#")


def _ensure_titled(content: str, title: str, source_name: str, category: str) -> str:
    body = (content or "").strip()
    if title:
        # Read-modify-store callers (the mind-with-barry journal, diaries,
        # revisited entries) hand back content that already leads with this
        # title. Prepending again stacked the same header once per store --
        # Amara's journal carried it four times (2026-09-15). If it is
        # already the first line, leave it.
        t = title.strip().upper()
        if body.split("\n", 1)[0].strip() == t:
            return body
        return t + "\n" + body
    first = body.split("\n", 1)[0].strip()
    # Leave anything that already leads with a heading convention alone --
    # the learning loop's PRIORITY/LESSON prefixes and markdown docs are
    # already navigable, and re-titling them would just add noise.
    if first.startswith(_TITLE_ALREADY_THERE):
        return body
    # A short, non-sentence first line is already acting as a title.
    if first and len(first) <= 90 and not first.endswith((".", "!", "?")):
        return body
    # Otherwise derive one from real metadata. Never invent a summary -- a
    # wrong title is worse than a generic one.
    label = category.split(":", 1)[-1].replace("_", " ").upper() if category else "NOTE"
    stem = re.sub(r"\.(md|pdf|docx|xlsx|pptx|txt|zip|png|jpg|jpeg|mp4)$", "",
                  (source_name or "").strip(), flags=re.I)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    made = "%s -- %s (%s)" % (label, stem.upper(), stamp) if stem else "%s -- NOTE (%s)" % (label, stamp)
    return made + "\n" + body


def add_fact(category: str, content: str, source_name: str = "", title: str = ""):
    content = _ensure_titled(content, title, source_name, category)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO facts (category, content, source_name, created_at) VALUES (?, ?, ?, ?)",
            (category, content, source_name, datetime.datetime.now(datetime.UTC).isoformat()),
        )


def supersede_facts(category: str):
    """Mark old facts in a category as superseded rather than deleting them -
    keeps history instead of silently erasing it."""
    with get_db() as conn:
        conn.execute(
            "UPDATE facts SET status = 'superseded' WHERE category = ? AND status = 'active'",
            (category,),
        )


def get_active_facts(category: str = None):
    with get_db() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM facts WHERE status = 'active' AND category = ? ORDER BY created_at",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM facts WHERE status = 'active' ORDER BY category, created_at"
            ).fetchall()
        return [dict(r) for r in rows]


# Reference domain knowledge (the adapted knowledge-work-plugins content --
# see AgentCompanyBackend/knowledge/ and _seed_knowledge.py) lives under
# category 'domain:<name>', separate from 'private:<office_name>' notes
# (which stay genuinely one-agent-only, e.g. a specific contract dropped on
# Marcus's panel). A domain is reusable know-how; access to it is granted
# per office_name via agent_domains, not hardcoded to whoever it was
# originally written for -- so a new hire whose job touches, say, marketing
# can be granted the same campaign-plan/seo-audit/etc. knowledge Derek has,
# without duplicating the underlying facts.
KNOWN_DOMAINS = {"legal", "marketing", "business_ops", "engineering", "horticulture",
                 "operations",   # operations added 2026-09-09 (Priya's shelf; granted to Operations + CIO)
                 "leadership",   # leadership added 2026-09-09 (Victor's shelf; granted to CIO + Operations)
                 "creative",     # creative added 2026-09-10 (Vivian's shelf; granted to Creative)
                 # companionship added 2026-09-10 (Taliyah's shelf, hers alone).
                 # Deliberately its own domain and not shared: she is the one
                 # seat that is NOT a job, and none of this is office work.
                 "companionship",
                 # BASICS, 2026-09-18 -- the floor every new agent stands on,
                 # granted automatically at hire (main._register_hire). Barry:
                 # "math, files creations and reading etc are all part of basic
                 # skills they can get. search tools and the like are basic
                 # tools they can get and whatever other basic skills and tolls
                 # along with their new persona skills."
                 # ⚠️ EVERY DOC IN HERE MUST BE FREE OF HIS BUSINESS AND HIS
                 # DATA -- no venture, no store, no catalog, no numbers of his.
                 # It is the one shelf that reaches an agent built for somebody
                 # else, which is the whole reason it is a domain and not a
                 # bare knowledge: category (that is the shared tier, and the
                 # shared tier is exactly what a non-business hire is walled
                 # off from). Business craft lives in business_ops / commerce /
                 # operations and is granted only when he says the hire is for
                 # the business.
                 "basics",
                 # AUTHORSHIP, 2026-09-18 -- AND IT IS GRANTED TO NOBODY ON
                 # PURPOSE. Barry: "we are not making a new agent, we are just
                 # finding the skills." A domain with no row in agent_domains
                 # is a shelf that EXISTS and reaches no one, which is exactly
                 # what a kit built ahead of its hire should be. The day he
                 # creates the writer, one grant_domain_access hands them the
                 # whole shelf at once. Filing it here instead of in a
                 # knowledge: category matters: a bare knowledge: category is
                 # the SHARED tier and would have put craft essays on all nine
                 # shelves tonight. Check with get_domain_grants before
                 # assuming anyone can see it.
                 "authorship",
                 # THE PLANT SHELF SPLIT, 2026-09-18 (Barry: "herbs and veggies
                 # and fruit trees all need their own category, then sub cats.
                 # as well" + "house plants too"). It had grown to 20 docs on
                 # one flat `horticulture` hub, which is also how the brain map
                 # draws it -- one blob. These four are the crops a customer
                 # actually walks in asking about; `horticulture` KEEPS the
                 # cross-cutting fundamentals (nutrients, pH/EC, media,
                 # propagation, diagnosis, soil biology, physiology) because
                 # those apply to every one of the four and duplicating them
                 # per crop is exactly how two copies drift apart.
                 # All four are granted to all nine seats, same as horticulture.
                 "houseplants", "herbs", "vegetables", "fruit_trees",
                 # RESEARCH, 2026-09-19 (Barry: "all my creations need to be as
                 # smart as possible for what they are used for. this new agent
                 # will be for research too. so she will definitely need that
                 # skill"). domain:basics has `looking-things-up` -- query craft
                 # and reading a result honestly, which is the floor. This is
                 # the depth above it: running an investigation across many
                 # searches, judging what a source is worth, and reporting
                 # findings so the difference between known and guessed is
                 # visible. Deliberately its own shelf and not more basics
                 # documents: every agent needs the floor, only some are doing
                 # research, and the floor is already 6 docs on every new seat.
                 # Contains nothing of his -- generic by construction, same rule
                 # as basics, so it can reach an agent built for somebody else.
                 "research",
                 # BDUBB_PRODUCTS, 2026-09-19 (Barry, of the horticulture
                 # specialist: "she should know about the Bionova products, she
                 # needs to know what they're made of and all to assist the
                 # team" -- and, the same minute, of a different agent: "i dont
                 # want My author when i create it to know anything").
                 # Both are only possible if product knowledge is a SHELF he
                 # HANDS OVER instead of a shared-tier category that is either
                 # on for everyone or off for everyone.
                 # ⚠️ WHAT THE PRODUCTS ARE, never what they cost: the selling
                 # guide, the which-product-for-which-problem map, the feeding
                 # chart, the lab results. Cost basis, wholesale pricelists,
                 # suggested retail and the business brain stay in
                 # business:bdubbgrows behind the 2026-09-18 wall. A
                 # horticulturist advising his team needs the first and has no
                 # use for the second, and the second is his money.
                 "bdubb_products",
                 "herbalism",
                 # LOCAL KNOWLEDGE, 2026-09-28 (Barry: "make the ones that already live here have
                 # present day knowledge of here"). Granted to the locals by his word: Sophie and
                 # Taliyah (Colorado Springs), Ilnora (Manitou Springs).
                 "colorado_springs",
                 # WHERE TO LIVE, 2026-09-28 (Barry: "yes, give them the neighborhoods"). The movers
                 # pick their own new homes; this is the real neighborhoods and prices, nothing about
                 # which to choose. Granted to all ten -- the ONE copy (moved out of colorado_springs).
                 "colorado_springs_neighborhoods",
                 "folklore"}   # folklore added 2026-09-24 (Ilnora: Halloween history, myths, legends, witch-herb lore)  # herbalism added 2026-09-24 (Ilnora's shelf: using herbs, preparations, distillation, holistic practice)


def grant_domain_access(office_name: str, domain: str):
    if domain not in KNOWN_DOMAINS:
        raise ValueError(f"Unknown knowledge domain: {domain}")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO agent_domains (office_name, domain) VALUES (?, ?)",
            (office_name, domain),
        )


def grant_tool(office_name: str, tool_name: str, why: str = ""):
    """Give a seat one extra tool at runtime -- see the agent_tools table.

    Deliberately additive only: nothing here can remove a tool the code grants,
    so a bad grant widens a seat and never breaks one. The judgement about WHICH
    tools may be handed out lives with the caller (main._GRANTABLE_TOOLS), not
    here, because it is a policy question and this is storage.
    """
    from datetime import datetime as _dt
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO agent_tools (office_name, tool_name, granted_at, granted_why) "
            "VALUES (?, ?, ?, ?)",
            (office_name, tool_name, _dt.now().isoformat(timespec="seconds"), (why or "").strip()))


def revoke_tool(office_name: str, tool_name: str) -> bool:
    """Take back a RUNTIME grant. Cannot touch a code-granted tool."""
    with get_db() as conn:
        return conn.execute(
            "DELETE FROM agent_tools WHERE office_name = ? AND tool_name = ?",
            (office_name, tool_name)).rowcount > 0


def get_agent_tools(office_name: str) -> list[str]:
    with get_db() as conn:
        return [r["tool_name"] for r in conn.execute(
            "SELECT tool_name FROM agent_tools WHERE office_name = ? ORDER BY tool_name",
            (office_name,)).fetchall()]


def get_agent_domains(office_name: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT domain FROM agent_domains WHERE office_name = ?", (office_name,)
        ).fetchall()
        return [r["domain"] for r in rows]


# Barry's call, 2026-08-03. Shared facts go to everyone by default, which is
# right for owner identity but wrong for the commercial stack: the B Dubb brand
# voice, crop policy, email platforms and product catalog totalled ~12.6K chars
# riding EVERY message for EVERY agent. Taliyah is explicitly not a business
# agent, and Elliot only does Talia Crew film work -- neither has ever needed a
# nutrient product catalogue, and it was crowding out what they do need.
#
# Deliberately narrow. Vivian (Creative) is NOT excluded even though she is not
# a commercial agent either: she makes B Dubb visuals and needs the brand voice
# and crop policy to do it. business:pid is NOT excluded from anyone -- PID
# visibility was added deliberately after it was invisible to 8 of 9 agents, and
# the pid-guardrails skill handles keeping it separate. Owner identity is never
# excluded; every agent has to know who Barry is.
_SHARED_CATEGORY_EXCLUSIONS = {
    # knowledge:commerce (2026-08-13): the business-craft skill set -- finance/
    # taxes, product sourcing, scam red flags. Same reasoning as the brand
    # categories: Taliyah is the personal seat and Elliot is film-only, so
    # commerce craft is index noise for them at best and a separation leak at
    # worst.
    # knowledge:teamwork (2026-09-18): how to hand work to a teammate via
    # delegate_to. Taliyah was excluded here for exactly ONE DAY, on the correct
    # reasoning at the time -- she was the only seat without that tool, so the
    # document would have taught her to call something she did not have. Barry
    # then changed the fact rather than the reasoning ("she also needs to be
    # able to put together my ideas i come up with and file it and hand it to
    # the team"), she now carries delegate_to, and the exclusion came straight
    # back out. The commercial exclusions below stay: she hands HIS ideas to the
    # team, she does not join the commercial stack.
    # LIFTED 2026-10-10 (Barry: "they can all know the business, but only the business ones act on the
    # business"): Taliyah and Elliot know the businesses like everyone else. Acting stays with the business seats --
    # neither seat holds a store or commercial tool, and the team block says who acts.
    # 2026-10-15, Barry: "he really dont need the business stuff. hes strictly my Vel Dominion Stuff only. Ilnora is
    # strictly Youtube holistic healer, so she dont need the business stuff either" -- all three business shelves off
    # Elliot and Ilnora (~98K chars of facts; ~19K of it rode Elliot's every turn). Taliyah keeps the 10-10 ruling.
    "MovieDirector": ("business:bdubbgrows", "business:gotchoback", "business:pid"),
    "ilnora": ("business:bdubbgrows", "business:gotchoback", "business:pid"),
}


def shared_tier_offices() -> set:
    """The ONLY offices the shared tier reaches: Barry's own nine.

    🔒 Barry, 2026-09-18: "a new agent should be a blank slate until we add what
    that new agent needs. we need to lock my personal stuff away. my businesses
    and ideas etc. needs to be only for my own personal 9 agents. any new agent
    doesnt need it."

    WHY THIS IS A WALL AND NOT A FLAG. `include_shared` already existed and the
    hire default was flipped to business_context=False the same day -- but both
    are a CALLER'S choice, and one wrong argument anywhere (a new endpoint, a
    script, a future me passing business_context=True to be helpful) hands a
    stranger's agent 58 facts / 475K chars of his ventures, his PID work and his
    owner identity. He may build an agent FOR SOMEBODY ELSE, so this is not
    tidiness, it is the difference between a subject-matter agent and his
    business walking out of the building. A wall keyed on WHO IS ASKING cannot
    be switched off by a caller.

    Resolved from the live roster rather than hardcoded, so it can never drift
    from `agents.py`. Imported lazily: agents imports memory, and a module-level
    import here would be a cycle. Any failure falls back to the nine literals --
    it must never fail OPEN.
    """
    try:
        import agents as _agents
        return set(_agents.OFFICE_NAME_TO_AGENT_ID)
    except Exception:  # noqa: BLE001 -- never fail open
        return {"CIO", "Operations", "BusinessOps", "Legal", "Marketing",
                "Creative", "MovieDirector", "Engineer", "Taliyah"}


def get_active_facts_for_agent(office_name: str, include_shared: bool = True):
    """This agent's own private notes, the reference knowledge for any domain
    it has been granted (see grant_domain_access), and -- for Barry's own nine
    seats ONLY -- the shared tier.

    A HIRED AGENT IS A BLANK SLATE. It gets what was explicitly given to it and
    nothing else: no owner identity, no ventures, no catalog, no canon. See
    shared_tier_offices() for why that is enforced here rather than trusted to
    the caller. The generic craft shelf (`domain:basics`) is granted at hire so
    a blank slate is still competent -- main._register_hire.

    include_shared=False remains honoured as a second, narrower gate (a built-in
    seat can still be asked for a private-only view), but passing True does NOT
    grant the shared tier to anyone outside the nine."""
    domain_categories = {f"domain:{d}" for d in get_agent_domains(office_name)}
    private_category = f"private:{office_name}"
    # A hire is not in the shared tier, whatever the caller passed.
    granted_shared = set()
    if office_name not in shared_tier_offices() and "everything" in knows_about(office_name):
        pass            # his to keep (KNOWS_ABOUT["everything"]): the shared tier, like his nine
    elif office_name not in shared_tier_offices():
        include_shared = False
        # ...unless he ticked a specific piece of his world for this agent
        # (2026-09-19). One named category at a time, never the whole tier.
        granted_shared = _granted_shared_categories(office_name)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM facts WHERE status = 'active' ORDER BY category, created_at"
        ).fetchall()
    result = []
    for r in rows:
        cat = r["category"]
        if cat.startswith("private:"):
            if cat == private_category:
                result.append(dict(r))
        elif cat.startswith("domain:"):
            if cat in domain_categories:
                result.append(dict(r))
        elif include_shared:
            if cat in _SHARED_CATEGORY_EXCLUSIONS.get(office_name, ()):
                continue
            result.append(dict(r))  # shared topic fact -- everyone sees these
        elif cat in granted_shared:
            # HE TICKED THIS ONE (2026-09-19). The wall stays shut by default;
            # a named grant opens exactly one category for exactly one agent.
            # See grant_shared_category / KNOWS_ABOUT.
            result.append(dict(r))
    return result


# ---------------------------------------------------------------------------
# WHAT A NEW AGENT KNOWS ABOUT HIS WORLD -- ticked, never inherited
#
# Barry, 2026-09-19: "on boarding needs a check of what they need to know. The
# businesses, The PID, barry, Bia, the other agents. that stuff needs to be a
# thing in a check box."
#
# The 2026-09-18 wall made the shared tier reach his nine and nobody else,
# which was right and also all-or-nothing: there was no way to say "she may
# know the products and nothing else". These five are the pieces of his world
# as HE names them, each openable on its own, for one agent, on purpose.
#
# Default for every one of them is OFF. A hire that is never ticked sees none.
KNOWS_ABOUT = {
    "businesses": {
        "label": "The businesses",
        "what": "B Dubb Grows and Gotcho Back -- what they sell, how they run",
        "categories": ["business:bdubbgrows", "business:gotchoback",
                       "knowledge:commerce"],
    },
    "pid": {
        "label": "PID",
        "what": "The PID / piddevice venture. Kept apart from the other two by "
                "his standing rule, so it is its own tick.",
        "categories": ["business:pid"],
    },
    "owner": {
        "label": "You",
        "what": "Who you are -- your name and the owner identity facts",
        "categories": ["owner"],
    },
    "film": {
        "label": "The film",
        "what": "Talia Crew: Bia, Keth, Tazz, Yannah, Vor'Shara, the canon",
        "categories": ["knowledge:talia_crew"],
    },
    "thinking": {
        # 2026-09-24 (Barry: "Ilnora needs to be smart too. give her everything too"). Generic method
        # only -- how-to-think + check-your-work (reading the office's readback / OFFICE CHECK notes).
        # No venture, no store, no owner data lives in this category.
        "label": "How to think and check work",
        "what": "Verify before claiming, read the office's read-back, numbers only from tools or shown math",
        "categories": ["knowledge:thinking"],
    },
    "everything": {
        # 2026-09-24, Barry about Ilnora: "she can know me, shes mine to keep, not going to anyone" +
        # "give her everything too". The whole shared tier, exactly as his own nine see it (same
        # per-seat exclusions apply). Still ONE named grant for ONE agent -- every future hire keeps
        # the blank-slate default; revoke_knows_about undoes it.
        "label": "Everything (one of my own)",
        "what": "The whole shared tier his own nine see -- for an agent that is his to keep",
        "categories": [],
    },
    "team": {
        "label": "The other agents",
        "what": "Who the nine are and what each one owns, so they can hand work "
                "back and forth",
        "categories": [],          # a prompt block + delegate map, not facts
    },
}


def knows_about(office_name: str) -> list:
    """Which pieces of his world this agent has been given. Empty for a blank
    slate, which is the default and the point."""
    try:
        with get_db() as conn:
            return [r[0] for r in conn.execute(
                "SELECT area FROM agent_knows WHERE office_name = ? ORDER BY area",
                (office_name,)).fetchall()]
    except Exception:  # noqa: BLE001 -- a missing table means nobody was granted
        return []


def grant_knows_about(office_name: str, area: str, why: str = ""):
    """Open ONE named piece of his world to ONE agent. Logged, reversible."""
    if area not in KNOWS_ABOUT:
        raise ValueError("Unknown area: %s. Valid: %s"
                         % (area, ", ".join(sorted(KNOWS_ABOUT))))
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO agent_knows (office_name, area, granted_at, why) "
            "VALUES (?, ?, ?, ?)",
            (office_name, area, datetime.datetime.now().isoformat(timespec="seconds"), why))


def revoke_knows_about(office_name: str, area: str):
    with get_db() as conn:
        conn.execute("DELETE FROM agent_knows WHERE office_name = ? AND area = ?",
                     (office_name, area))


def _granted_shared_categories(office_name: str) -> set:
    out = set()
    for area in knows_about(office_name):
        out |= set(KNOWS_ABOUT.get(area, {}).get("categories", []))
    return out


def get_shared_facts():
    """Every fact every agent sees regardless of who it was taught to --
    the real 'main brain' (owner identity, both businesses, anything Barry
    drops directly on Victor's panel, which is the shared-scope entry
    point). Same category test as get_active_facts_for_agent's shared
    branch (anything not private:/domain:-prefixed), pulled out on its own
    for the dashboard's Brain view -- so a fact that affects every agent can
    actually be seen and deleted from one place, not buried inside just one
    agent's private list."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM facts WHERE status = 'active' ORDER BY category, created_at"
        ).fetchall()
    return [
        dict(r) for r in rows
        if not r["category"].startswith("private:") and not r["category"].startswith("domain:")
    ]


def delete_fact(fact_id: int) -> bool:
    """Permanently removes one fact from whichever brain it's in -- shared
    or a specific agent's private notes, same DELETE either way since
    category is just a column, not a separate table. No other table
    references facts.id (confirmed -- no foreign keys anywhere in this
    schema), and brain_context_block/get_active_facts_for_agent both query
    fresh from this table on every single chat call with no caching layer,
    so a deleted fact stops showing up in the very next conversation with
    no extra cleanup step needed anywhere. Returns False if no row matched."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        return cur.rowcount > 0


# A "skill" fact is a full seeded reference document (a SKILL.md or a plain
# knowledge/*.md adaptation -- see _seed_knowledge.py / _seed_ops_design_
# prod.py, both of which only ever seed from a real .md file and always set
# source_name to that filename). Everything else (a quick note, a dropped
# file's extracted text, a one-line correction) has no .md source_name and
# is small enough to stay always-on. This split is what makes
# brain_context_block() cheap by default: full skill CONTENT only gets
# pulled into context on demand via the read_skill tool (see llm_router.py),
# not stuffed into every single turn regardless of relevance -- confirmed
# this was previously blowing up to tens of thousands of characters per
# agent on every message, drowning out actual conversation.
def _is_skill_fact(fact: dict) -> bool:
    return fact.get("source_name", "").lower().endswith(".md")


def _skill_title(fact: dict) -> str:
    # "contract-review/SKILL.md" -> "contract-review"; "seo-audit.md" -> "seo-audit"
    name = fact.get("source_name", "")
    if "/" in name:
        name = name.split("/")[0]
    elif name.lower().endswith(".md"):
        name = name[:-3]
    return name


# A bare title is a very weak routing signal -- measured across every LLM call
# this office had ever made, read_skill fired in ~1% of them, despite the index
# header already shouting "MANDATORY BEFORE REAL WORK". Exhortation without
# information does not work: the model cannot tell from the slug alone whether
# a skill touches the job. This is the "description" half of a real SKILL.md
# frontmatter -- the routing contract -- and it was the missing piece.
#
# Convention: a skill document may carry a single line starting with
# "USE WHEN:" anywhere in its first ~1200 chars. If present it is printed
# beside the title in the index. Skills without one render exactly as before,
# so this is additive and safe for all ~49 existing skills. Keep them short --
# every one of these rides along on every message.
_USE_WHEN_PREFIX = "USE WHEN:"
_USE_WHEN_MAX = 200
# 2026-09-23: the always-on index shows TITLES only (routing uses the full
# line through recall). Flip to True to put the trigger words back.
INDEX_SHOWS_USE_WHEN = False
_INDEX_SKIP_PREFIXES = ("mind-", "worknote-", "conversation-history-")


def _skill_use_when(fact: dict, max_len: int = _USE_WHEN_MAX) -> str:
    """The doc's USE WHEN routing line. max_len defaults to the DISPLAY cap
    (the always-on index pays for every char); recall passes a large value
    because the scorer must see the WHOLE line -- measured 2026-09-08: tokens
    past char 200 of a routing line were invisible to routing, office-wide."""
    head = (fact.get("content") or "")[:1200]
    for raw in head.splitlines():
        line = raw.strip().lstrip("#*->  ").strip()
        if line.upper().startswith(_USE_WHEN_PREFIX):
            text = line[len(_USE_WHEN_PREFIX):].strip().strip("*_`")
            return text[:max_len]
    return ""


def brain_context_block(office_name: str = None, include_shared: bool = True,
                        pinned_titles: list = None) -> str:
    """Renders this agent's ALWAYS-ON facts (small notes, not full skill
    documents) into a text block, plus a short index of which deeper skills
    are available -- the model pulls a skill's full content in for itself
    via the read_skill tool (see llm_router.py's READ_SKILL_TOOL) only when
    a question actually touches it, instead of every skill ever seeded
    riding along on every single turn regardless of relevance. Pass no
    office_name to render everything (e.g. for a debug view) -- skill
    filtering only applies when a specific agent is given. include_shared
    controls whether shared facts (owner identity, both businesses) get
    included -- see get_active_facts_for_agent."""
    facts = get_active_facts_for_agent(office_name, include_shared=include_shared) if office_name else get_active_facts()
    if not facts:
        return "No business knowledge stored yet."

    always_on = [f for f in facts if not _is_skill_fact(f)]
    skills = [f for f in facts if _is_skill_fact(f)]

    lines = []
    current_category = None
    for f in always_on:
        if f["category"] != current_category:
            current_category = f["category"]
            if current_category.startswith("private:"):
                label = current_category[len("private:"):] + " (private)"
            elif current_category.startswith("domain:"):
                label = current_category[len("domain:"):] + " (reference knowledge)"
            else:
                label = current_category
            # MARKDOWN LAYOUT (2026-09-23, Barry: "Does Markdown style make
            # things easier? if so convert"). Formatting only -- not one word
            # of any fact changes. A category is a ## heading and each fact's
            # own TITLE line (enforced by _ensure_titled) is a ### heading, so
            # a long multi-paragraph note is a scannable section instead of
            # one run-on bullet under a bracket label.
            lines.append(f"\n## {label.upper()}")
        source = f"  _({f['source_name']})_" if f["source_name"] else ""
        body = (f["content"] or "").strip()
        first, _, rest = body.partition("\n")
        if first and len(first) <= 140 and rest.strip():
            lines.append(f"### {first.strip()}{source}\n{rest.strip()}")
        else:
            lines.append(f"- {body}{source}")

    if not lines:
        lines.append("No always-on business notes stored yet.")

    if skills:
        # THE CATALOGUE DIET (2026-09-23, Barry: "optimize my entire build").
        # Measured: this index was 13-27K chars on EVERY message of every seat
        # -- ~186 entries, each with its full trigger-word list -- and a third
        # to a half of the entries were the agent's own DIARY (mind-*), notes
        # it sent Barry (worknote-*) and old thread summaries. Recall already
        # delivers the right docs by their full USE WHEN line (it reads the
        # line itself, not this index), so here: titles only, and those three
        # kinds left out (recall excludes mind- from work on purpose; the date
        # door serves summaries). All of them are still readable by name.
        titles = sorted({_skill_title(f) for f in skills
                         if not _skill_title(f).startswith(_INDEX_SKIP_PREFIXES)})
        # Best (longest) USE WHEN line per title -- a skill can exist in more
        # than one fact row, and only some copies may carry the convention.
        use_when_by_title = {}
        for f in skills:
            t = _skill_title(f)
            uw = _skill_use_when(f)
            if uw and len(uw) > len(use_when_by_title.get(t, "")):
                use_when_by_title[t] = uw
        lines.append(
            "\n[SKILLS -- MANDATORY BEFORE REAL WORK. These are NOT loaded "
            "below; call the read_skill tool with the matching name to pull "
            "one in. The rule (Barry's, non-negotiable): before producing "
            "ANY deliverable -- a draft, a recommendation, a generation "
            "prompt, advice, anything headed for his pending box -- read "
            "every skill on this list that touches the job FIRST, then do "
            "the work from what it actually says. Skills COMBINE: a video "
            "post should draw on the hooks skill AND the brand-style skill "
            "AND the product data together, not whichever one came to mind. "
            "And learn from your own record -- your brain holds what Barry "
            "APPROVED (do more like that) and what he REJECTED (study why "
            "before making the same mistake) -- getting better over time is "
            "part of the job. Casual conversation doesn't need any of this; "
            "work does. Never answer a question a listed skill covers from "
            "memory alone.]"
        )
        # A pinned skill is already printed in full elsewhere in the system
        # prompt (see pinned_skills_block), so listing it here unmarked
        # invites a pointless read_skill round-trip for something the model
        # can already see.
        pinned_lower = {p.strip().lower() for p in (pinned_titles or [])}
        for title in titles:
            t = title.lower()
            is_pinned = any(p == t or p in t for p in pinned_lower)
            suffix = "  [PINNED -- already loaded in full above, do not read_skill this]" if is_pinned else ""
            # The routing signal. A pinned skill needs none -- it is already
            # in front of the model in full, so spending chars telling it when
            # to read something it cannot read is pure waste.
            use_when = "" if (is_pinned or not INDEX_SHOWS_USE_WHEN) else use_when_by_title.get(title, "")
            desc = f" -- {use_when}" if use_when else ""
            lines.append(f"- {title}{desc}{suffix}")

    return "\n".join(lines)


# PINNED SKILLS -- the counterweight to the read_skill tool, added
# 2026-08-04 after measuring the actual trace log: across all 349 LLM calls
# ever made by this office, read_skill was invoked exactly FOUR times (~1%),
# and Elliot used any tool at all in only 2 of his 25 calls. The on-demand
# model is sound for the long tail (his 38 skills are 481K chars, physically
# unloadable against any context window) but it fails completely for the
# handful of documents that must NEVER be absent -- his character canon
# being the one whose absence produced every documented render error.
#
# Note there is already a free way to force a document always-on: drop the
# .md off its source_name (see _is_skill_fact). That is NOT usable here,
# because it is per-FACT, not per-agent: barry-character-canon lives in the
# shared knowledge:talia_crew category, so un-.md-ing it would dump 10.7K
# chars onto Marcus doing legal work too. Pinning is the per-agent version
# of that switch, which is the only reason this function exists.
def pinned_skills_block(office_name: str, titles: list, budget_chars: int = 160000) -> str:
    """Renders the FULL content of this agent's pinned skills for injection
    straight into the system prompt, bypassing read_skill entirely. Titles
    are matched the same way get_skill_content matches them (exact title
    first, then substring) so a pin list stays readable. Returns "" when the
    agent has no pins, so callers can inject unconditionally.

    budget_chars is a backstop, not a target: pins are rendered in the order
    given and the first one that would breach the budget stops the loop, so
    the priority order of a pin list is meaningful. Anything skipped is
    named in the block, because a silently dropped canon file would be the
    exact failure this whole mechanism exists to prevent.

    Raised 60000 -> 80000 on 2026-08-08. At 60000 Elliot's 4th pin,
    ep1-scene-anchor-prompts (26.4K), never loaded -- it was named as skipped
    rather than lost, but Barry's instruction is that the director gets ALL
    of it: "Elliot should have it all and hes the on that is the director and
    movie person". His four pins total 75,676 chars ~= 18.9K tokens of the
    65,536-token window, which leaves ample room for brain context, history
    and the reply. Vivian's two pins (40.5K) are unaffected either way.

    Raised 95000 -> 105000 -> 120000 across 2026-08-11 and 2026-08-13 as pins
    were added, then 120000 -> 160000 on 2026-08-14, Barry: "if elliot needs
    mor room, give it to him, stop being skimpy with it."

    160000 is not arbitrary and is close to the real ceiling. Elliot's window
    is 65,536 tokens ~= 262K chars (OLLAMA_NUM_CTX in llm_router). Everything
    else in a turn has to fit alongside the pins: his brain block (~9.8K
    chars), 20 messages of history (tens of K on a long session), the shared
    prompt tail and tool schemas (~10K), and the reply itself (num_predict
    4096 tokens ~= 16K chars). That non-pin load is ~76K chars on a bad day,
    so ~185K is the hard wall and 160000 keeps a genuine margin under it.
    Past that the fix is NOT a bigger number -- the window itself has to grow,
    or a pin has to come off the list. Overflow does not error; Ollama
    silently truncates, and a silently truncated canon is the one failure
    this whole mechanism exists to prevent.

    At 160000 nothing anywhere is skipped: Elliot 113,167, Vivian 26,795,
    Derek 5,213, Sophie 12,852."""
    if not titles:
        return ""

    facts = get_active_facts_for_agent(office_name)
    skills = [f for f in facts if _is_skill_fact(f)]

    rendered, skipped, missing, used = [], [], [], 0
    for title in titles:
        t = title.strip().lower()
        exact = [f for f in skills if _skill_title(f).lower() == t]
        matches = exact or [f for f in skills if t in _skill_title(f).lower()]
        if not matches:
            missing.append(title)
            continue
        fact = matches[0]
        content = fact["content"]
        if used + len(content) > budget_chars:
            skipped.append(_skill_title(fact))
            continue
        used += len(content)
        rendered.append(f"\n### {_skill_title(fact)}\n{content}")

    if not rendered and not skipped and not missing:
        return ""

    header = (
        "--- PINNED SKILLS (loaded in full, already in front of you) ---\n"
        "These are the documents Barry has decided you must never work "
        "without, so they are printed below in full rather than left behind "
        "the read_skill tool. Do NOT call read_skill for any of these -- you "
        "already have them. Where one of these disagrees with your own "
        "assumption, memory, or a picture you have been shown, THESE WIN."
    )
    parts = [header] + rendered
    if skipped:
        parts.append(
            "\n[NOTE: pinned but not loaded -- context budget reached: "
            + ", ".join(skipped)
            + ". Use read_skill to pull one in if the job needs it.]"
        )
    if missing:
        parts.append(
            "\n[NOTE: pinned but not found in your brain: "
            + ", ".join(missing)
            + ".]"
        )
    parts.append("\n--- END PINNED SKILLS ---")
    return "\n".join(parts)


def get_skill_content(office_name: str, topic: str) -> dict:
    """Full content of one specific skill this agent actually has access to
    (matched by skill title, case-insensitive, substring-tolerant so
    "contract" matches "contract-review"). Used by the read_skill tool --
    the on-demand counterpart to brain_context_block()'s always-on facts."""
    facts = get_active_facts_for_agent(office_name)
    skills = [f for f in facts if _is_skill_fact(f)]
    topic_lower = topic.strip().lower()

    exact = [f for f in skills if _skill_title(f).lower() == topic_lower]
    matches = exact or [f for f in skills if topic_lower in _skill_title(f).lower()]

    if not matches:
        available = sorted({_skill_title(f) for f in skills})
        return {
            "found": False,
            "error": f"No skill matching '{topic}'.",
            "available_skills": available,
        }

    return {
        "found": True,
        "skills": [
            {"title": _skill_title(f), "content": f["content"]}
            for f in matches
        ],
    }


def get_latest_summary_time(office_name: str) -> str | None:
    """created_at of this agent's newest auto-summarized conversation, or
    None. Feeds the presence block (main.py) so an agent can say how long
    it's been since the last real conversation even after a thread reset
    wiped the raw history."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT created_at FROM facts WHERE status='active' AND category=? "
            "AND source_name=? ORDER BY id DESC LIMIT 1",
            (f"private:{office_name}", "Auto-summarized conversation (thread reset)"),
        ).fetchone()
    return row[0] if row else None


def log_message(agent_id: str, role: str, content: str, channel: str = "work"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (agent_id, role, content, timestamp, channel) VALUES (?, ?, ?, ?, ?)",
            (agent_id, role, content, datetime.datetime.now(datetime.UTC).isoformat(),
             "personal" if channel == "personal" else "work"),
        )


def get_recent_history(agent_id: str, limit: int = 20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def count_conversation(agent_id: str) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM conversations WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return row["c"]


def clear_conversation(agent_id: str, keep_last: int = 0):
    """Wipes an agent's raw turn-by-turn history -- called once it's been
    rolled into a summary fact (see main.py's _summarize_and_reset_thread),
    so the next turn starts a fresh thread instead of carrying an
    ever-growing transcript.

    keep_last > 0 keeps that many of the NEWEST raw turns (2026-08-21: a
    full wipe mid-working-session left Elliot with no memory of the fence
    he had just written and the redo Barry had just asked for -- "he
    should know what im talking about". The summary preserves decisions;
    the kept tail preserves the live working context)."""
    with get_db() as conn:
        if keep_last > 0:
            conn.execute(
                "DELETE FROM conversations WHERE agent_id = ? AND id NOT IN ("
                "SELECT id FROM conversations WHERE agent_id = ? "
                "ORDER BY id DESC LIMIT ?)",
                (agent_id, agent_id, keep_last))
        else:
            conn.execute("DELETE FROM conversations WHERE agent_id = ?", (agent_id,))


def queue_for_approval(agent_id: str, action_type: str, content: str, file_path: str = "") -> int | None:
    # 2026-07-30: the global "Think on it" gate that used to live here was
    # REMOVED on the owner's order -- it silently discarded finished work
    # (real image generations vanished with no trace, three separate times
    # in two days, each looking like "generation is broken"). The Live/
    # Paused toggle now scopes to agent-initiated SUGGESTIONS only, checked
    # at the two suggestion call sites (ideation delivery, Sophie's
    # fix-suggestion dispatch) -- never here, so owner-triggered work
    # (images, outputs) always lands in Pending Review.
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO approvals (agent_id, action_type, content, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (agent_id, action_type, content, file_path, datetime.datetime.now(datetime.UTC).isoformat()),
        )
        new_id = cur.lastrowid
    # WHO IT CAME FROM (2026-09-28, gallery.py): recorded at filing, while the thread still
    # holds the words. Never raises; non-gallery rows are ignored inside.
    try:
        import gallery
        gallery.note_origin(new_id, agent_id, action_type, content, file_path)
    except Exception as e:  # noqa: BLE001
        print(f"[gallery] origin hook failed: {e}")
    return new_id


def get_pending_approvals():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_approved_approvals(limit: int = 100):
    """The Approved box (owner's two-stage pipeline, 2026-07-31): things he
    has approved in Pending Review, newest first -- his staging area to
    look over finished/blessed work and decide what actually gets posted.
    Capped so years of approvals don't ship to the browser in one call."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = 'approved' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_agent_outputs(agent_id: str):
    """Every output this agent has ever produced -- unlike
    get_pending_approvals(), this returns every status (pending/approved/
    rejected), most recent first, so the office's Outputs panel can show a
    real per-agent history/archive, not just what's still waiting on a
    decision."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_agent_stats(agent_id: str) -> dict:
    """Message count + pending-approval count for one agent -- powers the
    activity badges on the web dashboard's agent cards (AgentDashboard/)."""
    with get_db() as conn:
        pending_count = conn.execute(
            "SELECT COUNT(*) FROM approvals WHERE agent_id = ? AND status = 'pending'",
            (agent_id,),
        ).fetchone()[0]
        return {"messages": count_conversation(agent_id), "pending": pending_count}


def get_output_by_id(approval_id: int):
    """One output row by id -- used to resolve its file_path server-side
    for the web dashboard's file-serving endpoint (AgentDashboard/), so the
    browser never has to be trusted with a raw filesystem path itself."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None


def delete_output(approval_id: int) -> bool:
    """Removes one output/approval entry permanently -- lets the owner clear
    unwanted items from an agent's Outputs archive (outputs_ui.gd) instead
    of them accumulating forever. Returns False if no row matched."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM approvals WHERE id = ?", (approval_id,))
        return cur.rowcount > 0


def decide_approval(approval_id: int, approved: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE approvals SET status = ?, decided_at = ? WHERE id = ?",
            (
                "approved" if approved else "rejected",
                datetime.datetime.now(datetime.UTC).isoformat(),
                approval_id,
            ),
        )
    # LEARNING (2026-09-24, outcomes.py): Barry's own click is the strongest real signal there is.
    # Work items only -- an agent's home picture (agent_scene) is theirs, not a work outcome.
    try:
        row = get_output_by_id(approval_id)
        if row and row.get("action_type") in ("public_content", "idea", "email", "social_post",
                                                "engineer_task", "code_fix"):
            import agents as _agents
            import outcomes
            aid = row.get("agent_id") or ""
            office = (_agents.AGENTS.get(aid) or {}).get("office_name") or next(
                (c["office_name"] for c in get_custom_agents() if c.get("agent_id") == aid), aid)
            first = ((row.get("content") or "").strip().splitlines() or [""])[0][:160]
            outcomes.record(office, "approved" if approved else "rejected",
                            f"Barry {'APPROVED' if approved else 'REJECTED'} your {row['action_type']} #{approval_id}: {first}",
                            approval_id=int(approval_id))
    except Exception:                               # noqa: BLE001 -- a decision must never fail on logging
        pass


def hire_custom_agent(name: str, role: str, job_description: str, business_context: bool = True) -> dict:
    """Creates a new, permanently persisted agent from a plain job
    description typed live in the hiring UI (see main.py's
    POST /api/agents/hire) -- this is how a new hire's job actually gets set
    "right then and there" rather than needing a code change. Slugifies the
    name into a unique agent_id/office_name, since both get used as
    dictionary/lookup keys elsewhere (agent_ui.gd's OFFICE_NAME_TO_AGENT_ID,
    this file's private-fact scoping).

    business_context=False is for a purely topical/personal-interest hire
    (a current-events analyst, a gardening expert unrelated to the business,
    etc.) -- see agents.py's build_hired_agent_prompt for what this actually
    changes. Defaults to True so existing callers/behavior are unchanged."""
    base_slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_") or "agent"
    with get_db() as conn:
        agent_id = base_slug
        suffix = 1
        while conn.execute("SELECT 1 FROM custom_agents WHERE agent_id = ?", (agent_id,)).fetchone():
            suffix += 1
            agent_id = f"{base_slug}_{suffix}"
        office_name = agent_id
        conn.execute(
            "INSERT INTO custom_agents (agent_id, name, office_name, role, job_description, business_context, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, name, office_name, role, job_description, int(business_context), datetime.datetime.now(datetime.UTC).isoformat()),
        )
    return {
        "agent_id": agent_id,
        "name": name,
        "office_name": office_name,
        "role": role,
        "job_description": job_description,
        "business_context": business_context,
    }


def get_custom_agents() -> list[dict]:
    """All previously hired custom agents, for main.py to reload into the
    live roster on every backend restart -- a hire is permanent, not a
    per-session thing."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM custom_agents ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def get_custom_agent(agent_id: str) -> dict | None:
    """One hired agent by id, or None.

    main.py has called this in two places (`/api/agents/{id}/like` and
    `/api/agents/{id}/clear-thread`) since they were written, and it did not
    exist -- only the plural `get_custom_agents()` did. Both call sites sit
    behind a short-circuit (`AGENTS.get(id) or ...`), so the nine built-in
    seats never reached it and the gap stayed invisible; a HIRED agent would
    have hit an AttributeError and got a 500. Found by scripts/preflight_check.py
    on 2026-08-31.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM custom_agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return dict(row) if row else None


def seed_default_domain_access():
    """The original 3 specialists (plus Sophie/Engineer) get their own
    domain by default -- safe to run every startup, INSERT OR IGNORE makes
    it a no-op after the first time."""
    grant_domain_access("Legal", "legal")
    grant_domain_access("Marketing", "marketing")
    grant_domain_access("BusinessOps", "business_ops")
    grant_domain_access("Engineer", "engineering")
    # Horticulture (plants, minerals, media, Bionova -- owner's 2026-07-30
    # "skills my agents need for B DUBB GROWS") goes to every business-
    # facing agent, not one specialist: they all advise on the products.
    for office in ("CIO", "Operations", "BusinessOps", "Marketing", "Creative"):
        grant_domain_access(office, "horticulture")


def seed_initial_facts():
    """Seeds the brain with what's known so far about the owner and both of
    his businesses. Safe to run multiple times - only inserts if these
    categories are already empty."""
    if not get_active_facts("owner"):
        add_fact(
            "owner",
            "The owner's name is Barry Jermaine White (goes by B DUBB / Barry White "
            "in creative credits). Every agent in this office works directly for him "
            "personally, across both B Dubb Grows LLC and Gotcho Back. Address him by "
            "name when it feels natural, not performatively.",
        )
        add_fact(
            "owner",
            "Big-picture motivation worth keeping in mind: Barry's long-term goal is "
            "building real, substantial wealth from these businesses -- enough to buy "
            "land and build a house in Florida. This isn't a request to act on "
            "directly, it's context for why growth, margin, and smart reinvestment "
            "recommendations matter to him beyond just running the businesses day to day.",
        )

    if get_active_facts("business:bdubbgrows"):
        return
    add_fact(
        "business:bdubbgrows",
        "B Dubb Grows LLC (bdubbgrowsllc.com) is the owner's primary business -- "
        "NOT 'YieldCraft', that was a considered rename that never actually "
        "happened; the real, current legal and operating name is B Dubb Grows LLC. "
        "Premium indoor/hydroponic gardening supply retailer: nutrient systems "
        "(Bionova and GHF lines), grow lights, grow tents, water filtration/reverse "
        "osmosis systems, plant additives and accessories. Targets hobbyist and "
        "commercial growers of vegetables, herbs, and houseplants. Runs on "
        "WooCommerce. Free shipping over $200; 15% newsletter signup discount. "
        "Social: Instagram @b.dubb_growsllc, Facebook @BDUBB4ch, TikTok @bdubbgrows, "
        "X/Twitter @BDUBB64760448, YouTube @BDUBBGROWS. Contact: info@bdubbgrowsllc.com.",
    )
    add_fact(
        "business:bdubbgrows",
        "IMPORTANT: B Dubb Grows does not sell cannabis or controlled substances - "
        "it sells legal indoor/hydroponic gardening supplies for vegetables, herbs, "
        "and houseplants. Marketing and product copy must stay clearly on that side "
        "of the line and avoid language that implies otherwise.",
    )
    add_fact(
        "business:gotchoback",
        "Gotcho Back (gotchoback.com) is the owner's second business -- a "
        "fashion-forward backpack brand, tagline 'Where Backpacks Are Fashion'. "
        "Sells school backpacks, fashion backpacks, hemp backpacks, leather "
        "options, convertible designs (backpack-to-handbag), and sling bags, "
        "priced roughly $22-$68. Casual, youth-oriented, style-first tone -- "
        "backpacks as a style statement, not just a functional item. Targets "
        "students, young professionals, and fashion-conscious buyers. Social: "
        "Instagram @gotcho.back. Completely separate product line and brand "
        "voice from B Dubb Grows -- don't mix gardening-supply language into "
        "Gotcho Back content or vice versa.",
    )


# --- Global model/backend selection ---
# One switch for the WHOLE office, not per-agent -- every agent (and the
# idle-ideation loop, see ideation.py) generates through whichever
# backend+model is currently selected here (see the Godot Settings tab's
# dropdown / main.py's GET+POST /api/settings/models). Persisted so a
# choice survives a backend restart, unlike the in-memory session cost
# counter.
ACTIVE_BACKEND_KEY = "active_backend"
ACTIVE_MODEL_KEY = "active_model"
DEFAULT_BACKEND = "ollama"


def get_setting(key: str, default: str = None) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_active_generation() -> tuple[str, str]:
    """(backend, model) every agent should generate through right now."""
    from config import OLLAMA_MODEL, CLAUDE_MODEL, BONSAI_MODEL_NAME  # local import avoids a load-order dependency on config at module import time
    backend = get_setting(ACTIVE_BACKEND_KEY, DEFAULT_BACKEND)
    if backend == "bonsai":
        default_model = BONSAI_MODEL_NAME
    elif backend == "ollama":
        default_model = OLLAMA_MODEL
    else:
        default_model = CLAUDE_MODEL
    model = get_setting(ACTIVE_MODEL_KEY, default_model)
    return backend, model


def set_active_generation(backend: str, model: str):
    # "bonsai" = Ternary Bonsai 27B via the PrismML llama-server (see
    # bonsai_llm.py) -- local like Ollama, but a separate serving process
    # because ternary Q2_0 physically can't load under Ollama.
    if backend not in ("ollama", "claude", "bonsai"):
        raise ValueError(f"Unknown backend: {backend}")
    set_setting(ACTIVE_BACKEND_KEY, backend)
    set_setting(ACTIVE_MODEL_KEY, model)


# Hard privacy switch, separate from the backend/model dropdown above: when
# on, nothing about a conversation (scripts, legal/business details) may
# leave the machine, full stop -- not just "don't use Claude," but also no
# live web search (the query itself, built from conversation content, would
# leave via DuckDuckGo/SearXNG) and no incidental telemetry-shaped traffic
# (the version-check pings) either. See main.py's enforcement at every one
# of those call sites -- this flag only stores the setting.
# Per-agent model overrides the OWNER can change at runtime, layered ON TOP of
# main.py's hardcoded AGENT_OLLAMA_MODEL_OVERRIDES (which stays the default).
# Added 2026-08-11 so Taliyah can be moved between the abliterated 9b and
# Bonsai without a code edit and a restart -- she is the one seat where both
# models do the job (Bonsai is warmer and faster in her register; the 9b is the
# one that writes explicit vocabulary), so which is "right" is a mood call, not
# an engineering one.
#
# Stored as one JSON object under a single settings key: {agent_id: value}.
#   value = an Ollama model name -> pin that agent to it (backend forced ollama)
#   value = None                 -> that agent FOLLOWS THE GLOBAL backend/model
#   agent_id absent              -> fall back to the hardcoded default
# The None case is the whole point: it is how an agent gets onto Bonsai while
# the hardcoded map would otherwise pin it to Ollama.
#
# Read live on every resolve, exactly like facts -- no restart, which is the
# entire reason this exists rather than editing main.py.
AGENT_MODEL_OVERRIDES_KEY = "agent_model_overrides"


def get_agent_model_overrides() -> dict:
    """Owner-set per-agent overrides. Returns {} when unset or unparseable --
    a corrupt value must degrade to 'use the hardcoded defaults', never break
    every chat in the office."""
    raw = get_setting(AGENT_MODEL_OVERRIDES_KEY, None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def set_agent_model_override(agent_id: str, model: str | None, follow_global: bool = False):
    """Pin one agent to an Ollama model, make it follow the global setting, or
    clear the override so the hardcoded default applies again.

    model=<name>        -> pin
    follow_global=True  -> store an explicit None (follow the global dropdown)
    model=None + follow_global=False -> REMOVE the override entirely
    """
    overrides = get_agent_model_overrides()
    if follow_global:
        overrides[agent_id] = None
    elif model:
        overrides[agent_id] = model
    else:
        overrides.pop(agent_id, None)
    set_setting(AGENT_MODEL_OVERRIDES_KEY, json.dumps(overrides))


OFFLINE_MODE_KEY = "offline_mode"


def is_offline_mode() -> bool:
    return get_setting(OFFLINE_MODE_KEY, "false") == "true"


def set_offline_mode(enabled: bool):
    set_setting(OFFLINE_MODE_KEY, "true" if enabled else "false")


# "Think on it" pause -- owner's explicit request: a way to stop new items
# landing in Pending Review while he's still working through what's already
# there, rather than it piling up faster than he can clear it. Manual
# toggle only (not auto-cleared when the queue empties) -- see main.py's
# enforcement at queue_for_approval's call sites and ideation.py's delivery
# check.
QUEUE_PAUSED_KEY = "queue_paused"


def is_queue_paused() -> bool:
    return get_setting(QUEUE_PAUSED_KEY, "false") == "true"


def set_queue_paused(paused: bool):
    set_setting(QUEUE_PAUSED_KEY, "true" if paused else "false")


if __name__ == "__main__":
    init_db()
    seed_initial_facts()
    print(f"Brain initialized at {DB_PATH}")
    print(brain_context_block())
