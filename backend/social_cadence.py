"""DEREK'S SOCIAL POSTS -- TikTok twice a week, Facebook once, same shape as
the email cadence.

Barry, 2026-09-18: "i say we just focus on Tik Tok, but facebook is good for
marketing as well. I want derek to have the same abilities as with emails."
Preceded by the two facts that set the lanes: "instagram is where i Usually
post cannabis stuff" and, of the Facebook page with the bud on it, "i dont
even use that one."

WHAT "THE SAME ABILITIES AS WITH EMAILS" MEANS HERE, honestly split:

  BUILT (this file): the drafting half, and it is the same machinery as
  email_cadence.py on purpose -- scheduled slots, a rotation of post kinds so
  the feed is not three sells in a row, the brief that forces him to read real
  product data first, the live fact-check with one re-run, and the finished
  post queued to Barry's Out box with its date on it. He copies it out and
  posts it. That is exactly how he asked for email to work before he let it
  send ("I want to just copy and paste the emails that they create").

  NOT BUILT, and not blocked by code: the SENDING half. Email sends because
  Omnisend has an API and his key is in .env. TikTok's Content Posting API and
  Meta's Graph publishing both need a developer app and a platform review
  under his own account -- his clicks, not ours, the same shape as the
  Microsoft Ads developer token. `social_post` is deliberately absent from
  dispatch._DESTINATIONS, so an approve click records "approved but not sent"
  rather than pretending. When he has the access, wiring it is one adapter
  function plus one line in that table, and the autonomy phase can come with
  it -- there is no point in a `social_autonomy` switch that approves a draft
  nothing can deliver.

CROP POLICY IS HIS, NOT THE PLATFORM'S. He posts cannabis on Instagram and has
been doing it; TikTok and Meta both enforce by business CATEGORY, which is the
same wall the Microsoft drug classifier is. So the rule is a live setting
rather than a guess baked into a brief: `social_cannabis_platforms` lists the
platforms where cannabis-forward content is allowed, and it starts as
"instagram" because that is the lane he named. One setting change moves it.
Without this, Derek hedges every caption into mush or gets the account
restricted -- both bad, and neither is Claude's call to make for him.

State: data/social_cadence_state.json. Log: data/social_cadence.log.
Manual trigger: `draft_now()` or `draft_now("tiktok", "grower-tip")`.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re

import httpx

import clock
import content_policy
import factcheck
import ideation
import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE = os.path.join(_ROOT, "data", "social_cadence_state.json")
_LOG = os.path.join(_ROOT, "data", "social_cadence.log")

AGENT_ID = "marketing"
CHECK_EVERY_SECONDS = 15 * 60
STARTUP_DELAY_SECONDS = 240        # after the email cadence, never the same tick
DRAFT_LEAD_HOURS = 48

# How many undecided social drafts may sit in Pending before the cadence stops
# adding more. A week of not clicking must not stack up nine posts he then has
# to wade through -- the same guard home_refresh uses for pictures.
MAX_PENDING = 4

# Which platforms may carry cannabis-forward content. His lane, live setting.
CANNABIS_KEY = "social_cannabis_platforms"
CANNABIS_DEFAULT = "instagram"

# Post slots: (weekday, hour, platform). Monday = 0.
# "just focus on Tik Tok, but facebook is good for marketing as well" -> two
# TikToks and one Facebook a week. Deliberately not Wednesday or Saturday:
# those are the email slots, and one channel a day keeps the GPU turns apart.
SLOTS = (
    (1, 10, "tiktok"),      # Tuesday
    (3, 10, "facebook"),    # Thursday
    (4, 10, "tiktok"),      # Friday
)

# THE ANGLES ARE BARRY'S, 2026-09-18, verbatim: "tips tricks, how to use
# Bionova with house plants, what nutrients are good for whatever plant they
# are growing. how to use bionova with indoor veggie and herb gardens. Also
# promoting other products."
#
# These replaced a generic set Claude had invented, and they are better for two
# reasons worth keeping: house plants, herbs and indoor veg are CROP-NEUTRAL by
# nature, so the whole TikTok/Meta category problem simply does not arise -- and
# they still sell Bionova, which is the 55-60% margin line and the recurring
# revenue engine. "What nutrients for what plant" is also the exact phrasing
# people type into TikTok search.
#
# Rotation is per platform so neither feed gets the same shape twice running,
# and the two lists differ in length so the weeks do not lock in step.
KINDS = {
    "tiktok": ("tips-and-tricks", "bionova-houseplants", "which-nutrients",
               "bionova-veggies-herbs", "other-products"),
    "facebook": ("bionova-houseplants", "other-products", "which-nutrients",
                 "bionova-veggies-herbs", "tips-and-tricks", "store-news"),
}

# WHAT A POST IS ALLOWED TO BE ABOUT (Barry, 2026-09-18): "their posts dont
# always need to be about whats selling or not, but also Plants in general and
# how bdubbgrowsllc.com can help... they should do a mixture off things to help
# sell this stuff. I paid for Bionova so it needs to go."
#
# Two corrections in one message. The store data had become the brief, and it
# is only ONE input -- most of what earns an audience is plant talk with no
# product in it at all. And there is a commercial priority that was nowhere in
# any of this: he has real money sitting in Bionova stock, it is the highest
# margin line in the shop and the one that reorders, so when a post does carry
# a product, that is the default one.
_MIX = content_policy.MIX

_BAR = (
    "\n\nTHE BAR -- Barry's words: real creative posts that kill, and he wants "
    "the two of you at MASTER LEVEL. That is a craft standard, so here is what "
    "it actually means:\n"
    "  * ONE IDEA. Say it to yourself in a single sentence before you write. "
    "If you cannot, you do not have a post yet.\n"
    "  * OPEN ON THEIR PROBLEM, not your product. The first line is something "
    "they are already looking at on their own plant.\n"
    "  * SPECIFIC BEATS TRUE. 'Yellowing between the veins on the older leaves "
    "first' lands; 'unhealthy plants' does not. Detail is the proof you grow.\n"
    "  * EARN IT WITH A TURN -- what everyone believes, then what is actually "
    "happening. A post with no turn in it is a leaflet.\n"
    "  * SHOW, DO NOT ANNOUNCE. Put the proof in the frame rather than "
    "claiming it in words.\n"
    "  * WRITE THE CAPTION LAST, out of the strongest line you already wrote.\n"
    "  * END ON A NEXT ACTION a grower can take today, not a slogan.\n"
    "Automatic fails: a numbered listicle read out loud, 'here are 5 tips "
    "for', opening by announcing what the video is about, advice so general it "
    "fits any plant and any shop, and the enthusiastic-brand voice. If your "
    "draft would work just as well with another store's name on it, it is not "
    "the post -- start again."
)

# ONE BRIEF PER ANGLE, not per platform: the platform difference is already
# carried by the format block and the crop rule, so a per-platform copy of each
# brief would just be two things to drift apart.
_BRIEFS = {
    "tips-and-tricks": (
        "A TIP OR TRICK. One real thing that makes a plant do better, that most "
        "people get wrong or have never heard. Your horticulture shelf is the "
        "source -- feeding, pH and EC, medium, light, water quality, root zone "
        "-- read the doc that covers it rather than writing from memory. Teach "
        "first; a product appears only if it genuinely is the answer, and only "
        "if the store shows it in stock."),
    "bionova-houseplants": (
        "BIONOVA ON HOUSE PLANTS. The angle Barry wants worked: people with "
        "monsteras, pothos, figs, snake plants, orchids -- feeding them properly "
        "with the real line instead of a bottle of blue stuff from a garden "
        "centre. Read the actual products first (read_product, lookup_product) "
        "and the Bionova selling guide, and pick the ONE product this post is "
        "about.\n\n"
        "DOSING, and this is a real limit, not caution for its own sake: the "
        "official Bionova chart is written for coco and hydro at grow-room "
        "strength (EC 1.0-1.9). House plants are fed far weaker than that. There "
        "is NO official Bionova house-plant chart in your brain. So either speak "
        "in relative terms -- much weaker than the chart, a fraction of a "
        "grow-room dose, start low -- or give no numbers at all. Do NOT invent a "
        "ml-per-litre figure and do not quote the coco chart at a house plant; "
        "someone will follow it and burn a plant they have had for six years."),
    "which-nutrients": (
        "WHICH NUTRIENTS FOR WHICH PLANT -- Barry's angle: 'what nutrients are "
        "good for whatever plant they are growing.' This is the one people TYPE "
        "INTO SEARCH, so say the plant's name out loud and in the on-screen "
        "text. Pick a real plant or a real group (leafy herbs, fruiting veg, "
        "tropical foliage, seedlings) and answer the actual question: what it "
        "needs, why, and which product from the store does it.\n\n"
        "Work from your horticulture shelf for the plant's needs and from "
        "read_product for what each product actually is. Where the answer "
        "depends on their medium or their water, say so -- that honesty is the "
        "whole reason a grower trusts the next post. Same dosing rule as above: "
        "no invented numbers."),
    "bionova-veggies-herbs": (
        "BIONOVA FOR AN INDOOR VEG OR HERB GARDEN -- Barry's angle. Someone "
        "growing basil, lettuce, peppers, tomatoes or microgreens under a light "
        "in their house. What the line does for them, what to run and when it "
        "changes as the plant moves from leaf to fruit. Read the products and "
        "the feeding chart before you write a word about how to use them.\n\n"
        "Anything edible carries one extra rule: no health, medical or "
        "nutritional claims about the food it grows, ever. And the same dosing "
        "limit -- the chart is grow-room strength; a windowsill herb pot is not "
        "a grow room. Relative language or no numbers."),
    "other-products": (
        "PROMOTING SOMETHING OTHER THAN BIONOVA -- Barry's angle: 'Also "
        "promoting other products.' Pick ONE in-stock product from the rest of "
        "the catalogue (tents, lights, filtration and RO, meters, media, "
        "Gard'N Clean, Grower's Ally, Emerald Harvest, fans) -- read_product for "
        "the real description, lookup_product for the live price, photo and "
        "link. Write why a grower would want it, what it pairs with, and who it "
        "is NOT for; 'who it is not for' is what makes the rest believable.\n\n"
        "The offer codes, if one belongs here: BIG15 is Bionova only, BIG10 is "
        "everything EXCEPT Bionova, both first order. Whichever you use, the "
        "footnote MUST appear: 'To get both discounts, use the codes separately "
        "- they can't be combined on the same order.'"),
    "store-news": (
        "STORE NEWS -- what is genuinely new or back in stock, a recent blog "
        "post worth reading, what is in season. browse_site and lookup_product "
        "so every claim is real. If nothing is genuinely new, say what is in "
        "season instead of inventing news -- an email told customers a product "
        "was back in stock while it was out, and that is the one mistake here "
        "that costs trust rather than reach."),
}

# Barry, 2026-09-18: "they should get all info from the website before making
# posts." Stated as an absolute, because the first live post read two products
# correctly and STILL carried a dose rate that came from nowhere -- reading is
# not the same as every fact tracing back to something read.
_READ_FIRST = (
    "\n\nEVERYTHING IN THIS POST COMES OFF THE WEBSITE. Before you write a "
    "word: call read_product for the full description of every product you "
    "will name, as it stands on the site right now; lookup_product for the "
    "live price, the stock status and the photo; browse_site for anything "
    "about the store itself. What you say about a product comes from what you "
    "just read -- never from what you assume it is, and never from memory of "
    "an earlier session.\n\n"
    "If you have not read it, you do not mention it. A product the store shows "
    "as out of stock does not go in a post. And every FACT in the post -- a "
    "figure, a size, a ratio, what it does, what it pairs with -- has to trace "
    "to something you actually read: the description, the label in the product "
    "photo, or the official feeding chart. If you cannot point at where a "
    "number came from, it does not go in."
)

_FORMAT = {
    "tiktok": (
        "\n\nFORMAT, exactly these labels, each on its own line, nothing before "
        "or after -- no notes to me, no explanation:\n"
        "HOOK: the first two seconds, spoken or on screen. It has to earn the "
        "next five.\n"
        "SHOTS: the shot list, numbered, one line each -- what is in frame and "
        "what is said or shown. Keep the whole thing under 40 seconds.\n"
        "ONSCREEN: the text overlays, in order, one per line.\n"
        "CAPTION: the caption as it will be pasted, in Barry's voice, grower to "
        "grower.\n"
        "HASHTAGS: 4-8, relevant, no walls of tags.\n"
        "SOUND: what kind of audio or trending sound suits it, described -- you "
        "cannot pick a real trending sound, so say what to look for.\n"
        "FOR VIVIAN: ONE LINE on what the visual has to DO -- the job it has to "
        "pull off, never what it looks like. She designs it, all of it; do not "
        "describe the picture for her."),
    "facebook": (
        "\n\nFORMAT, exactly these labels, each on its own line, nothing before "
        "or after -- no notes to me, no explanation:\n"
        "POST: the post text as it will be pasted, in Barry's voice, paragraphs "
        "separated by blank lines. Include the live price and the product link "
        "where the brief calls for them.\n"
        "HASHTAGS: 3-5, or the word NONE -- Facebook is not Instagram.\n"
        "CAPTION: the one line that goes with the image.\n"
        "FOR VIVIAN: ONE LINE on what the image has to DO -- the job, never "
        "what it looks like. She designs it, all of it."),
}


def _log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(f"[social-cadence] {msg}")
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _state() -> dict:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    os.makedirs(os.path.dirname(_STATE), exist_ok=True)
    tmp = _STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _STATE)


def cannabis_platforms() -> set[str]:
    raw = memory.get_setting(CANNABIS_KEY, CANNABIS_DEFAULT) or ""
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _crop_rule(platform: str) -> str:
    if platform in cannabis_platforms():
        return ("\n\nCROP POLICY for this platform: cannabis is fine here -- this "
                "is where Barry posts it. Write it plainly, no euphemisms, no "
                "hedging.")
    allowed = ", ".join(sorted(cannabis_platforms())) or "nowhere yet"
    return ("\n\nCROP POLICY for this platform: keep it CROP-NEUTRAL. TikTok and "
            "Meta enforce by business category, not by the wording of one post, "
            "and a restriction here costs the account. Herbs, tomatoes, peppers, "
            "microgreens, fruit trees, houseplants -- the technique is identical "
            "and so is the audience. Cannabis-forward content belongs on: "
            f"{allowed}. Do not hint at it either; write the post for a food "
            "grower and mean it.")


def pending_social() -> int:
    with memory.get_db() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE action_type = 'social_post' "
            "AND status = 'pending'").fetchone()
    return int(r["n"] or 0)


def upcoming_slots(now: datetime.datetime | None = None, days: int = 8):
    """(post_at, slot_index, platform) for every slot in the next `days` days."""
    now = now or datetime.datetime.now()
    out = []
    for ahead in range(0, days):
        day = (now + datetime.timedelta(days=ahead)).date()
        for idx, (wd, hour, platform) in enumerate(SLOTS):
            if day.weekday() == wd:
                at = datetime.datetime.combine(day, datetime.time(hour, 0))
                if at > now:
                    out.append((at, idx, platform))
    return sorted(out, key=lambda t: t[0])


def kind_for(post_at: datetime.datetime, slot_idx: int, platform: str) -> str:
    kinds = KINDS[platform]
    week = post_at.isocalendar()[1]
    return kinds[(week * len(SLOTS) + slot_idx) % len(kinds)]


def _slot_key(post_at: datetime.datetime, platform: str) -> str:
    return f"{post_at:%Y-%m-%d-%H}-{platform}"


_LABEL_RE = re.compile(r"^([A-Z][A-Z ]{2,}):\s*(.*)$")

# --- CLAIMS THE FACT-CHECK CANNOT SEE -----------------------------------------
# factcheck.check_email reads the live store, so it catches stock, price and
# product claims. It cannot catch a number that is simply MADE UP, because
# there is nothing to check it against -- and on the very first live post the
# brief's "never invent a ml-per-litre figure" lost: Derek put "Use 1-3 ml per
# gallon for deficiency" in the on-screen text. House rule is that a prompt
# rule which fails becomes code, and this one has real consequences (someone
# follows it and burns a plant) so it is not waiting for a second failure.
_DOSE_RE = re.compile(
    r"[^.\n]*\b\d+(?:\s*[-–to]+\s*\d+)?\s*"
    r"(?:ml|mls|millilit\w*|l|lit\w*|tsp|teaspoon\w*|tbsp|tablespoon\w*|"
    r"g|grams?|oz|ounces?)\s*(?:per|/|a|each)\s*"
    r"(?:gal\w*|l\b|lit\w*|quart|qt|pot|plant|water\w*|feed\w*)[^.\n]*",
    re.I)

# A DOSE NUMBER IS FINE IF IT IS SOURCED. Corrected 2026-09-18 the same hour
# it was written, by opening the real MgO 10 photo: the label itself carries
# "1:3000" and "Food grade minerals", so both are Bionova's own claims on
# Bionova's own bottle. The first version of this net banned "food-grade"
# outright and would have banned a correctly-cited ratio -- wrong on both, and
# Barry caught it. What is actually dangerous is a number with no source, so
# the check is for sourcing, not for numbers.
_SOURCED_RE = re.compile(
    r"\b(label|bottle|chart|feeding chart|manufacturer|bionova (?:says|states)|"
    r"1\s*:\s*\d{3,}|per the|according to)\b", re.I)

# INTERNAL FRAMING MUST NOT REACH A CUSTOMER. Caught on the second live post:
# Derek picked a product off the what_is_selling SITTING list -- correct, that
# is the angle Barry asked for -- and then put "SITTING IN STOCK, NOT SLEEPING"
# in the ON-SCREEN TEXT. His own manual says the sitting list is planning data
# and to never call anything unpopular in public, and the accuracy check does
# not catch it because the statement is TRUE; it is just not ours to say.
_INTERNAL_RE = re.compile(
    r"\b(sitting in stock|not selling|nobody buys|no one buys|slow mover|"
    r"slow.moving|overstock|unpopular|not sleeping|hasn'?t sold|"
    r"cold product|gathering dust)\b", re.I)

_UNSOURCED_RE = (
    (_INTERNAL_RE,
     "that is INTERNAL framing from the sitting-in-stock list -- true, but not "
     "ours to say. Never tell a customer a product is not selling; write about "
     "what it does instead"),
    (re.compile(r"\b(cure|cures|heals?|prevents?)\s+(?!deficien)", re.I),
     "treatment/cure language -- no medical or health claims, ever"),
    (re.compile(r"\b\d{1,3}\s*%\s*(?:more|bigger|higher|increase|yield)", re.I),
     "a yield or performance percentage -- never in a post"),
)


def unsupported_claims(text: str) -> list[str]:
    """Invented dose rates and claims nobody can stand behind."""
    found = []
    # Sourcing is judged on the whole LINE, not the matched span: `[^.\n]*`
    # stops at the period inside "1.25", so a correctly-cited "the label says
    # 1:3000, so about 1.25 ml per gallon" matched only the fragment "25 ml per
    # gallon" and read as unsourced. Measured, not guessed.
    for raw in (text or "").splitlines():
        m = _DOSE_RE.search(raw)
        if not m:
            continue
        line = m.group(0).strip()
        if _SOURCED_RE.search(raw):
            continue          # cited to the label or the chart -- that is fine
        found.append(
            f"UNSOURCED DOSE RATE: {line[:120]!r} -- where did this number come "
            "from? If it is the bottle's own ratio or the official feeding "
            "chart, SAY SO in the line and keep it. If you worked it out or "
            "guessed it, cut it: the chart is coco/hydro at grow-room strength "
            "and there is no house-plant or herb chart.")
    for rx, why in _UNSOURCED_RE:
        m = rx.search(text or "")
        if m:
            found.append(f"UNSUPPORTED CLAIM: {m.group(0).strip()!r} -- {why}.")
    return found


def _parse_reply(reply: str, platform: str) -> dict | None:
    """Labelled sections -> dict. Forgiving about order and extra labels, strict
    about the two that decide whether this is postable at all."""
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", (reply or "").strip(),
                  flags=re.I | re.S).strip()
    out, cur = {}, None
    for line in text.splitlines():
        m = _LABEL_RE.match(line.strip())
        if m:
            cur = m.group(1).strip()
            out[cur] = m.group(2).strip()
        elif cur:
            out[cur] = (out[cur] + "\n" + line).strip()
    body = out.get("CAPTION") if platform == "tiktok" else out.get("POST")
    if not body or len(body) < 40:
        return None
    if platform == "tiktok" and not out.get("SHOTS"):
        return None
    return out


def _render(platform: str, kind: str, post_at: datetime.datetime,
            parts: dict, vivian: str = "", huddle: str = "") -> str:
    """The row Barry reads. The thing he PASTES comes first, under its own rule,
    because that is the whole point of this phase -- everything below it is
    production notes for him and for Vivian."""
    when = post_at.strftime("%a %b %d").replace(" 0", " ")
    order = (["HOOK", "SHOTS", "ONSCREEN", "SOUND", "FOR VIVIAN"]
             if platform == "tiktok" else ["HASHTAGS", "CAPTION", "FOR VIVIAN"])
    paste = parts.get("CAPTION" if platform == "tiktok" else "POST", "")
    if platform == "tiktok" and parts.get("HASHTAGS"):
        paste = paste + "\n\n" + parts["HASHTAGS"]
    lines = [f"{platform.upper()} -- {kind} -- for {when}",
             "",
             "=== PASTE THIS ===",
             paste,
             ""]
    for label in order:
        val = (parts.get(label) or "").strip()
        if val and val.upper() != "NONE":
            lines += [f"=== {label} ===", val, ""]
    extra = [k for k in parts
             if k not in order and k not in ("CAPTION", "POST", "HASHTAGS")]
    for label in extra:
        val = (parts.get(label) or "").strip()
        if val:
            lines += [f"=== {label} ===", val, ""]
    if vivian.strip():
        lines += ["=== VIVIAN -- CREATIVE DIRECTION (her words) ===",
                  vivian.strip(), ""]
    if huddle.strip():
        lines += ["=== HOW THEY GOT HERE (their idea huddle) ===",
                  huddle.strip(), ""]
    return "\n".join(lines).strip() + "\n"


async def _ask(prompt: str, agent_id: str = AGENT_ID) -> tuple[str, list]:
    async with httpx.AsyncClient(timeout=600) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": agent_id, "message": prompt,
                                "task": True, "activity": "social post work"})
    r.raise_for_status()
    data = r.json() or {}
    return (data.get("reply") or ""), (data.get("tool_calls") or [])


# --- THE CONFERRAL ------------------------------------------------------------
# Barry, 2026-09-18: "he needs to confer with Vivian for all posts. maybe they
# work together on this social media thing."
#
# Derek writing a VISUAL: line into a queued row is not two people working
# together -- it is one person leaving a note. So every post that survives the
# fact-check goes to Vivian ON HER OWN SEAT before it is queued: she has the
# design shelf, she can open the REAL product photo (look_at_product_photo)
# and her own past renders, and she knows which engine a thing has to render
# on. Her answer is attached to the row in HER words, not summarised.
#
# She is also asked what she would change about the post itself. She is the
# Creative Director and a visual problem is usually a concept problem -- if
# the shot cannot be made, that is worth knowing before Barry stands in front
# of a camera, not after.
#
# COST, stated honestly: one extra model turn per post, three posts a week.
# If the card is busy the conferral is skipped and the row says so, because a
# post with no creative direction is still a post and a stalled slot is not.
CREATIVE_ID = "creative"


async def _confer_with_vivian(platform: str, kind: str, parts: dict,
                              post_at: datetime.datetime, idea: str = "") -> str:
    """Vivian's own direction on Derek's draft. Her words, verbatim."""
    body = parts.get("CAPTION" if platform == "tiktok" else "POST", "")
    derek_visual = (parts.get("FOR VIVIAN") or "").strip()
    shots = (parts.get("SHOTS") or "").strip()
    when = post_at.strftime("%A %B %d").replace(" 0", " ")
    ask = (
        f"Derek has written the {platform.upper()} post for {when} -- a "
        f"{kind.replace('-', ' ')}. You two run social together, so it comes to "
        f"you before it goes to Barry.\n\n"
        + (f"THE IDEA YOU TWO AGREED ON EARLIER:\n  {idea}\n\n" if idea else "")
        + f"--- THE POST ---\n{body}\n"
        + (f"\n--- HIS SHOT LIST ---\n{shots}\n" if shots else "")
        + (f"\n--- THE JOB HE SAYS THE VISUAL HAS TO DO ---\n{derek_visual}\n"
           if derek_visual else "")
        + "\n--- YOUR PART ---\n"
        "Barry's split, his words: he writes the real good stuff and you "
        "design it all. So the look is YOURS. His line above is the job the "
        "visual has to pull off, not a description to follow -- if a better "
        "picture does that job, make that one instead.\n\n"
        "If a real product is in this, open its actual photo "
        "(look_at_product_photo) before you say anything about how it should "
        "look -- work from the real bottle, not from the name.\n\n"
        "Barry's own four posts are the house style -- square, the bottle "
        "centre on a reflective surface, soft daylight, the logo top-right, a "
        "black caption box when the line goes on the image. His instruction "
        "for the new ones: LOSE THE LUSH VEGETATION. The jungle wall behind "
        "the bottle is out; what replaces it is yours, and it should serve "
        "this post. Label text and the logo are never generated -- they come "
        "out garbled every time -- so composite the real product photo and "
        "say where the logo and the caption go.\n\n"
        "Give Barry the design, the way you would brief a shoot: what is in "
        "frame, what it sits on, what the light is doing, the crop for this "
        "platform, and the one thing the picture has to make someone feel. If "
        "it should be a still you render rather than something he shoots, say "
        "so and say which engine and why.\n\n"
        "Then, as Creative Director: is there anything about the POST you "
        "would change? If the shot cannot be made, or the idea does not carry "
        "visually, say it plainly now -- Barry is the one who has to stand "
        "there with a camera. If it is good, say that and stop; do not invent "
        "a criticism.\n\n"
        "Plain prose for the direction. Then, LAST, give the render itself in "
        "an ```image``` fence -- Barry cannot approve a post he cannot see, so "
        "this one actually gets rendered and attached to the post before it "
        "reaches him.\n\n"
        "THE FENCE IS THE SCENE ONLY -- and this is stricter than it sounds, "
        "because the first one missed on all four counts:\n\n"
        "1. DO NOT DESCRIBE THE PRODUCT AT ALL. Not the bag, not the bottle, "
        "not its label or colour. The real photo is composited on top "
        "afterwards. Describing it makes the generator draw a second, fake one "
        "underneath the real one, which is exactly what happened.\n"
        "2. NO EQUIPMENT WE DO NOT SELL. Asking for 'a grow tent' or 'a grow "
        "light' makes the generator invent a generic one -- and a tent in "
        "frame is a product claim about gear Barry does not stock. If you want "
        "real equipment in shot, look it up first (lookup_product, "
        "browse_site) and name the actual product; otherwise keep it out of "
        "frame. A surface, a light source and depth is almost always better.\n"
        "3. POSITIVE PHRASING ONLY. 'no lush vegetation', 'no harsh shadows' "
        "-- every engine here runs at cfg 1.0 where the negative field is "
        "INERT, and a word after 'no' still gets painted. Say what IS there. "
        "Skip the negative block; it does nothing.\n"
        "4. PUT AN IDEA IN IT. 'Product on a surface' is not a shot. Name the "
        "idea in one line first -- a moment, a contrast, a before-and-after -- "
        "then build the frame for it. Three layers always: something soft in "
        "the near foreground, the subject sharp, something falling away "
        "behind. ONE named light source and what it rakes across. One real "
        "detail that says a person works here (spilled powder, a used "
        "measuring cup, a scribbled EC number). A scale cue. Say what is sharp "
        "and what is not.\n"
        "5. THE LUSH LOOK IS THE TEMPLATE -- his words: 'the lush image is "
        "what i like but they can use it to create their own versions based on "
        "the plant or post.' So the scene is RICH: warm, saturated, abundant, "
        "a product standing in a full living scene, exactly like his own four "
        "posts. What VARIES is what is growing in it, and that comes from the "
        "post -- houseplants get monstera and pothos, herbs get a full basil "
        "and mint counter, veg gets tomato trusses and peppers, a corrective "
        "gets whatever plant shows that deficiency, thriving. The one "
        "adjustment: keep the planting in DEPTH rather than on the product's "
        "plane, so the bottle still reads instantly. Lush AND legible. A bare "
        "or dark scene is the failure here -- he rejected exactly that.\n\n"
        "THE TEST before you send the fence: cover the product with your "
        "thumb. If what is left is still a photograph someone would stop on, "
        "you have a shot. If it is an empty surface, start again.\n\n"
        "The logo and the caption text go on afterwards in the editor -- never "
        "in the render. Say in your direction where each of them sits."
    )
    try:
        reply, tools = await _ask(ask, CREATIVE_ID)
    except Exception as e:  # noqa: BLE001 -- her turn failing must not lose his post
        _log(f"{platform}/{kind}: conferral with Vivian failed "
             f"({type(e).__name__}: {e}) -- queued without it")
        return ""
    reply = (reply or "").strip()
    if len(reply) < 40:
        _log(f"{platform}/{kind}: Vivian came back with {len(reply)} chars -- skipped")
        return ""
    _log(f"{platform}/{kind}: Vivian conferred ({len(reply)} chars, "
         f"tools {[t for t in tools] if tools else 'none'})")
    return reply


# --- THE HUDDLE ---------------------------------------------------------------
# Barry, 2026-09-18: "they should confer with each other before creating. they
# should come up with ideas together but each do their part once they decide
# what they want to post."
#
# So the conferral moved to the FRONT as well as the end. Derek proposes,
# Vivian picks and reshapes with her own eye on whether it can be seen, they
# land on one idea, and only then do they split and each do their half. It is
# the teamwork.py huddle pattern, two seats, kept short -- an idea round is
# cheap and it stops the expensive half being spent on a concept that cannot
# be photographed.
#
# Four model turns a post, three posts a week. That is the cost of them
# actually working together rather than one handing the other a note.
async def _idea_huddle(platform: str, kind: str,
                       post_at: datetime.datetime) -> tuple[str, str]:
    """Derek proposes, Vivian picks and shapes. Returns (transcript, the idea)."""
    when = post_at.strftime("%A %B %d").replace(" 0", " ")
    brief = _BRIEFS[kind]
    ask_d = (
        f"You and Vivian are about to make the {platform.upper()} post for "
        f"{when}. Before either of you writes or designs anything, you two "
        f"work out WHAT it should be.\n\n{brief}{_MIX}{_crop_rule(platform)}"
        f"{_READ_FIRST}\n\nRight now, your part -- and START BY LOOKING AT THE "
        "STORE, not by thinking of an idea. Call what_is_selling to see what "
        "has actually MOVED lately and what is SITTING in stock, then "
        "read_product on whatever you are drawn to. A recent seller is proof "
        "of demand; a product that has not sold is usually one nobody has "
        "explained yet, and that is a post. Let the store choose the subject.\n\n"
        "Then put THREE concepts on the table -- and make them DIFFERENT "
        "SHAPES, not three versions of one idea. At least one of the three is "
        "pure plant talk with no product in it at all. One or two lines each: "
        "the idea, and why it would stop a thumb. Number them 1, 2, 3. Name "
        "the real product in any concept that has one, and say for each where "
        "it came from -- the mover list, the sitting list, or a plant question "
        "that has nothing to do with either. Nothing else: no caption, no shot "
        "list, no hashtags. Just the three ideas."
    )
    derek, _ = await _ask(ask_d)
    derek = (derek or "").strip()
    if len(derek) < 60:
        # Measured on the first live run: he called what_is_selling and
        # browse_site and then returned ZERO characters -- the documented
        # Bonsai empty-content case. Skipping silently drops the huddle, which
        # is the one thing Barry asked for, so it gets one retry. The retry
        # says to look at the store ONCE, because two heavy tool results in a
        # row is the shape that produced the empty reply.
        _log(f"{platform}/{kind}: huddle -- Derek returned {len(derek)} chars, retrying once")
        derek, _ = await _ask(
            ask_d + "\n\n[Your last attempt came back empty. Call "
                    "what_is_selling ONCE, then write the three concepts "
                    "straight out. Do not call any other tool first.]")
        derek = (derek or "").strip()
    if len(derek) < 60:
        _log(f"{platform}/{kind}: huddle -- still {len(derek)} chars, no huddle this time")
        return "", ""

    ask_v = (
        f"Derek has three concepts on the table for the {platform.upper()} "
        f"post on {when}. You two decide together before either of you starts "
        f"-- he writes it, you design it, so the idea has to work for both.\n\n"
        f"--- HIS THREE ---\n{derek}\n\n--- YOUR PART ---\n"
        "Pick the one that will actually carry as a picture, and say plainly "
        "why the others will not. You are allowed to reshape the one you pick, "
        "and you are allowed to reject all three and put up a fourth if none "
        "of them can be seen -- that is the point of talking first.\n\n"
        "If a real product is in it, open its photo (look_at_product_photo) "
        "before you commit.\n\nEnd with exactly one line:\n"
        "THE IDEA: <one sentence, what this post is>"
    )
    vivian, _ = await _ask(ask_v, CREATIVE_ID)
    vivian = (vivian or "").strip()
    m = re.search(r"^THE IDEA:\s*(.+)$", vivian, re.M)
    idea = (m.group(1).strip() if m else "")
    if not idea:
        # she talked but never committed -- take her last substantial line
        lines = [l.strip() for l in vivian.splitlines() if len(l.strip()) > 40]
        idea = lines[-1] if lines else ""
    transcript = (f"DEREK -- three concepts:\n{derek}\n\n"
                  f"VIVIAN -- the pick:\n{vivian}").strip()
    _log(f"{platform}/{kind}: huddle done, idea = {idea[:80]!r}")
    return transcript, idea


# --- THE VISUAL ---------------------------------------------------------------
# Barry, 2026-09-18: "i need to see visuals as well in order to aprove
# anything." Fair, and obvious in hindsight -- a post arriving as words plus a
# paragraph describing a picture is not something anyone can approve. So the
# scene from Vivian's fence is rendered and hung on the approval row, and the
# deck shows it inline like any other render.
#
# THE SCENE ONLY, and the real bottle composited on top of it: a generator
# cannot write, so every label it draws comes out as "PREMIUM FERTILIZSES" --
# which is exactly what happened on Barry's own four reference posts. The real
# product photo is on this disk. Rendering the room and compositing the truth
# beats asking a model to paint a label it cannot read.
_FENCE_RE = re.compile(r"```image\s*\n(.+?)```", re.S | re.I)
PREVIEW_SIZE = (768, 1344)     # 9:16 for TikTok; Facebook gets 4:5 below


def product_photo_for(text: str) -> str:
    """The real photo of whatever product the post is about, off this disk.

    Matched on the distinctive words of the product's own name, so 'Bionova
    MgO 10' in a caption finds bionova-mgo-10-magnesium-mineral-additive.jpg.
    Returns "" when nothing clearly matches -- a wrong bottle composited into
    a post is worse than no bottle.
    """
    folder = os.path.join(_ROOT, "data", "product-images")
    idx = os.path.join(folder, "_index.json")
    if not os.path.isfile(idx):
        return ""
    try:
        with open(idx, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    entries = data if isinstance(data, list) else data.get("products", [])
    low = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    # Generic words are the trap: scoring by raw hit count picked a "Dimlux
    # Infra Red Plant Temperature Camera" for a post about MgO 10, on "red",
    # "plant" and "10". A long product name accumulates lucky tokens, so the
    # score is the FRACTION of a name's distinctive words that appear, and the
    # single most distinctive word has to be one of them.
    stop = {"bionova", "the", "and", "for", "with", "premium", "fertilizer",
            "fertilizers", "all", "one", "in", "of", "plus", "plant", "plants",
            "indoor", "outdoor", "garden", "gardening", "grow", "growing",
            "soil", "hydro", "coco", "water", "nutrient", "nutrients", "pro",
            "kit", "long", "meter", "meters", "inch", "gal", "gallon", "litre",
            "liter", "size", "sizes", "pack", "bottle", "red", "green", "light",
            "system", "new", "free", "best", "high", "low", "10", "20", "100"}
    scored: list[tuple[tuple, str, str]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").lower()
        fname = e.get("file") or e.get("filename") or ""
        if not name or not fname:
            continue
        words = {w for w in re.findall(r"[a-z0-9]+", name)
                 if len(w) > 2 and w not in stop}
        if not words:
            continue
        hits = {w for w in words if w in low}
        anchor = max(words, key=len)          # the most distinctive word
        # The anchor is what does the work: a catalogue name only counts if its
        # most distinctive word is actually in the post, which is what stopped
        # the Dimlux camera ("temperature") matching a magnesium caption. A
        # fraction-of-words floor was tried and was WRONG in the other
        # direction -- store names carry descriptors ("MINERAL ADDITIVE") that
        # a caption never repeats, so it rejected the correct bottle.
        if anchor not in hits or len(hits) < 2:
            continue
        key = (len(hits), -len(words))        # most hits, then the tighter name
        p = os.path.join(folder, fname)
        if os.path.isfile(p):
            scored.append((key, p, name, words))

    if not scored:
        return ""
    scored.sort(key=lambda s: s[0], reverse=True)
    best_key, best, _, best_words = scored[0]

    # AMBIGUITY GUARD -- and this one cost a wrong bag in a real post.
    # "GHF Mineral Line Grow" and "GHF Mineral Line long Flowering" share
    # nearly every word in their names, and the post explained what NOT to use
    # ("you keep running the flower nutrient into the vegetative stage"), so
    # BOTH names matched and the flowering bag won on a coin-flip tiebreak.
    # The render then composited a real, perfectly legible label for the wrong
    # product. When two candidates are this close the text cannot separate
    # them, so the honest answer is no photo at all -- the scene still renders,
    # and a missing bottle is recoverable in a way that a confidently wrong one
    # is not.
    # Only a SAME-FAMILY tie is ambiguous. A different product tying on hit
    # count is fine -- the tighter-name tiebreak handles that, and a first
    # version of this guard that fired on any tie also threw away a perfectly
    # unambiguous MgO 10 match. Family = the two names share most of their
    # words, which is exactly the Grow / long Flowering case.
    for key, _p, _n, words in scored[1:]:
        if key[0] < best_key[0]:
            break
        overlap = len(best_words & words) / max(1, len(best_words | words))
        if overlap >= 0.5:
            return ""
    return best


# "no X" clauses are worse than useless in a positive prompt here: the
# negative field is INERT at cfg 1.0 with the Lightning LoRA, and the word
# after "no" still gets painted. Her first fence carried "no lush vegetation"
# and the render came back with leaves in frame. The rule is in her brief and
# in her manual; this is the net for when it loses -- and it caught the office's
# OWN prompt, which was appending ", no text, no writing, no logo, no labels".
_NEGATIVE_CLAUSE_RE = re.compile(
    r"\s*,?\s*\b(?:no|without|avoid|free of)\s+[^,.\n]{1,60}", re.I)


def strip_negatives(prompt: str) -> str:
    out = _NEGATIVE_CLAUSE_RE.sub("", prompt or "")
    out = re.sub(r"\s*,\s*,+", ", ", out)
    return re.sub(r"\s{2,}", " ", out).strip().strip(",").strip()


def _fence_of(text: str) -> str:
    m = _FENCE_RE.search(text or "")
    return strip_negatives((m.group(1).strip() if m else "").strip())


async def _render_preview(approval_id: int, platform: str, vivian: str,
                          product_photo: str = "") -> str:
    """Render Vivian's scene and hang it on the row. Best effort, never fatal."""
    scene = _fence_of(vivian)
    if not scene:
        _log(f"approval {approval_id}: no image fence from Vivian -- no preview")
        return ""
    import comfy_image
    if comfy_image.render_in_progress():
        _log(f"approval {approval_id}: card busy -- preview skipped")
        return ""
    w, h = PREVIEW_SIZE if platform == "tiktok" else (1024, 1280)
    try:
        import llm_router   # Bonsai out of memory before a render (office rule; see email_design 09-26)
        await llm_router.unload_all_models()
        res = await comfy_image.generate_image(prompt=scene, width=w, height=h)
    except Exception as e:  # noqa: BLE001
        _log(f"approval {approval_id}: preview render failed "
             f"({type(e).__name__}: {e})")
        return ""
    path = (res or {}).get("file_path") or (res or {}).get("path") or ""
    if not path:
        _log(f"approval {approval_id}: render returned no file")
        return ""
    if product_photo:
        try:
            path = composite_product(path, product_photo) or path
        except Exception as e:  # noqa: BLE001 -- a failed composite still
            _log(f"approval {approval_id}: composite failed ({e})")  # leaves a scene
    with memory.get_db() as conn:
        conn.execute("UPDATE approvals SET file_path = ? WHERE id = ?",
                     (path, approval_id))
    _log(f"approval {approval_id}: preview attached -> {path}")
    return path


