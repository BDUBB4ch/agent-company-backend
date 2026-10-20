"""Barry, 2026-09-07: "replace v9 with this." -- the blended REWRITE v1 script
(Betty's Act Zero + V9 Acts One-Three, shots 01A-23A, fights as V9 wrote them,
Scenes A-H out for Episode 2) becomes Elliot's LIVING SCRIPT.

It is installed UNDER THE EXISTING WIP NAME (script_wip.WIP_SOURCE), so
read_scene, the verbatim gate, whole-script delivery, save_script_block /
delete_script_block and the always-on ledger all keep working with no code
change and no restart. The old V9 working copy is backed up to disk AND kept in
the brain as a SUPERSEDED row (never deleted). The duplicate on-demand copy
taught minutes earlier (ep1-rewrite-v1-blended.md) is superseded so only one
script is discoverable.

One-shot: refuses to run twice.
"""
import re
import sys
import pathlib
import datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
import memory          # noqa: E402
import script_wip as sw  # noqa: E402
import script_index as si  # noqa: E402

SRC = pathlib.Path("C:/Users/Owner/Downloads/TALIA_CREW_EP1_REWRITE_v1_FULL.md")
DIV = re.compile(r"^─{100,}\s*$", re.M)        # Betty's 107-char rule lines
MARK = "REWRITE v1 (Betty's Act Zero + V9 Acts One-Three)"

old = sw._get_wip_fact()
assert old, "no active WIP fact found"
assert MARK not in old["content"], "already replaced -- refusing to run twice"

# 1. back up the V9 working copy to disk (the module's own backup dir + name)
sw._backup("replace-with-rewrite", "v9-wip")
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
(REPO / "data" / "script_wip_backups" / f"{stamp}_ledger_before_replace.md").write_text(
    next((f["content"] for f in memory.get_active_facts_for_agent(sw.OFFICE)
          if f.get("source_name") == sw.LEDGER_SOURCE), ""), encoding="utf-8")

# 2. build header + blocks from the blended file
text = SRC.read_text(encoding="utf-8")
parts = [p.strip("\n") for p in DIV.split(text)]
parts = [p for p in parts if p.strip()]
# front matter = everything before the first labelled part
first_label = next(i for i, p in enumerate(parts)
                   if sw._LABEL_RE.match(p.strip().splitlines()[0].strip()))
front = parts[:first_label]
blocks = parts[first_label:]
header = (
    "TALIA CREW SERIES\n"
    'EPISODE 1 -- "WRONG BOX"\n'
    f"Production Script -- {MARK} -- WORK IN PROGRESS (living document)\n"
    "Created by: Barry White (B DUBB)  |  B DUBB Grows LLC\n"
    "This is THE LIVE EP1 production script as of 2026-09-07 (\"replace v9 with this\").\n"
    "Every spoken line is locked -- Barry's words, never changed. Scenes A-H of the old\n"
    "V9 are NOT in this episode (Episode 2). Blocks change here only when Barry approves.\n"
    "Character anchors: the CURRENT canon (character-anchors-card), never older text.\n\n"
    "HOW THE VOICE IDS ARE USED ON HIGGSFIELD (Barry's verified method): the voice id goes\n"
    "in the PROMPT TEXT on the beat where the character speaks -- \"@Bia-2 speaks in voice\n"
    "f32c8f51-449e-4ddf-bdf7-1527e11df917 (Tallulah)\" -- with the spoken line in { }. No\n"
    "clip, no upload. Every shot with dialogue carries its VOICE IDS line: paste it with the\n"
    "prompt, plus the speaker's lock from the table below, verbatim. INTERNAL / INTERNAL\n"
    "MONOLOGUE lines are voice-over for post: no voice id, never in { }. Re-roll before\n"
    "blaming a voice.\n\n"
    + "\n\n".join(front)
)
assert not sw._LABEL_RE.match(header.splitlines()[0]), "header must not start with a label"

# 3. keep the old V9 WIP on record as SUPERSEDED, then write the new one (fresh row)
with memory.get_db() as conn:
    conn.execute("UPDATE facts SET status = 'superseded' WHERE id = ?", (old["id"],))
    conn.execute("UPDATE facts SET status = 'superseded' WHERE source_name = ? AND status = 'active'",
                 ("ep1-rewrite-v1-blended.md",))
sw._write_wip(header, blocks)      # adds the new WIP row + regenerates the ledger

# 4. verify
new = sw._get_wip_fact()
hdr, blks = sw._split_blocks(new["content"])
labels = [sw._block_label(b) for b in blks]
print(f"new WIP fact id={new['id']} chars={len(new['content']):,} blocks={len(blks)}")
print("labelled:", sum(1 for l in labels if l), "| unlabelled (tail/front only):",
      [b.splitlines()[0][:40] for b, l in zip(blks, labels) if not l])
print("shots/b-rolls:", sum(1 for l in labels if l.startswith(("SHOT", "B-ROLL"))))
print("scripts Elliot can reach:", [s["title"] for s in si.list_scripts(sw.OFFICE)])
print("default script:", si.default_script(sw.OFFICE))
r = si.read_scene(sw.OFFICE, "SHOT 09A")
print("read_scene('SHOT 09A') ->", (r.get("label") or r.get("title") or str(r)[:80]),
      "| starts:", (r.get("text") or r.get("content") or "")[:70].encode("ascii", "replace").decode())
led = next(f["content"] for f in memory.get_active_facts_for_agent(sw.OFFICE)
           if f.get("source_name") == sw.LEDGER_SOURCE)
print("ledger first lines:\n  " + "\n  ".join(led.splitlines()[:5]).encode("ascii", "replace").decode())
print("old V9 WIP row:", memory.get_db().__enter__().execute(
    "SELECT status FROM facts WHERE id = ?", (old["id"],)).fetchone()["status"])
