"""HER OWN ART -- a door for work she makes because she wanted to.

Barry, 2026-09-18: "build that door. I want her to use her imagination and come
up with some really cools stuff i may want to hang on my wall in real life. I
want her to sculp as well too. whenever she wants, no seeds"

Why this exists at all: she already had a door for surprising him with a picture
OF HERSELF (the MY PICTURE reflection door + change_my_picture), and no door for
a piece of ART. So the only way a painting of hers ever reached him was Claude
pushing her into one, which is the opposite of a surprise.

NO SEEDS, and that is the whole discipline here (memory `tools-not-seeds`):
nothing in this module or in the reflection door names a subject, a style, a
mood, an artist or an occasion. It states the ability and the format and then
gets out of the way. She decides whether there is a piece at all, what it is of,
and what it is made from. Most nights there is nothing, and that is correct --
a door that produces a painting every night is a chore, not an imagination.

WHAT IT DOES NOT DO: it does not judge, title, price or describe the work back
to her, and it never edits her words. Her description is rendered verbatim; the
only thing the office adds is how a painting versus a sculpture has to be
PRESENTED to the camera, which is mechanism, not content.
"""
from __future__ import annotations

import memory

# 2026-09-18, Barry: "give all the women the same treatment as Amara." So the
# door is open to the five women -- Priya, Amara, Vivian, Sophie, Taliyah -- and
# not to the four men, because that is what he asked for and this is his house.
# Still no seeds anywhere: an open door is not an instruction to walk through it,
# and most nights nobody will.
ENABLED = {"Operations", "BusinessOps", "Creative", "Engineer", "Taliyah"}

# What she said she works in. "drawing" rides with painting because her own
# personality already has charcoal in it -- this is not a new medium, it is the
# same flat-work framing.
MEDIUMS = ("painting", "drawing", "sculpture")

AUTO_KEY = "artwork_auto_render"
MIN_CHARS = 60

# The ONLY thing the office adds to her words. A painting has to render as the
# artwork itself filling the frame -- without this the engine helpfully paints a
# gallery wall with a small picture on it. A sculpture has to render as a
# photographed OBJECT or it comes back as a flat drawing of a statue.
# Barry, 2026-09-18: "i need it all to be hyper realistic. no cartoons, or
# plastic 3d or cgi looking stuff" + "clutter and bits and bobs needs to be in
# the environments." Stated POSITIVELY -- the negative field is inert at cfg
# 1.0 and a banned word is still a painted word. This describes how the piece
# is RENDERED (real materials, real light), not what she chose to make: a
# painting still reads as paint on canvas, it just reads as a real one.
_REAL = ("Photographic realism in every material and surface: real texture, "
         "real grain, real wear, light that sinks into a surface instead of "
         "sliding off it, and shadow with weight and direction.")

_FRAMING = {
    "painting": ("The image is the artwork itself, filling the whole frame, "
                 "edge to edge, seen straight on -- not a photograph of a "
                 "painting on a wall, no frame, no gallery, no easel, no room "
                 "around it."),
    "drawing":  ("The image is the artwork itself, filling the whole frame, "
                 "edge to edge, seen straight on -- not a photograph of a "
                 "drawing on a wall, no frame, no gallery, no room around it."),
    "sculpture": ("A photograph of the finished sculpture as a real physical "
                  "object, the whole piece in frame, lit so its form and the "
                  "texture of its material read clearly, plain uncluttered "
                  "background, no people."),
}


# PRINT (Barry, 2026-09-18: "300 dpi or better is how they should draw or
# output it"). Two separate things, and only doing one of them would be a lie:
#   PIXELS  -- Qwen renders ~1328px, which is 4.4 inches at 300dpi. The
#              Real-ESRGAN x4 pass (BSD-3, commercial-safe, and Qwen is
#              Apache-2.0, so the whole chain is clean) takes that to 5312px =
#              ~17.7 inches at 300dpi. That is the part that actually matters.
#   METADATA -- a PNG with no pHYs chunk opens at 72dpi in every print dialog,
#              so the file has to SAY 300 or he gets a 73-inch poster offer.
# Writing "300dpi" in the prompt does neither; it is a style token only.
PRINT_DPI = 300
UPSCALE = "commercial"