def composite_product(scene_path: str, product_photo: str) -> str:
    """Drop the REAL product photo onto the rendered scene. No model involved,
    so the label is the actual label -- which is the whole point."""
    from PIL import Image
    scene = Image.open(scene_path).convert("RGBA")
    prod = Image.open(product_photo).convert("RGBA")
    # the store photos are on white -- lift the bottle off it
    bg = prod.getpixel((2, 2))
    if sum(bg[:3]) > 720:
        # The store photos are on white. A hard cut at 243 leaves a bright
        # halo, because the anti-aliased edge pixels sit just under it -- it
        # was plainly visible on the first composited post. Feather the band
        # between 228 and 248 instead of clipping it, so the edge fades out.
        px = prod.load()
        for y in range(prod.height):
            for x in range(prod.width):
                r, g, b, a = px[x, y]
                lo = min(r, g, b)
                if lo >= 248:
                    px[x, y] = (r, g, b, 0)
                elif lo > 228:
                    px[x, y] = (r, g, b, int(a * (248 - lo) / 20))
    box = prod.getbbox() or (0, 0, prod.width, prod.height)
    prod = prod.crop(box)
    target_h = int(scene.height * 0.46)
    scale = target_h / prod.height
    prod = prod.resize((max(1, int(prod.width * scale)), target_h),
                       Image.LANCZOS)
    x = (scene.width - prod.width) // 2
    y = int(scene.height * 0.52) - prod.height // 2 + int(scene.height * 0.10)
    scene.alpha_composite(prod, (max(0, x), max(0, y)))
    out = os.path.splitext(scene_path)[0] + "_post.png"
    scene.convert("RGB").save(out)
    return out


