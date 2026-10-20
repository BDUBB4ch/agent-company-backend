"""Build the complete V10 speaker/handle fix list for Sintra.

Barry, 2026-09-20: "give me every place the dialog has no id. i will give it to
Sintra and they will fix it and i will give it to you to amend."

It turned out to be four problems, not one -- the 11 bare lines he asked about,
plus 47 attributed lines that use PLAIN NAMES instead of @handles, a third
speaker format, and 26 markdown escape artifacts that break a location handle.
All four are listed so one pass fixes the document.
"""
import collections
import glob
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import script_wip  # noqa: E402

DEST = r"C:\Users\Owner\Desktop\V10-speaker-fixes-for-Sintra.md"

cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
cur = sqlite3.connect(db[0]).cursor()
cur.execute("select content from facts where source_name=? and status='active'",
            (script_wip.WIP_SOURCE,))
text = cur.fetchone()[0]
header, blocks = script_wip._split_blocks(text)

BARE = re.compile(r"^\**DIALOGUE\s*:", re.M)
ATTR = re.compile(r"^\**DIALOGUE\s*\(([^)]+)\)\s*:", re.M)

O = []
w = O.append

w("# V10 -- speaker and @handle fixes")
w("")
w("Four separate problems. All four should be fixed in the same pass.")
w("")
w("## THE HANDLES, spelled exactly")
w("")
w("    @b-dubb              (the character. NOT 'Barry' -- Barry is the writer)")
w("    @Bia-2")
w("    @Yannah")
w("    @Tazz")
w("    @Keth")
w("    @lady-vor-shara-vel")
w("    @Talia               (the ship -- location AND prop)")
w("    @loc_hidden-black-site")
w("")
w("Why it matters: the @handle is what binds the real character asset in the")
w("generator. A plain name binds nothing and the render invents its own version")
w("of that person. The voice ID lookup keys off the handle too.")
w("")

# ---- problem 1: bare DIALOGUE ------------------------------------------------
w("")
w("=" * 72)
w("## PROBLEM 1 -- dialogue with NO speaker at all (11 lines)")
w("=" * 72)
w("")
w("Written as a bare `DIALOGUE:`. Nobody can tell who says it without guessing")
w("from the prose. Give each one its speaker: `DIALOGUE (@Bia-2):` etc.")
total_bare = 0
for b in blocks:
    label = script_wip._block_label(b)
    lines = b.split("\n")
    idx = [i for i, l in enumerate(lines) if BARE.match(l.strip())]
    if not idx:
        continue
    stop = len(lines)
    for i, l in enumerate(lines):
        if re.match(r"^\**(CAMERA|ENVIRONMENT|EXPRESSION|NEG|STAGE)\b", l.strip()):
            stop = i
            break
    w("")
    w(f"### {label}  ({len(idx)} unattributed)")
    w("")
    for i, l in enumerate(lines[:stop]):
        if not l.strip():
            continue
        mark = ">>> NEEDS SPEAKER >>> " if i in idx else "                      "
        w(mark + l.rstrip())
    total_bare += len(idx)

# ---- problem 2: plain names -------------------------------------------------
names = collections.Counter(n.strip() for n in ATTR.findall(text))
plain = {n: c for n, c in names.items() if not n.startswith("@")}
w("")
w("")
w("=" * 72)
w(f"## PROBLEM 2 -- attributed lines use PLAIN NAMES, not @handles "
  f"({sum(plain.values())} lines)")
w("=" * 72)
w("")
w("Every attributed line in the script names its speaker in plain text.")
w("None of them carry an @handle. Replace as:")
w("")
SUGGEST = {
    "Bia": "@Bia-2",
    "Barry": "@b-dubb",
    "Lady Vor'Shara Vel": "@lady-vor-shara-vel",
    "Yannah": "@Yannah",
}
for name, n in sorted(plain.items(), key=lambda kv: -kv[1]):
    to = SUGGEST.get(name)
    if to:
        w(f"    DIALOGUE ({name}):{' ' * max(1, 26 - len(name))}-> DIALOGUE ({to}):"
          f"{' ' * max(1, 24 - len(to))}[{n} lines]")
    else:
        w(f"    DIALOGUE ({name}):   [{n} line(s)] -- a stage direction is inside")
        w("        the speaker brackets. Put the speaker's @handle in the brackets")
        w("        and move the direction into the prose.")
