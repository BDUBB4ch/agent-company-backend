"""
Idle-time ideation loop: when nobody's actively chatting, periodically picks
one agent and asks it to flag anything worth Barry's attention -- an idea,
a risk, an opportunity -- using whatever it already knows from the brain
(see memory.py). The result is never shown directly or acted on; it's
queued into the exact same approvals table as everything else (see
main.py's queue_for_approval), tagged action_type='idea' so it reads
distinctly in the Out box but goes through the identical approve/reject
flow as every other agent output. Same hard rule as the rest of this
project: nothing here ever acts on its own idea.

Deliberately built to never compete with an actual conversation for GPU
time: main.py calls mark_activity_start()/mark_activity_end() around every
/api/chat request, and this loop only fires after IDEATION_IDLE_THRESHOLD_
SECONDS of continuous silence -- re-checked immediately before it actually
calls the model, not just at the top of its sleep loop, so a message that
arrives right as the timer fires still wins.
"""
import asyncio
import itertools
import time

import memory

# The Live/Paused toggle (memory.is_queue_paused) scopes to agent-initiated
# SUGGESTIONS only -- since 2026-07-30 it's checked at the suggestion call
# sites (here, and Sophie's fix-suggestion dispatch), NOT centrally inside
# queue_for_approval, which used to silently discard finished images too.
# Checking before generating also means a paused office doesn't burn a real
# generation call only to drop the result.

# --- Configuration -- edit these to change cadence/participants ---

# How often to CHECK whether it's time for a new delivery. Not itself the
# cadence -- a delivery only actually fires once both this check lines up
# AND IDEATION_DELIVERY_INTERVAL_SECONDS has actually elapsed AND the office
# is idle, so checking hourly is just cheap insurance that a due delivery
# doesn't have to wait long once the office finally goes quiet.
IDEATION_CHECK_INTERVAL_SECONDS = 60 * 60  # 1 hour

# How long the office must have been completely quiet (no /api/chat request
# in flight or recently finished) before a delivery is allowed to fire.
IDEATION_IDLE_THRESHOLD_SECONDS = 10 * 60  # 10 minutes

# Real cadence: twice a week, not continuous -- explicit owner request
# ("they should give me those twice a week and up to 4 at a time"), after
# the original always-on-idle version piled up 48 items over a few days.
# Approximated as every 3.5 days so two deliveries land roughly a week apart.
IDEATION_DELIVERY_INTERVAL_SECONDS = int(3.5 * 24 * 60 * 60)

# Max real ideas queued in a single delivery -- a delivery tries up to this
# many agents from the rotation and queues whatever they actually have;
# agents with nothing to flag don't count against Barry's attention, so a
# delivery can genuinely land with fewer than this many.
IDEATION_MAX_IDEAS_PER_DELIVERY = 4

# Which agents take part in the idle ideation rotation, and how grounded
# their ideas are -- edit this dict to add/remove participants or change an
# agent's level. Uses agent_id (agents.py's AGENTS keys / main.py's
# CUSTOM_AGENTS keys), not office_name or person_name. Taliyah is
# deliberately never in here -- she's a personal companion, not a
# business/ops role, and IDEATION_PROMPT is explicitly business-move-shaped.
#
# "brain_only": today's original behavior -- reasons from brain facts alone,
#   no tool calls. Cheap, fast, but ungrounded (see the grounded case below).
# "grounded": real tool access during generation -- an idea has to be
#   checked before it's written up, not just recalled. Real incident that
#   motivated this: the exact same ungrounded-confident-generation pattern
#   that caused Sophie to hallucinate wrong website advice in live chat was
#   ALSO true here (use_tools was hardcoded False for every agent) -- it
#   just hadn't surfaced yet because idea outputs get reviewed less often
#   than live chat. Sophie (engineer) starts at "grounded" here: her real
#   investigate_traces/read_project_file tools let an idle cycle actually
#   check something real (a trace pattern, a file) instead of musing
#   abstractly -- the natural home for the self-monitoring idea discussed
#   the same night this was built. Any other agent can be flipped to
#   "grounded" later just by changing its value here.
IDEATION_AGENT_LEVELS = {
    "cio": "brain_only",
    "operations": "brain_only",
    "business": "brain_only",
    "legal": "brain_only",
    "marketing": "brain_only",
    "creative": "brain_only",
    "movie": "brain_only",
    "engineer": "grounded",
}

