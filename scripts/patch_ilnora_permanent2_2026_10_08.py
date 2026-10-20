r"""One-off patch (2026-10-08, part 2 of "Ilnora is permanent"): a hire he keeps (KNOWS_ABOUT "everything") is NOT
rewritten owner-neutral at prompt-build time. She still gets no business TEAM block (not a business seat)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "agents.py"), [
(r'''def build_hired_agent_prompt(name: str, role: str, job_description: str, business_context: bool = True) -> str:''',
 r'''def build_hired_agent_prompt(name: str, role: str, job_description: str, business_context: bool = True,
                             his: bool = False) -> str:'''),
(r'''    # verbatim. See for_a_stranger's `keep`.
    return for_a_stranger(out, keep=(job_description.strip(), role, name))''',
 r'''    # verbatim. See for_a_stranger's `keep`.
    # A HIRE HE KEEPS (2026-10-08, Barry: "i told you before, Ilnora is permanent"): KNOWS_ABOUT "everything" means
    # his world is hers -- no owner-neutral rewrite (she still gets no business team block: not a business seat).
    if his:
        return out
    return for_a_stranger(out, keep=(job_description.strip(), role, name))'''),
])

patch(os.path.join(ROOT, "backend", "main.py"), [
(r'''        "system_prompt": build_hired_agent_prompt(
            record["name"], record["role"], record["job_description"],
            business_context=business_context,
        ),''',
 r'''        "system_prompt": build_hired_agent_prompt(
            record["name"], record["role"], record["job_description"],
            business_context=business_context,
            # 2026-10-08: a hire he keeps (KNOWS_ABOUT "everything" -- Ilnora) is not rewritten owner-neutral
            his="everything" in memory.knows_about(office),
        ),'''),
])
