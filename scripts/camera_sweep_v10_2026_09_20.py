"""Sweep the static-camera language out of V10.

Barry, 2026-09-20: "update the script for him too."

Same sweep applied to V9A.1 on 2026-09-16 (38 edits) on his go. V10 came from a
source that predates it, so all 37 came back. Measured basis: seven of his own
finished Higgsfield clips diffed frame by frame -- `static`/`no push`/`holding`
shots averaged ~3 frame-to-frame motion against ~13 for `slow push-in`, and the
Talia B-ROLL decayed to 0.9 and froze for its last 2.5 seconds.

DELIBERATELY NOT TOUCHED, and any future sweep must skip these too:
  * NEG: lines -- "no static" there is a NEGATIVE; flipping it inverts his meaning
  * character stillness -- "@keth: complete stillness" is ACTING
  * mood/atmosphere stillness in the prose
  * spoken dialogue
  * the VOICE LOCKS header table

Edits BOTH copies (the fact Elliot reads and Barry's .md), and backs up first.
"""
import glob
import os
import re
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402
import script_wip  # noqa: E402

MD = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
BAK_DIR = os.path.join(ROOT, "data", "script_backups")
os.makedirs(BAK_DIR, exist_ok=True)

# (pattern, replacement, why) -- ordered, longest/most specific first
RULES = [
    # SPEED RAMP is about TIME, not camera. "Static" there means "no time ramp",
    # so "Constant" is the same instruction without the poisoned word.
    (r"(\*\*SPEED RAMP:\*\*|SPEED RAMP:)\s*Static Locked\b", r"\1 Constant", "speed ramp"),
    (r"(\*\*SPEED RAMP:\*\*|SPEED RAMP:)\s*Static to\b", r"\1 Constant to", "speed ramp"),
    (r"(\*\*SPEED RAMP:\*\*|SPEED RAMP:)\s*Full Speed to Static\b",
     r"\1 Full Speed to Constant", "speed ramp"),
    (r"(\*\*SPEED RAMP:\*\*|SPEED RAMP:)\s*Static\b", r"\1 Constant", "speed ramp"),

    # explicit "do not move" instructions
    (r"Camera does not move\.", "The camera creeps in almost imperceptibly, never fully still.", "camera"),
    (r"CAMERA HOLDS\s*[—–-]\s*static on", "The camera drifts a hair on", "camera"),
    (r"\bcamera settles static\b", "camera settles into a near-imperceptible drift", "camera"),
    (r"\|\s*no movement\s*\|", "| minimal drift |", "camera"),

    # STATIC LOCKED as a prose/camera opener
    (r"STATIC LOCKED\s*[—–-]\s*", "NEAR-IMPERCEPTIBLE DRIFT — ", "camera"),
    (r"\bStatic locked (\d+mm)", r"\1, near-imperceptible drift", "camera"),
    (r"\bstatic locked (\d+mm)", r"\1, near-imperceptible drift", "camera"),
    (r"(\d+mm)\s*\|\s*static locked\b", r"\1 | near-imperceptible drift", "camera"),
    (r"\bStatic lock\s*[—–-]\s*(\d+mm)", r"\1, near-imperceptible drift", "camera"),
    (r"\bStatic (\d+mm)", r"\1, slow drift", "camera"),
    (r"\bstatic on the destroyed room\b", "drifting slowly across the destroyed room", "camera"),
    # second pass, 2026-09-20 -- three camera phrasings the first pass missed
    # because they are not followed by a lens number
    (r"\bCamera static, (\d+mm)", r"Camera drifting a hair, \1", "camera"),
    (r"\bStatic extreme close\b", "Near-imperceptible drift, extreme close", "camera"),
    (r"\bstatic on crouch between arcs\b", "a hair of drift on the crouch between arcs", "camera"),
    # ⚠️ DELIBERATELY NOT SWEPT: "The flood light from below remains static,
    # unmoving" (ENVIRONMENT, ~L300). That describes a FIXED FLOODLIGHT, not
    # the camera, and a light that does not move is correct filmmaking. Two
    # freeze-words in a prompt is a mild risk, but rewording Barry's
    # environment prose is not what this sweep was authorised to do. Flagged
    # to him instead.
]

SKIP_LINE = re.compile(r"^\**NEG\b", re.I)


def sweep(text: str, label: str) -> tuple[str, list]:
    lines = text.split("\n")
    edits = []
    for i, line in enumerate(lines):
        if SKIP_LINE.match(line.strip()):
            continue                                  # NEG: is a negative
        new = line
        for pat, rep, why in RULES:
            new2 = re.sub(pat, rep, new)
            if new2 != new:
                edits.append((i + 1, why, new.strip()[:110], new2.strip()[:110]))
                new = new2
        lines[i] = new
    return "\n".join(lines), edits


def main() -> int:
    stamp = "2026-09-20_motion"

    # ---- the fact Elliot reads ---------------------------------------------
    cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
    db = [c for c in cands if "brain" in os.path.basename(c)] or cands
    cur = sqlite3.connect(db[0]).cursor()
    cur.execute("select id, content from facts where source_name=? and status='active'",
                (script_wip.WIP_SOURCE,))
    fid, fact_text = cur.fetchone()
    open(os.path.join(BAK_DIR, f"v10_fact_before_{stamp}.md"), "w",
         encoding="utf-8").write(fact_text)

    new_fact, edits = sweep(fact_text, "fact")
    print(f"=== {len(edits)} edits ===")
    for ln, why, was, now in edits:
        print(f"\n  L{ln} [{why}]")
        print(f"    was: {was}")
        print(f"    now: {now}")

    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new_fact, fid))

    # ---- Barry's .md, kept in step -----------------------------------------
    if os.path.exists(MD):
        shutil.copy2(MD, os.path.join(BAK_DIR, f"v10_md_before_{stamp}.md"))
        md_text = open(MD, encoding="utf-8").read()
        new_md, md_edits = sweep(md_text, "md")
        open(MD, "w", encoding="utf-8").write(new_md)
        print(f"\n.md: {len(md_edits)} edits")

    # ---- verify -------------------------------------------------------------
    print("\n=== verification (NEG lines and character stillness excluded) ===")
    BAD = r"(static\s+lock(?:ed)?|locked[- ]off|\bstatic\b|no push|no movement|frame holds|camera does not move|CAMERA HOLDS)"
    left = []
    for i, line in enumerate(new_fact.split("\n")):
        s = line.strip()
        if SKIP_LINE.match(s):
            continue
        for m in re.finditer(BAD, s, re.I):
            left.append((i + 1, m.group(0), s[:110]))
    print(f"  camera-static language left: {len(left)}")
    for ln, tok, s in left:
        print(f"    L{ln} [{tok}]  {s}")

    neg = len(re.findall(r"^\**NEG\b.*\bstatic\b", new_fact, re.I | re.M))
    print(f"  NEG lines still saying 'no static' (correct, untouched): {neg}")
    still = len(re.findall(r"complete stillness|stillness\b", new_fact, re.I))
    print(f"  character/mood stillness left (acting, untouched): {still}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
