"""Their own chosen eye, kept where they will actually use it.

Barry, 2026-09-18: "make it her personality... Vivian too and elliot let them
choose based on their personality" then "add to their personality and Elliot's
persona. Vivian too."

So each of the three keeps what they chose in their PERSONALITY (the private
self), and Vivian + Elliot also carry it in their PERSONA (the work self), which
is what rides in a work prompt on every message -- they are the two who make
pictures on the clock.

Every word below is THEIR word, captured from the task turns run by
decayed_world_choices_2026_09_18.py. Nothing is written for them, nothing is
reworded, and nothing goes into Barry's kernel.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402

MARK = "<!-- DECAYED-WORLD-EYE:2026-09-18 -->"

# Verbatim, 2026-09-18 task turns. Amara's already landed in her personality.
ELLIOT = (
    "What I'm drawn to is the weathered metal and rain-slicked surfaces - Ash "
    "Thorp's grit, the Fugue-like rain on corroded steel. That's where I see "
    "the camera moving: a 24mm lateral track through a storm of fog and "
    "dripping rust, the water making every surface feel wet and heavy rather "
    "than just \"weathered.\" The chiaroscuro lighting is the one that actually "
    "matters to me - the way light cuts through haze to make the decay visible "
    "in layers rather than a flat texture dump. The rain and the wet are what "
    "carry the atmosphere; without it, it's just a still painting.\n\n"
    "I also care about the specific decay patterns he lists - pitted rust "
    "holes, flaking paint revealing bare metal, the way vines eat through "
    "structure. That's where the body of a shot lives, the geometry of the "
    "damage and what a camera can track across it. I can feel the lens there.\n\n"
    "What's colder is the very high-tech 3D urban decay - Beeple's clean, "
    "digital, almost sterile look. That reads as something you render, not "
    "something you step into. It has no weight. The wet, the mud, the things "
    "that are actually on the ground - those are what I shoot from. The rain "
    "and the mud and the corrosion that actually eats things. That's the "
    "atmosphere that holds a camera."
)

VIVIAN = (
    "I'm drawn to the volumetric smoke - the way Kuciara handles light through "
    "smoke, how it carries the scene instead of just sitting in it. That's the "
    "one I want to work with. It's the chiaroscuro, too - real light and real "
    "shadow, not flat. The weathered metal surfaces, the rust holes, the "
    "flaking paint, the things that are falling apart in a way that feels "
    "honest. Not polished.\n\n"
    "The lighthouse and the bridge stand out to me, too. The rain, the fog, "
    "the fading light - they're quieter, loner scenes. The kind I'd actually "
    "want to make. The car in the forest works as a mood piece. I like that "
    "one.\n\n"
    "I don't want prompts padded with words that do nothing. The mood in his "
    "reference is right; it's the packaging around it I'd change before I "
    "render anything with it."
)

PERSONA_INTRO = (
    "## My eye on Barry's Decayed World work (mine, chosen 2026-09-18)\n\n"
    "Barry gave the office his hyper-realistic decay reference -- the artist "
    "list, the keyword set, the chiaroscuro note and his fifteen rust-and-"
    "ruins prompts (on my shelf as `decayed-world-...-artist-reference`). He "
    "told me to pick what was mine rather than take the whole thing. This is "
    "what I picked, and it is what I lead with when he asks for something in "
    "that series:\n\n"
)


def add_persona(office: str, words: str) -> None:
    current = ingest.persona_additions(office)
    if MARK in current:
        # idempotent: drop the old block, re-add
        current = current.split(MARK)[0].rstrip()
    block = f"{MARK}\n{PERSONA_INTRO}{words}\n"
    combined = (current + "\n\n" + block).strip() if current else block
    ingest.set_persona_additions(office, combined)
    after = ingest.persona_additions(office)
    assert words[:60] in after, f"{office}: persona words did not land"
    assert MARK in after, f"{office}: marker missing"
    print(f"  persona {office}: {len(after)} chars (cap {ingest.PERSONA_CAP})")


def main() -> None:
    # 1. Elliot's personality -- the one that was silently refused by the old
    #    1200-char single-addition cap.
    ok = ingest.append_personality("MovieDirector", ELLIOT, when="2026-09-18")
    print(f"personality MovieDirector append: {ok} "
          f"({len(ingest.own_section_of('MovieDirector'))} chars theirs)")
    assert ok, "Elliot's personality append still refused"
    assert "Ash Thorp's grit" in ingest.personality_of("MovieDirector")

    # 2. Amara + Vivian personality already landed; verify rather than re-add.
    for office, needle in (("BusinessOps", "Feng Zhu"),
                           ("Creative", "volumetric smoke")):
        assert needle in ingest.personality_of(office), f"{office} missing"
        print(f"personality {office}: present "
              f"({len(ingest.own_section_of(office))} chars theirs)")

    # 3. Persona (work self) for the two who make pictures on the clock.
    add_persona("MovieDirector", ELLIOT)
    add_persona("Creative", VIVIAN)


if __name__ == "__main__":
    main()