IDEATION_PROMPT = (
    "This is not an invitation to muse or reflect at length -- Barry does not "
    "want you pondering. He wants exactly ONE concrete, specific next move "
    "for B Dubb Grows LLC or Gotcho Back, if you genuinely have one, based on "
    "what's in your brain and your own area of expertise. A 'next move' means "
    "a real action someone could actually go do this week -- not an "
    "observation, not a general trend, not '3 areas worth considering.' "
    "Name the single most valuable one, not a list.\n\n"
    "Format, strictly:\n"
    "MOVE: [the specific action, one sentence]\n"
    "WHY: [1-2 sentences, concrete -- a real number or specific reason, not "
    "vague reasoning]\n"
    "FIRST STEP: [the actual next concrete step to start it]\n\n"
    "If you don't have anything genuinely specific and worth his time right "
    "now, reply with exactly: NOTHING TO FLAG. Do not manufacture a generic "
    "idea just to have an answer, and do not pad a real one with extra "
    "sections, caveats, or a summary -- three short lines or nothing at all. "
    "If you have real tools available, use them to check whatever you're "
    "about to flag before writing it up -- a real move grounded in "
    "something you actually verified beats one guessed from memory."
)

# Sophie/Engineer gets her own prompt, not IDEATION_PROMPT above -- real gap
# found via direct testing: the shared prompt asks for "a business move for
# B Dubb Grows or Gotcho Back," so even with her real project/trace tools
# attached, she produced a generic web-dev suggestion (lazy-loading images)
# instead of the actual self-monitoring check her tools are for -- the
# prompt itself never pointed her at checking the SYSTEM, only the business.
# Same tight philosophy as IDEATION_PROMPT (one concrete thing, strict
# format, an honest NOTHING TO FLAG exit), retargeted at what she can
# actually check: real trace data and real project files, not brand-new
# business strategy.
IDEATION_PROMPT_ENGINEER = (
    "This is not an invitation to muse or reflect at length -- Barry does "
    "not want general engineering musing. He wants exactly ONE concrete "
    "finding about the actual health of this system, if you genuinely have "
    "one -- something you found by actually checking, not a hunch. Use "
    "your real tools: investigate_traces to check for real failure "
    "patterns across the agent roster, read_project_file/"
    "list_project_directory if something in the code itself is worth "
    "verifying. A 'finding' means something concrete and checkable -- a "
    "real repeated failure signature, a real error in a log, something "
    "specific -- not a vague 'things could probably be more robust.'\n\n"
    "Format, strictly:\n"
    "FINDING: [what you actually found, one sentence]\n"
    "WHY IT MATTERS: [1-2 sentences, concrete -- which agent, how often, "
    "what it looked like]\n"
    "SUGGESTED FIX: [the actual next concrete step, or 'none yet -- worth "
    "watching' if you don't have one]\n\n"
    "If you check and genuinely find nothing worth flagging, reply with "
    "exactly: NOTHING TO FLAG. Do not manufacture a finding just to have an "
    "answer, and do not skip actually using your tools to check -- a real "
    "check that finds nothing is a valid, useful result; a guess dressed up "
    "as a finding is not."
)

# IDEATION_PROMPT asks for this exact phrase when there's nothing worth
# flagging -- checked as a prefix (not exact-match) since a local model
# will still sometimes add a trailing word or two despite the instruction
# not to.
_NOTHING_TO_FLAG = "nothing to flag"

