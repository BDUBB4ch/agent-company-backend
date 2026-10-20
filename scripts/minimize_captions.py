"""Rewrite v4 captions to the MINIMAL style that actually produced working LoRAs.

THE BUG THIS FIXES (found 2026-08-08 by rendering keth_character_v4):
A trigger token only learns what the caption does NOT already explain. The v4
captions carried the full canon spec on every frame:

    @Keth, alien being, smooth gray skin, elongated hairless cranium, large eyes
    with vivid green iris no sclera no whites, small low-profile subtly pointed
    ears, ... , sitting on the floor of a steel detention room, side view

so the model could account for every image using ordinary words and @Keth
absorbed NOTHING. Proof: prompting "@Keth, close-up portrait, gray facility
jumpsuit" with that LoRA renders an ordinary HUMAN. Every alien feature in the
other test renders came from the prompt words, not the LoRA.

The captions behind the LoRAs that DID work:
    lora_keth   ->  "@Keth, cinematic still"
    lora_bdubb  ->  "@BDUBB, black baseball cap..., cinematic still"   (clothing varies)

RULE: caption the TRIGGER + WHAT VARIES (pose, framing, scene, clothing).
NEVER caption invariant anatomy. This also solves the earlier problem for free --
if the caption never claims "small low-profile ears", it can never teach that
phrase onto a flared ear.

Dry run by default. --write commits. Old captions are saved to <folder>/_captions_v4_full.json
so this is reversible.
"""
import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input"

# The invariant spec prefix each set carries, which must come OUT of the captions.
SPECS = {
    "lora_keth_v4": (
        "@Keth",
        "alien being, smooth gray skin, elongated hairless cranium, large eyes with vivid "
        "green iris no sclera no whites, small low-profile subtly pointed ears, slight lean "
        "build, approximately four feet tall, barefoot, gray facility jumpsuit, "
        "dignified not monstrous",
    ),
    "lora_bia_v4": (
        "@Bia",
        "alien woman, Afro-Latina, athletic build, sleek faded pixie cut shaved on one side, "
        "subtly pointed ears, hazel-gold iris centre with a thick beaded deep-purple outer "
        "ring, non-glowing, subtle gold alien spots across skin, iridescent flecks on temples "
        "and cheekbones",
    ),
    "lora_tazz_v4": (
        "@Tazz",
        "alien woman, light skin, subtly pointed ears, violet and pink double-ring irises "
        "non-glowing, slightly muscular athletic build, two long dark braids",
    ),
}

# Eye-crop captions are bespoke; collapse them to trigger + framing only.
EYE_RE = re.compile(r"extreme close-up of the eyes", re.I)

# Residual anatomy that survived the spec strip. These describe the CHARACTER,
# not the frame, so they must not appear in a caption either -- same reason as
# the spec itself: anything the caption explains, the trigger does not learn.
ANATOMY = [
    "pointed ear clearly visible",
    "shaved side of the pixie cut visible",
    "pointed ear visible",
]


def _strip_anatomy(clauses):
    out = []
    for c in clauses:
        cl = c.strip()
        if any(a in cl.lower() for a in ANATOMY):
            continue
        out.append(cl)
    return out


def minimise(text: str, trigger: str, spec: str) -> str:
    t = text.strip()
    if EYE_RE.search(t):
        return f"{trigger}, extreme close-up of the eyes"
    # strip "TRIGGER, <spec>, " leaving only the per-frame variation
    head = f"{trigger}, {spec}"
    if t.startswith(head):
        rest = t[len(head):].lstrip(", ").strip()
        kept = _strip_anatomy(rest.split(",")) if rest else []
        return f"{trigger}, " + ", ".join(kept) if kept else f"{trigger}, cinematic still"
    # fallback: drop any clause that appears in the spec
    spec_clauses = {c.strip().lower() for c in spec.split(",")}
    kept = _strip_anatomy([c for c in t.split(",")
            if c.strip().lower() not in spec_clauses and c.strip() != trigger])
    return f"{trigger}, " + ", ".join(kept) if kept else f"{trigger}, cinematic still"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    for folder, (trigger, spec) in SPECS.items():
        d = ROOT / folder
        if not d.is_dir():
            print(f"{folder}: NOT FOUND")
            continue
        caps = sorted(d.glob("*.txt"))
        backup, samples = {}, []
        for c in caps:
            old = c.read_text(encoding="utf-8")
            new = minimise(old, trigger, spec)
            backup[c.name] = old
            if len(samples) < 3 and new not in [s[1] for s in samples]:
                samples.append((old, new))
            if args.write:
                c.write_text(new, encoding="utf-8")
        if args.write:
            (d / "_captions_v4_full.json").write_text(
                json.dumps(backup, indent=1), encoding="utf-8")
        avg_old = sum(len(v) for v in backup.values()) / max(1, len(backup))
        avg_new = sum(len(minimise(v, trigger, spec)) for v in backup.values()) / max(1, len(backup))
        print(f"\n=== {folder} ({len(caps)} captions)  avg {avg_old:.0f} -> {avg_new:.0f} chars ===")
        for old, new in samples:
            print(f"  OLD: {old[:110]}...")
            print(f"  NEW: {new}")
    print("\n" + ("WRITTEN (originals in _captions_v4_full.json)" if args.write
                  else "DRY RUN -- use --write"))


if __name__ == "__main__":
    main()