# --- THE ACCURACY GATE --------------------------------------------------------
# Barry, 2026-09-18: "everything must be accurate before they give it to me, so
# however they do that, do it. check their work."
#
# The nets that already exist only catch what a machine can check: factcheck
# reads the live store for stock and price claims, unsupported_claims catches
# an unsourced dose or a cure word. NOTHING checked the horticulture -- whether
# magnesium deficiency really does show between the veins on older leaves
# first, whether a plant actually wants that medium. Those are the claims that
# make the shop look like it knows what it is talking about, and they were
# going out unchecked.
#
# So a THIRD seat reads it before Barry does. Marcus, because auditing Derek's
# claims on copy is already his documented job (reasoning.py cross-check), and
# because he holds the same horticulture shelf everyone does plus the store
# tools to check a product statement against the real description.
#
# He is told to check, not to rewrite. A checker who edits becomes a second
# author and the seat that owns the words stops owning them.
LEGAL_ID = "legal"
_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(ACCURATE|PROBLEMS)\b", re.M | re.I)


async def _verify(platform: str, content: str) -> tuple[bool, str]:
    """Marcus checks every factual claim. Returns (ok, his findings)."""
    ask = (
        "Accuracy check before this goes to Barry. This is a "
        f"{platform.upper()} post Derek wrote and Vivian designed. Your job is "
        "to CHECK IT, not to rewrite it -- the words are his.\n\n"
        "--- THE POST ---\n" + content + "\n\n--- WHAT TO CHECK ---\n"
        "Go through it claim by claim:\n"
        "1. HORTICULTURE. Is every statement about plants, nutrients, "
        "deficiencies, media and symptoms actually TRUE? Use your own "
        "horticulture shelf -- read the doc, do not go from memory. A symptom "
        "attributed to the wrong nutrient, or a plant said to want the wrong "
        "medium, is the kind of thing a real grower spots instantly.\n"
        "2. PRODUCTS. Call read_product and lookup_product on every product "
        "named. Does the post describe what the product actually is? Is the "
        "price right? Is it in stock?\n"
        "3. NUMBERS. Every figure, ratio, percentage and dose -- where did it "
        "come from? A number from the label or the official chart is fine if "
        "the post says so. A number from nowhere is not.\n"
        "4. CLAIMS. Any yield, health, medical or performance promise. Any "
        "'exclusive'. Any comparison to another brand we cannot stand behind.\n"
        "5. ANYTHING OVERSTATED -- a maybe written as a certainty.\n\n"
        "Then answer in exactly this shape, nothing before it:\n"
        "VERDICT: ACCURATE\n"
        "  -- or --\n"
        "VERDICT: PROBLEMS\n"
        "then one line per problem: what is wrong, and what the truth is.\n\n"
        "Do not invent problems to look thorough. If it is right, say it is "
        "right. If you could not verify something, say that rather than "
        "passing it."
    )
    try:
        reply, tools = await _ask(ask, LEGAL_ID)
    except Exception as e:  # noqa: BLE001 -- the check failing must not eat the post
        _log(f"accuracy check failed to run ({type(e).__name__}: {e})")
        return True, ""
    reply = (reply or "").strip()
    m = _VERDICT_RE.search(reply)
    if not m:
        _log(f"accuracy check: no verdict line in {len(reply)} chars -- treated as unchecked")
        return True, ""
    ok = m.group(1).upper() == "ACCURATE"
    _log(f"accuracy check: {m.group(1).upper()} "
         f"(tools {tools or 'none'}, {len(reply)} chars)")
    return ok, reply


