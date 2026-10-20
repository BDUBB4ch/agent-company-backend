"""Add USE WHEN routing lines to Elliot's six prompt-grammar skills.

Part of the 2026-08-16 seedance-interference fix (Barry: "check and see if
the seedance info is interfering. he may not know when to use it"). These
six docs are coming OFF Elliot's pin list -- 40,912 chars (26% of his pins)
of machine grammar was riding on every message including pure story
conversations, and the measured result was prompt-language leaking into
everything (he attempted an image fence on a character-motivation
question). With auto-recall (recall.py) live, on-demand no longer means
"never read": these lines are the routing contract that pulls each doc in
exactly when its job comes up.

The lines are deliberately token-rich and include word-form variants
(write/writing, prompt/prompts) because recall.py matches exact tokens on
the USE WHEN line at 3 points each -- the line is written for the scorer
first, the model second.

Re-runnable: skips any doc that already has a USE WHEN line. Also updates
the matching knowledge/*.md disk copies so DB and disk stay in sync (the
seedance sync-script rule). Only Claude-authored skill docs are touched --
never Barry's authored story files.
"""

import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "brain.db")

# source_name -> USE WHEN line (kept under 200 chars, recall.py's cap)
USE_WHEN = {
    "seedance-prompting.md": (
        "USE WHEN: you write or rewrite a shot, scene, video, or clip prompt "
        "(prompts) for Higgsfield/Seedance -- writing shots, scenes, "
        "references, audio, timestamps."
    ),
    "seedance-production-tasks.md": (
        "USE WHEN: choosing or writing a Seedance task -- edit, editing, "
        "extend, extension, first-frame, keyframes, storyboard, reference "
        "video, ratio, duration parameters."
    ),
    "seedream-image-generation.md": (
        "USE WHEN: generating a Seedream image or still -- image prompts, "
        "posters, character sheets, stills for Higgsfield."
    ),
    "image-prompting.md": (
        "USE WHEN: you write an image fence prompt for a local render -- "
        "diffusion prompt structure, negatives, SDXL limits, palette, crop."
    ),
    "prop-shot-structure.md": (
        "USE WHEN: writing a prop shot, weapon render, or object shot -- "
        "props, weapons, guns, white background product-style renders."
    ),
    "character-image-pipeline.md": (
        "USE WHEN: making character images or renders -- render, Kontext, "
        "SDXL, reference images, LoRA, likeness, canon consistency."
    ),
}

DISK_DIRS = [os.path.join(BASE, "knowledge")]


def add_line(text: str, line: str) -> str | None:
    if "USE WHEN:" in text[:1200]:
        return None
    lines = text.split("\n")
    # After the title line if there is one, else at the very top.
    at = 1 if lines and (lines[0].startswith("#") or len(lines[0]) < 120) else 0
    return "\n".join(lines[:at] + ["", line, ""] + lines[at:])


def main(apply: bool):
    conn = sqlite3.connect(DB)
    for source, line in USE_WHEN.items():
        rows = conn.execute(
            "SELECT id, content FROM facts WHERE source_name=? AND status='active'",
            (source,)).fetchall()
        for fid, content in rows:
            updated = add_line(content, line)
            if updated is None:
                print(f"  skip (has USE WHEN): fact {fid} {source}")
                continue
            print(f"  {'UPDATE' if apply else 'would update'}: fact {fid} {source}")
            if apply:
                conn.execute("UPDATE facts SET content=? WHERE id=?", (updated, fid))
        # Disk twin, when one exists.
        for d in DISK_DIRS:
            path = os.path.join(d, source)
            if os.path.exists(path):
                text = open(path, encoding="utf-8").read()
                updated = add_line(text, line)
                if updated is not None:
                    print(f"  {'WRITE' if apply else 'would write'}: {path}")
                    if apply:
                        open(path, "w", encoding="utf-8", newline="\n").write(updated)
    if apply:
        conn.commit()
        print("Committed.")
    conn.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
