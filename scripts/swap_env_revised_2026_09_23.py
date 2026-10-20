"""Barry, 2026-09-23: "put the cut lines back, then swap."

Swaps the merged ENV_REVISED scripts in as Elliot's only EP1 and EP2.
In place (UPDATE), no backup copies kept -- his standing script-version rule.
EP1 keeps its plumbing source_name (script_wip.WIP_SOURCE) so read_scene / the
verbatim gate / save_script_block keep working with no restart.
"""
import re, sys, sqlite3
sys.path.insert(0, "backend")
import memory, script_wip, agent_files

SEP = script_wip._SEP

def tidy(t):
    return re.sub(r"\n{3,}", "\n\n", t).strip() + "\n"

ep1 = tidy(open("data/merged_EP1.md", encoding="utf-8").read())
# WIP format: the V7 separator line before every shot / b-roll / scene block
ep1 = re.sub(r"\n(?=## (SHOT|B-ROLL|SCENE)\b)", "\n" + SEP + "\n\n", ep1)
ep2 = tidy(open("data/merged_EP2.md", encoding="utf-8").read())

with memory.get_db() as conn:
    n1 = conn.execute("UPDATE facts SET content=? WHERE id=3683 AND source_name=?",
                      (ep1, script_wip.WIP_SOURCE)).rowcount
    n2 = conn.execute("UPDATE facts SET content=?, source_name=? WHERE id=3893",
                      ("TALIA CREW EP2 PRODUCTION V2 -- ENVIRONMENT REVISED\n" + ep2,
                       "talia-crew-ep2-production-v2.md")).rowcount
assert n1 == 1 and n2 == 1, (n1, n2)

header, blocks = script_wip._split_blocks(ep1)
script_wip._regenerate_ledger(blocks)
print("EP1 blocks:", len(blocks), "| EP1 chars:", len(ep1), "| EP2 chars:", len(ep2))

# Barry's copies on his DESK (Elliot's shelf)
for fn, body, what in [
    ("TALIA_CREW_EP1_V11_ENV_REVISED_merged.md", ep1,
     "EP1 V11 environment revision with every cut line put back"),
    ("TALIA_CREW_EP2_V2_ENV_REVISED_merged.md", ep2,
     "EP2 V2 environment revision with every cut line put back"),
]:
    r = agent_files.write_file("MovieDirector", fn, body, what)
    print("desk:", r if isinstance(r, str) else {k: r.get(k) for k in ("ok", "filename", "approval_id", "error")})
