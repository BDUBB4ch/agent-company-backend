"""Camera sweep of EP1 V9A.1 -- Barry's explicit go, 2026-09-16 ("do the camera sweep").

WHY: measured on his own Higgsfield renders -- a shot whose camera line says
"static / locked / no push / the frame holds" comes back as a frozen frame with
audio over it. 24 of 32 blocks in the live script carried that language, so three
quarters of the episode was instructing the generator to hold still.

WHAT THIS DOES NOT TOUCH, deliberately:
  * NEG: lines. "NEG: static, wide, glamour" is a NEGATIVE prompt -- it already
    says do not be static. Rewriting it would invert Barry's meaning.
  * Character stillness. Keth's "trained stillness", Tazz "moving with the same
    stillness", "@keth: complete stillness" -- that is ACTING, not camera, and it
    is some of the best writing in the script.
  * Mood/sound stillness. "each one audible in the stillness", "The stillness is
    eerie after the noise" -- environment, not camera.
  * Dialogue, beats, canon, structure. Camera instructions only.

SPEED RAMP lines: "Static" there means "no time ramp", not a camera state -- so it
becomes "Constant", which preserves Barry's meaning and removes the word that
poisons the render.

Backup taken before this ran:
  data/script_backups/v9A.1_before_camera_sweep_2026-09-16.md
Revert = write that file back over fact 2282 and the Downloads copy.
"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")
DISK = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_PRODUCTION_V9A.1.md"
FACT_ID = 2282

# (line index, exact substring to replace, replacement)
EDITS = [
    # --- SPEED RAMP lines: "Static" = no time ramp, not a camera state ---
    (63, "SPEED RAMP: Static Locked", "SPEED RAMP: Constant"),
    (77, "SPEED RAMP: Static to Slow Motion", "SPEED RAMP: Constant to Slow Motion"),
    (150, "SPEED RAMP: Static", "SPEED RAMP: Constant"),
    (240, "SPEED RAMP: Static to Slow Motion", "SPEED RAMP: Constant to Slow Motion"),
    (286, "SPEED RAMP: Static", "SPEED RAMP: Constant"),
    (304, "SPEED RAMP: Static Locked", "SPEED RAMP: Constant"),
    (370, "SPEED RAMP: Static Locked", "SPEED RAMP: Constant"),
    (398, "SPEED RAMP: Static Locked", "SPEED RAMP: Constant"),
    (460, "SPEED RAMP: Full Speed to Static", "SPEED RAMP: Full Speed to Constant"),
    (535, "SPEED RAMP: Static", "SPEED RAMP: Constant"),
    (626, "SPEED RAMP: Static to Slow Motion", "SPEED RAMP: Constant to Slow Motion"),
    (650, "SPEED RAMP: Static to Slow Motion", "SPEED RAMP: Constant to Slow Motion"),
    (698, "SPEED RAMP: Static", "SPEED RAMP: Constant"),
    (812, "SPEED RAMP: Static", "SPEED RAMP: Constant"),
    (897, "SPEED RAMP: Static", "SPEED RAMP: Constant"),

    # --- B-ROLL 00: the ship cruising ---
    (67, "Static locked 24mm.", "Slow lateral drift, 24mm."),
    (69, "24mm | static locked |", "24mm | slow lateral drift |"),

    # --- SHOT 00 bridge ---
    (98, "CAMERA: Static 50mm on Bia at console",
         "CAMERA: Slow drift 50mm on Bia at console"),

    # --- the Vor'Shara call ---
    (193, "CAMERA: Static 50mm on Bia's face",
          "CAMERA: Slow drift 50mm on Bia's face"),

    # --- the Talia dropping toward Earth ---
    (290, "Static locked 24mm.", "Slow push, 24mm."),
    (292, "24mm | static locked |", "24mm | slow push |"),

    # --- ridge line establishing ---
    (308, "STATIC LOCKED \u2014 24mm wide establishing.",
          "SLOW PUSH \u2014 24mm wide establishing."),
    (308, "Camera does not move.",
          "The camera pushes in almost imperceptibly, never fully still."),
    (310, "24mm | static locked |", "24mm | slow push |"),

    # --- B Dubb's face, extreme close ---
    (374, "STATIC LOCKED \u2014 85mm, extreme close",
          "IMPERCEPTIBLE PUSH \u2014 85mm, extreme close"),
    (374, "Camera does not move.",
          "The camera creeps in almost imperceptibly, never fully still."),
    (384, "CAMERA HOLDS \u2014 static on empty ridge",
          "CAMERA LINGERS \u2014 a near-imperceptible drift on the empty ridge"),
    (386, "CAMERA: Static lock \u2014 85mm | extreme close | no movement |",
          "CAMERA: Imperceptible push \u2014 85mm | extreme close | minimal drift |"),

    # --- the black site, low angle ---
    (402, "STATIC LOCKED \u2014 35mm low angle", "SLOW RISE \u2014 35mm low angle"),
    (404, "35mm | static locked |", "35mm | slow rise |"),
    (418, "| static on crouch between arcs |",
          "| the arc slows but never stops between passes |"),

    # --- service corridor ---
    (464, "Camera static, 50mm,", "Camera drifting slowly, 50mm,"),
    (466, "CAMERA: Static 50mm |", "CAMERA: Slow drift 50mm |"),

    # --- after Tazz wrecks the room ---
    (543, "| static on the destroyed room |",
          "| slow drift across the destroyed room |"),

    # --- the lab: finding Keth ---
    (585, "Static 85mm.", "Slow push, 85mm."),
    (590, "CAMERA: Static 85mm, dolly forward slow",
          "CAMERA: 85mm, dolly forward slow"),

    # --- inside the case ---
    (636, "CAMERA: Static extreme close inside case",
          "CAMERA: Slow drift, extreme close inside case"),

    # --- cargo hold, crew enters ---
    (663, "| camera settles static |", "| camera settles into a slow drift |"),
]


def main():
    con = sqlite3.connect(DB)
    text = con.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()[0]
    before = text

    disk_matched = False
    if os.path.exists(DISK):
        with open(DISK, encoding="utf-8") as fh:
            disk_matched = fh.read() == text

    lines = text.split("\n")
    applied, failed = 0, []
    for lineno, old, new in EDITS:
        if lineno >= len(lines):
            failed.append((lineno, old, "line out of range"))
            continue
        line = lines[lineno]
        if line.count(old) != 1:
            failed.append((lineno, old, "found %d times" % line.count(old)))
            continue
        lines[lineno] = line.replace(old, new, 1)
        applied += 1

    if failed:
        print("ABORTED -- nothing written. Failed edits:")
        for lineno, old, why in failed:
            print("  line %s  %r  -> %s" % (lineno, old[:50], why))
        return 1

    out = "\n".join(lines)
    # Length sanity: this sweep only rewords camera instructions.
    print("chars %d -> %d  (delta %+d)" % (len(before), len(out), len(out) - len(before)))
    print("edits applied: %d" % applied)

    con.execute("update facts set content=? where id=?", (out, FACT_ID))
    con.commit()
    con.close()

    if disk_matched:
        with open(DISK, "w", encoding="utf-8") as fh:
            fh.write(out)
        print("disk copy updated (it was byte-identical before)")
    elif os.path.exists(DISK):
        print("WARNING: disk copy already differed from the fact -- NOT touched.")

    # What survives, and it should: NEG lines, acting, mood.
    low = out.lower()
    print()
    print("after the sweep:")
    print("  'static' remaining : %d" % low.count("static"))
    print("  'stillness'        : %d" % low.count("stillness"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
