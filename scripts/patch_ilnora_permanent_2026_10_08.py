r"""One-off patch (2026-10-08, Barry: "i told you before, Ilnora is permanent"): the owner wall (main._strip_owner_world)
was blanking his businesses and his town inside Ilnora's turns because the gate read `not in AGENTS`. memory already
treats a hire with KNOWS_ABOUT "everything" as his to keep (the shared tier); main now uses the same rule for the
system prompt, the per-turn auto parts and "Barry" vs "your owner". She stays out of the business TEAM block (she is
not a business seat) and keeps her neutral tool names (her toolkit names them)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "main.py"), [
(r'''def _strip_owner_world(text: str, agent_id: str, keep=()) -> str:''',
r'''def _his_seat(agent_id: str) -> bool:
    """One of his: the nine, or a hire he keeps (KNOWS_ABOUT "everything" -- Ilnora; Barry 2026-10-08: "i told you
    before, Ilnora is permanent"). The same rule memory.py uses for the shared tier, so the wall and the recall agree."""
    if agent_id in AGENTS:
        return True
    try:
        rec = CUSTOM_AGENTS.get(agent_id) or memory.get_custom_agent(agent_id) or {}
        office = rec.get("office_name") or agent_id
        return "everything" in memory.knows_about(office)
    except Exception:  # noqa: BLE001 -- never fail open
        return False


def _strip_owner_world(text: str, agent_id: str, keep=()) -> str:'''),
(r'''        if req.agent_id not in AGENTS:
            system_prompt = _strip_owner_world(
                system_prompt, req.agent_id,
                keep=_owner_typed_words(req.agent_id))''',
r'''        if not _his_seat(req.agent_id):
            system_prompt = _strip_owner_world(
                system_prompt, req.agent_id,
                keep=_owner_typed_words(req.agent_id))'''),
(r'''            if req.agent_id not in AGENTS:
                _auto = _strip_owner_world(_auto, req.agent_id)
                _dirs = _strip_owner_world(_dirs, req.agent_id)
            _whose = "Barry" if req.agent_id in AGENTS else "your owner"''',
r'''            if not _his_seat(req.agent_id):
                _auto = _strip_owner_world(_auto, req.agent_id)
                _dirs = _strip_owner_world(_dirs, req.agent_id)
            _whose = "Barry" if _his_seat(req.agent_id) else "your owner"'''),
])
