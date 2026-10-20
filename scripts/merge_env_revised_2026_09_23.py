"""Barry, 2026-09-23: "put the cut lines back, then swap."

Merges Elliot's current scripts (EP1 fact 3683, EP2 fact 3893) into the
ENV_REVISED files Barry supplied. Every line of the NEW file is kept as written.
Every line of the OLD file that the new file no longer carries is put back in
the same section and the same field (STAGE n / CAMERA / EXPRESSION / NEG ...),
directly after the line it used to follow. Whole missing sections go back in
their original position. No model in the path.

Writes data/merged_EP1.md + data/merged_EP2.md and a report. Does NOT touch the
database -- the swap is a separate step.
"""
import re, sys, sqlite3, difflib
sys.path.insert(0, "backend")
import memory

NEW1 = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V11_ENV_REVISED.md"
NEW2 = r"C:\Users\Owner\Downloads\TALIA_CREW_EP2_V2_ENV_REVISED (1).md"
STOP = set("""a an the and or but of to in on at by for with from into onto over under
as is are was were be been being it its it's this that these those his her their
him she he they them you your we our not no so then than just only all any each
one two there here what who when where which while up down out off""".split())
SEP_WIP = "─" * 110

def norm(s):
    s = s.replace("*", "").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", s.lower())).strip()

def cwords(s):
    return [w for w in norm(s).split() if len(w) > 2 and w not in STOP]

# ---------------------------------------------------------------- sections
HEAD = re.compile(r"^(#{1,4}) (.+)$", re.M)
LABEL = re.compile(r"\b(SHOT \d+[A-Z]?|B-ROLL \d+[A-Z]?|SCENE [A-Z0-9]+)\b")

def sections(text):
    hs = list(HEAD.finditer(text))
    pre = text[: hs[0].start()] if hs else text
    out = []
    for i, h in enumerate(hs):
        end = hs[i + 1].start() if i + 1 < len(hs) else len(text)
        out.append({"head": h.group(0), "body": text[h.end():end]})
    return pre, out

def sec_title(head):
    t = re.sub(r"^#+ ", "", head)
    t = t.split("|")[0]
    t = LABEL.sub("", t)
    return norm(t.replace("—", " ").replace("--", " "))

def sec_label(head):
    m = LABEL.search(head)
    return m.group(1) if m else None

def match_sections(old, new):
    """old index -> new index (title first, then label, then fuzzy title)."""
    mp, used = {}, set()
    for i, o in enumerate(old):
        ot = sec_title(o["head"])
        for j, n in enumerate(new):
            if j not in used and ot and sec_title(n["head"]) == ot:
                mp[i] = j; used.add(j); break
    for i, o in enumerate(old):
        if i in mp: continue
        ol = sec_label(o["head"])
        for j, n in enumerate(new):
            if j not in used and ol and sec_label(n["head"]) == ol:
                mp[i] = j; used.add(j); break
    for i, o in enumerate(old):
        if i in mp: continue
        best, bj = 0, None
        for j, n in enumerate(new):
            if j in used: continue
            r = difflib.SequenceMatcher(None, sec_title(o["head"]), sec_title(n["head"])).ratio()
            if r > best: best, bj = r, j
        if bj is not None and best >= 0.8:
            mp[i] = bj; used.add(bj)
    return mp

# ---------------------------------------------------------------- paragraphs
PLAB = re.compile(r"^\*\*([A-Z][A-Z0-9 &/\-]+?)(?:\s*\(([^)]*)\))?:?\*\*:?")

def paras(body):
    return [p for p in re.split(r"\n\s*\n", body.strip("\n")) if p.strip()]

def pkey(p):
    s = p.strip()
    m = PLAB.match(s)
    if not m: return None
    k = m.group(1).strip()
    if k.startswith("STAGE"):
        n = re.match(r"STAGE\s*(\d+)", k + " " + (m.group(2) or ""))
        return "STAGE " + (n.group(1) if n else k)
    if k in ("DIALOGUE", "INTERNAL", "VO"):
        return None           # dialogue verified separately; match by content
    return k

def mode(key):
    if key == "CAMERA": return "pipe"
    if key in ("NEG", "POSITIVE LOCKS"): return "comma"
    return "sent"

def split_units(p, m):
    s = p.strip()
    lab = ""
    mm = PLAB.match(s)
    if mm:
        lab, s = s[: mm.end()], s[mm.end():]
    if m == "pipe":
        units = [u.strip() for u in s.split("|")]
    elif m == "comma":
        s2 = s.strip().rstrip(".")
        units = [u.strip() for u in s2.split(",")]
    else:
        units = [u.strip() for u in re.split(r"(?<=[.!?])\s+(?=[A-Z@\"*(])|(?<=[.!?][\"”])\s+", s)]
    return lab, [u for u in units if u]

def join_units(lab, units, m):
    if m == "pipe": body = " | ".join(units)
    elif m == "comma": body = ", ".join(units) + "."
    else: body = " ".join(units)
    return (lab + " " + body).strip() if lab else body

