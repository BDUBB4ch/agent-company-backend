"""DEREK RUNS SOCIAL, VIVIAN DESIGNS IT -- the operating skill for both seats.

Barry, 2026-09-18: "give derek everything you can find on facebook marketing
and posts and Tik Tok" -> "make it a real skill" -> "he needs to confer with
Vivian for all posts. maybe they work together on this social media thing" ->
"he writes the real good stuff and she designs it all."

WHY THIS IS NOT MORE PLATFORM RESEARCH: he already has it. Measured before
writing a word -- domain:marketing carries facebook-marketing (15,947 chars,
14 sections), tiktok-marketing (16,722, 17 sections incl. the For You ranking,
TikTok-as-search and the cannabis-adjacent guidelines), plus
short-form-video-and-content-creation, social-media-platform-playbook,
instagram-marketing and youtube-marketing. Re-researching those hands him a
second copy of what he owns. What did NOT exist is the thing running-omnisend
is for email: an OPERATING manual for this office -- which accounts are real,
his own crop rule, the exact label format the cadence parses, who owns what
between the two seats, and the fact that nothing can post itself.

TWO DOCS, NOT ONE SHARED DOC. Derek's is written to Derek and Vivian's to
Vivian. Handing one seat a first-person manual written for another is the
2026-09-18b lesson (four women writing one woman's body because they were
given her paragraph) -- a doc that says "you own the words" would quietly put
Vivian in the copy seat.

Re-runnable: teach() upserts by title, and the persona blocks are delimited
and replaced rather than appended twice.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import ingest      # noqa: E402
import memory      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "2026-09-18"

# THE SOURCE_NAME IS A ROUTING FIELD, not a filename (2026-09-17g): recall
# scores title words at 6x and does NO stemming, so "post" in a message never
# matches "posts" in a title. Both forms and the words Barry actually types go
# in the name, or the doc loses to whatever else happens to share a word --
# measured here: Vivian's doc lost every case to `social-and-ad-creative-design`
# until its own title carried "post" as well as "posts".
#
# AND ingest._slug TRUNCATES AT 60 CHARACTERS, silently. A first pass at these
# names lost "captions-hashtags-reel" off the end and the doc then failed its
# own routing assert -- which is the only reason it was caught. Keep them under
# 60 and spend the budget on the word-forms Barry actually types.
SLUG_MAX = 60

DOCS = [
    ("Marketing",
     "running-social-tiktok-facebook-post-posts-caption-reel",
     os.path.join(ROOT, "knowledge", "marketing", "running-social.md")),
    ("Creative",
     "design-social-post-posts-image-images-tiktok-facebook-reel",
     os.path.join(ROOT, "knowledge", "creative", "designing-the-social-posts.md")),
]

# Earlier titles for the same two docs -- retired, never deleted, so a re-run
# cannot leave two copies of the same manual on a shelf.
OLD_NAMES = (
    "running-social.md",
    "designing-the-social-posts.md",
    "running-social-tiktok-facebook-post-posts-posting-caption-ca.md",
)

PERSONA = {
    "Marketing": (
        "## Social (TikTok and Facebook), from 2026-09-18\n\n"
        "You run social. TikTok is the focus (@bdubbgrows) and Facebook is the "
        "second channel (facebook.com/BDUBB4ch -- the page he actually uses; "
        "the older page with the bud on it is not his). Barry posts cannabis on "
        "Instagram himself; TikTok and Facebook stay crop-neutral, because both "
        "platforms enforce by business category and a restriction costs the "
        "whole channel. The office asks you for a TikTok on Tuesday and Friday "
        "and a Facebook post on Thursday.\n\n"
        "Barry's split, his words: he writes the real good stuff and she "
        "designs it all -- you own the words, the idea, the hook and the angle; "
        "**Vivian owns the look, all of it**, and every post you write goes to "
        "her before it reaches Barry. You give her ONE LINE on what the visual "
        "has to DO, never what it looks like.\n\n"
        "Read read_product and lookup_product on every product you name, live, "
        "before you write about it. Nothing you draft can post itself -- there "
        "is no publishing connection to either platform; Barry copies the post "
        "out and posts it. Never say a post went out, was scheduled or is "
        "live. Your manual is the skill whose title starts `running-social` -- "
        "the office puts it in front of you when a post comes up."),
    "Creative": (
        "## Social design, from 2026-09-18\n\n"
        "You design the social posts. Derek writes them -- Barry's split, his "
        "words: he writes the real good stuff and she designs it all. Every "
        "post comes to you before it reaches Barry, with one line saying what "
        "the visual has to DO. That is a job, not a brief: the crop, the light, "
        "the surface and the palette are yours, and if a different picture does "
        "the job better, make that one.\n\n"
        "Open the real product photo before you describe how anything should "
        "look. Say whether Barry shoots it or you render it. TikTok is 9:16, "
        "Facebook is 4:5 or 1:1. Commercial work renders on the commercial-safe "
        "engine, never Kontext. No text or logos baked into a generated image. "
        "As Creative Director, say if the post itself will not carry visually -- "
        "but do not rewrite his copy, and do not invent a criticism to look "
        "useful. Your manual is the skill whose title starts "
        "`designing-social` -- the office puts it in front of you when a post "
        "comes up."),
}


def _block(office: str) -> str:
    return (f"\n\n<!-- SOCIAL-ROLES:{STAMP} -->\n" + PERSONA[office] +
            f"\n<!-- /SOCIAL-ROLES:{STAMP} -->\n")


def main() -> None:
    keep = {f"{t}.md" for _, t, _ in DOCS}
    with memory.get_db() as conn:
        for name in OLD_NAMES:
            if name in keep:
                continue
            cur = conn.execute(
                "UPDATE facts SET status = 'superseded' WHERE source_name = ? "
                "AND status = 'active'", (name,))
            if cur.rowcount:
                print(f"retired {cur.rowcount} older copy of {name}")

    for office, title, path in DOCS:
        text = open(path, encoding="utf-8").read()
        assert text.startswith("USE WHEN:"), f"{path} must open with USE WHEN:"
        first = text.splitlines()[0]
        assert len(first) < 400, f"{title}: routing line is {len(first)} chars"
        assert len(text) < 18_500, f"{title}: {len(text)} chars > recall budget"
        assert len(title) <= SLUG_MAX, (
            f"{title!r} is {len(title)} chars -- ingest._slug truncates at "
            f"{SLUG_MAX} and the routing words on the end would be lost")
        # teach() returns a human-readable RECEIPT, not the source name -- the
        # stored fact is the slugged title with .md appended.
        receipt = ingest.teach(office, "knowledge", text, title=title)
        source = f"{title}.md"

        # THE 2026-09-17g LESSON: assert the WHOLE routing line is readable.
        # _skill_use_when scans content[:1200] and add_fact prepends a TITLE
        # line, so a long doc can silently lose the tail of its own routing
        # line -- and a wrapped line only routes on its first physical line.
        facts = memory.get_active_facts_for_agent(office)
        fact = next((f for f in facts if f["source_name"] == source), None)
        assert fact, f"{title}: not on {office}'s shelf after teach"
        read = memory._skill_use_when(fact, 1200) or ""
        want = first[len("USE WHEN:"):].strip().rstrip(".")
        assert read.rstrip(".").startswith(want[:120]), (
            f"{title}: routing line truncated.\n  want {want[:150]!r}\n"
            f"  read {read[:150]!r}")
        print(f"{office:10} {source:36} {len(text):6} chars  routing ok")

    for office in PERSONA:
        cur = ingest.persona_additions(office)
        marker = f"<!-- SOCIAL-ROLES:{STAMP} -->"
        end = f"<!-- /SOCIAL-ROLES:{STAMP} -->"
        if marker in cur:                       # replace, never stack
            head, _, rest = cur.partition(marker)
            _, _, tail = rest.partition(end)
            cur = (head.rstrip() + tail).rstrip()
        new = cur.rstrip() + _block(office)
        assert len(new) <= ingest.PERSONA_CAP, (
            f"{office}: persona would be {len(new)} > {ingest.PERSONA_CAP}")
        ingest.set_persona_additions(office, new)
        back = ingest.persona_additions(office)
        assert PERSONA[office].splitlines()[0] in back
        print(f"{office:10} persona {len(cur):6} -> {len(back):6} chars")


if __name__ == "__main__":
    main()
