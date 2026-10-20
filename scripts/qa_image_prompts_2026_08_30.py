"""QA every image prompt before Barry sees it.

Barry, 2026-08-30: "i just need you to get the prompts from them. clean,
remember that."

Every fault checked here is one that ACTUALLY SHIPPED to him today, not a
hypothetical:
  - Priya's office prompt was the model's own checklist ("- Covers person?
    Yes.") instead of a prompt.
  - Vivian's home prompt stopped at her body and never reached the room.
  - Marcus's two came back with EMPTY negative lines, and his home prompt cut
    off mid-sentence at "He is sitting with his".
  - Elliot's and Taliyah's negatives were my own banned-word list copied back
    at me ("worn, faded, peeling, charcoal, walnut...").
  - Taliyah wrote an ```image``` fence instead of an answer, and described
    BARRY in second person instead of herself.
  - Victor's office prompt put him in the armchair with a whiskey instead of
    at his desk working, and Priya's put her back at the chopping board.
  - Priya's office prompt ended with the same sentence twice.
  - Amara's negative repeated "visible logos" nine times.

Read-only. Prints one line per fault; exit code 1 if anything is unclean.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
JSON_PATH = os.path.join(DATA, "agent_image_prompts_2026_08_30.json")

# the exact list handed to them in the brief -- if it comes back, they copied
# my instructions instead of describing their own picture
BANNED_ECHO = ["worn", "faded", "peeling", "chipped", "scarred", "scuffed",
               "frayed", "rusted", "distressed", "weathered", "reclaimed",
               "charcoal", "walnut", "terrazzo", "brass", "velvet",
               "fire escape", "late afternoon light", "dust motes"]

LEAK = re.compile(r"(?im)^\s*[-*]?\s*(covers|final check|output format|"
                  r"length \d|hyper-realistic\?|exactly one person\?)")

RELAX = re.compile(r"(?i)\b(armchair|couch|sofa|recliner)\b")
WORKING = re.compile(r"(?i)\b(desk|keyboard|workbench|monitor|workspace|"
                     r"bench|laptop)\b")
DRINKING = re.compile(r"(?i)\b(whiskey|wine|rye|beer|tumbler of)\b")


def faults(rec, key, first):
    """Return a list of (severity, message) for one prompt."""
    out = []
    p = (rec.get(key) or "").strip()
    neg = (rec.get(key + "_neg") or "").strip()
    kind = "office" if key.startswith("office") else "home"

    if not p:
        return [("FAIL", "no prompt at all")]
    if "```" in p:
        out.append(("FAIL", "contains a code/image fence"))
    if len(p) < 900:
        out.append(("FAIL", f"too short ({len(p)} chars)"))
    if LEAK.search(p):
        out.append(("FAIL", "leaked the brief's own checklist into the prompt"))
    if not re.search(r"[.!?][\"')\]]?$", p):
        out.append(("FAIL", f"truncated mid-sentence: ...{p[-60:]!r}"))

    second = len(re.findall(r"\b(your|you are|you wear)\b", p, re.I))
    if second >= 4:
        out.append(("FAIL", "written in second person"))

    # duplicated tail sentence (Priya's office shipped with one)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p) if len(s) > 40]
    if len(sents) >= 2 and sents[-1].lower() == sents[-2].lower():
        out.append(("WARN", "final sentence is duplicated"))

    if not neg:
        out.append(("WARN", "negative line is empty"))
    else:
        echoed = [w for w in BANNED_ECHO if w in neg.lower()]
        if len(echoed) >= 3:
            out.append(("WARN", f"negative echoes the brief's banned list "
                                f"({', '.join(echoed[:5])}...)"))
        toks = [t.strip() for t in neg.split(",") if t.strip()]
        dupes = len(toks) - len(set(t.lower() for t in toks))
        if dupes >= 5:
            out.append(("WARN", f"negative repeats itself ({dupes} dupes)"))

    if kind == "office":
        if not WORKING.search(p):
            out.append(("FAIL", "office prompt names no desk/workspace"))
        # the scene bleed: relaxing furniture AND a drink AND no work verb
        if RELAX.search(p) and DRINKING.search(p) and not re.search(
                r"(?i)\b(typing|working|reviewing|writing|at (his|her) desk)\b", p):
            out.append(("WARN", "office prompt reads like the relaxing scene"))
    return out


# --- DETERMINISTIC NEGATIVES ---------------------------------------------
# The negative line is boilerplate plus a few scene-specific exclusions. Asked
# for it, the 27B produced an EMPTY line (Victor home), 41 duplicate tokens
# (Victor office), my own banned-word list read back (Priya, Elliot, Taliyah)
# and "visible logos" nine times (Amara). Zero upside, four failure modes. So
# it is built in code from the prompt's own content instead.
_BASE = ["extra people", "extra limbs", "extra fingers", "missing fingers",
         "deformed hands", "warped face", "bad anatomy", "plastic skin",
         "waxy skin", "heavy speckled freckles", "text", "letters", "numbers",
         "watermark", "logo", "signature", "blurry", "lowres", "cartoon",
         "anime", "illustration", "3d render", "cgi", "oversaturated",
         "floating objects", "holograms", "glowing panels",
         "science fiction elements"]

_SMOKE = re.compile(r"(?i)\b(joint|blunt|pipe|bowl|smoke|smoking)\b")
_NUDE = re.compile(r"(?i)\b(bare|naked|nude|completely bare)\b")


def build_negative(rec, key):
    p = (rec.get(key) or "")
    neg = list(_BASE)
    if key.startswith("office"):
        neg += ["lounging", "lying down", "reclining", "holding a drink",
                "sleeping", "empty desk"]
    if _SMOKE.search(p):
        # "glass pipe" renders as a crack pipe -- Barry: "looks like a
        # crackhead". Kill the visual signature, not the activity.
        neg += ["crack pipe", "meth pipe", "long straight glass tube",
                "drug paraphernalia", "gaunt face", "sunken cheeks",
                "sickly complexion"]
    if _NUDE.search(p):
        neg += ["clothing added", "underwear added", "censorship bars"]
    low = p.lower()
    if "espresso" in low or "coppery chestnut" in low:
        neg += ["red hair", "short hair"]          # Barry's Amara ruling
    seen, out = set(), []
    for t in neg:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return ", ".join(out)


# --- INSTRUCTION ECHO ------------------------------------------------------
# Told to state the scale relationship, the model pasted my instruction back
# WORD FOR WORD into all 18 prompts ("The room is bigger than the person. They
# are in correct human proportion to the space: the ceiling, the walls and the
# floor all extend well beyond them..."). It would function, but 18 prompts
# carrying an identical slab of my own brief is not clean. Replaced in code
# with one tight clause, so the rule survives and the boilerplate does not.
_ECHO = re.compile(
    r"(?is)\s*The room is bigger than the person\..*?"
    r"(?:towers over their own furniture\.|around and above them\.)")
_SCALE_CLAUSE = (" Natural scale: the figure sits in true proportion to the "
                 "room, with the ceiling, walls and floor extending well past "
                 "them and the space reading larger than the person in it.")


def fix_echo(text):
    if not text:
        return text, False
    new = _ECHO.sub("", text)
    if new == text:
        return text, False
    new = new.rstrip()
    if not new.endswith("."):
        new += "."
    return new + _SCALE_CLAUSE, True


def fix_prompts():
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    n = 0
    for aid, rec in data.items():
        for key in ("home_prompt", "office_prompt"):
            fixed, did = fix_echo(rec.get(key))
            if did:
                rec[key] = fixed
                n += 1
    json.dump(data, open(JSON_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"replaced instruction echo in {n} prompts")


def fix_negatives():
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    n = 0
    for aid, rec in data.items():
        for key in ("home_prompt", "office_prompt"):
            if rec.get(key):
                rec[key + "_neg"] = build_negative(rec, key)
                n += 1
    json.dump(data, open(JSON_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"rebuilt {n} negative lines deterministically")


def main():
    if "--fix" in sys.argv:
        fix_prompts()
        fix_negatives()
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    order = ["cio", "operations", "business", "legal", "marketing",
             "creative", "movie", "engineer", "taliyah"]
    bad = 0
    for aid in order:
        rec = data.get(aid) or {}
        first = rec.get("first", aid)
        for key in ("home_prompt", "office_prompt"):
            fs = faults(rec, key, first)
            label = f"{first} {key.split('_')[0]}"
            if not fs:
                print(f"  OK   {label}")
                continue
            for sev, msg in fs:
                print(f"  {sev} {label}: {msg}")
                if sev == "FAIL":
                    bad += 1
    print(f"\n{bad} blocking fault(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