def present(unit, new_text_norm, new_words):
    k = norm(unit)
    if not k or k in new_text_norm: return True
    cw = cwords(unit)
    if len(cw) < 8: return False
    have = sum(1 for w in cw if w in new_words)
    return have / len(cw) >= 0.85

def best_anchor(units, anchor):
    """index in units of the unit that best matches anchor (old previous unit)."""
    if anchor is None: return -1
    a = set(cwords(anchor)); na = norm(anchor)
    best, bi = 0.0, None
    for i, u in enumerate(units):
        if na and na == norm(u): return i
        w = set(cwords(u))
        if not a or not w: continue
        r = len(a & w) / len(a)
        if r > best: best, bi = r, i
    return bi if best >= 0.5 else None

# ---------------------------------------------------------------- merge
def merge(old_text, new_text, name, report):
    opre, osecs = sections(old_text)
    npre, nsecs = sections(new_text)
    mp = match_sections(osecs, nsecs)
    restored = 0
    for i, o in enumerate(osecs):
        if i not in mp: continue
        n = nsecs[mp[i]]
        new_norm = norm(n["body"]); new_words = set(cwords(n["body"]))
        nps = paras(n["body"])
        prev_new_para = -1
        for op in paras(o["body"]):
            if re.fullmatch(r"\s*(\*\*\*|---|─+|_+)\s*", op): continue
            key = pkey(op); m = mode(key)
            # find target paragraph
            tgt = None
            if key:
                for j, np_ in enumerate(nps):
                    if pkey(np_) == key: tgt = j; break
            else:
                ow = set(cwords(op)); best = 0
                for j, np_ in enumerate(nps):
                    if pkey(np_): continue
                    w = set(cwords(np_))
                    r = len(ow & w) / max(1, len(ow))
                    if r > best: best, tgt = r, j
                if best < 0.35: tgt = None
            _, ounits = split_units(op, m)
            nall_units = [x for q in nps for x in split_units(q, mode(pkey(q)))[1]]
            def _inside_one(u):
                cw = set(cwords(u))
                return bool(cw) and any(cw <= set(cwords(x)) for x in nall_units)
            missing = [(k, u) for k, u in enumerate(ounits)
                       if not present(u, new_norm, new_words) and not _inside_one(u)]
            if not missing:
                if tgt is not None: prev_new_para = max(prev_new_para, tgt)
                continue
            if tgt is None:
                # whole paragraph absent -> insert it where it used to sit
                if len(missing) == len(ounits) or not key:
                    ins = prev_new_para + 1
                    nps.insert(ins, op.strip()); prev_new_para = ins
                    restored += len(missing)
                    report.append(f"{name} | {o['head'][:60]} | +para: {op.strip()[:110]}")
                    new_norm = norm("\n\n".join(nps)); new_words |= set(cwords(op))
                    continue
                tgt = prev_new_para if prev_new_para >= 0 else 0
            lab, nunits = split_units(nps[tgt], m if pkey(nps[tgt]) == key else "sent")
            m2 = m if pkey(nps[tgt]) == key else "sent"
            for k, u in missing:
                ocw = set(cwords(u))
                sub = next((ix for ix, x in enumerate(nunits)
                            if len(set(cwords(x))) >= 2 and set(cwords(x)) <= ocw), None)
                if sub is not None:
                    report.append(f"{name} | {o['head'][:60]} | {key or 'prose'} | FULLER OLD REPLACES '{nunits[sub][:60]}' -> {u[:100]}")
                    nunits[sub] = u; restored += 1
                    continue
                anc = ounits[k - 1] if k > 0 else None
                ai = best_anchor(nunits, anc)
                pos = (ai + 1) if ai is not None else (0 if k == 0 else len(nunits))
                nunits.insert(pos, u)
                restored += 1
                report.append(f"{name} | {o['head'][:60]} | {key or 'prose'} | {u[:120]}")
            nps[tgt] = join_units(lab, nunits, m2)
            prev_new_para = max(prev_new_para, tgt)
            new_norm = norm("\n\n".join(nps)); new_words = set(cwords("\n\n".join(nps)))
        n["body"] = "\n\n" + "\n\n".join(nps) + "\n\n"
    # whole sections missing from new -> insert after the new match of the previous old section
    order = list(range(len(nsecs)))
    inserts = []
    for i, o in enumerate(osecs):
        if i in mp: continue
        if not cwords(o["body"]) and not cwords(o["head"]): continue
        # version-title / header lines are not content
        if re.search(r"Production Script V|PRODUCTION V1GOLD", o["head"], re.I): continue
        prev = next((mp[k] for k in range(i - 1, -1, -1) if k in mp), -1)
        inserts.append((prev, o))
        restored += max(1, len(re.findall(r"[.!?]", o["body"])))
        report.append(f"{name} | +SECTION after new #{prev}: {o['head'][:80]}")
    out = [npre]
    for j in [-1] + order:
        if j >= 0:
            out.append(nsecs[j]["head"] + nsecs[j]["body"])
        for prev, o in inserts:
            if prev == j:
                out.append(o["head"] + o["body"])
    return "".join(out), restored