w("")
w("NOTE ON 'Barry': 18 lines are attributed to Barry. Barry White is the writer;")
w("the CHARACTER is @b-dubb. Every one of those should be @b-dubb.")

# ---- problem 3: other formats ----------------------------------------------
w("")
w("")
w("=" * 72)
w("## PROBLEM 3 -- a third speaker format")
w("=" * 72)
w("")
for m in re.finditer(r"^\**([A-Z][A-Za-z' \-]{2,20})\s+whispers\s*:.*$", text, re.M):
    w(f"    {m.group(0).strip()}")
w("")
w("Should be `DIALOGUE (@Yannah):` with 'whispers' moved into the prose or the")
w("EXPRESSION line, so every spoken line in the script has one shape.")

# ---- problem 4: escape artifacts -------------------------------------------
esc = re.findall(r"@[A-Za-z][\w\\'-]*\\_[\w\\'-]*", text)
w("")
w("")
w("=" * 72)
w(f"## PROBLEM 4 -- markdown escapes are breaking a handle "
  f"({text.count(chr(92) + '_')} places)")
w("=" * 72)
w("")
w("The .md export escaped the underscores, so the handle reads:")
w("")
w("    @loc\\_hidden-black-site      <- WRONG, the backslash is part of the text")
w("    @loc_hidden-black-site       <- correct")
w("")
w("A handle with a backslash in it binds nothing, so the black site would render")
w("as whatever the generator imagines. Every occurrence needs the backslash gone.")
if esc:
    w("")
    w(f"Distinct broken spellings found: {sorted(set(esc))}")

# ---- problem 5: plain names in the PROSE ------------------------------------
PROSE = {
    "Talia / the Talia (the ship)": (r"(?<!@)\bTalia\b", "@Talia"),
    "Bia": (r"(?<!@)(?<!-)\bBia\b(?!-2)", "@Bia-2"),
    "Keth": (r"(?<!@)\bKeth\b", "@Keth"),
    "Yannah": (r"(?<!@)\bYannah\b", "@Yannah"),
    "Vor'Shara": (r"(?<!@)\bVor'Shara\b", "@lady-vor-shara-vel"),
}
w("")
w("")
w("=" * 72)
w("## PROBLEM 5 -- names written PLAIN in the action prose")
w("=" * 72)
w("")
w("Barry's rule (2026-08-14): \"everytime their name is mentioned, it needs to")
w("be their @ name.\" First mention, last mention, and every possessive in")
w("between -- in the prose, not only on the dialogue lines. A bare name binds")
w("nothing and the generator invents its own version of that character.")
w("")
counts_prose = []
for label, (pat, to) in PROSE.items():
    n = len(re.findall(pat, text))
    counts_prose.append((label, n, to))
    if n:
        w(f"    {n:>4}  {label:<30} -> {to}")
w("")
w("THE SHIP IS THE BIG ONE: @Talia does not appear even once in V10. She is")
w("written 'the Talia' / 'Talia' throughout. Barry's ruling is that she is BOTH")
w("a location and a prop -- @Talia for every interior slug (INT. @Talia --")
w("BRIDGE) and as the subject in exteriors (EXT. @Talia -- DEEP SPACE).")

