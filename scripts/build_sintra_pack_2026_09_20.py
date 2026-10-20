"""Build a reference pack for Sintra (Barry's script-rewriting agent).

Barry, 2026-09-20: "give me some .md for her to make her better."

Everything here is DERIVED FROM LIVE DATA -- the canon anchors card (Barry's
own words, verbatim), the voice roster, and a real block out of V10. Nothing is
invented; where something is unsettled it says so and points at Barry.
"""
import glob
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import script_wip  # noqa: E402

DEST = r"C:\Users\Owner\Desktop\SINTRA PACK"
os.makedirs(DEST, exist_ok=True)

cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
cur = sqlite3.connect(db[0]).cursor()


def fact(name):
    cur.execute("select content from facts where source_name=? and status='active'", (name,))
    r = cur.fetchone()
    return r[0] if r else ""


anchors = fact("character-anchors-card.md")
v10 = fact(script_wip.WIP_SOURCE)

written = []


def write(fn, body):
    p = os.path.join(DEST, fn)
    open(p, "w", encoding="utf-8").write(body)
    written.append((fn, len(body)))


# ---------------------------------------------------------------- 1. CANON ---
# Strip the office-internal preamble -- she has no read_skill or recall.
body = anchors
i = body.find("=== THE SIX ANCHORS")
core = body[i:] if i > 0 else body
write("1-CANON-characters-weapons-locations.md", f"""# CANON — characters, weapons, locations

**These are Barry's own words, copied verbatim from his canon bible.**

Copy the anchors exactly. Never paraphrase them, never "improve" them, and
never derive a description from looking at a render — where a render disagrees
with these words, **the render is wrong**.

If you think an anchor is wrong, say so and stop. Do not change it. Character
descriptions are already set and changing one needs Barry's explicit yes.

---

{core}
""")

# --------------------------------------------------------- 2. SCRIPT FORMAT ---
header, blocks = script_wip._split_blocks(v10)
example = ""
for b in blocks:
    if script_wip._block_label(b).replace(" ", "").upper() in ("SHOT2", "SHOT02"):
        example = b.strip()
        break

write("2-SCRIPT-FORMAT.md", f"""# The script block format

Every shot in the episode is one block, and every block has the same shape.
Keep it identical across the whole document — this is what makes the script
machine-readable downstream.

## The shape

    SHOT NN — NAME | duration | MUSIC: ...
    GENRE: ... | SPEED RAMP: ...
    INT./EXT. PLACE — TIME.

    <action prose — the beat played moment by moment, with the
     DIALOGUE lines sitting where they actually land in the action>

    CAMERA: lens | movement | framing | film grain
    ENVIRONMENT & LIGHTING: materials, light sources, textures, what the
                            light does NOT reach
    EXPRESSION: per character in frame
    NEG: ...

## Numbering — the thing that broke the last version

**One numbering run for the whole script, no duplicates, no letters.**

V9A.1 carried two runs in one file — an Act Zero numbered 00–05 alongside a
second track numbered 01A–23A. That produced **two SHOT 03s and two SHOT 04s**,
so asking for "shot 3" served the wrong scene and it looked like the system was
handing back old material. It wasn't; the document was ambiguous.

V10 is correct: **B-ROLL 00, 01, 02 and SHOT 00 through SHOT 28.** Keep it that
way. If shots are added, renumber the whole run rather than adding 14A.

## Act headings

Act headings (ACT ZERO, ACT ONE...) sit between blocks and are fine. They are
not shots and carry no number.

## A real block — SHOT 02 from V10

Use this as the reference for spacing, field order and how dialogue sits inside
the action rather than being collected at the end.

```
{example[:2600]}
```
""")