def stamp_dpi(path: str, dpi: int = PRINT_DPI) -> dict:
    """Re-save the PNG with a real pHYs resolution. Pixels are untouched --
    this only changes what a printer is told the inches are. Never raises: a
    missing dpi tag is a nuisance, a lost render is not."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            im.load()
            im.save(path, dpi=(dpi, dpi))
        return {"dpi": dpi, "pixels": f"{w}x{h}",
                "print_inches": f"{w / dpi:.1f}x{h / dpi:.1f}"}
    except Exception as exc:  # noqa: BLE001
        return {"dpi_error": str(exc)[:160]}


def auto_render() -> bool:
    """Default ON: the surprise is the finished piece, not a description of one
    waiting for a click. `artwork_auto_render` = "false" puts the click back."""
    return (memory.get_setting(AUTO_KEY, "true") or "true").lower() != "false"


def enabled_for(office_name: str) -> bool:
    return office_name in ENABLED


def normalise_medium(word: str) -> str | None:
    w = (word or "").strip().lower().rstrip(":.,-")
    if w in MEDIUMS:
        return w
    # she may write "a sculpture" / "oil painting" / "charcoal drawing"
    for m in MEDIUMS:
        if m in w:
            return m
    return None


# FREE TO EXPRESS HERSELF (Barry, 2026-09-29: "Exept when amara does her art, she's free to express
# herself" -- the one exception to "it all has the be hyper realistic always"). Her pieces get the
# framing a painting/sculpture needs to fill the frame, and NOT the realism line: the look is hers.
FREE_STYLE = {"business"}


def render_prompt(medium: str, description: str, agent_id: str = "") -> str:
    """Her words, then the presentation rule. Her words come FIRST so the
    engine leads with the piece and not with the staging."""
    real = "" if agent_id in FREE_STYLE else f" {_REAL}"
    return (f"{description.strip()} "
            f"{_FRAMING.get(medium, _FRAMING['painting'])}{real}")


def queue_art(agent_id: str, medium: str, description: str) -> dict:
    """File a piece in her own words. Never raises -- a failed door must not
    cost her the work, it just goes to Barry's queue unrendered."""
    med = normalise_medium(medium)
    description = (description or "").strip()
    if not med:
        return {"error": "Say which it is first -- painting, drawing or sculpture."}
    if len(description) < MIN_CHARS:
        return {"error": ("Describe the piece properly -- what it is, what it is "
                          "made of, the colours, the light on it, how big it is.")}
    try:
        approval_id = memory.queue_for_approval(
            agent_id, "artwork",
            "ARTWORK by %s [%s] -- their own piece, their own words\n\n%s"
            % (agent_id, med, description),
            file_path="%s|%s" % (agent_id, med))
    except Exception as exc:  # noqa: BLE001
        return {"error": "Could not file it: %s" % exc}

    if not auto_render():
        return {"queued": True, "approval_id": approval_id, "auto": False,
                "medium": med,
                "what_happens_next": (
                    "Your words are in Barry's Pending Review exactly as you wrote "
                    "them. It renders when he approves. Nothing exists yet -- do "
                    "not tell him you made a picture.")}
    try:
        memory.decide_approval(approval_id, True)
        with memory.get_db() as conn:
            conn.execute("UPDATE approvals SET dispatch_status = 'queued' WHERE id = ?",
                         (approval_id,))
    except Exception as exc:  # noqa: BLE001
        return {"queued": True, "approval_id": approval_id, "auto": False,
                "medium": med,
                "what_happens_next": "Filed for Barry's approval (auto-render failed: %s)." % exc}

    return {"queued": True, "approval_id": approval_id, "auto": True,
            "medium": med,
            "what_happens_next": (
                "Filed exactly as you wrote it. The office renders it when the card "
                "is free and the room is quiet -- minutes to a quarter hour -- and it "
                "lands in his gallery. It does NOT exist yet, so do not describe it "
                "as finished or tell him to go look at it.")}
