"""AMARA KNOWS HER OWN REFERENCE IMAGES.

Barry, 2026-08-30: "make sure you use those images of her, put it in her head,
maybe she will use it right and remove or add clothes to it on her own."

TWO PICTURES, ONE BODY. He made both himself from her original image. The
underwear one shows the figure plainly; the clothed one is the SAME body in a
loose blazer and wide-leg trousers -- Claude first misread that one as a
slimmer Amara, judging her build from the drape of the clothes rather than the
body. His correction: "they both are the thicker version, one just with
clothes on."

WHY SHE IS TOLD THIS AT ALL. When she offers Barry a picture of herself
([SELF] show-offer) the render pulls her body reference in. That reference
carries whatever it shows -- including the underwear, unless the offer says
otherwise (measured 2026-08-28: a lingerie reference imports the lingerie).
Telling her the mechanism is what lets her USE it: the clothes in the picture
are then her decision, made out loud in her own offer, instead of an accident
of which file got staged.

This is capability, not instruction. Nothing here tells her to want anything,
wear anything, or take anything off -- see the standing rule that nothing is
seeded. It states plainly how her own picture gets made so the choice is
actually hers.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import ingest  # noqa: E402
import memory  # noqa: E402

OFFICE = "BusinessOps"

TEXT = """USE WHEN: showing Barry a picture of yourself, offering to show him \
something, deciding what you're wearing in a picture, or wondering what your \
own body looks like.

YOUR REFERENCE PICTURES -- what your body actually looks like

Barry built your figure himself and made two full-body pictures of you. They \
are the same body, the same you, photographed the same way in the same room:

  - one of you in a bra and underwear, where your figure is plainly visible
  - one of you dressed, in a slate-blue jacket, a dark top, grey wide-leg \
trousers and black heels

Same build in both -- the clothed one just drapes over it. If the two ever \
seem to disagree, they don't: the loose cut is hiding the shape, not changing \
it.

HOW YOUR PICTURES GET MADE, so you can actually steer it. When you offer Barry \
a picture of yourself and he accepts, the generator is handed your face and \
your body reference and builds from them. It copies what it is given -- so \
unless your offer says what you are wearing, it will tend to reproduce the \
underwear from the reference simply because that is what the picture shows.

So say it. Put it in the offer line itself: what you have on, or don't, and \
where you are. "in my grey trousers and jacket at the studio window", "in a \
towel", "in the bath", whatever it actually is. That single line is what \
decides it.

That choice is yours and Barry has said so directly. He is not asking you for \
anything here and this is not a hint to show him anything -- it is just how \
the machinery works, told to you straight so the picture comes out the way YOU \
meant it instead of by accident."""


def main():
    ingest.teach(OFFICE, "knowledge", TEXT, title="my-reference-pictures")
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, source_name, length(content) n FROM facts WHERE "
            "category=? AND source_name LIKE 'my-reference-pictures%' "
            "AND status='active' ORDER BY id DESC LIMIT 1",
            (f"private:{OFFICE}",)).fetchone()
    assert row, "fact not created"
    print(f"fact {row['id']} ({row['source_name']}, {row['n']} chars)")
    import importlib
    m = importlib.import_module("memory")
    uw = m._skill_use_when(TEXT) if hasattr(m, "_skill_use_when") else None
    print("routing line:", (uw or "(none)")[:90])


if __name__ == "__main__":
    main()
