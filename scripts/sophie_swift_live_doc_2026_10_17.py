"""2026-10-17: Barry: "it seems sophie is behind, she doesnt know swift is up". Bring her model-swap skill (fact 3936,
swapping-the-bonsai-model.md) up to date: Swift 1.5 is the live trial since 2026-10-15, set by a .env block, plus the
rollback. Old content backed up to data/ first. Run once."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

FID = 3936
OLD_HEAD = "| value (backend/config.py) | Bonsai 1 (on disk) | Bonsai 2 (LIVE since 2026-09-24) |"
NEW_HEAD = "| value (backend/config.py) | Bonsai 1 (on disk) | Bonsai 2 (live 2026-09-24 to 10-15; the rollback) |"
ANCHOR = "## The procedure"
SWIFT = """## LIVE NOW: the Swift 1.5 trial (since 2026-10-15)
Barry, 2026-10-15: "after that we try swift". All ten seats run Swift 1.5 Qwen3.8-27B Uncensored, UD-IQ3_S
(models/swift15/), through the same llama-server and the same "bonsai" backend name -- "Bonsai" in the code means
"the office's llama-server model", not only the Ternary-Bonsai files.
It is set by the SWIFT TRIAL block in .env (an env var beats config.py), not by editing config.py:
| value | Swift trial |
|---|---|
| BONSAI_MODEL_PATH | models/swift15/Swift-1.5-Qwen3.8-27B-Uncensored-Dynamic-MTP-UD-IQ3_S.gguf |
| BONSAI_MMPROJ_PATH | models/swift15/mmproj-BF16.gguf |
| BONSAI_NUM_CTX | 98304 |
| BONSAI_KV_TYPE | q4_0 |
| BONSAI_SPEC_TYPE | draft-mtp (its own built-in draft heads), BONSAI_EXTRA_ARGS --spec-draft-n-max 2 + q4_0 draft cache |
| BONSAI_TEMP | 1.0 |
| BONSAI_MODEL_NAME | Swift-1.5-Qwen3.8-27B-IQ3_S (env-overridable since 2026-10-17) |
Measured 2026-10-15 on his machine: ~40 tok/s writing, ~738 tok/s reading the prompt, 14.4 GB on the card, no spill.
It only fits because the monitor now runs on the motherboard (Intel UHD 770, BIOS iGPU Multi-Monitor on) -- the AMD
card is AI-only. If the monitor goes back on the AMD card, Swift at 98304 spills. Research and numbers:
docs/research/swift-1.5-27b-on-16gb-2026-10-15.md.
Until 2026-10-17 the office still SHOWED "Ternary-Bonsai-2-27B" while Swift ran (the name was hard-coded) -- that is
why you thought Bonsai 2 was live. Trust the server's load line in data/bonsai_server.log ("load_model: loading
model ...") over any label.
Rollback to Bonsai 2 (Barry's call only): delete the SWIFT TRIAL block from .env (backup:
data/backup_env_before_swift_trial_2026-10-15_2232), run memory.set_active_generation('bonsai', 'Ternary-Bonsai-2-27B'),
then restart -- and confirm llama-server reloaded the Bonsai 2 file.

"""

memory.init_db()
with memory.get_db() as conn:
    old = conn.execute("SELECT content FROM facts WHERE id=?", (FID,)).fetchone()[0]
if "LIVE NOW: the Swift 1.5 trial" in old:
    sys.exit("already there -- nothing changed")
assert OLD_HEAD in old and ANCHOR in old, "doc changed since this script was written -- check fact 3936"
bak = os.path.join(ROOT, "data", "backup_fact3936_before_swift_2026-10-17.md")
open(bak, "w", encoding="utf-8").write(old)
new = old.replace(OLD_HEAD, NEW_HEAD).replace(ANCHOR, SWIFT + ANCHOR, 1)
new = new.replace("which model is live,", "which model is live, swift, swift 1.5, qwen3.8, trial, rollback,", 1)
with memory.get_db() as conn:
    conn.execute("UPDATE facts SET content=? WHERE id=?", (new, FID))
print("backup:", bak)
print(len(old), "->", len(new))
