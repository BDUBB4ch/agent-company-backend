"""Blend V9's Acts One-Three into Betty's Seedance 2.5 production script.

Barry, 2026-09-07: "basically you are to write the new one and add in the fight
like it is in v9. thats it. everything she took out is supposed to be in
episode 2 anyways."

WHAT THIS DOES -- conversion, not authorship:
  * V9 blocks B-ROLL 01, SHOT 01-08 -> Act One; SHOT 09-16 -> Act Two;
    SHOT 17-23 -> Act Three. SCENES A-H are NOT included (Episode 2).
  * Every spoken line is V9's, verbatim, in order. Speakers are attributed from
    the surrounding prose (see SPEAKERS) so the {} channel can carry the lock
    and the voice id.
  * Prose, CAMERA, ENVIRONMENT & LIGHTING and EXPRESSION are carried verbatim,
    with only the standing substitutions Barry has ruled: current handles,
    weapon handles where a file says "alien pistol" / "Glock", the black-site
    location handle outside spoken lines, and Bia's current iris colour.
  * BEATS are V9's paragraphs in order, grouped into STAGES with time ranges
    allocated proportionally to paragraph length inside the shot's own
    duration (integers, consecutive, no gaps). Timings are a scaffold for him
    to adjust, not a claim.
  * ASSET BINDINGS restate each present character from the CURRENT canon
    (every prompt is an island) plus the location binding.
  * POSITIVE LOCKS = documentary realism + appearance consistency + V9's NEG
    items carried as "no ..." (the way Betty did it in Act Zero).
  * Betty's Act Zero and SCENE FINAL are untouched. Her three placeholder
    regions are replaced in place.

Backs up the target first. Asserts every splice anchor.
"""
raise SystemExit("HISTORICAL -- do not re-run: V9A.1 is maintained in the WIP (script_wip), and a re-run would regress the 2026-09-07 fight extensions.")
import re
import sys
import shutil
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
import script_index as si  # noqa: E402

TARGET = pathlib.Path("C:/Users/Owner/Downloads/TALIA_CREW_EP1_SEEDANCE2.5_PRODUCTION (1).md")
V9 = REPO / "data" / "ep1_production_v9_WIP_snapshot_2026-09-07.md"
BACKUP = REPO / "data" / "backup_blacksite_handle_2026-09-07" / "TALIA_CREW_EP1_SEEDANCE2.5_PRODUCTION (1).BEFORE_BLEND.md"

LOC = "@loc_hidden-black-site"

VOICE = {
    "@b-dubb": ("clean voice, an inner city Black man from the South",
                "9b162037-e549-4065-9562-ebac293ee72a", "B-Dubb-Voice, Barry's own"),
    "@Bia-2": ("feminine; direct, the leader; measured, with authority",
               "f32c8f51-449e-4ddf-bdf7-1527e11df917", "Tallulah"),
    "@Yannah": ("feminine; smart but sexy; normal speaking pace, witty, sometimes snarky",
                "032386ec-491b-5bdc-81ac-49e9a6a2c89d", "Daisy"),
    "@Tazz": ("feminine; calm, mid-range, the faintest husky edge",
              "3811e986-0891-47cf-a1f5-78a1d62a547a", "Imogen"),
    "@keth": ("higher-pitched, nasally, raspy; careful delivery, open hatred when speaking to B Dubb",
              "6b528d43-c056-4a2f-9d82-1591a7ba13b0", "John"),
}