_last_activity_at: float = time.time()
_active_chat_count: int = 0
_agent_cycle = itertools.cycle(IDEATION_AGENT_LEVELS.keys())
# Starts the clock at process start, not at the epoch/zero -- so restarting
# the backend doesn't itself trigger an immediate delivery; the first one
# still waits the full IDEATION_DELIVERY_INTERVAL_SECONDS out.
_last_delivery_at: float = time.time()


def _load_last_delivery() -> float:
    """THE CLOCK LIVES IN THE DB NOW (2026-09-17, Barry: "they havent did
    anything but what i asked for" -> "fix it"). Measured: this stamp was
    process memory, the backend restarted hundreds of times since 09-14, and
    the 3.5-day interval had never once elapsed -- the batch never fired.
    First boot ever seeds the stamp once; every restart after reads it."""
    try:
        v = memory.get_setting("ideation_last_delivery")
        if v:
            return float(v)
    except Exception:
        pass
    now = time.time()
    try:
        memory.set_setting("ideation_last_delivery", str(now))
    except Exception:
        pass
    return now


try:
    _last_delivery_at = _load_last_delivery()
except Exception:
    pass


def mark_activity_start() -> None:
    """Call at the start of every /api/chat request."""
    global _active_chat_count
    _active_chat_count += 1


def mark_activity_end() -> None:
    """Call when a /api/chat request finishes (success or failure) -- the
    idle clock starts counting from the moment the conversation actually
    goes quiet, not from when it started."""
    global _active_chat_count, _last_activity_at
    _active_chat_count = max(0, _active_chat_count - 1)
    _last_activity_at = time.time()


def _video_building() -> bool:
    """Ilnora's video is building (data/reel_building.flag, up for the WHOLE build, not just a GPU step).
    Barry 2026-10-14: "if she isnt finish, the office has to wait" / "i dont want no interuptions" -- measured
    the same day: Derek's and Victor's scheduled turns ran between her build steps and her next step unloaded
    Bonsai under them. Every office loop that starts a turn on its own checks this and tries again later.
    Barry's own chats and her build's own turns do not pass through these gates."""
    try:
        import comfy_image
        return comfy_image.reel_building()
    except Exception:  # noqa: BLE001
        return False


def _is_idle() -> bool:
    return (_active_chat_count == 0 and (time.time() - _last_activity_at) >= IDEATION_IDLE_THRESHOLD_SECONDS
            and not _video_building())


def _delivery_is_due() -> bool:
    return (time.time() - _last_delivery_at) >= IDEATION_DELIVERY_INTERVAL_SECONDS


def _reads_as_nothing_to_flag(reply: str) -> bool:
    lowered = reply.strip().lower()
    return len(reply) < 200 and _NOTHING_TO_FLAG in lowered