async def draft(platform: str, kind: str, post_at: datetime.datetime) -> dict:
    """One post, through Derek's full seat, queued for Barry to copy out."""
    brief = _BRIEFS[kind]
    when = post_at.strftime("%A %B %d").replace(" 0", " ")

    # They decide together FIRST, then split.
    huddle, idea = await _idea_huddle(platform, kind, post_at)
    agreed = (f"\n\nYOU TWO ALREADY AGREED WHAT THIS POST IS. Vivian picked it "
              f"and shaped it with you:\n\n  {idea}\n\nWrite THAT post. Do not "
              f"start a different idea now -- she is designing for this one."
              if idea else "")

    prompt = (
        f"Scheduled job from the office: your {platform.upper()} post for "
        f"{when}.\n\n{brief}{agreed}{_MIX}{_BAR}{_crop_rule(platform)}{_READ_FIRST}"
        f"{_FORMAT[platform]}"
    )
    reply, tool_calls = await _ask(prompt)
    parts = _parse_reply(reply, platform)
    if not parts:
        _log(f"{platform}/{kind}: reply did not parse ({len(reply)} chars) -- skipped")
        return {"ok": False, "why": "unparseable", "reply": reply[:300]}

    # ONLY REAL STUFF (Barry, 2026-09-09). Same rule as email, same reason: a
    # post that says something is back in stock when it is out is a false
    # claim whichever channel it goes out on. check_email is text-based -- it
    # reads product and stock claims against the LIVE store -- so it is the
    # right check here despite the name.
    content = _render(platform, kind, post_at, parts)
    check = factcheck.check_email(content)
    bad = unsupported_claims(content)
    if not tool_calls or not check["ok"] or bad:
        why = ("You called NO tools -- nothing in this post was read from the "
               "store. " if not tool_calls else "")
        _log(f"{platform}/{kind}: rejected (tools={len(tool_calls)}, "
             f"problems={len(check['problems'])}, claims={len(bad)}) -- re-running once")
        nudge = ("\n\n[OFFICE FACT-CHECK -- your draft was NOT accepted. " + why
                 + "Findings:\n" + factcheck.report(check)
                 + ("\n" + "\n".join(bad) if bad else "")
                 + "\nRewrite it. Only real stuff, and only what is there: every "
                   "product you name must be read with read_product NOW and "
                   "called in stock only if the store shows instock; no "
                   "percentages or figures you did not read from the store or "
                   "the offer codes. Same labels, nothing before or after.]")
        reply2, tools2 = await _ask(prompt + nudge)
        parts2 = _parse_reply(reply2, platform)
        if parts2:
            parts, tool_calls = parts2, tools2
            content = _render(platform, kind, post_at, parts)
            check = factcheck.check_email(content)
            bad = unsupported_claims(content)
        if not tool_calls or not check["ok"] or bad:
            _log(f"{platform}/{kind}: STILL failing -- queued with the banner")
        else:
            _log(f"{platform}/{kind}: re-run passed ({len(tool_calls)} tool calls)")

    # MARCUS CHECKS IT, before Vivian spends a turn designing something that
    # may have to change. A re-run here costs one turn; after the design it
    # would cost two.
    ok, findings = await _verify(platform, content)
    if not ok and findings:
        _log(f"{platform}/{kind}: accuracy check found problems -- one re-run")
        fix = ("\n\n[ACCURACY CHECK -- Marcus went through your draft against "
               "the live store and his horticulture shelf. Findings:\n\n"
               + findings + "\n\nRewrite the post so every one of those is "
               "right. Where he says a claim is wrong, fix the claim -- do not "
               "just soften it. Where he says a number has no source, cite it "
               "or cut it. Same labels, nothing before or after them.]")
        reply3, tools3 = await _ask(prompt + fix)
        parts3 = _parse_reply(reply3, platform)
        if parts3:
            parts, tool_calls = parts3, tools3
            content = _render(platform, kind, post_at, parts)
            check = factcheck.check_email(content)
            bad = unsupported_claims(content)
            ok2, findings2 = await _verify(platform, content)
            ok, findings = ok2, findings2
            _log(f"{platform}/{kind}: after the re-run, accuracy "
                 f"{'ACCURATE' if ok else 'STILL HAS PROBLEMS'}")

    # Vivian's turn -- after the facts are settled, so she is directing a post
    # that is actually true, and before it reaches Barry, so what he opens is
    # the finished thing from both of them.
    vivian = await _confer_with_vivian(platform, kind, parts, post_at, idea)
    content = _render(platform, kind, post_at, parts, vivian, huddle)
    # Barry sees that it was checked, and by whom, either way.
    if findings:
        content += ("\n=== ACCURACY CHECK (Marcus) ===\n" + findings.strip()
                    + "\n")
    if not ok:
        content = ("[OFFICE -- DO NOT POST AS-IS. The accuracy check still "
                   "found problems after a rewrite; they are listed at the "
                   "bottom.]\n\n") + content
    if bad:
        content = ("[OFFICE -- DO NOT POST AS-IS. Unsupported claims:\n"
                   + "\n".join(f"  * {b}" for b in bad) + "]\n\n" + content)
    if not check["ok"]:
        content = factcheck.banner(check) + content

    aid = memory.queue_for_approval(AGENT_ID, "social_post", content)
    with memory.get_db() as conn:
        conn.execute("UPDATE approvals SET send_at = ? WHERE id = ?",
                     (post_at.isoformat(timespec="minutes"), aid))
    _log(f"{platform}/{kind}: drafted -> approval {aid}, for {post_at:%Y-%m-%d %H:%M}")

    # He cannot approve what he cannot see.
    photo = product_photo_for(content)
    preview = await _render_preview(aid, platform, vivian, photo)

    return {"ok": True, "approval_id": aid, "platform": platform, "kind": kind,
            "preview": preview, "product_photo": os.path.basename(photo) if photo else ""}


