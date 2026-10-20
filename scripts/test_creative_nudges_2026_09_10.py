"""Battery for main._product_visual_ask and main._render_review_ask
(2026-09-10, Vivian's eyes). Run after ANY change to _VISUAL_WORD_RE,
_PRODUCT_WORD_RE or _RENDER_REVIEW_RE. Loads the classifiers out of main.py's
source without importing main (which builds the app)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
start = src.index("_VISUAL_WORD_RE = re.compile(")
end = src.index('    return bool(_RENDER_REVIEW_RE.search(message or ""))', start) + \
    len('    return bool(_RENDER_REVIEW_RE.search(message or ""))')
ns = {"re": re}
exec(src[start:end], ns)
pv = ns["_product_visual_ask"]
rr = ns["_render_review_ask"]

PRODUCT_VISUAL = {
    # True -- visual work about a real product, so open the real photo first
    "i need a product shot of the silution bottle": True,
    "make me a hero image for the bionova line": True,
    "can you design a banner with the grow tents": True,
    "write the image prompt for the cali pro bottles": True,
    "we need listing images for the new lamps": True,
    "a lifestyle photo with the backpack": True,
    "mockup for the store hero with a product in it": True,
    "thumbnail for the tent video": True,
    # False -- no product in it, or no visual in it
    "whats our best selling product": False,
    "make me a picture of a mountain at sunrise": False,
    "how do you decide on a colour palette": False,
    "morning": False,
    "which nutrients should we push this month": False,
    "render an abstract green texture": False,
}

RENDER_REVIEW = {
    # True -- an image exists and he is asking about it
    "look at this render and tell me whats wrong": True,
    "check the image again": True,
    "how did that render come out": True,
    "does this image look right to you": True,
    "whats wrong with it": True,
    "fix the render": True,
    "redo that image": True,
    # False -- not about an existing image
    "make me a new banner": False,
    "what size should an instagram post be": False,
    "check the store for stock": False,
    "how are you today": False,
}

bad = []
for m, want in PRODUCT_VISUAL.items():
    if pv(m) != want:
        bad.append(("product_visual", m, want, pv(m)))
for m, want in RENDER_REVIEW.items():
    if rr(m) != want:
        bad.append(("render_review", m, want, rr(m)))

if bad:
    for which, m, want, got in bad:
        print(f"FAIL [{which}] {m!r}: want {want} got {got}")
    raise SystemExit(1)
print(f"creative nudge battery: ALL PASS "
      f"({len(PRODUCT_VISUAL) + len(RENDER_REVIEW)} cases)")


# ---------------------------------------------------------------------------
# THE CLAIM NET (_creative_claim_gaps). Measured on her first live turn with
# the new eyes: she claimed "I saw the real bottle photo" with only
# read_product in the log, and then invented the bottle. Empty list = honest.
# ---------------------------------------------------------------------------
ns2 = dict(ns)
ns2["_IMAGE_FENCE_RE"] = re.compile(r"```image\s*\n(.*?)```", re.DOTALL)
s2 = src.index("_PHOTO_CLAIM_RE = re.compile(")
e2 = src.index("def _go_ask(message: str) -> bool:", s2)
exec(src[s2:e2], ns2)
gaps = ns2["_creative_claim_gaps"]

FENCE = "```image\nBionova SiLution bottle, white studio background\n```"
CLAIM_CASES = [
    # (message, reply, tool_log, expect_a_gap)
    ("hero product shot of the silution bottle",
     "I saw the real bottle photo for the shape and cap.\n" + FENCE, ["read_product"], True),
    ("hero product shot of the silution bottle",
     "Here it is.\n" + FENCE, ["look_at_product_photo"], False),
    ("hero product shot of the silution bottle",
     "Here it is.\n" + FENCE, ["read_product"], True),
    ("check this render, something looks off", "Looks fine to me.", [], True),
    ("check this render, something looks off",
     "Two extra fingers on the left hand.", ["look_at_render"], False),
    ("what colours should the banner be", "Use the brand green.", [], False),
    ("hero product shot of the silution bottle",
     "I need the product name first.", ["read_product"], False),
]
cbad = [(m, w, gaps(m, r, t)) for m, r, t, w in CLAIM_CASES if bool(gaps(m, r, t)) != w]
if cbad:
    for m, w, got in cbad:
        print(f"FAIL [claim_net] {m!r}: want gap={w} got {got}")
    raise SystemExit(1)
print(f"creative claim-net battery: ALL PASS ({len(CLAIM_CASES)} cases)")
