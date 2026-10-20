"""Amara face pass v2 -- her BROWS, which v1 missed entirely.

Barry, 2026-08-29: "Amaras look good but I still don't see her bushy eyebrows
and the way she looks now."

WHY v1 MISSED: the instruction described her generically ("Greek woman, olive
skin, freckles, hazel eyes, auburn hair") and never named a single distinctive
feature. The editor duly produced a generic pretty face with thin groomed arch
brows. Her actual portrait (agent_face_business.png, opened at native res) is
dominated by HEAVY, STRAIGHT, DARK, UNPLUCKED BROWS that nearly meet -- that
one feature IS her face, and it was not in the prompt.

Body, pose, room and lighting stay untouched -- he said the body is perfect.
"""
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qwen_edit  # noqa: E402

HOMES = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes")
INPUT = os.path.join(ROOT, "tools", "ComfyUI", "input")
DATA = os.path.join(ROOT, "data")
SRC = os.path.join(HOMES, "business_me.png")

# Written from her portrait, opened at native resolution. Brows FIRST because
# front position is weight -- the lesson that fixed the wrong-race renders.
INSTRUCTION = (
    "Change ONLY the woman's face in image 1 to the face of the woman in "
    "image 2. Her eyebrows are the most important feature and they are wrong "
    "in image 1: give her THICK, HEAVY, STRAIGHT, DARK BROWN, COMPLETELY "
    "UNPLUCKED eyebrows that sit low and close to her eyes and almost meet in "
    "the middle — bold and natural, absolutely not thin, not arched, not "
    "groomed. Also match image 2 exactly: hazel green-brown eyes, clear "
    "freckles scattered high across both cheeks and the bridge of her nose, "
    "warm olive-tan skin, a strong straight nose, full natural lips, and a "
    "defined jaw. Keep her body, her figure, her pose, her hair, her hands, "
    "the room, the paintings and the lighting of image 1 completely "
    "unchanged. Change nothing except the face."
)


def flag(on):
    p = os.path.join(DATA, "video_rendering.flag")
    try:
        if on:
            open(p, "w").write(str(time.time()))
        else:
            os.remove(p)
    except OSError:
        pass


def main():
    assert os.path.isfile(SRC), "no current Amara image"
    backup = os.path.join(HOMES, "_before_face_fix_2026-08-29",
                          "business_me_v1face.png")
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    shutil.copyfile(SRC, backup)
    print(f"backed up current -> {os.path.basename(backup)}")

    staged = "amara_facefix2.png"
    shutil.copyfile(SRC, os.path.join(INPUT, staged))
    flag(True)
    try:
        out = qwen_edit.run([staged, "agent_face_business.png"], INSTRUCTION,
                            prefix="amara_face_v2", timeout=4800)
        shutil.copyfile(out, SRC)
        print(f"done -> homes/business_me.png  (from {os.path.basename(out)})")
    finally:
        flag(False)


if __name__ == "__main__":
    main()