def verify(old_text, merged, new_text, name):
    """Every old sentence present (strict) + every new line present."""
    m_norm = norm(merged); m_words = set(cwords(merged))
    miss_old = []
    for o in re.split(r"(?<=[.!?])\s+|\n+", re.sub(r"\*\*[A-Z &/]+(\([^)]*\))?:\*\*", " ", old_text)):
        if len(cwords(o)) >= 3 and norm(o) not in m_norm:
            cw = cwords(o)
            if sum(w in m_words for w in cw) / len(cw) < 0.85:
                miss_old.append(o.strip())
    msets = [set(cwords(x)) for x in re.split(r"(?<=[.!?])\s+|\n+|\s*\|\s*", merged) if x.strip()]
    def _covered(u):
        cw = set(cwords(u))
        return bool(cw) and any(cw <= ms for ms in msets)
    miss_new = []
    for l in new_text.splitlines():
        l = PLAB.sub("", l.strip())
        for u in re.split(r"\s*\|\s*|(?<=[.!?])\s+|,\s+", l):
            if len(norm(u)) > 3 and norm(u) not in m_norm and not _covered(u):
                miss_new.append(u.strip())
    return miss_old, miss_new

c = sqlite3.connect(memory.DB_PATH)
report = []
for name, fid, path, outp in [("EP1", 3683, NEW1, "data/merged_EP1.md"),
                              ("EP2", 3893, NEW2, "data/merged_EP2.md")]:
    old = c.execute("select content from facts where id=?", (fid,)).fetchone()[0]
    new = open(path, encoding="utf-8").read()
    # EP2 carried a stale older draft AFTER "## END EPISODE 2" (an old SHOT 23
    # and B-ROLL 04, then a second END). It is not part of the episode; drop it
    # from the comparison so it is not appended after the ending.
    e = "## END EPISODE 2"
    if old.count(e) == 2:
        i1 = old.find(e); i2 = old.find(e, i1 + len(e))
        old = old[:i1] + old[i2:]
    merged, n = merge(old, new, name, report)
    # final pass: force in any old sentence the paragraph merge still missed,
    # right after the old sentence that preceded it (raw text match)
    mo, _ = verify(old, merged, new, name)
    for miss in mo:
        if re.search(r"Production Script V|PRODUCTION V1GOLD", miss, re.I): continue
        i = old.find(miss)
        before = old[max(0, i - 400):i]
        prev = re.split(r"(?<=[.!?])\s+", before.strip())[-1] if before.strip() else ""
        prev = re.sub(r"^.*\*\*[A-Z &/]+:\*\*\s*", "", prev)
        j = merged.find(prev) if len(prev) > 8 else -1
        if j >= 0:
            j += len(prev)
            merged = merged[:j] + " " + miss + merged[j:]
            n += 1
            report.append(f"{name} | forced after '{prev[:50]}' | {miss[:120]}")
        else:
            report.append(f"{name} | COULD NOT PLACE | {miss[:120]}")
            print("   COULD NOT PLACE:", miss[:120])
    open(outp, "w", encoding="utf-8").write(merged)
    mo, mn = verify(old, merged, new, name)
    print(f"{name}: old {len(old)}  new {len(new)}  merged {len(merged)}  restored units {n}")
    print(f"   old lines still missing after merge: {len(mo)}   new lines lost by merge: {len(mn)}")
    for x in mo[:40]: print("     OLD-MISSING:", x[:140])
    for x in mn[:10]: print("     NEW-LOST:", x[:140])
# hand placements for lines whose anchor sentence was reworded (asserted)
MANUAL = [
    ("@b-dubb — loyalty and honor offered.", "@b-dubb — loyalty and honor offered in the only currency he has."),
    ("@Tazz — the real laugh.", "Not performed, not held back, just real."),
    ("almost imperceptible blur in the lower frame.", "The hum is physical — light seems to vibrate with it."),
    ("the \"shit\" calculation → tactical retreat.", "All without breaking stride."),
]
m2 = open("data/merged_EP2.md", encoding="utf-8").read()
for anchor, line in MANUAL:
    if line in m2: continue
    assert m2.count(anchor) == 1, anchor
    m2 = m2.replace(anchor, anchor + " " + line)
    report.append(f"EP2 | hand-placed after '{anchor[:50]}' | {line}")
# fuller old wording replaces a condensed new line whose words it fully contains
REPLACE = [("@b-dubb — steady, no flinch. Acceptance.",
            '@b-dubb — steady, no flinch, "whatever it takes" is acceptance not bravado.')]
for was, now in REPLACE:
    if now in m2: continue
    assert m2.count(was) == 1, was
    m2 = m2.replace(was, now)
    report.append(f"EP2 | hand-replaced '{was}' -> {now}")
open("data/merged_EP2.md", "w", encoding="utf-8").write(m2)
open("data/_merge_report.txt", "w", encoding="utf-8").write("\n".join(report))
print("report lines:", len(report))