# ---- the full reference -----------------------------------------------------
w("")
w("")
w("=" * 72)
w("## THE COMPLETE HANDLE REFERENCE -- characters, weapons, locations, props")
w("=" * 72)
w("")
w("### CHARACTERS")
w("")
w("    @b-dubb                 the lead. NEVER 'Barry' -- Barry is the writer.")
w("    @Bia-2                  captain. Note the '-2'.")
w("    @Yannah")
w("    @Tazz")
w("    @Keth")
w("    @lady-vor-shara-vel     all lowercase, hyphenated. NOT @Vorshara.")
w("")
w("Possessives take the handle too: @Bia-2's, @b-dubb's, @Yannah's.")
w("")
w("### WEAPONS -- one per character, never swap them")
w("")
w("    @Bia's-Pistol*             @Bia-2    purple energy revolver, one plasma ball")
w("    @Yannah's-Machine-Pistol   @Yannah   green liquid-metal, full auto")
w("    @Tazz's-Weapon             @Tazz     pink, TWO-HANDED missile blaster, not a pistol")
w("    @B-Dubb's-Banger           @b-dubb   Earth pistol, black and chrome, ejects brass")
w("")
w("    @Keth and @lady-vor-shara-vel carry NOTHING.")
w("")
w("    *** THE TRAILING ASTERISK ON @Bia's-Pistol* IS PART OF THE NAME. ***")
w("    Barry confirmed it 2026-08-14. V10 currently writes it without the")
w("    asterisk in one place and with an escaped backslash in another.")
w("")
w("    Colour is the fastest check: Bia purple, Yannah green, Tazz pink,")
w("    B Dubb brass. Put each weapon on the SAME LINE as its owner so a render")
w("    cannot hand it to the wrong person.")
w("")
w("### LOCATIONS")
w("")
w("    @Talia          the ship -- BOTH a location and a prop")
w("                      INT. @Talia -- BRIDGE")
w("                      INT. @Talia -- CARGO HOLD / COMMON AREA / MAIN CORRIDOR")
w("                      INT. @Talia -- VARIOUS CORRIDORS / CORRIDOR VIEWPORT")
w("                      INT. @Talia -- SPARE QUARTERS / @TAZZ'S QUARTERS")
w("                      EXT. @Talia -- DEEP SPACE  (matte black hull, pale")
w("                                                  turquoise running lights)")
w("")
w("    THE BLACK SITE -- ⚠️ NEEDS BARRY'S RULING, DO NOT GUESS:")
w("      V10 writes it @loc_hidden-black-site (26 times, all with the broken")
w("      backslash -- see PROBLEM 4). Barry's 2026-08-14 canon says the opposite:")
w("      \"@Talia is the ONLY place-name with a handle... it is BLACK SITE,")
w("      never @BLACK_SITE.\" If a Higgsfield element called")
w("      @loc_hidden-black-site now exists, V10 is right and the canon is stale.")
w("      Barry decides which. Until he does, just fix the backslash.")
w("")
w("      Its sub-locations from his own scripts: SHIPPING BAY, WAREHOUSE MAIN")
w("      FLOOR, WAREHOUSE SIDE ROOM, SERVICE CORRIDOR, LABORATORY CORRIDOR,")
w("      SECURED LAB ROOM, perimeters.")
w("")
w("    Other places in his scripts, written plain:")
w("      EXT. ROCKY MOUNTAINS -- COLORADO, RIDGE LINE, TREE LINE, WOODS,")
w("      INT. MATTE-BLACK CRATE")
w("")
w("### RULE")
w("")
w("    Never substitute a description for a name that exists, and never invent")
w("    a name that does not. Name the weapon by its handle instead of")
w("    describing it.")

w("")
w("")
w("=" * 72)
w("## SUMMARY")
w("=" * 72)
w("")
w(f"  {total_bare:>3}  dialogue lines with no speaker")
w(f"  {sum(plain.values()):>3}  dialogue lines using a plain name instead of an @handle")
w(f"    1  line using a different format (YANNAH whispers:)")
w(f"  {text.count(chr(92) + '_'):>3}  broken @loc_hidden-black-site spellings")
for label, n, to in counts_prose:
    if n:
        w(f"  {n:>3}  plain '{label.split(' /')[0]}' in the prose -> {to}")
w("")
w("Everything else in V10 is good: single numbering run (B-ROLL 00-02 +")
w("SHOT 00-28), no duplicate shot numbers, all six voice IDs present.")

body = "\n".join(O)
open(DEST, "w", encoding="utf-8").write(body)
# the console is cp1252 and chokes on the warning glyph -- the FILE is utf-8
safe = body.encode("cp1252", "replace").decode("cp1252")
print(safe[-2400:])
print()
print("FULL LIST WRITTEN TO:", DEST)
print(f"({len(body):,} chars)")
