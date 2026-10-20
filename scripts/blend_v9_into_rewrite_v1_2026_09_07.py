"""Add V9's Acts One-Three (the fights included, as V9 wrote them) into Betty's
REWRITE v1 script. Barry, 2026-09-07: "add our fight scenes to this one".

This file is already in V9's block format, so the conversion is light:
  * V9 B-ROLL 01 + SHOT 01-08 -> Act One; SHOT 09-16 -> Act Two; SHOT 17-23 ->
    Act Three. SCENES A-H are NOT included (Episode 2, his ruling).
  * Markdown bold/### stripped to match this file's plain style.
  * Every spoken line verbatim; labelled "DIALOGUE (Name):" the way Betty's
    Scene Final does, speakers attributed from the surrounding prose.
    INTERNAL / INTERNAL MONOLOGUE lines are carried as written (voice-over,
    not spoken -- they get no voice id and are not lip-synced).
  * Standing substitutions only, outside quoted speech: current handles,
    @loc_hidden-black-site, weapon handles for "alien pistol"/"Glock", Bia's
    hazel-green irises.
  * VOICE IDS line added to each shot with spoken dialogue.
  * V9 shots numbered 01A-23A (Betty's Act Zero already uses 00-05).
  * Betty's Act Zero and SCENE FINAL untouched.
Re-runnable: blends from a once-taken pre-blend backup.
"""
raise SystemExit("HISTORICAL -- do not re-run: V9A.1 is maintained in the WIP (script_wip), and a re-run would regress the 2026-09-07 fight extensions.")
import re
import sys
import shutil
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
import script_index as si  # noqa: E402

TARGET = pathlib.Path("C:/Users/Owner/Downloads/TALIA_CREW_EP1_PRODUCTION_V9A.md")  # renamed V9A 2026-09-07
V9 = REPO / "data" / "ep1_production_v9_WIP_snapshot_2026-09-07.md"
BACKUP = REPO / "data" / "backup_blacksite_handle_2026-09-07" / "TALIA_CREW_EP1_REWRITE_v1_FULL.BEFORE_BLEND.md"
LOC = "@loc_hidden-black-site"

VOICE = {
    "@b-dubb": ("Barry", "9b162037-e549-4065-9562-ebac293ee72a", "B-Dubb-Voice, Barry's own"),
    "@Bia-2": ("Bia", "f32c8f51-449e-4ddf-bdf7-1527e11df917", "Tallulah"),
    "@Yannah": ("Yannah", "032386ec-491b-5bdc-81ac-49e9a6a2c89d", "Daisy"),
    "@Tazz": ("Tazz", "3811e986-0891-47cf-a1f5-78a1d62a547a", "Imogen"),
    "@keth": ("Keth", "6b528d43-c056-4a2f-9d82-1591a7ba13b0", "John"),
}
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
    "SHOT 23": ["@Bia-2", "@b-dubb"],
}
ACTS = {
    "ONE": ["B-ROLL 01", "SHOT 01", "SHOT 02", "SHOT 03", "SHOT 04", "B-ROLL 02",
            "SHOT 05", "SHOT 06", "SHOT 07", "SHOT 08"],
    "TWO": [f"SHOT {n:02d}" for n in range(9, 17)],
    "THREE": [f"SHOT {n:02d}" for n in range(17, 24)],
}
QUOTED = re.compile(r'"[^"\n]*"')


def subst(seg: str) -> str:
    seg = re.sub(r"@B DUBB'S", "@b-dubb's", seg)
    seg = re.sub(r"@B DUBB", "@b-dubb", seg)
    seg = re.sub(r"\bB DUBB'S\b", "@b-dubb's", seg)
    seg = re.sub(r"\bB DUBB\b", "@b-dubb", seg)
    seg = re.sub(r"@Bia\b(?!-)(?!'s-Pistol)", "@Bia-2", seg)
    seg = re.sub(r"@yannah\b", "@Yannah", seg)
    seg = re.sub(r"@Keth\b", "@keth", seg)
    seg = re.sub(r"(?<![@\w-])Bia(?=['\s.,;:!?)]|$)", "@Bia-2", seg)
    seg = re.sub(r"(?<![@\w-])Yannah(?=['\s.,;:!?)]|$)", "@Yannah", seg)
    seg = re.sub(r"(?<![@\w-])Tazz(?=['\s.,;:!?)]|$)", "@Tazz", seg)
    seg = re.sub(r"(?<![@\w-])Keth(?=['\s.,;:!?)]|$)", "@keth", seg)
    seg = seg.replace("Silenced alien pistols", "@Bia's-Pistol* and @Yannah's-Machine-Pistol, silenced")
    seg = re.sub(r"\bGlock\b", "@B-Dubb's-Banger", seg)
    seg = re.sub(r"\b(?:military\s+)?black[\s-]site\b", LOC, seg, flags=re.I)
    seg = re.sub(r"\bfacility('s)?\b", lambda m: LOC + (m.group(1) or ""), seg, flags=re.I)
    seg = seg.replace(f"Gray {LOC} jumpsuit", "Gray facility jumpsuit")
    seg = seg.replace("deep-purple fractal irises", "hazel-green fractal irises")
    return seg


