"""Read-only audit of Elliot's always-on load. Prints per-fact size so the
bloat can be identified before the diet. Does NOT change anything."""
import pathlib, sqlite3, sys
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import memory
m = memory.Memory(str(REPO / "data" / "brain.db"))
agent = "movie"
block = m.brain_context_block(agent)
print("ELLiot ALWAYS-ON TOTAL:", len(block), "chars")
facts = [f for f in m.get_agent_facts(agent) if f.get("always_on")]
print("\nPER-FACT (always-on, sorted by size):")
for f in sorted(facts, key=lambda x: -x.get("chars", 0)):
    print(f"  {f.get('chars'):>8}  {f.get('category','?'):28}  {f.get('source_name','?')[:60]}")
print("\nDOMAIN GRANTS (what routes skills to him):")
con = sqlite3.connect(str(REPO / "data" / "brain.db"))
for r in con.execute("SELECT * FROM grants WHERE agent_id=? OR agent_name=?", (agent, agent)):
    print("  ", r)
con.close()