# Current canon, tactical/mission wardrobe -- the binding line per character.
BIND = {
    "@b-dubb": "@b-dubb (appearance reference): Face, fuller rounded salt-and-pepper goatee, brownish-red skin, medium build, slightly muscular. Wardrobe: black hoodie with a tactical black vest over it, black cargo pants, black boots, black baseball cap pulled low. Gold number 4 pendant with diamonds worn over the vest, always visible. Belt: @B-Dubb's-Banger, utility knife, tactical gloves. Define entire appearance — do not reconstruct.",
    "@Bia-2": "@Bia-2 (appearance reference): Face, subtly pointed ears, hazel-green double-ring fractal irises with faint violet iridescence (non-glowing), clean-edged gold spots, faint iridescent vein-map at temples and neck. Athletic build with natural curves. Wardrobe: grey and black form-fitting tactical suit, utility belt, multi-tool on the right hip; @Bia's-Pistol* at the left. Define entire appearance — do not reconstruct.",
    "@Yannah": "@Yannah (appearance reference): Face, warm brown skin with very faint gold freckles on the cheeks only, noticeably pointed ears with a gold ear cuff on the exposed ear, emerald-green-and-brown double-ring fractal irises (non-glowing), small gem stud under the right eye, short asymmetrical twisted locs swept up with copper-auburn tips, one side shaved. Athletic, lean. Wardrobe: black fitted tactical jumpsuit with teal piping, reinforced knees, utility belt, thigh holster rig, compact comms unit at hip; @Yannah's-Machine-Pistol. Define entire appearance — do not reconstruct.",
    "@Tazz": "@Tazz (appearance reference): Face, light skin, noticeably pointed ears, pink-and-blue double-ring irises (non-glowing), two long dark braids secured tight, very strong visibly muscular build. Wardrobe: all-black form-fitting one-piece tactical jumpsuit, sleeveless; @Tazz's-Weapon carried two-handed. Define entire appearance — do not reconstruct.",
    "@keth": "@keth (appearance reference): Face and body, approximately 4 feet tall, gray deeply weathered skin, slightly elongated cranium, no hair, large dark green eyes with no visible whites, small barely-pointed ears, lean compressed build. Gray facility jumpsuit, worn, torn at the collar, no shoes, raw wrists from restraints. Define entire appearance — do not reconstruct.",
}

# Speaker attribution per shot, in the order the quoted lines appear in V9.
SPEAKERS = {
    "SHOT 04": ["@b-dubb", "@b-dubb"],
    "SHOT 14": ["@Bia-2"],
    "SHOT 17": ["@Yannah"],
    "SHOT 18": ["@Bia-2"],
    "SHOT 19": ["@b-dubb", "@Bia-2", "@b-dubb", "@Bia-2", "@b-dubb", "@Bia-2"],
    "SHOT 20": ["@b-dubb", "@Bia-2", "@b-dubb", "@b-dubb", "@Bia-2", "@b-dubb"],
    "SHOT 21": ["@Yannah", "@Bia-2"],
    "SHOT 22": ["@Bia-2", "@b-dubb", "@Bia-2", "@b-dubb", "@b-dubb", "@Bia-2", "@b-dubb",
                "@Bia-2", "@b-dubb", "@Bia-2", "@b-dubb", "@Bia-2", "@b-dubb"],
    "SHOT 23": ["@Bia-2", "@b-dubb"],   # "You can bargain. / Or you can bleed. / Pick." is ONE line in V9
}

ACTS = {
    "ONE": ["B-ROLL 01", "SHOT 01", "SHOT 02", "SHOT 03", "SHOT 04", "B-ROLL 02",
            "SHOT 05", "SHOT 06", "SHOT 07", "SHOT 08"],
    "TWO": [f"SHOT {n:02d}" for n in range(9, 17)],
    "THREE": [f"SHOT {n:02d}" for n in range(17, 24)],
}

QUOTED = re.compile(r'"[^"\n]*"')