async def draft_now(platform: str | None = None, kind: str | None = None) -> dict:
    """Manual trigger -- a test, or Barry saying 'do this week's TikTok now'."""
    slots = upcoming_slots()
    if platform:
        slots = [s for s in slots if s[2] == platform] or slots
    at, idx, plat = slots[0] if slots else (
        datetime.datetime.now() + datetime.timedelta(hours=1), 0,
        platform or "tiktok")
    plat = platform or plat
    return await draft(plat, kind or kind_for(at, idx, plat), at)


async def tick() -> None:
    """One look: a slot inside its drafting window, on the clock, office idle,
    the queue not already backed up, and not yet drafted. One per tick."""
    if not clock.is_work_hours():
        return
    if ideation._active_chat_count > 0 or ideation._video_building():
        return
    if pending_social() >= MAX_PENDING:
        return
    st = _state()
    now = datetime.datetime.now()
    for at, idx, platform in upcoming_slots(now):
        key = _slot_key(at, platform)
        if st.get(key):
            continue
        if at - now > datetime.timedelta(hours=DRAFT_LEAD_HOURS):
            continue
        kind = kind_for(at, idx, platform)
        st[key] = {"platform": platform, "kind": kind,
                   "started": now.isoformat(timespec="seconds")}
        _save(st)                      # mark first so a crash cannot double-draft
        res = await draft(platform, kind, at)
        st[key].update({"done": now.isoformat(timespec="seconds"), **{
            k: v for k, v in res.items() if k in ("ok", "approval_id", "why")}})
        _save(st)
        return


async def run_social_cadence_loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await tick()
        except Exception as e:  # noqa: BLE001 -- a loop must never die
            _log(f"loop error: {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