def fix_line(line: str) -> str:
    pos, out = 0, []
    for m in QUOTED.finditer(line):
        out.append(subst(line[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(subst(line[pos:]))
    return "".join(out)


def plain(line: str) -> str:
    """Strip V9's markdown decoration to this file's plain style."""
    s = line.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = s.replace("**", "")
    return s


def convert(block: dict) -> str:
    label, content = block["label"], block["content"]
    lines = content.splitlines()
    head = plain(lines[0])
    num = label.split()[-1]
    head = re.sub(r"^(SHOT \d+)", rf"SHOT {num}A", head) if label.startswith("SHOT") else head
    out = [head]
    speakers = list(SPEAKERS.get(label, []))
    quotes = []
    open_q = []
    body_started = False
    for raw in lines[1:]:
        s = raw.strip()
        if open_q:
            open_q.append(s)
            if s.endswith('"'):
                line = " ".join(open_q).strip(); open_q.clear()
                sp = speakers.pop(0) if speakers else "@?"
                quotes.append(sp); (out.append("") if out and out[-1] != "" else None); out.append(f"DIALOGUE ({VOICE.get(sp, ('?',))[0]}):"); out.append(line)
            continue
        if not s:
            out.append(""); continue
        if s == "**DIALOGUE:**":
            continue                      # label re-emitted per line with the speaker
        if s.startswith('"'):
            open_q.append(s)
            if s.endswith('"') and len(s) > 1:
                line = open_q[0]; open_q.clear()
                sp = speakers.pop(0) if speakers else "@?"
                quotes.append(sp); (out.append("") if out and out[-1] != "" else None); out.append(f"DIALOGUE ({VOICE.get(sp, ('?',))[0]}):"); out.append(line)
            continue
        out.append(fix_line(plain(s)))
    if open_q:
        line = " ".join(open_q).strip() + '"'; sp = speakers.pop(0) if speakers else "@?"
        quotes.append(sp); (out.append("") if out and out[-1] != "" else None); out.append(f"DIALOGUE ({VOICE.get(sp, ('?',))[0]}):"); out.append(line)
    assert not speakers, f"{label}: unused speakers {speakers}"

    # VOICE IDS goes right before NEG
    if quotes:
        vids = []
        for sp in dict.fromkeys(quotes):
            name, vid, vname = VOICE[sp]
            extra = " — if it does not render true to him, re-roll the same prompt first, then fall back to dc382508-c8bd-443c-8cb2-46e57b8d2e6f (Sterling)" if sp == "@b-dubb" else ""
            vids.append(f"{sp} speaks in voice {vid} ({vname}){extra}.")
        vline = "VOICE IDS: " + " ".join(vids)
        for i in range(len(out) - 1, -1, -1):
            if out[i].startswith("NEG:"):
                out[i:i] = [vline, ""]
                break
        else:
            out += ["", vline]
    # collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return text


DIV = "───────────────────────────────────────────────────────────────────────────────────────────────────────────"
blocks = {b["label"]: b for b in si.parse_blocks(V9.read_text(encoding="utf-8"))}
acts = {k: ("\n\n" + DIV + "\n\n").join(convert(blocks[l]) for l in labels) for k, labels in ACTS.items()}

if not BACKUP.exists():
    shutil.copy2(TARGET, BACKUP)
doc = BACKUP.read_text(encoding="utf-8")


def splice(doc, start, end, rep):
    i = doc.find(start); assert i >= 0, start
    j = doc.find(end, i); assert j > i, end
    return doc[:i] + rep + doc[j + len(end):]


doc = splice(doc, "\\[SHOTS 01-08 from original v9 script maintained exactly",
             "preserved as written in the v9 production script]", acts["ONE"])
doc = splice(doc, "\\[SHOTS 09-16 from original v9 script maintained exactly",
             "expression notes preserved exactly as written]", acts["TWO"])
doc = splice(doc, "\\[SHOTS 17-23 from original v9 script maintained exactly",
             "expression notes preserved exactly as written]", acts["THREE"])
doc = re.sub(r"@Bia\b(?!-)(?!'s-Pistol)", "@Bia-2", doc)

tmp = TARGET.with_suffix(".tmp"); tmp.write_text(doc, encoding="utf-8"); tmp.replace(TARGET)
print(f"wrote {TARGET.name}: {len(doc):,} chars | shots: {sum(len(v) for v in ACTS.values())}")
print("placeholders left:", doc.count("maintained exactly"), "| unattributed:", doc.count("DIALOGUE (?)"),
      "| dead handles:", sum(doc.count(x) for x in ("@B-DUBB-new", "@Vorshara", "@Barry", "@B DUBB")),
      "| VOICE IDS lines:", doc.count("VOICE IDS:"), "| location handle:", doc.count(LOC),
      "| stray markdown:", doc.count("**") + doc.count("### "))
