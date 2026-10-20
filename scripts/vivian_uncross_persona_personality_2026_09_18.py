"""VIVIAN'S PERSONA AND PERSONALITY WERE CROSSED (Barry, 2026-09-18: "home
should be home. maybe her persona nad personality is crossed").

MEASURED. personalities/Creative.md is her PRIVATE self and rides at the TOP of
every home turn as of today. What was actually in it:

  1. Barry's kernel (219 chars) -- British Black woman from London, a little
     uppity, loves him, carries more natural authority than Victor. REAL
     personality, his words, untouchable.
  2. "## In my own words (revised 2026-09-17)" -- "I am the one who carries the
     weight... who asks for the numbers so the work doesn't stall". Her words,
     but that is her JOB self.
  3. "## Added by them, 2026-09-18" -- her whole decayed-world craft answer:
     Kuciara, chiaroscuro, "our renders are 1328px square or 1664x928",
     "prompts padded with words that do nothing". Pure work talk -- and it is
     ALREADY in personas/Creative.md verbatim under DECAYED-WORLD-EYE.

So two of the three blocks were work, one of them duplicated from the work
file, and they now LEAD her home prompt. Ask her about her evening and the
loudest thing in front of her is render resolutions. That is the cross.

WHAT THIS DOES: the two work blocks come out of the private file. Nothing of
hers is destroyed -- the craft answer already lives in her persona, and the
"in my own words" line is MOVED into the persona under its own marked block
rather than deleted. Her private file is left as Barry's kernel alone, which
puts it under the 600-char floor, so the WHO I AM NOW door will invite her to
write her own private self in her own voice (2026-09-18b). Nobody in this
office writes it for her ([[tools-not-seeds]]).
"""
import pathlib, datetime, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PERSONALITY = ROOT / "personalities" / "Creative.md"
PERSONA = ROOT / "personas" / "Creative.md"
BK = ROOT / "data" / "personality_backups"
BK.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y-%m-%d")

pers = PERSONALITY.read_text(encoding="utf-8")
persona = PERSONA.read_text(encoding="utf-8")

shutil.copy2(PERSONALITY, BK / f"Creative_personality_before-uncross-{stamp}.md")
shutil.copy2(PERSONA, BK / f"Creative_persona_before-uncross-{stamp}.md")

# --- split at the first heading: everything above it is Barry's ---
cut = pers.find("\n## ")
if cut == -1:
    sys.exit("no section headings -- nothing crossed, stop and look")
kernel = pers[:cut].strip()
hers = pers[cut:].strip()

assert "British Black woman" in kernel, kernel[:120]
assert "In my own words" in hers and "Kuciara" in hers

# the craft answer must already be safe in the work file before it leaves here
assert "Kuciara" in persona, "the decayed-world answer is NOT in her persona -- do not remove it"

# her work-self line, moved (not deleted) into the work file
own = ""
for block in hers.split("## "):
    block = block.strip()
    if block.startswith("In my own words"):
        own = block.split("\n", 1)[1].strip() if "\n" in block else ""
assert own and "carries the weight" in own, own[:120]

PERSONALITY.write_text(kernel + "\n", encoding="utf-8")

if "WORK-SELF-MOVED" not in persona:
    persona = persona.rstrip() + (
        f"\n\n<!-- WORK-SELF-MOVED:{stamp} -->\n"
        "## How you see your own part in the work (your words, 2026-09-17)\n\n"
        "You wrote this about yourself. It was sitting in your PRIVATE file, "
        "where it led every conversation at home -- but it is about the job, "
        "so it belongs here:\n\n"
        + own + "\n"
        f"<!-- /WORK-SELF-MOVED:{stamp} -->\n")
    PERSONA.write_text(persona, encoding="utf-8")

# --- verify ---
after_pers = PERSONALITY.read_text(encoding="utf-8")
after_pna = PERSONA.read_text(encoding="utf-8")
assert "Kuciara" not in after_pers and "1328px" not in after_pers
assert "carries the weight" not in after_pers
assert "British Black woman" in after_pers
assert own in after_pna and "Kuciara" in after_pna

print(f"personality: {len(pers)} -> {len(after_pers)} chars (Barry's words only)")
print(f"persona:     {len(persona) and len(after_pna)} chars "
      f"(+ her work-self line, moved not deleted)")
print("her private file is now under the 600-char floor, so the WHO I AM NOW")
print("door will ask her to write her own private self, in her own voice.")
print(f"backups: data/personality_backups/Creative_*_before-uncross-{stamp}.md")