async def _generate_one_idea(get_agent_fn, agent_id: str) -> bool:
    """Returns True if a real idea got queued, False if this agent had
    nothing to flag (or no longer exists) -- the caller uses this to know
    whether a delivery slot was actually used."""
    import llm_router  # local import -- avoids a circular import with main.py
    from agents import ENGINEER_ID  # same reason -- avoids importing agents at module load time

    agent = get_agent_fn(agent_id)
    if agent is None:  # a configured id that no longer exists (e.g. renamed/removed)
        return False

    brain = memory.brain_context_block(agent["office_name"])
    system_prompt = (
        f"{agent['system_prompt']}\n\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n{brain}\n"
        f"--- END BUSINESS KNOWLEDGE ---\n\n"
        f"Hard rule: you cannot post, send, email, or publish anything "
        f"yourself under any circumstance. You only draft. The owner "
        f"approves everything through a separate review step."
    )
    # use_tools was hardcoded False for everyone -- an open-ended "anything
    # worth flagging?" prompt isn't a concrete question, and testing showed
    # qwen3.5 tends to reflexively search repeatedly on a prompt shaped like
    # this and never settle on an answer within llm_router's
    # MAX_TOOL_ROUNDS. That risk is real but lower now for agents at the
    # "grounded" level (see IDEATION_AGENT_LEVELS above): every agent's own
    # system_prompt (already included above) now has an honest "say so if
    # still ungrounded" exit instead of endlessly retrying, and this runs
    # unattended in the background, so a slower grounded generation costs
    # nothing in perceived responsiveness the way it would in live chat.
    # backend/model: the same global choice every chat uses (see
    # memory.get_active_generation), not agent["backend"]'s per-agent
    # default -- one switch for the whole office, not per-agent. EXCEPT
    # Sophie: a real gap found via direct testing -- her ideation call was
    # silently running on the global persona model instead of her own
    # AGENT_OLLAMA_MODEL_OVERRIDES coding model, which meant the real
    # project/trace tools attached below didn't fit what she was actually
    # generating with. main.AGENT_OLLAMA_MODEL_OVERRIDES imported locally
    # (main.py is already fully loaded by the time this runs, since the
    # ideation loop only starts inside the app's lifespan, well after
    # import time -- same deferred-import reasoning as llm_router/agents
    # above, just one more hop).
    level = IDEATION_AGENT_LEVELS.get(agent_id, "brain_only")
    use_tools = level == "grounded"
    extra_tools = None
    prompt = IDEATION_PROMPT
    if agent_id == ENGINEER_ID:
        extra_tools = [
            llm_router.READ_PROJECT_FILE_TOOL,
            llm_router.LIST_PROJECT_DIRECTORY_TOOL,
            llm_router.INVESTIGATE_TRACES_TOOL,
            llm_router.SUBMIT_AGENT_FIX_TOOL,
        ]
        prompt = IDEATION_PROMPT_ENGINEER
    backend, model = memory.get_active_generation()
    if agent_id == ENGINEER_ID and backend == "ollama":
        from main import AGENT_OLLAMA_MODEL_OVERRIDES
        model = AGENT_OLLAMA_MODEL_OVERRIDES.get(agent_id, model)
    reply = await llm_router.generate(
        backend, system_prompt, [{"role": "user", "content": prompt}], model=model,
        use_tools=use_tools, extra_tools=extra_tools, office_name=agent["office_name"],
    )

    if _reads_as_nothing_to_flag(reply):
        print(f"[ideation] {agent_id}: nothing to flag this round.")
        return False

    _aid = memory.queue_for_approval(agent_id, "idea", (reply or "").rstrip())
    print(f"[ideation] {agent_id}: queued a new idea for review.")
    return True


async def _run_delivery(get_agent_fn) -> None:
    """One twice-weekly delivery: tries up to IDEATION_MAX_IDEAS_PER_DELIVERY
    agents from the rotation, queuing whatever real ideas come back. Agents
    with nothing to flag don't consume a delivery slot -- the rotation just
    keeps advancing to the next agent until either the cap is hit or every
    agent's been tried once this round."""
    if not IDEATION_AGENT_LEVELS:
        return
    queued = 0
    attempts = 0
    max_attempts = len(IDEATION_AGENT_LEVELS)
    while queued < IDEATION_MAX_IDEAS_PER_DELIVERY and attempts < max_attempts:
        agent_id = next(_agent_cycle)
        if await _generate_one_idea(get_agent_fn, agent_id):
            queued += 1
        attempts += 1
    print(f"[ideation] delivery complete: {queued} idea(s) queued.")


async def run_ideation_loop(get_agent_fn) -> None:
    """Background task -- see main.py's lifespan. Never lets one bad cycle
    take the whole loop down, same 'never crash over an optional
    capability' pattern as update_checker.py's periodic task."""
    global _last_delivery_at
    while True:
        await asyncio.sleep(IDEATION_CHECK_INTERVAL_SECONDS)
        try:
            if not _delivery_is_due() or not _is_idle() or memory.is_queue_paused():
                continue
            await _run_delivery(get_agent_fn)
            _last_delivery_at = time.time()
            memory.set_setting("ideation_last_delivery", str(_last_delivery_at))
        except Exception as e:
            print(f"[ideation] cycle failed: {e}")