# ------------------------------------------------------ 3. WRITING RULES ---
plain_names = len(re.findall(r"(?<!@)(?<![\w'-])Bia(?![\w-])", v10))
write("3-WRITING-RULES.md", """# Writing rules for this script

## 1. Every mention gets its @handle

Barry's rule, 2026-08-14: *"everytime their name is mentioned, it needs to be
their @ name."* First mention, last mention, and every possessive in between.

The handle is what binds the real asset in the generator. A plain name binds
nothing, so the render invents its own version of that character, that gun or
that ship.

    RIGHT: @Bia-2 fires @Bia's-Pistol*, one plasma ball leaving @Bia-2's emitter
    WRONG: @Bia-2 fires, one plasma ball leaving Bia's emitter

This applies in **every** field, not just the action prose:

    CAMERA:                  close 85mm on @Bia-2's hands
    ENVIRONMENT & LIGHTING:  the @Talia's corridors are minimal
    EXPRESSION:              @Keth: complete stillness
    NEG:                     no characters other than @Bia-2 and @Yannah

Those craft fields are exactly where it slips. Both rewrite passes so far
missed them.

## 2. Handle OUTSIDE the quotes, plain name INSIDE them

**Never put a handle inside spoken dialogue.** The `{}` dialogue channel drives
lip-sync — a handle in there gets pronounced out loud by the generator.

    RIGHT: DIALOGUE (@lady-vor-shara-vel): "Captain Bia. I trust you received the signal."
    WRONG: DIALOGUE (@lady-vor-shara-vel): "Captain @Bia-2. I trust you received the signal."

Characters call each other by their names, the way people do. Only the speaker
LABEL and the surrounding prose carry handles.

Same for a name the script deliberately quotes as a name:

    EXPRESSION: ... The name "Keth" carries weight — she knows who he is.

## 3. Every spoken line names its speaker

    DIALOGUE (@Bia-2): "Forty years. Yes."

Never a bare `DIALOGUE:` with no speaker, and never a second format like
`YANNAH whispers:`. If the delivery matters, put it in the prose or the
EXPRESSION line — the speaker label holds the handle and nothing else.

    WRONG: DIALOGUE (Bia, slow motion on her face): "..."
    RIGHT: DIALOGUE (@Bia-2): "..."     + the slow motion in the prose/CAMERA

## 4. Barry is not a character

18 lines came back attributed to "Barry". **Barry White is the writer.** The
character is **@b-dubb**.

## 5. Dialogue is not yours to change

The events and the spoken lines are Barry's. Scenes, fights, action and camera
are open to craft work, but a line of dialogue stays word for word — never
reworded, never trimmed, never moved to the end of the block. It rides inside
the action at the point it lands.

## 6. Don't invent, don't rename

Never substitute a description for a name that exists, and never invent a name
that does not. Name the weapon by its handle instead of describing it. Use
Barry's name for a place — do not rename it or "improve" it.

If something looks wrong, say so and stop. Don't fix it silently.
""")

# --------------------------------------------------------- 4. VOICES ---
write("4-VOICES-AND-IDS.md", """# Voices and voice IDs

Each character has one voice, and the voice ID is what actually selects it in
the generator. The written lock carries the DIRECTION; the ID carries the voice.

## The roster — one line per character

    @b-dubb              9b162037-e549-4065-9562-ebac293ee72a   B-Dubb-Voice
    @Bia-2               f32c8f51-449e-4ddf-bdf7-1527e11df917   Tallulah
    @Yannah              032386ec-491b-5bdc-81ac-49e9a6a2c89d   Daisy
    @Tazz                3811e986-0891-47cf-a1f5-78a1d62a547a   Imogen
    @Keth                6b528d43-c056-4a2f-9d82-1591a7ba13b0   John
    @lady-vor-shara-vel  d081b915-6623-4a44-bacf-80d0f1c90a03   Nora

**Read the ID and the name off the SAME LINE.** They were crossed once before —
Bia's line came back carrying B Dubb's ID with Tallulah's name next to it,
because the roster was written as one long run-on list and the halves got
paired wrong. That is why it is laid out one per line here.

`@b-dubb`'s fallback, if his own voice ever fails, is **Sterling**
(`dc382508-c8bd-443c-8cb2-46e57b8d2e6f`). Barry's call, not an automatic swap.

## Where the IDs live in the script

In the **VOICE LOCKS table at the top of the document**. Keep that table
intact — it is the only place the IDs are recorded.

⚠️ **Export to `.md`, never `.docx`.** A `.docx` export flattened that table
and silently dropped @Keth's ID entirely. Nobody noticed until it was checked
against the roster.

## The direction, in Barry's words

    @Keth                higher-pitched voice, slightly synthesized
    @lady-vor-shara-vel  gritty, vengeful, a little deeper
    @Yannah              smart but sexy
    @Bia-2               direct, the leader
    @Tazz                deeper
    @b-dubb              clean

Vor'Shara is **stern** toward B Dubb, not hateful — she knows humans, he does
not yet know aliens. Barry's correction, and it matters for how her lines read.
""")

print("WROTE ->", DEST)
for fn, n in written:
    print(f"  {n:>7,}  {fn}")