def subst(seg: str) -> str:
    """Standing substitutions, applied OUTSIDE quoted speech only."""
    seg = re.sub(r"@B DUBB'S", "@b-dubb's", seg)
    seg = re.sub(r"@B DUBB", "@b-dubb", seg)
    seg = re.sub(r"\bB DUBB'S\b", "@b-dubb's", seg)
    seg = re.sub(r"\bB DUBB\b", "@b-dubb", seg)
    seg = re.sub(r"@Bia\b(?!-)(?!'s-Pistol)", "@Bia-2", seg)
    seg = re.sub(r"@yannah\b", "@Yannah", seg)
    seg = re.sub(r"@Keth\b", "@keth", seg)
    # bare names -> handles (his every-mention rule); possessives survive
    seg = re.sub(r"(?<![@\w-])Bia(?=['\s.,;:!?)]|$)", "@Bia-2", seg)
    seg = re.sub(r"(?<![@\w-])Yannah(?=['\s.,;:!?)]|$)", "@Yannah", seg)
    seg = re.sub(r"(?<![@\w-])Tazz(?=['\s.,;:!?)]|$)", "@Tazz", seg)
    seg = re.sub(r"(?<![@\w-])Keth(?=['\s.,;:!?)]|$)", "@keth", seg)
    # weapons
    seg = seg.replace("Silenced alien pistols", "@Bia's-Pistol* and @Yannah's-Machine-Pistol, silenced")
    seg = re.sub(r"\bGlock\b", "@B-Dubb's-Banger", seg)
    # the location
    seg = re.sub(r"\b(?:military\s+)?black[\s-]site\b", LOC, seg, flags=re.I)
    seg = re.sub(r"\bfacility('s)?\b", lambda m: LOC + (m.group(1) or ""), seg, flags=re.I)
    seg = seg.replace(f"Gray {LOC} jumpsuit", "Gray facility jumpsuit")
    # Bia's current iris colour (his 2026-08-10 ruling)
    seg = seg.replace("deep-purple fractal irises", "hazel-green fractal irises")
    seg = seg.replace("deep purple and gold fractal irises", "hazel-green fractal irises")
    return seg


def fix_line(line: str) -> str:
    pos, out = 0, []
    for m in QUOTED.finditer(line):
        out.append(subst(line[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(subst(line[pos:]))
    return "".join(out)


def field(content: str, name: str) -> str:
    m = re.search(r"\*\*" + re.escape(name) + r":\*\*\s*(.+)", content)
    return m.group(1).strip() if m else ""


def convert(block: dict) -> str:
    label, content = block["label"], block["content"]
    lines = content.splitlines()
    head = lines[0].strip().strip("#").strip().strip("*").strip()
    parts = [p.strip() for p in head.split("|")]
    title_part = parts[0]
    dur_m = re.search(r"(\d+)\s*sec", head)
    dur = int(dur_m.group(1)) if dur_m else 8
    music = next((p.split(":", 1)[1].strip() for p in parts if p.upper().startswith("MUSIC")), "")
    genre = field(content, "GENRE")
    genre_line = ""
    gm = re.search(r"\*\*GENRE:\*\*\s*(.+?)\s*\|\s*\*\*SPEED RAMP:\*\*\s*(.+)", content)
    if gm:
        genre_line = f"GENRE: {gm.group(1).strip()} | SPEED RAMP: {gm.group(2).strip()}"
    slug = next((l.strip().strip("*") for l in lines if re.match(r"\s*\*\*(INT|EXT)\.", l)), "")

    # body = everything between the slug and **CAMERA:**
    body = content.split("**CAMERA:**")[0]
    body_lines = body.splitlines()
    start = next((i + 1 for i, l in enumerate(body_lines) if re.match(r"\s*\*\*(INT|EXT)\.", l)), 1)
    body_lines = body_lines[start:]

    speakers = list(SPEAKERS.get(label, []))
    quotes = []            # (speaker, line) in order
    paras = []             # list of paragraph strings (prose + attributed dialogue, in order)
    buf = []
    open_quote = []        # a quoted line that has not closed yet (V9 breaks one utterance over lines)
    def flush():
        if buf:
            paras.append(" ".join(buf).strip()); buf.clear()
    def close_quote():
        line = " ".join(open_quote).strip(); open_quote.clear()
        sp = speakers.pop(0) if speakers else "@?"
        quotes.append((sp, line))
        paras.append(f"{sp}: {line}")
    for raw in body_lines:
        s = raw.strip()
        if open_quote:
            open_quote.append(s)
            if s.endswith('"'):
                close_quote()
            continue
        if not s:
            flush(); continue
        if s == "**DIALOGUE:**":
            flush(); continue
        if s.startswith('"'):
            flush()
            open_quote.append(s)
            if s.endswith('"') and len(s) > 1:
                close_quote()
            continue
        buf.append(fix_line(s))
    if open_quote:                       # unterminated quote at the end of the body
        open_quote[-1] += '"'; close_quote()
    flush()
    assert not speakers, f"{label}: unused speaker attributions {speakers}"

    # group consecutive dialogue lines into one exchange, then keep merging the
    # smallest adjacent pair until the stage count fits the shot's duration
    is_dlg = [bool(re.match(r"^@[\w'-]+: \"", p)) for p in paras]
    first_prose = next((p for p, d in zip(paras, is_dlg) if not d), "")
    merged, merged_dlg = [], []
    for p, d in zip(paras, is_dlg):
        if merged and d and merged_dlg[-1]:
            merged[-1] += "\n" + p
        else:
            merged.append(p); merged_dlg.append(d)
    paras = merged
    while len(paras) > max(dur, 1) and len(paras) > 1:
        k = min(range(len(paras) - 1), key=lambda i: len(paras[i]) + len(paras[i + 1]))
        paras[k:k + 2] = [paras[k] + "\n" + paras[k + 1]]

    # stages: proportional timing over the shot's duration
    weights = [max(len(p), 40) for p in paras]
    total = sum(weights) or 1
    alloc = [max(1, round(w * dur / total)) for w in weights]
    while sum(alloc) > dur and max(alloc) > 1:
        alloc[alloc.index(max(alloc))] -= 1
    if paras:
        alloc[-1] += dur - sum(alloc)
    beats, t = [], 0
    for i, (p, a) in enumerate(zip(paras, alloc), 1):
        beats.append(f"STAGE {i} ({t}–{t + a} sec):\n{p}")
        t += a

    # characters present, in order of first appearance across the whole block
    fixed_all = "\n".join(fix_line(l) for l in content.splitlines())
    order = sorted(BIND, key=lambda h: (fixed_all.find(h) if h in fixed_all else 10**9))
    present = [h for h in order if h in fixed_all]
    for sp in reversed(list(dict.fromkeys(s for s, _ in quotes))):   # speakers first, in speaking order
        if sp in present:
            present.remove(sp); present.insert(0, sp)
    bindings = [BIND[h] for h in present]
    if LOC in fix_line(slug) or "WAREHOUSE" in slug or "LAB" in slug or "SHIPPING BAY" in slug or "SERVICE CORRIDOR" in slug:
        bindings.append(f"{LOC} (location reference): the military black site — build the space from the environment description; take architecture and light from the reference, nothing else.")
    elif "CARGO HOLD" in slug:
        bindings.append("@Talia (location): the cargo hold — alien architecture, pale turquoise running lights; build the hold from the environment description.")
    elif "ROCKY MOUNTAINS" in slug or "RIDGE" in slug or "TREE LINE" in slug:
        bindings.append("Colorado exterior (no reference element): build from the environment description.")
    bindings.append("Do not use background environments from any character reference.")

    camera = fix_line(field(content, "CAMERA"))
    env = fix_line(field(content, "ENVIRONMENT & LIGHTING"))
    expr = fix_line(field(content, "EXPRESSION"))
    neg = field(content, "NEG")
    neg_items = [n.strip().rstrip(".") for n in neg.split(",") if n.strip()]

    audio = [f"() {music}" if music else "() (no music cue in V9 for this shot)",
             "<> Action and environment sound as the beats describe; no BGM beyond the music line."]
    for sp, line in quotes:
        lock = VOICE.get(sp, ("", "", ""))[0]
        audio.append(f"{{}} {sp}: {line} ({lock})")
    vids = []
    for sp in dict.fromkeys(s for s, _ in quotes):
        lock, vid, name = VOICE[sp]
        extra = " — if it does not render true to him, re-roll first, then fall back to dc382508-c8bd-443c-8cb2-46e57b8d2e6f (Sterling)" if sp == "@b-dubb" else ""
        vids.append(f"{sp} speaks in voice {vid} ({name}){extra}.")

    locks = ["Documentary realism", "heavy film grain"]
    locks += [f"{h}'s appearance consistent with the reference" for h in present]
    locks += [f"no {n[0].lower() + n[1:]}" for n in neg_items]

    shot_title = title_part.split("—", 1)[-1].split("--", 1)[-1].strip().title()
    brief_sent = shot_title + ". " + " ".join(re.split(r"(?<=[.!?])\s+", first_prose)[:2]) if first_prose else shot_title + "."

    # Betty's Act Zero already uses SHOT 00-05, so her placeholders numbered the
    # V9 shots 01A-23A. Follow her convention; B-ROLLs keep their own numbers.
    raw_title = title_part.split("—", 1)[-1].split("--", 1)[-1].strip()
    shot_id = f"SHOT {label.split()[-1]}A" if label.startswith("SHOT") else f"SHOT B-ROLL {label.split()[-1]}"
    out = [f"{shot_id} — {raw_title} | {dur} sec" + (f" | MUSIC: {music}" if music else "")]
    if genre_line: out.append(genre_line)
    out.append(fix_line(slug))
    out.append("")
    out.append(f"**BRIEF:** {brief_sent}")
    out.append("")
    out.append("**ASSET BINDINGS:**" + "\n".join(bindings))
    out.append("")
    out.append("**BEATS:**\n\n" + "\n\n".join(beats))
    out.append("")
    out.append(f"**CAMERA:** {camera}")
    out.append("")
    out.append(f"**ENVIRONMENT & LIGHTING:** {env}")
    if expr:
        out.append(""); out.append(f"**EXPRESSION:** {expr}")
    out.append("")
    out.append("**AUDIO:**" + "\n".join(audio))
    if vids:
        out.append(""); out.append("**VOICE IDS:** " + " ".join(vids))
    out.append("")
    out.append("**POSITIVE LOCKS:** " + ", ".join(locks) + ".")
    return "\n".join(out)


DIV = "───────────────────────────────────────────────────────────────────────────────────────────────────────────"

blocks = {b["label"]: b for b in si.parse_blocks(V9.read_text(encoding="utf-8"))}
acts = {k: ("\n\n" + DIV + "\n\n").join(convert(blocks[l]) for l in labels) for k, labels in ACTS.items()}

if not BACKUP.exists():
    shutil.copy2(TARGET, BACKUP)           # the fixed, UN-blended version -- taken once, never overwritten
doc = BACKUP.read_text(encoding="utf-8")   # always blend from the un-blended source, so re-runs are safe


def splice(doc: str, start_marker: str, end_marker: str, replacement: str) -> str:
    i = doc.find(start_marker); assert i >= 0, start_marker
    j = doc.find(end_marker, i); assert j > i, end_marker
    j = j + len(end_marker)
    return doc[:i] + replacement + doc[j:]


doc = splice(doc, "\\[ACT ONE SHOTS (COLORADO INFILTRATION)", "reformatted for Seedance 2.5 submission.]", acts["ONE"])
doc = splice(doc, "\\[ACT TWO SHOTS (WAREHOUSE PARALLEL ACTION & EXTRACTION)", "reformatted for Seedance 2.5 submission.]", acts["TWO"])
doc = splice(doc, "\\[ACT THREE SHOTS (CARGO HOLD EXTRACTION & NEGOTIATION)", "reformatted for Seedance 2.5 submission.]", acts["THREE"])
doc = doc.replace("Acts One, Two, and Three (Colorado infiltration, warehouse parallel action, cargo hold standoff) are marked for expansion with the same structure. All dialogue, music cues, camera notes, and environmental descriptions from your original v9 script are preserved.",
                  "Acts One, Two, and Three are now the V9 shots (B-ROLL 01, SHOT 01–23) in this structure, blended 2026-09-07: every spoken line is V9's verbatim, the fights are as V9 wrote them, current canon in every binding. V9's Scenes A–H are not in this episode (Episode 2).")

# Betty's own Act Zero still used the pre-rename @Bia in dialogue tags and expression lines.
doc = re.sub(r"@Bia\b(?!-)(?!'s-Pistol)", "@Bia-2", doc)   # never touch the weapon handle @Bia's-Pistol*
doc = re.sub(r"@yannah\b", "@Yannah", doc)

tmp = TARGET.with_suffix(".tmp"); tmp.write_text(doc, encoding="utf-8"); tmp.replace(TARGET)
print(f"wrote {TARGET.name}: {len(doc):,} chars")
print("shots converted:", sum(len(v) for v in ACTS.values()), "| unattributed speakers left:", doc.count("@?:"))
print("placeholders left:", doc.count("ready for expansion"), "| dead handles:", sum(doc.count(x) for x in ("@B-DUBB-new", "@Vorshara", "@Barry", "@B DUBB")), "| escapes:", doc.count("&#x"))
print("VOICE IDS lines:", doc.count("**VOICE IDS:**"), "| location handle:", doc.count(LOC))
