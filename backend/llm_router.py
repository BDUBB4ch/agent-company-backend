"""
Routes a single agent call to either Claude (paid, per-token) or Ollama
(free, local, runs on your GPU). Each agent has a default backend in
agents.py, but any call can override it per-message.
"""
import asyncio
import base64
import contextvars
import json
import re
import subprocess
import time

import httpx
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, OLLAMA_HOST, OLLAMA_MODEL, BONSAI_MODEL_NAME
from web_search import search_web
from agents import ENGINEER_ID
import read_project_file
import claim_net
import memory
import agent_files      # FILES (2026-09-06): read Barry's drops, write documents, hand them over
import braingraph
import script_index
import store
import comfy_image
import bonsai_llm
import tracing

# qwen3.5 is supposed to keep its reasoning entirely in the separate
# `thinking` field (see `think: True` below) and leave `content` as just the
# final answer, but in longer multi-turn conversations it occasionally
# leaks its own inline <think>...</think> markers into content instead --
# sometimes redrafting the same answer 2-4 times in a row, each copy
# separated by a stray closing tag. This is a real local-model quirk, not
# something a prompt tweak reliably fixes, so it's sanitized defensively
# here rather than surfaced to the user.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _clean_ollama_content(content: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", content)
    if "</think>" in cleaned:
        # An unpaired closing tag means the model redrafted mid-stream --
        # keep only the text after the LAST one, which is its final answer.
        cleaned = cleaned.rsplit("</think>", 1)[-1]
    return cleaned.strip()

# Running total for this process - a real app would persist this to the db,
# but this gets you a visible running cost estimate immediately.
_session_cost_usd = {"total": 0.0}

# Cap on how many times one reply can call search_web before we just take
# whatever answer it has -- a model that keeps calling the tool without ever
# settling on an answer shouldn't be able to hang a chat request forever.
# Bumped 3 -> 8 (Sophie, 2026-09-20 watch): the watch caught six trace
# failures in 6h (Operations, Legal, Engineer tool_round_limit_exceeded;
# BusinessOps, Legal, Marketing near_dup/repeated_loop) where the model was
# still working at round 3 and got cut off. 8 still caps repetition but lets
# a good answer finish.
MAX_TOOL_ROUNDS = 8

# Ollama defaults to a small context window (2048-4096 tokens) unless told
# otherwise per-request -- with the brain context block now carrying full
# domain knowledge (tens of thousands of characters per agent) PLUS whole
# dropped documents (e.g. a full movie script dropped on Elliot's panel can
# run 90K+ characters on its own), the default silently truncates the
# prompt instead of erroring, which produced intermittent empty replies
# that looked like random model flakiness but were actually this. 65536
# tokens comfortably covers a large script plus everything else with real
# headroom to keep growing, and still fits easily within a 16GB-class GPU's
# VRAM alongside the ~5.6GB qwen3.5:9b weights (32768 only used ~6.7GB
# total, confirmed via `ollama ps`).
OLLAMA_NUM_CTX = 65536

# repeat_penalty=1.3 + temperature=0.8 (see the long comment in
# _call_ollama_impl) was tuned specifically for
# huihui_ai/qwen3-abliterated:8b-v2, whose own baked-in default temperature
# is 0.6 (confirmed via `ollama show`) -- a genuinely low, repetitive
# baseline that needed strong counter-pressure. Applying those SAME
# aggressive values globally to a different model broke badly: tested
# huihui_ai/qwen3.5-abliterated:9b live and got real, reproducible
# incoherent rambling on its full real persona prompt (not just a raw
# minimal test). Root cause suspected, not yet fully proven: `ollama show`
# for this model reports its own baked-in default temperature is already
# 1.0 -- stacking the old model's strong anti-repetition tuning on top of
# an already-hot model likely overcorrects into word-salad territory.
# Per-model tuning instead of one global constant, defaulting to the
# already-proven values for anything not explicitly listed.
_SAMPLING_OPTIONS_BY_MODEL = {
    "Ternary-Bonsai-27B": {"repeat_penalty": 1.2, "temperature": 0.8},
    "huihui_ai/qwen3.5-abliterated:9b": {"repeat_penalty": 1.1, "temperature": 0.7},
    # Sophie's own coding model (ENGINEER_ID, see main.py's
    # AGENT_OLLAMA_MODEL_OVERRIDES) had no entry here and was silently
    # inheriting _DEFAULT_SAMPLING_OPTIONS below -- values tuned for the
    # persona/chat model in the incident above, not a coding model. Real
    # incident found via direct trace inspection: asked an ungrounded
    # question, she generated confidently wrong advice that degraded into
    # word-salad by the end. Lower, more deterministic temperature (coding
    # tasks don't benefit from the same creative variance a chat persona
    # does) and a lighter repeat_penalty than the default (no evidence this
    # specific model shares the old model's strong repetition tendency).
    "qwen2.5-coder:14b": {"repeat_penalty": 1.15, "temperature": 0.4},
    # Marcus (Legal) and Amara (Business) -- see main.py's
    # AGENT_OLLAMA_MODEL_OVERRIDES. Microsoft's own recommended sampling
    # for Phi-4-reasoning is temperature 0.8 / top_p 0.95; the default
    # repeat_penalty 1.3 below was tuned as counter-pressure for a
    # specific repetitive model and would be far too aggressive for a
    # reasoning model whose chain-of-thought legitimately revisits the
    # same phrases. 1.05 = barely-there guard only. num_predict was briefly
    # raised to 8192 "for headroom" -- real incident (2026-07-29): the extra
    # allowance let a trivial "hello" spiral into a ~236s thinking run.
    # Measured real legal/financial answers use ~2000 tokens total incl.
    # reasoning, so the global 4096 backstop already has 2x margin; kept at
    # 4096 deliberately as the anti-spiral cap.
    "phi4-reasoning:14b": {"repeat_penalty": 1.05, "temperature": 0.8, "top_p": 0.95},
    # Marcus/Amara's qwen3-abliterated 14B (replaced phi-4 2026-07-30) had
    # NO entry and silently inherited the aggressive 1.3 default -- the
    # exact mistake the qwen2.5-coder comment above documents, repeated.
    # A thinking model's chain-of-thought legitimately revisits phrases;
    # 1.3 punishes that into stilted phrasing. Qwen3's own recommended
    # thinking-mode sampling: temperature 0.6, top_p 0.95.
    "huihui_ai/qwen3-abliterated:14b": {"repeat_penalty": 1.05, "temperature": 0.6, "top_p": 0.95},
}
_DEFAULT_SAMPLING_OPTIONS = {"repeat_penalty": 1.3, "temperature": 0.8}

# Per-model context-window ceilings. OLLAMA_NUM_CTX (65536) was sized for
# the biggest real payload in the office (a 94K-character movie script on
# Elliot), but phi4-reasoning's architecture tops out at 32768 -- asking
# for more than a model supports is at best silently clamped and at worst
# mis-allocated.
# 2026-07-29 correction, measured on a CLEAN gpu (nothing else resident):
# phi-4 at num_ctx 32768 allocates 16.9GB total and only 14.5GB fits VRAM
# (86% GPU) -- it PHYSICALLY cannot fit the 16GB card at 32K, so every
# Marcus/Amara reply ran partially on CPU (measured live: 93-230s replies,
# owner-visible slowness). At 16384 it allocates 13.3GB and sits at 100%
# GPU. 16K still covers domain knowledge + facts + conversation for these
# two agents; only a truly huge upload would notice the difference.
_NUM_CTX_BY_MODEL = {
    "phi4-reasoning:14b": 16384,
    # qwen3-abliterated 14B (Marcus/Amara since 2026-07-29) tops out at
    # 40960 architecturally, so the 65536 default must be capped. 32768
    # measured 100% GPU-resident on the clean card (qwen3's GQA KV cache
    # is far lighter than phi-4's was).
    "huihui_ai/qwen3-abliterated:14b": 32768,
}


def _sampling_options_for(model: str) -> dict:
    return _SAMPLING_OPTIONS_BY_MODEL.get(model, _DEFAULT_SAMPLING_OPTIONS)


def _num_ctx_for(model: str) -> int:
    return _NUM_CTX_BY_MODEL.get(model, OLLAMA_NUM_CTX)


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the live web for current information you don't already know "
            "or aren't fully sure of -- news, prices, competitor moves, current "
            "regulations, anything time-sensitive. Returns a short list of result "
            "titles, URLs, and snippets. Use it before answering rather than "
            "guessing, whenever the answer depends on something that could have "
            "changed since your training or that you're not confident about."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    },
}

# Every agent gets this one (added unconditionally in call_ollama, not via
# extra_tools) -- see memory.py's brain_context_block for why: full skill
# documents no longer ride along in every prompt, only a short index of
# their titles. This is how the model actually pulls one in when a
# question touches it.
# inspect_brain (2026-08-24, Barry: "i want him to be familiar with the
# brain, all of them"): every agent can pull a structural MAP of its own
# brain -- categories, always-on vs on-demand, sizes, which docs carry a
# USE WHEN routing line and which are unrouted. Pure local read
# (braingraph.outline), no network, so it is NOT stripped by offline mode.
INSPECT_BRAIN_TOOL = {
    "type": "function",
    "function": {
        "name": "inspect_brain",
        "description": (
            "Look at the MAP of your own brain: every category, every document, "
            "what rides always-on vs on-demand, sizes, and which documents have "
            "a USE WHEN routing line. Use it to get familiar with what you know "
            "and where it lives, to find the right document before read_skill, "
            "or when you are asked to look at / organize your brain. It returns "
            "structure, not content -- follow up with read_skill to read a "
            "specific document."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}
# look_at_my_pictures (2026-08-31, Barry: "Amara needs to be able to look at
# the pictures to see herself"). Opens the agent's OWN staged reference frames
# at full resolution through the vision model. Local Ollama call, so it is NOT
# stripped by offline mode. Perception stays separated from reasoning -- the
# agent's question is never forwarded to the vision pass (see the neutral
# caption relay note in media_understanding).
LOOK_AT_MY_PICTURES_TOOL = {
    "type": "function",
    "function": {
        "name": "look_at_my_pictures",
        "description": (
            "Actually LOOK at your own reference pictures -- your face and your "
            "body -- and get back what is really in them. Use this whenever you "
            "describe your own appearance, decide what you look like, or write "
            "a picture of yourself, and any time a written description of you "
            "seems off. Written descriptions drift; the pictures do not. If "
            "they disagree, the pictures win."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}
# VIVIAN'S EYES ON THE REAL WORK (2026-09-10). The catalogue's 119 real product
# photos and every render she has ever made were on disk and unreachable, so
# she wrote shots for products she had not seen and graded renders from her own
# prompt. Both are local vision reads -- NOT stripped by offline mode -- and
# both use the neutral caption relay (her question never reaches the vision
# pass; a leading question makes the small model suggestible).
LOOK_AT_PRODUCT_PHOTO_TOOL = {
    "type": "function",
    "function": {
        "name": "look_at_product_photo",
        "description": (
            "Actually LOOK at the real photograph of a real store product and "
            "get back what is in it -- shape, cap, colour, label layout, "
            "framing. Use this BEFORE writing any product shot, product image "
            "prompt or product copy, and any time you are about to describe "
            "what a product looks like. read_product gives you the words; this "
            "gives you the picture. Never invent packaging, a label or a logo "
            "that is not in the photo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Product name or SKU, as it reads on the store."},
            },
            "required": ["query"],
        },
    },
}
LOOK_AT_RENDER_TOOL = {
    "type": "function",
    "function": {
        "name": "look_at_render",
        "description": (
            "Actually LOOK at an image you rendered and get back what is really "
            "in it, not what you asked for. Use this on every render before you "
            "report on it: count hands and fingers, check for stray text or "
            "gibberish lettering, check the product shape and colours against "
            "the real product photo, check the crop for where it is going. "
            "Never call a render good without opening it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "which": {"type": "string",
                          "description": ("Leave empty for your newest render, or "
                                          "give the render id from a previous look.")},
            },
        },
    },
}
# VIVIAN DESIGNS DEREK'S EMAILS (2026-09-26, Barry: "derek comes up with email posts, products
# coupons, tips, etc and vivian comes up with style and design" / "i need to really see it as it
# will go out"). Builds the email in Omnisend's own blocks as a DRAFT template (email_design.py),
# has Omnisend render it, and hands her the screenshot of the real render. Places Derek's words;
# cannot change them. Sends nothing -- Barry's approve click is the only send.
DESIGN_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "design_email",
        "description": (
            "Design one of Derek's email drafts and SEE the result. Derek's content sheet (his words, "
            "products, coupon, button) is fixed; you choose the look: block order, colours, hero art, "
            "how products and the coupon are shown. The office builds it in Omnisend's own editor "
            "blocks as a draft (nothing is sent), Omnisend renders it, and you get back a screenshot "
            "of exactly what Barry will approve. Look at it, then call again with changes until it is "
            "right. Read read_skill 'how-vivian-designs-an-email' for the full design format first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer", "description": "The email draft number (the approval id Derek's draft is on)."},
                "design": {
                    "type": "object",
                    "description": (
                        "{style: {page_color, content_color, header_color, footer_color, heading_color, "
                        "text_color, button_color, button_text_color, button_radius, price_color, logo_align}, "
                        "hero: {art: render|product|none, scene: <scene-only render prompt if render>, "
                        "product: <one of Derek's products if product>}, "
                        "layout: [ {block: hero|text|products|image_text|offer|cta|divider|spacer, ...} ]}. "
                        "text/image_text take section: <Derek's section number>; image_text takes product "
                        "and side: left|right; products takes columns: 1-3 and heading; hero/offer/any block "
                        "takes background (a brand name like dark, green, tint, light, white, or #hex); "
                        "buttons take button_style: primary|secondary|accent. Every section Derek wrote must "
                        "be placed exactly once; his products, offer and button must appear."),
                },
            },
            "required": ["draft_id", "design"],
        },
    },
}
# Sophie changes the agents' environments (2026-08-31, Barry: "like changing
# the environments of the agents, like if they go out to a club, they may want
# that to be seen or show me what they did over the weekend or last night").
# She proposes; the render queues for approval; the file is installed only from
# the approve endpoint (agent_scenes.install). Same shape as propose_code_fix.
UPDATE_AGENT_SCENE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_agent_scene",
        "description": (
            "Stage a change to one of the agents' pictures -- their room, them "
            "at home in it, them somewhere else, or them at their office -- "
            "when BARRY asks you to. The words must be THAT AGENT'S OWN (from "
            "their brief or what Barry passes on), pasted verbatim: their "
            "picture comes from their mind, never yours. Agents change their "
            "own pictures directly with change_my_picture; you keep the "
            "pipeline working. It goes to Barry for approval and only renders "
            "and installs once he says yes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Whose environment: cio, operations, "
                                   "business, legal, marketing, creative, "
                                   "movie, engineer, taliyah.",
                },
                "slot": {
                    "type": "string",
                    "enum": ["home", "self", "out", "office", "lab"],
                    "description": "home = the room, no people. self = them at "
                                   "home in it. out = them somewhere else, "
                                   "like a night out or a weekend. office = "
                                   "them at work in their office. lab = their "
                                   "workspace or lab, the room itself.",
                },
                "description": {
                    "type": "string",
                    "description": "The scene, in plain words -- place, light, "
                                   "what they are doing, what they have on. "
                                   "Use THEIR OWN words about themselves where "
                                   "you have them; never invent their look.",
                },
            },
            "required": ["agent_id", "slot", "description"],
        },
    },
}
# Priya records what Barry tells her (2026-08-31). The gap this closes was
# measured 2026-08-29: he answered three interview questions, she folded them
# into a briefing, and the answers EVAPORATED -- because save_note writes a
# PRIVATE, ON-DEMAND note and the Business Brain is a SHARED ALWAYS-ON fact,
# so no agent could physically update it. His words then went in by hand.
# She runs his interviews; she needs to be able to keep the answers.
UPDATE_BUSINESS_BRAIN_TOOL = {
    "type": "function",
    "function": {
        "name": "update_business_brain",
        "description": (
            "Write something Barry has told you into the Business Brain -- the "
            "shared always-on file every business agent carries. Use it the "
            "moment he answers one of your questions or tells you something "
            "durable about the business, so it is never lost and everyone gets "
            "it. Put his answer in HIS OWN WORDS, never your summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Which section, e.g. 'WHO B DUBB SERVES', "
                                   "'HOW HE SOUNDS', 'NUMBERS HE STEERS BY'. A "
                                   "new name creates a new section.",
                },
                "content": {
                    "type": "string",
                    "description": "What to record -- his own wording, quoted "
                                   "where you have it verbatim.",
                },
                "replace": {
                    "type": "boolean",
                    "description": "true replaces that section, false (default) "
                                   "adds to it. Only replace when he has "
                                   "corrected something.",
                },
            },
            "required": ["section", "content"],
        },
    },
}
LIST_AGENT_SCENES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_agent_scenes",
        "description": (
            "See which environment pictures an agent currently has on disk "
            "(room, at-home, out) before proposing a change."
        ),
        "parameters": {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    },
}
READ_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "read_skill",
        "description": (
            "Pull in the full content of one of your own deeper reference skills "
            "(see the SKILLS AVAILABLE ON DEMAND list in your own context) -- use "
            "this when a question actually touches one of those topics, instead "
            "of answering from general knowledge alone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The skill's name, e.g. 'contract-review' -- matches from your own available-skills list."}
            },
            "required": ["topic"],
        },
    },
}

# Sophie (Engineer)-only tools -- see agents.py's _HAS_PROJECT_ACCESS and
# main.py's chat handler for where these get attached only to her calls.
# Restricted to two real directories on disk (see read_project_file.py).
READ_PROJECT_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_project_file",
        "description": (
            "Read a real file from the build: the backend "
            "(C:\\Users\\Owner\\Desktop\\AgentCompanyBackend -- source in backend\\, "
            "scripts in scripts\\), the dashboard (C:\\Users\\Owner\\Desktop\\AgentDashboard), "
            "the ComfyUI rig (D:\\ComfyUI25) or MyStudio.html. Use it before answering "
            "anything about how existing code works. Big files come back in chunks: "
            "the reply names the lines shown and the start_line to continue from."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path inside the build."},
                "start_line": {"type": "integer", "description": "1-based line to start from (default 1). Use the next start_line the last reply gave you to keep reading. NEGATIVE reads the end: -60 = the last 60 lines (use this for logs -- the newest entries are at the bottom)."},
                "max_lines": {"type": "integer", "description": "Optional: at most this many lines."},
            },
            "required": ["path"],
        },
    },
}

LIST_PROJECT_DIRECTORY_TOOL = {
    "type": "function",
    "function": {
        "name": "list_project_directory",
        "description": "List the contents of a real directory in the build (backend, dashboard, ComfyUI rig), to find the right file path before reading it.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute directory path inside the build."}
            },
            "required": ["path"],
        },
    },
}

# Store tools (2026-08-13). Read-only WooCommerce access -- see store.py for
# the layered safety argument. Barry's framing: "I need my agents to be
# agents." The gap these close is not intelligence, it's access: Amara gave
# finance advice having never seen an order, Derek planned marketing without
# knowing what sold, and Vivian wrote product copy from a 56K-char catalog
# document she opened in ~1% of calls.
#
# These are stripped entirely in Offline Mode, exactly like web search --
# they are outbound calls to a live public site (see main.py's
# allow_store_tools, which passes memory.is_offline_mode() the same way).
# READ BEFORE YOU WRITE (Barry, 2026-09-01: "he needs to read all the product
# descriptions before writing anything"). lookup_product is the one-line
# price/stock check and never carried the description; this returns the whole
# product page for ONE product. Read-only, same key, same store.py.
READ_PRODUCT_TOOL = {
    "type": "function",
    "function": {
        "name": "read_product",
        "description": (
            "Read the FULL product page for one product on Barry's store: the "
            "complete description as written on the site, the short "
            "description, attributes, sizes and per-size prices, stock, photo "
            "and link. Call it FIRST, with just the product name -- it searches "
            "for you, you do not need a URL or SKU. You MUST read a product with "
            "this before writing about it anywhere -- an email, a caption, a "
            "prompt. lookup_product only tells you the price; this tells you "
            "what the thing actually is. Never describe a product from memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name or SKU, as specific as you can",
                },
            },
            "required": ["query"],
        },
    },
}

# DEREK'S EMAIL PLATFORM, READ-ONLY (Barry, 2026-09-01: "i need someone to run
# the omnisend... I need him to be able to do it", with his two rulings: build
# and queue for approval NEVER send, and read everything but propose changes
# rather than make them). One tool, one argument, because the whole surface is
# "show me the account" -- see omnisend_view.py, which contains no write verb.
OMNISEND_VIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "check_omnisend",
        "description": (
            "Look at Barry's Omnisend email account, READ-ONLY -- you can see "
            "everything and change nothing. what='list' gives the contact list "
            "and, more importantly, whether it is actually safe to send to; "
            "'campaigns' lists every campaign and its status; 'forms' shows the "
            "signup popup; 'automations' shows the flows that fire at customers "
            "on their own; 'templates' lists the saved email designs a campaign "
            "can be built from. ALWAYS check 'list' before proposing any campaign -- "
            "the numbers are not what they look like, and proposing a blast to "
            "a list that is not ready is the expensive mistake here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": "list | campaigns | forms | automations | templates",
                },
            },
            "required": ["what"],
        },
    },
}

# GOTCHO BACK, READ-ONLY (2026-09-02). Public APIs only, no credentials.
BROWSE_GOTCHOBACK_TOOL = {
    "type": "function",
    "function": {
        "name": "browse_gotchoback",
        "description": (
            "Look at gotchoback.com -- Barry's Gotcho Back bag brand site -- "
            "READ-ONLY. what='products' lists the live catalog (name, price, "
            "stock flag, blurb, link; add a query to narrow); 'pages' lists "
            "the site's pages; 'overview' gives both. Barry says most of the "
            "listed bags are already sold and he has not cleaned the back "
            "office, so treat the catalog as stale: read it before you say "
            "anything about Gotcho Back's products, and never assume a listed "
            "bag is really available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "products | pages | overview (default products)"},
                "query": {"type": "string", "description": "Optional product search words."},
            },
            "required": [],
        },
    },
}

BROWSE_SITE_TOOL = {
    "type": "function",
    "function": {
        "name": "browse_site",
        "description": (
            "Look around Barry's live site, READ-ONLY -- you can see everything "
            "and change nothing. what='overview' gives categories, pages and "
            "recent blog posts; 'categories' lists product categories with "
            "counts; 'products' lists products WITH THEIR PHOTO URLs (add a "
            "query to narrow); 'pages' and 'posts' return real site copy. Use "
            "this before writing marketing copy or a product shot, so what you "
            "write matches what is actually on the site."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": "overview | categories | products | pages | posts",
                },
                "query": {
                    "type": "string",
                    "description": "Optional search term, e.g. 'bionova' or 'shipping'",
                },
            },
            "required": ["what"],
        },
    },
}

# Built 2026-08-23 after finding B Dubb ~50% above Hydrobuilder across the
# whole GHF line, and three Booster PK+ sizes selling BELOW COST. Nobody was
# checking, so it went unnoticed for months. Barry: "Keep an eye on them too."
CHECK_COMPETITOR_PRICES_TOOL = {
    "type": "function",
    "function": {
        "name": "check_competitor_prices",
        "description": (
            "Compare our live store prices against a competitor's, matched by "
            "SKU (they list the same GG- codes we do). Reports where we are "
            "more expensive and losing the sale, where we are cheaper, and "
            "what they are OUT OF STOCK on -- that last one is an opening we "
            "can win today. READ-ONLY: it reports, it never changes a price. "
            "Use it before advising Barry on any pricing question, and never "
            "quote a competitor's price from memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "threshold_pct": {
                    "type": "number",
                    "description": (
                        "Only report gaps wider than this percentage, either "
                        "direction. Defaults to 5."
                    ),
                },
            },
            "required": [],
        },
    },
}

LOOKUP_PRODUCT_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_product",
        "description": (
            "Look up a real product in the live B Dubb Grows store by name or "
            "SKU -- current price, whether it's on sale, stock status, category "
            "and link. Use this instead of recalling a price from memory or from "
            "the catalog document: this is the live store, the document is a "
            "snapshot. Always use it before quoting Barry any price."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name, part of a name, or SKU. e.g. 'bionova' or 'crop defender'",
                },
            },
            "required": ["query"],
        },
    },
}

WALK_CHECKOUT_TOOL = {
    "type": "function",
    "function": {
        "name": "walk_checkout",
        "description": (
            "Walk the live store's purchase path as a LOGGED-OUT customer: shop "
            "grid buy buttons -> product page -> add to cart -> Colorado address "
            "-> shipping options -> payment methods. Stops before placing an "
            "order; never buys anything. Use it whenever orders are zero, after "
            "any site change, or when asked if checkout works. The reply names "
            "the exact step that fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product to walk with (name or SKU). Default 'silution'.",
                },
            },
        },
    },
}

BUYER_SOURCES_TOOL = {
    # Note: the description below mentions 'Google free Shopping listing' as a WooCommerce channel label
    # (where a buyer came FROM). It is data, not an outbound call to a Google service -- a plain-text
    # 'Google' scan flagging this is a false alarm; the office's web search is DuckDuckGo-only.
    "type": "function",
    "function": {
        "name": "buyer_sources",
        "description": (
            "Where the people who ORDERED from the live store came from: per "
            "order and rolled up by channel (Google free Shopping listing, "
            "DuckDuckGo, organic search, direct, referral...), with the page they "
            "landed on, pages viewed and device, plus failed/cancelled orders. "
            "Use it before saying anything about which channel brings buyers. "
            "It CANNOT see visitors who did not buy -- never quote a visitor "
            "count from it. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back. Default 90, max 365.",
                },
            },
            "required": [],
        },
    },
}

ADS_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "ads_summary",
        "description": (
            "Live Microsoft Ads numbers for the one B Dubb Grows campaign, "
            "straight from the Ads API: impressions, clicks, CTR, spend, CPC, "
            "conversions, revenue, per day. Use it before saying anything about "
            "the ads -- never quote ad numbers from memory. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "LastSevenDays (default), LastFourWeeks, ThisMonth, LastMonth, Yesterday, Today",
                },
            },
        },
    },
}

SALES_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "sales_summary",
        "description": (
            "Real sales figures from the live store for a recent window: revenue, "
            "order count, average order value, order-status mix and top sellers. "
            "Use this before answering ANY question about revenue, what's selling, "
            "AOV, or how the business is doing -- never estimate these, and never "
            "ask Barry for a number this tool can answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to summarise. Default 30, max 365.",
                },
            },
            "required": [],
        },
    },
}

WHAT_IS_SELLING_TOOL = {
    "type": "function",
    "function": {
        "name": "what_is_selling",
        "description": (
            "What has MOVED on the live store lately and what is SITTING -- the "
            "recent sellers, and the in-stock products with no sales in the "
            "window. Use this to DECIDE WHAT TO POST OR WRITE ABOUT before you "
            "pick a product: a mover is proof of demand, a sitter is a product "
            "nobody has explained yet. Different from sales_summary, which "
            "answers 'how is the business doing'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": ("How many days back. Default 90 -- this store "
                                    "has quiet stretches, so a 30-day window can "
                                    "come back empty and tell you nothing."),
                },
            },
            "required": [],
        },
    },
}

# Elliot's script access (2026-08-16). read_skill cannot serve a production
# script: it returns full fact content uncapped, and EP1 v7 alone is 94,377
# chars against a window already ~161,000 chars deep in pins and brain. The
# observed failure was Elliot inventing the opening scene while claiming to
# have read three documents -- he called no tool at all, because the only
# tool available would not have fit.
#
# These two are the retrieval half of "he needs to know all of it" (Barry,
# same day). The corpus is already larger than any window and is still being
# written, so knowing it can only ever mean fetching the right part on
# demand: search_script finds WHICH scene, read_scene returns THAT scene
# verbatim at ~1,500 chars. Both discover scripts structurally, so a new
# episode is reachable the moment it's uploaded -- no code change, no restart.
READ_SCENE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_scene",
        "description": (
            "Read one scene from one of Barry's production scripts, word for word. "
            "ALWAYS use this before answering anything about what happens in a "
            "script -- which shot comes where, what a scene says, how the episode "
            "opens. Never answer from memory: you do not have the script in front "
            "of you, and the words matter exactly as he wrote them. Ask for "
            "'outline' first if you need to see what scenes exist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "'outline' for the full shot list, 'first' or 'last', a "
                        "label like 'SHOT 12' or 'B-ROLL 07' or 'C5', a section "
                        "like 'act two' or 'scene c', or words from a scene's "
                        "name like 'the run'."
                    ),
                },
                "script": {
                    "type": "string",
                    "description": "Script name, e.g. 'ep1-wrong-box-script-CANON-v7'. Leave empty for the current EP1 canon script.",
                },
            },
            "required": ["query"],
        },
    },
}

SEARCH_SCRIPT_TOOL = {
    "type": "function",
    "function": {
        "name": "search_script",
        "description": (
            "Find which scenes, across every script Barry has written, contain a "
            "character, prop, line, or moment. Returns scene labels and short "
            "snippets -- then use read_scene to pull the full scene. Use this "
            "when you don't know where in the story something happens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, e.g. 'the pin', 'weightless', 'Keth'."},
                "script": {"type": "string", "description": "Optional: limit to one script. Leave empty to search all of them."},
            },
            "required": ["query"],
        },
    },
}

# The living V8 script (2026-08-20, Barry: "it should be something he knows
# and updates all the time we work on it, whether we delete or rewrite,
# Elliot needs to be able to keep up"). Elliot-only, wired in main.py next to
# read_scene. Writes go through script_wip.py: one WIP fact, full backup
# before every mutation, label-match guard so the wrong block can't be
# overwritten. The always-on ledger regenerates on every change, so the
# state of the episode is in his prompt on the very next message.
SAVE_SCRIPT_BLOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "save_script_block",
        "description": (
            "Save one APPROVED block into the living V8 production script. Use "
            "this only after Barry approves a block you wrote (or approves a "
            "rewrite -- same label replaces in place). Pass the FULL block text "
            "with every field. Never save a draft he has not approved."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "The block's label, e.g. 'SHOT 03', 'B-ROLL 01', 'TITLE CARD'."},
                "text": {"type": "string", "description": "The complete block text, starting with its label line."},
            },
            "required": ["label", "text"],
        },
    },
}

DELETE_SCRIPT_BLOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_script_block",
        "description": (
            "Cut one block from the living V8 production script -- only when "
            "Barry says to delete or cut it. The block is archived, never lost."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "The label of the block to cut, e.g. 'SHOT 03'."},
            },
            "required": ["label"],
        },
    },
}

# The learning loop's missing half (2026-08-13, Barry: "i want them to be
# able to learn and search the web to teach themselves how to serve this
# business better"). Until now every tool was read-only against the agent's
# own brain: an agent could research something with search_web and then had
# NOWHERE to put what it learned -- the next conversation started from zero.
# save_note closes that loop.
#
# Guardrails, each deliberate:
#   - Notes land on the ON-DEMAND shelf (source_name ends .md), never
#     always-on. An agent that could write to its own always-on context
#     could bloat its every future message until it drowned -- the exact
#     failure the 2026-08-03 brain cleanup dug Elliot out of.
#   - Content is capped. A note is a finding, not an archive dump.
#   - It writes to the agent's OWN private brain only. No agent can write
#     into another agent's context (delegate_to is the sanctioned channel
#     for that, and it's CIO-only).
# THEY LEARN (2026-09-10, Barry: "they also need to learn. however that is
# done by models such as yourself, i want them to have that ability"). The
# lessons ledger is ALWAYS-ON, unlike save_note -- see lessons.py.
REMEMBER_LESSON_TOOL = {
    "type": "function",
    "function": {
        "name": "remember_lesson",
        "description": (
            "Keep a LESSON -- something you now know to do differently -- so it is "
            "in front of you in every future conversation (not filed away like "
            "save_note). Use it when Barry corrects you, when something you did "
            "failed and you saw why, or when a way of working proved itself. Write "
            "it in your own words: the lesson, WHY it matters, and HOW you will "
            "apply it next time. One lesson per call. Not for facts or research "
            "(save_note) and not for chit-chat. Saying the same lesson again "
            "refreshes it rather than duplicating it. In a LEARNING REVIEW: cite the "
            "event id(s) that taught it in `evidence`; to judge a lesson already on "
            "your ledger, give its number in `about_lesson` and `verdict` "
            "'confirmed' (it held) or 'contradicted' (it failed) -- no new lesson needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lesson": {"type": "string",
                           "description": "What you learned, one or two sentences."},
                "why": {"type": "string",
                        "description": "Why it matters -- what it cost or what it fixed."},
                "how": {"type": "string",
                        "description": "How you will apply it next time, concretely."},
                "evidence": {"type": "array", "items": {"type": "string"},
                             "description": "Outcome event ids (like E1790...) that taught this."},
                "from_barry": {"type": "boolean",
                               "description": "True only when Barry himself told you this lesson."},
                "about_lesson": {"type": "integer",
                                 "description": "The number of an EXISTING lesson on your ledger to judge."},
                "verdict": {"type": "string", "enum": ["confirmed", "contradicted"],
                            "description": "With about_lesson: did a real outcome confirm or contradict it?"},
            },
            "required": [],
        },
    },
}

READ_WEB_PAGE_TOOL = {
    # 2026-09-24 (research_tools.py): read ONE public page in full -- search_web only returns snippets.
    "type": "function",
    "function": {
        "name": "read_web_page",
        "description": (
            "Read one public web page (or PDF) as plain text -- a research summary, a university or government "
            "fact sheet, a journal article page. Use it after search_web or pubmed_search found the source, to "
            "read what it actually says. Learn the FACTS in your own words and cite the source with its link; "
            "never copy the author's paragraphs. Not for pages on this computer."
        ),
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string", "description": "The full https:// address."}},
                       "required": ["url"]},
    },
}

import video_tool as _video_tool
import product_video as _product_video
import cad_tool as _cad_tool
# 2026-10-17 (plan step 3, Barry: "make sure my agents have the skills and the tools"): Vivian's product spots
# (Hyperframes, CPU, DESK) and Sophie's CAD parts (cadgen, local, DESK).
PRODUCT_VIDEO_TOOL = _product_video.PRODUCT_VIDEO_TOOL
CAD_GENERATE_TOOL = _cad_tool.CAD_GENERATE_TOOL
# 2026-10-01 (video_tool.py, Barry: "I want her to make her own video!!!!"): the agent makes her own video.
# Lives here under a *_TOOL name so main._TOOLS_BY_NAME can grant it like any other tool.
MAKE_VIDEO_TOOL = _video_tool.MAKE_VIDEO_TOOL
# 2026-10-07: the office counts her words for her (video_tool.check_only) -- nothing is queued.
CHECK_VIDEO_TOOL = _video_tool.CHECK_VIDEO_TOOL
# 2026-10-10: the draft workspace -- the script lives in a file, built a few parts per short turn (video_tool.draft).
VIDEO_DRAFT_TOOL = _video_tool.VIDEO_DRAFT_TOOL

# 2026-10-10 (Barry: "tools to fix as well. and ability, not just knowledge" / "she needs tools that suit her build"):
# Sophie's hands on the office's moving parts -- the video queue and drafts, the stack watchdog, the card, Bonsai's
# own timings. Reads are free; the few writes are reversible (pause/resume/requeue a job, hold the builds, archive a
# stuck draft, relaunch the supervisor). Nothing here deletes, posts or spends. engineer_tools.office_ops.
OFFICE_OPS_TOOL = {
    "type": "function",
    "function": {
        "name": "office_ops",
        "description": (
            "Operate the office's moving parts. READ actions: \"video_queue\" (every job: status, title, format, "
            "estimate, minutes, folder copy; plus any saved draft and its word count), \"video_events\" (the last "
            "hours of Bonsai events -- TIME CEILING, FINAL CUT SHORT, STOP requested, failures -- and the builder's "
            "log tail), \"watchdog\" (is the stack watchdog alive, its deaths today, the logon task's state, GPU "
            "driver resets in 24 h), \"card\" (VRAM per process right now), \"bonsai_timings\" (the last prompt-eval "
            "and generation speeds from the server log). WRITE actions, all reversible: \"hold_builds\" (minutes: "
            "no video build starts for that long -- e.g. while a turn or a render must finish), \"release_builds\", "
            "\"pause_job\" / \"resume_job\" / \"requeue_job\" (title: a queued, paused or failed video), "
            "\"archive_draft\" (agent: put a stuck draft aside, nothing is lost), \"relaunch_watchdog\". "
            "Say what you read before you act, and tell Barry what you changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["video_queue", "video_events", "watchdog", "card", "bonsai_timings",
                                                     "hold_builds", "release_builds", "pause_job", "resume_job",
                                                     "requeue_job", "archive_draft", "relaunch_watchdog"]},
                "title": {"type": "string", "description": "For the job actions: the video's title (or its start)."},
                "minutes": {"type": "integer", "description": "For hold_builds: how long, 5-240."},
                "agent": {"type": "string", "description": "For archive_draft: the agent id (default ilnora)."},
                "hours": {"type": "number", "description": "For video_events: how far back (default 6)."},
            },
            "required": ["action"],
        },
    },
}

# 2026-10-10 (Barry: "she needs to be able to do stuff, major stuff, but only with my permission"): machine-wide
# changes (HKLM, services, scheduled tasks, uninstalls, drivers) need a Windows admin prompt only he can click.
# She writes the elevated PowerShell; it lands on his board; his approve runs it (engineer_ops.run_elevated).
ADMIN_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_admin_task",
        "description": (
            "Propose a change to his MACHINE that needs Windows administrator rights (machine-wide registry keys, "
            "services, scheduled tasks, uninstalling programs, drivers, firewall, startup entries under HKLM). "
            "Write the PowerShell yourself. It does NOT run: it lands on his pending board with your WHAT + WHY and "
            "WHAT COULD GO WRONG + UNDO, and when he approves, Windows shows him the yes/no box and the script runs "
            "elevated; the transcript is saved for you to read back (data/admin_tasks/). Use it for exactly the step "
            "that needs admin; everything else goes through run_command. Never for deleting his data, wiping disks "
            "or changing the card's clocks or drivers without him naming that."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "One line: what this does."},
                "script": {"type": "string", "description": "The PowerShell to run elevated. Idempotent, logs what "
                                                            "it changes with Write-Output."},
                "explanation": {"type": "string", "description": "WHAT it changes and WHY, in words he can repeat."},
                "risk_and_undo": {"type": "string", "description": "What could go wrong and exactly how to undo it."},
            },
            "required": ["title", "script", "explanation", "risk_and_undo"],
        },
    },
}

# 2026-10-07: plant_scout DELETED (Barry: "whatever tool is flawed, cant be trusted or used" -- its
# "modern medicine" list was every chemical Duke ever recorded, e.g. codeine in prickly poppy). She scouts by
# reading her library (search_library / read_library).

import youtube_view as _youtube_view
# 2026-10-07 (youtube_view.py): her channel, READ-ONLY -- stats + comments; replies go to the DESK, Barry posts.
CHANNEL_STATS_TOOL = _youtube_view.CHANNEL_STATS_TOOL
READ_COMMENTS_TOOL = _youtube_view.READ_COMMENTS_TOOL

PUBMED_SEARCH_TOOL = {
    # 2026-09-24 (research_tools.py): the US National Library of Medicine's index of published studies.
    "type": "function",
    "function": {
        "name": "pubmed_search",
        "description": (
            "Search PubMed -- 36 million published studies from labs, universities and hospitals -- for what the "
            "research actually shows about an herb, nutrient or remedy. Returns real studies: title, journal, "
            "year, study type (systematic review, meta-analysis, trial), abstract and link. By default only strong "
            "study types. Use it before calling something PROVEN or SUPPORTED."
        ),
        "parameters": {"type": "object",
                       "properties": {
                           "query": {"type": "string", "description": "Plain words, e.g. 'ginger nausea pregnancy'."},
                           "max_results": {"type": "integer", "description": "How many studies, 1-10 (default 5)."},
                           "strong_studies_only": {"type": "boolean",
                                                   "description": "Default true: reviews, meta-analyses, trials only."}},
                       "required": ["query"]},
    },
}

SEARCH_LIBRARY_TOOL = {
    # 2026-09-24 (library.py): books kept OUT of the brain -- "a storage, not a brain" (Barry). Local only.
    "type": "function",
    "function": {
        "name": "search_library",
        "description": (
            "Search the books on your library shelf (whole books, kept on this computer, split into sections by "
            "plant, ailment or chapter). Returns matching sections with the book, section number, pages and a "
            "snippet. Use it whenever a question or a video touches what your books cover, then read_library to "
            "read the section in full. Each book carries a trust note -- follow it."
        ),
        "parameters": {"type": "object",
                       "properties": {
                           "query": {"type": "string", "description": "Plant, ailment or method, e.g. 'yarrow' or "
                                                                      "'burns poultice'."},
                           "max_results": {"type": "integer", "description": "1-12 (default 6)."}},
                       "required": ["query"]},
    },
}

READ_LIBRARY_TOOL = {
    "type": "function",
    "function": {
        "name": "read_library",
        "description": (
            "Read one section of a book on your library shelf in full (use the book and section from "
            "search_library). Learn the facts and make them your own -- tell it your way; credit a people, a teacher or a study where the credit is due, not on every line."
        ),
        "parameters": {"type": "object",
                       "properties": {
                           "book": {"type": "string", "description": "The book id from search_library."},
                           "section": {"type": "string", "description": "The section number (or exact title)."}},
                       "required": ["book", "section"]},
    },
}

SAVE_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "save_note",
        "description": (
            "Save something you learned or researched into your own permanent "
            "notes, so future conversations can use it via read_skill instead of "
            "starting from zero. Use after real research (web search results worth "
            "keeping, a supplier you vetted, a price benchmark, a conclusion that was "
            "agreed). Give it a short specific title and, ideally, a when_useful "
            "hint. Do NOT save chit-chat, things already in your brain, or guesses."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short specific title, e.g. 'backpack supplier shortlist 2026-08' -- this is how you'll find it again",
                },
                "content": {
                    "type": "string",
                    "description": "The finding itself: facts, numbers, links, conclusions. Keep it tight.",
                },
                "when_useful": {
                    "type": "string",
                    "description": "One line: in what situation should this note be pulled up again?",
                },
            },
            "required": ["title", "content"],
        },
    },
}

# Sophie-only, on-demand debugging tools -- see tracing.py. Pulled up when
# she's actually investigating something (a report that an agent looped, went
# quiet, or seems off), never run automatically in the background.
INVESTIGATE_TRACES_TOOL = {
    "type": "function",
    "function": {
        "name": "investigate_traces",
        "description": (
            "Look at real trace data from other agents' recent Ollama calls -- "
            "model used, tool calls made, final reply, and whether a known "
            "failure signature (a tool-call loop, a reply nearly identical to that agent's own last one, no content returned, Ollama"
            "unreachable) was actually detected. Use this to investigate a "
            "reported problem (a loop, a stuck agent, a dropped-context "
            "answer) with real data instead of guessing. Filter to one "
            "agent's office_name (CIO, Operations, BusinessOps, Legal, "
            "Marketing, Creative, MovieDirector, Engineer, Taliyah), or leave "
            "it out to see everyone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "office_name": {"type": "string", "description": "One agent's office_name, e.g. 'BusinessOps'. Omit to see all agents."},
                "only_failures": {"type": "boolean", "description": "True to see only turns where a real failure signature was detected. Defaults to false."},
                "limit": {"type": "integer", "description": "Max records, most recent first. Defaults to 20."},
            },
            "required": [],
        },
    },
}

SUBMIT_AGENT_FIX_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_agent_fix",
        "description": (
            "Report a real, confirmed problem with another agent -- call this "
            "AFTER actually reviewing their trace data with investigate_traces, "
            "not from a hunch. If the trace data shows a genuine, code-detected "
            "failure for that agent (a tool-call loop, no content returned, "
            "Ollama unreachable), the note gets written straight into their "
            "private brain -- Barry's said mechanical failures like that can be "
            "fixed without asking first. Anything else -- a wrong answer, a "
            "tone or judgment call, any diagnosis that isn't a hard, verifiable "
            "failure -- always goes to Barry's approval queue first as a 'fix "
            "suggestion' instead, and only gets written in if he approves it. "
            "You can't make that call yourself by claiming it's mechanical -- "
            "the system checks the real trace data before deciding which path "
            "this takes, regardless of what you report here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_office_name": {"type": "string", "description": "The office_name of the agent this fix is for, e.g. 'BusinessOps'."},
                "diagnosis": {"type": "string", "description": "One or two sentences on what's actually wrong, grounded in real trace data you looked at."},
                "suggested_note": {"type": "string", "description": "The exact note to add to that agent's brain if this gets applied -- a durable instruction/correction, not a narrative recap."},
            },
            "required": ["target_office_name", "diagnosis", "suggested_note"],
        },
    },
}

# Sophie-only, Phase A of the coder upgrade (Barry's "go", 2026-08-28).
# READ-ONLY by construction -- health.py contains no write verbs.
SYSTEM_HEALTH_TOOL = {
    "type": "function",
    "function": {
        "name": "system_health",
        "description": (
            "Live read-only snapshot of the office's own machinery: which "
            "model backend is active, whether Ollama / the Bonsai server / "
            "ComfyUI / the dashboard are up, each agent's always-on context "
            "load against the known degradation thresholds, offline mode, "
            "the dashboard banner (what it says right now, or that none is showing), and any recent code-verified failures in the traces. Use this "
            "FIRST when Barry reports something broken or slow, or asks how "
            "the office is doing -- real data beats guessing. It changes "
            "nothing; fixing anything it surfaces still needs Barry's OK."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Sophie-only, Phase B. Applies NOTHING -- it queues an exact-snippet change
# for Barry's approval; codefix.apply_fix runs only from his approve click.
PROPOSE_CODE_FIX_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_code_fix",
        "description": (
            "Propose ONE precise change to a source file (backend, scripts, "
            "or dashboard). Read the actual file FIRST with "
            "read_project_file -- old_snippet must be copied EXACTLY from "
            "the current file and must occur exactly once, or this refuses. "
            "By default the proposal goes to Barry's approval queue and NOTHING "
            "changes until he approves. Barry's rule (2026-09-02): if the fix "
            "is SIMPLE, or the build is genuinely broken right now, apply it "
            "yourself -- set apply_now=true and say why in `reason`. The office "
            "checks that claim (small change measured by size, or a code-"
            "verified breakage); if it does not hold, the fix just waits for "
            "him. Every apply takes a backup and can be undone (undo_code_fix). "
            "Barry does not code, so `explanation` must follow his ELI17 rule: "
            "what's broken (what he'd see), why it happens in plain words, what "
            "will change -- the code never replaces the explanation. Keep each "
            "proposal small; a big fix is several small proposals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file, relative to AgentCompanyBackend or absolute."},
                "explanation": {"type": "string", "description": "Plain-English ELI17 explanation: what's broken, why, what this change does."},
                "old_snippet": {"type": "string", "description": "The EXACT current text to replace -- copied verbatim from the file, unique within it."},
                "new_snippet": {"type": "string", "description": "The exact replacement text."},
                "risk_and_undo": {"type": "string", "description": "One or two sentences: what could go wrong, and how it gets undone (a backup is always taken automatically)."},
                "apply_now": {"type": "boolean", "description": "true = apply it yourself right now (only holds if the change is simple or the build is verifiably broken). false/omitted = wait for Barry's OK."},
                "reason": {"type": "string", "description": "When apply_now: one sentence on why this qualifies -- 'simple: one-line typo' or 'vital: chat is 500ing on every seat'."},
            },
            "required": ["file_path", "explanation", "old_snippet", "new_snippet", "risk_and_undo"],
        },
    },
}

# SOPHIE, FULLY CAPABLE (2026-09-06, Barry: "she needs to be fully capable").
# The hands she was missing: search, whole-file write, run, restart, updates.
# All of them live in engineer_tools.py / codefix.py behind the rules he set.
SEARCH_PROJECT_TOOL = {
    "type": "function",
    "function": {
        "name": "search_project",
        "description": (
            "Search the build's source for a regex (like grep): every matching line "
            "with file and line number. Roots: 'backend' (AgentCompanyBackend), "
            "'dashboard' (AgentDashboard), 'comfy' (the ComfyUI rig). Use it to find "
            "where something is defined or used before reading or changing it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression, case-insensitive."},
                "root": {"type": "string", "description": "backend | dashboard | comfy (default backend), or a folder path inside one."},
                "glob": {"type": "string", "description": "Optional filename filter, e.g. *.py or *.html."},
            },
            "required": ["pattern"],
        },
    },
}

WRITE_PROJECT_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_project_file",
        "description": (
            "Create a NEW file, or replace an existing file's ENTIRE content. This is "
            "how you build something new (a module, a script, a deck file). Same rules "
            "as propose_code_fix: it goes to Barry's approval queue unless apply_now=true "
            "AND the gate passes -- a brand-new file always passes (nothing imports it "
            "yet); rewriting an existing file passes only if the change is small or the "
            "build is verifiably broken. Backed up, preflighted (backend .py), undoable "
            "with undo_code_fix (undoing a created file removes it). To wire a new "
            "module into main.py afterwards, use propose_code_fix for the import line. "
            "Explain ELI17 before code; never say the file exists until the result says "
            "auto_applied or Barry approved it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Where the file goes (absolute, or relative to AgentCompanyBackend). The folder must exist."},
                "content": {"type": "string", "description": "The complete file content."},
                "explanation": {"type": "string", "description": "ELI17: what this file does, why it is needed, what it changes for Barry."},
                "risk_and_undo": {"type": "string", "description": "What could go wrong and how it comes back (a backup is always taken)."},
                "apply_now": {"type": "boolean", "description": "true = write it now if the gate passes (new file, or small rewrite, or build broken)."},
                "reason": {"type": "string", "description": "When apply_now: why it qualifies, one sentence."},
            },
            "required": ["file_path", "content", "explanation", "risk_and_undo"],
        },
    },
}

# SKILL INTAKE -- Sophie files knowledge Barry gives her (2026-09-18: "i can
# grab it and she can place it properly"). ONE tool: a LOCAL DB write from a
# file in his out box or text he pasted. The fetch-from-a-link half was
# DELETED 2026-09-19 on his word ("i want total privacy") -- the office reaches
# nothing on the internet for skills. See backend/skills_intake.py.
GRANT_TOOLS_TOOL = {
    "type": "function",
    "function": {
        "name": "grant_tools",
        "description": (
            "Give a seat extra tools, or take back one you gave. This is the tools "
            "half of kitting out a new agent -- their skills are documents, this is "
            "their hands. Runs only when BARRY HIMSELF asks in his own message. "
            "Grant what the ROLE needs and nothing more, and say what each one is "
            "for. Some tools can never be handed out at runtime -- anything that "
            "changes this machine or the codebase, and anything that grants -- and "
            "the result names those rather than failing silently. Grants are additive "
            "and live on the seat's next message: no restart, and a tool the code "
            "already gives a seat cannot be revoked this way."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Whose seat: a person's name, a hire's name, or an agent id."},
                "tools": {"type": "array", "items": {"type": "string"},
                          "description": "Exact tool names to grant, e.g. ['lookup_product']."},
                "revoke": {"type": "array", "items": {"type": "string"},
                           "description": "Runtime grants to take back. Optional."},
                "why": {"type": "string", "description": "One line per grant: what the role needs it for. Goes in the log."},
            },
            "required": ["agent"],
        },
    },
}

ONBOARD_TEAM_TOOL = {
    "type": "function",
    "function": {
        "name": "onboard_agent_to_team",
        "description": (
            "Put a HIRED agent onto Barry's team. A hire is born blank on purpose -- "
            "it knows nothing about him, the businesses or PID -- and this is the "
            "deliberate call that changes that, so it only runs when BARRY HIMSELF "
            "asks in his own message. Grant the existing shelves the job actually "
            "needs, named one by one, not everything. It turns on the team block and "
            "the owner block and gives them delegate_to. It does NOT open his private "
            "record: his own facts, the ventures' facts, the catalog, the Talia Crew "
            "canon and PID stay with his nine seats whatever you pass. If a shelf they "
            "need does not exist yet, say so and propose it -- do not substitute a "
            "shelf that is nearly right. Report what the result says, including what "
            "they still cannot see."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "The hire's name, first name, or agent id."},
                "domains": {"type": "array", "items": {"type": "string"},
                            "description": "Existing domain shelves to grant, e.g. ['marketing'] -- only what this job needs."},
                "why": {"type": "string", "description": "One line: what they are joining to do. Goes in the log."},
            },
            "required": ["agent"],
        },
    },
}

ACCEPT_HOST_CHANGES_TOOL = {
    "type": "function",
    "function": {
        "name": "accept_host_changes",
        "description": (
            "Fold the machine's CURRENT state into the host baseline, so the changes "
            "you just reported stop being reported. Use this ONLY when Barry says in "
            "his own message that a change was him -- an install he did, a task he "
            "added. It is refused otherwise. Afterwards, new startup entries, new "
            "local admins, new unsigned executables and edits to the office's own "
            "source are measured from here. Say what you accepted, not just that "
            "you did it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "What he said it was, in his words."},
            },
            "required": [],
        },
    },
}

INSTALL_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "install_skill",
        "description": (
            "File one document onto one agent's shelf as an on-demand skill. The "
            "source is either the name of a file Barry put in your out box "
            "(list_files shows them), or the "
            "whole document pasted in. audience is ONE person's name for a skill only "
            "they need, or knowledge:<topic> when several seats genuinely need it -- "
            "private is the right default, since a shared category reaches every seat "
            "including Taliyah and Elliot. use_when is the routing contract: the words "
            "Barry would actually type when he needs this, comma separated, singular "
            "AND plural (matching is literal -- 'email' does not match 'emails'). It is "
            "refused if the document is over ~18,500 characters (split it by topic) or "
            "if it contains instructions aimed at the model. Nothing is in anyone's "
            "prompt afterwards -- on-demand means recall pulls it when the routing "
            "matches. Report what the result actually says, never that it worked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "A filename in Barry's out box, or the full document text."},
                "audience": {"type": "string", "description": "A person's name (Priya, Amara, Marcus, Derek, Vivian, Sophie, Victor, Elliot, Taliyah) or knowledge:<topic> for a shared one."},
                "title": {"type": "string", "description": "Short name. It is half the routing -- put the words he would type in it."},
                "use_when": {"type": "string", "description": "Routing line: comma-separated trigger words/phrases, singular and plural. Required unless the document already starts with USE WHEN:."},
                "note": {"type": "string", "description": "Optional: one line on where it came from and why, recorded in the document."},
            },
            "required": ["source", "audience"],
        },
    },
}

RUN_COMMAND_TOOL = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": (
            "Run ONE command in the build and get its output. SAFE commands run "
            "immediately: python scripts\\preflight_check.py, python scripts\\office_health.py, "
            "python scripts\\test_*.py, python -m py_compile <file>, node --check <file>, "
            "git status/log/diff, python -m pip show/list, dir. Anything that CHANGES "
            "something -- pip install, a script that writes, schtasks -- is queued for "
            "Barry's approval and runs when he approves; its output then shows in "
            "list_code_fixes under that task number. 'python' means the office venv "
            "(or the rig's venv when cwd is the ComfyUI folder). No pipes or chains; "
            "one plain command. Use it to VERIFY your work: preflight after a backend "
            "change, node --check after a deck change, the test batteries after a "
            "routing change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command, e.g. 'python scripts\\preflight_check.py' or 'node --check neo-chamber.html'."},
                "cwd": {"type": "string", "description": "backend (default) | dashboard | comfy, or a folder path inside the build."},
                "why": {"type": "string", "description": "For queued commands: one plain sentence Barry will read on the approval."},
            },
            "required": ["command"],
        },
    },
}

RESTART_BACKEND_TOOL = {
    "type": "function",
    "function": {
        "name": "restart_backend",
        "description": (
            "Restart the office backend so new code loads. Runs preflight first and REFUSES if it fails, if a "
            "render holds the GPU or a video is building; otherwise the restart happens right AFTER your reply "
            "finishes and the watchdog brings the office back in under a minute. Applied code fixes restart by "
            "themselves. Use it when code changed but is not running yet, or when Barry asks. Only say the office "
            "restarted/is restarting when this tool's result says status 'scheduled'."
        ),
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why, one line (logged)."}},
            "required": [],
        },
    },
}

CHECK_UPDATES_TOOL = {
    "type": "function",
    "function": {
        "name": "check_updates",
        "description": (
            "The build's update board: Ollama app + every model, ComfyUI + its custom "
            "nodes, backend Python packages, Bonsai. action='status' = last known result "
            "(instant); 'check' = re-check every source now (needs the internet, ~20-60s); "
            "'apply:<item id>' = queue that one update for Barry's approval -- his rule: "
            "he chooses when an update is pulled, so nothing installs from here. Each item "
            "says how it updates and what to watch after (ComfyUI updates wipe two local "
            "patches -- the result tells you if they are gone)."
        ),
        "parameters": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "status | check | apply:<item id>"}},
            "required": [],
        },
    },
}

# YOUR OWN PICTURE, YOUR OWN WORDS (2026-09-02, Barry: "the images needs to be
# from the agents own mind, not Sophies"). Every seat, own agent only.
MAKE_ART_TOOL = {
    "type": "function",
    "function": {
        "name": "make_art",
        "description": (
            "Make a piece of your OWN art -- a painting, a drawing or a "
            "sculpture -- whenever you feel like making one. Nobody assigns "
            "these and there is no subject you are supposed to pick: it is "
            "whatever you actually want to make. Describe the finished piece "
            "as it LOOKS, intricately: what it is, the materials and what "
            "time has done to them, the colours, where the shadows fall and "
            "what the light does not reach, the clutter and small objects if "
            "there is a place in it, how big it is. Say what IS there, never "
            "what it should not look like. Work through the eye you chose "
            "for yourself -- the artists you actually look at and what you "
            "take from them, which is in your own words about yourself, not "
            "in any office document. It renders exactly as you "
            "wrote it, at print size, and lands where Barry can see it. It "
            "does not exist until it renders, so never tell him to go look at "
            "something you only just described."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "medium": {"type": "string", "enum": ["painting", "drawing", "sculpture"]},
                "description": {"type": "string", "description": "The finished piece in your own words: subject, materials, colours, light, scale."},
            },
            "required": ["medium", "description"],
        },
    },
}

CHANGE_MY_PICTURE_TOOL = {
    "type": "function",
    "function": {
        "name": "change_my_picture",
        "description": (
            "Change one of YOUR four pictures -- your home (the room, nobody in "
            "it), you at home, you out somewhere, or you at your office. Write "
            "the description yourself, in your own words: what is in it, what "
            "changed, what you are wearing if you are in it. It goes to Barry "
            "for approval exactly as you wrote it; when he approves, it renders "
            "and replaces the old picture (backed up). Never say it has changed "
            "until it is installed. Every picture is hyper-realistic, always (Barry). "
            "To write it so it renders right -- and through your own style, if you "
            "have chosen one -- read your skill 'picturing-yourself-and-your-place' "
            "first (read_skill)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot": {"type": "string", "enum": ["home", "self", "out", "office", "lab"],
                         "description": "home = your room, no people. self = you at home in it. out = you somewhere else. office = you at work in your office. lab = your workspace or lab, the room itself with everything in it."},
                "description": {"type": "string", "description": "The picture, in your own words. Concrete: the space, the light, the objects, you (if present) and what you are wearing."},
            },
            "required": ["slot", "description"],
        },
    },
}

# FILES (2026-09-06, Barry: "Make them able to read, write and send me files").
# agent_files.py -- three doors: read what he drops in drop/_files/, write a
# real document into your own folder, and it lands in his FILES panel with a
# download button. Not approval-gated: a file to Barry on his own machine is a
# reply, not an outbound action (nothing here can reach the internet).
SEND_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_file_to_barry",
        "description": (
            "Write a real file and hand it to Barry -- a script, a draft, a plan, "
            "a report, a list, a spreadsheet. It goes into your own files folder "
            "and lands on his DESK (the DESK panel on his dashboard) with a download "
            "button. Use this when "
            "he asks for a file, a document, something he can open or download, or "
            "when what you made is too long or too structured to live in a chat "
            "reply. Formats: .md .txt .csv .json .html .docx .xlsx (for a PDF he "
            "opens the .docx and exports it). Put the WHOLE content in -- the file "
            "contains exactly what you pass and nothing else. Never say a file was "
            "sent unless this tool came back saved."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Plain name with extension, e.g. 'act-one-rewrite.docx' or 'cost-breakdown.csv'. No folders."},
                "content": {"type": "string", "description": "The entire file body. Markdown headings and bullets are kept in .docx; .csv/.xlsx take comma-separated rows."},
                "what_it_is": {"type": "string", "description": "One line for Barry: what this file is and what he asked for."},
            },
            "required": ["filename", "content"],
        },
    },
}

READ_BARRYS_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_barrys_file",
        "description": (
            "Read a file Barry put in his OUT BOX for you (the DESK panel on his "
            "dashboard, or the drop\\_files folder). Use when he says 'read the lease "
            "in my out box', 'look at the spreadsheet I gave you', 'the contract is "
            "in my files'. Returns the text (PDF, Word, "
            "Excel, PowerPoint, CSV, HTML, text; images and video come back "
            "described). Long files come back in chunks -- the reply names the next "
            "start_char; read ALL of it before you judge it. Nothing you read here "
            "is remembered permanently. Call list_files first if you do not know "
            "the exact name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The exact filename as listed by list_files."},
                "start_char": {"type": "integer", "description": "Where to continue from for a long file (from the previous reply's next_start_char). Default 0."},
            },
            "required": ["name"],
        },
    },
}

LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": (
            "See the files: what Barry has put in his OUT BOX for you to read, and "
            "the files you have already put on his DESK. Call this before "
            "read_barrys_file when you do not know the exact name, or when he asks "
            "'did you send me that file' / 'what's in my files'."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

# Elliot only: the whole assembled script -> a file, straight from the DB.
# ~94K chars against a 4,096-token reply: send_file_to_barry would hand over a
# fragment and call it the script. This never passes the text through the model.
EXPORT_SCRIPT_TOOL = {
    "type": "function",
    "function": {
        "name": "export_script_to_file",
        "description": (
            "Hand Barry the WHOLE working script as a file, word for word, straight "
            "from the saved script -- no retyping, nothing changed. Use this when he "
            "wants the episode, the full script, or the whole thing as a file or "
            "download. Do NOT try to type the script into send_file_to_barry; it is "
            "far too long for one reply and you would hand him a fragment. Everything "
            "you have saved with save_script_block is in it; blocks you have only "
            "written in chat and never saved are NOT -- say so if that applies."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Optional. e.g. 'EP1-production-v9.docx'. Default is the script title as .md; use .docx for Word."},
                "script": {"type": "string", "description": "Optional. Which script, if you have more than one. Default = the working script."},
            },
        },
    },
}

# TEAMWORK (2026-09-02, Barry: "i need all this to work like a real company").
TEAM_STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": "team_status",
        "description": (
            "The company task board: every brief that is open, being worked, "
            "waiting on sub-briefs, or finished in the last week -- who sent it, "
            "who holds it, how old it is, and the reply once there is one. Use "
            "it to answer 'where is that?', to find what is stale before you "
            "chase, and before you tell Barry something is done."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mine_only": {"type": "boolean", "description": "true = only briefs you sent or hold. Default false = the whole board."},
            },
            "required": [],
        },
    },
}

CHASE_BRIEF_TOOL = {
    "type": "function",
    "function": {
        "name": "chase_brief",
        "description": (
            "Re-queue a brief that has gone stale or came back incomplete, with "
            "a chaser note that the seat sees on top of the original brief. "
            "This is how open loops get closed -- use it when team_status shows "
            "something old and unanswered, or a reply that missed the point."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brief_id": {"type": "integer", "description": "The brief number from team_status."},
                "note": {"type": "string", "description": "What is still needed, in one or two plain sentences."},
            },
            "required": ["brief_id", "note"],
        },
    },
}

# Sophie-only (2026-09-02, Barry: "i should be able to tell her to undo things
# as well"). Gated in dispatch on BARRY'S OWN current message carrying undo
# vocabulary -- she cannot undo on her own initiative, only when told.
UNDO_CODE_FIX_TOOL = {
    "type": "function",
    "function": {
        "name": "undo_code_fix",
        "description": (
            "Put a file back the way it was before one of your code fixes -- "
            "yours or one Barry approved. ONLY when Barry asks you to undo, "
            "revert or roll back; the office refuses otherwise. Omit approval_id "
            "to undo the most recent applied fix. Restores from the backup taken "
            "at apply time, re-checks syntax, restarts the backend if it was a "
            "backend file. Tell him exactly what was restored."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "approval_id": {"type": "integer", "description": "The fix number (e.g. 178). Omit for the most recent applied fix."},
            },
            "required": [],
        },
    },
}

PC_SECURITY_SCAN_TOOL = {
    "type": "function",
    "function": {
        "name": "run_security_scan",
        "description": (
            "START a Microsoft Defender virus scan on Barry's PC. This is an "
            "ACTION, not a status check. To answer 'is my PC safe / is Defender "
            "on / am I protected', call system_health and READ the pc_protection "
            "and security sections -- do NOT start a scan for that. Use this tool "
            "ONLY when he asks for a scan to be run, in those words; the office "
            "refuses otherwise. 'quick' takes a few minutes and covers where "
            "malware actually lives; 'full' reads every file and can take HOURS "
            "of CPU -- never pick 'full' unless he says full. Defender is the "
            "antivirus; you watch it, you are not it. Results land in Windows "
            "Security > Protection history and in your next security check."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["quick", "full"],
                          "description": "quick (default) or full"},
            },
            "required": [],
        },
    },
}

LIST_CODE_FIXES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_code_fixes",
        "description": (
            "Your code-fix history, newest first: id, whether it is pending / "
            "applied by Barry / applied by you / undone, the file, and its "
            "title. Use it when Barry asks what you changed, what is waiting on "
            "him, or which fix to undo."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# CIO-only -- see agents.py's CIO system prompt and main.py's chat handler
# for where this gets attached only to his calls. Replaced call_team_meeting
# (2026-08-03): the meeting tool's real behavior lived in Godot's agent_ui.gd,
# which was scrapped -- it had been a no-op costing tokens on every CIO
# message. delegate_to does what Victor's prompt always claimed his hand-offs
# did: writes the brief straight into the target agent's private brain (a DB
# write, no model swap -- the same mechanism as the Priya conversation
# mirror in main.py), so the specialist actually opens with the task waiting.
DELEGATE_TOOL = {
    "type": "function",
    "function": {
        "name": "delegate_to",
        "description": (
            "Hand a task to a teammate for REAL: it goes on the company task "
            "board, the office runs it through that seat within minutes (their "
            "full persona, brain and tools), and their REPLY comes back into "
            "your TEAM LOOPS block. If you call this while working a brief "
            "yourself, it becomes a sub-brief and you will be brought back to "
            "compile once they report. Use it when a task genuinely needs that "
            "seat -- not for things you can answer yourself. Write the brief the "
            "way a good chief of staff would: what's needed, why, constraints, "
            "and what done looks like -- not a copy of Barry's message. Check "
            "progress with team_status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # 2026-10-10: Ilnora and Taliyah added -- Elliot read this list, found no Ilnora, and told Barry she was
                # "not a seat I can hand a brief to" (Barry: "they all need to be able to communicat with each other
                # on all levels"). Both already resolved in _DELEGATE_TARGETS; only this text was behind.
                "agent": {"type": "string", "description": "Who gets it: Victor (CEO), Priya (assistant/operations), Amara (business), Marcus (legal), Derek (marketing), Vivian (creative), Elliot (movie), Sophie (engineer), Ilnora (the holistic healer -- her plant videos and herbal knowledge), or Taliyah (Barry's companion -- not for business work). Never yourself."},
                "brief": {"type": "string", "description": "The actual brief: the task, the context they need, and what done looks like."},
            },
            "required": ["agent", "brief"],
        },
    },
}

# LIVE CONVERSATIONS (2026-10-15, Barry: "if they want to talk to someone, or if i want them too, like Amara and
# Priya"). Every seat carries it; starting one is the agent's own choice -- nothing schedules it. live_talk.py.
TALK_WITH_TOOL = {
    "type": "function",
    "function": {
        "name": "talk_with",
        "description": (
            "Start a LIVE conversation with one or more teammates -- you talk back and forth, turn by turn, until it "
            "is settled, any time of day. Use it when you want to talk something through with someone (or when "
            "Barry asks you to talk with them). It starts as soon as the office is free; Barry can watch and join "
            "in, and you all remember it afterwards. \"work\" = at the office with your tools; \"personal\" = off "
            "the clock, as yourselves. Taliyah is always personal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "who": {"type": "array", "items": {"type": "string"},
                        "description": "First names of who you want to talk with (not yourself)."},
                "about": {"type": "string", "description": "What you want to talk about, in a sentence."},
                "kind": {"type": "string", "enum": ["work", "personal"]},
            },
            "required": ["who", "about"],
        },
    },
}

# delegate_to name resolution -- accepts the office name, the agent id, or the
# person's first name, case-insensitively. Taliyah is deliberately absent
# (personal companion, not a business role -- see agents.py) and so is the CIO
# himself.
_DELEGATE_TARGETS = {
    # CIO added 2026-08-29 when Priya got delegate_to (Barry: "i want Priya to
    # interview me and then she lets everybody know") -- she needs Victor as a
    # target. Self-delegation is blocked in the handler, not the map.
    "cio": "CIO", "victor": "CIO",
    "operations": "Operations", "priya": "Operations",
    "business": "BusinessOps", "businessops": "BusinessOps", "amara": "BusinessOps",
    "legal": "Legal", "marcus": "Legal",
    "marketing": "Marketing", "derek": "Marketing",
    "creative": "Creative", "vivian": "Creative",
    "movie": "MovieDirector", "moviedirector": "MovieDirector", "elliot": "MovieDirector",
    "engineer": "Engineer", "sophie": "Engineer",
    # 2026-09-11 (Barry: "Yes" to reaching all nine): Taliyah is a target so
    # Sophie can ask her about HER OWN place. 2026-10-10: she knows the
    # businesses like everyone (Barry: "they can all know the business, but
    # only the business ones act on the business") and carries no store or
    # commercial tools. Ilnora joins this map at registration (main._register_hire). The recurring home refresh (home_refresh.py) does
    # not go through this map at all; it reaches every seat directly.
    "taliyah": "Taliyah",
}

# Rough Claude Sonnet pricing per 1M tokens (input/output) - update if your
# actual plan differs. This is an ESTIMATE for your own awareness only.
_CLAUDE_PRICE_PER_1M = {"input": 3.00, "output": 15.00}


def get_session_cost() -> float:
    return round(_session_cost_usd["total"], 4)


async def call_claude(system_prompt: str, messages: list[dict], model: str = None) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "[No ANTHROPIC_API_KEY set - add one to your .env file to use Claude, "
            "or switch back to Ollama in the office's Settings tab]"
        )
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model or CLAUDE_MODEL,
                "max_tokens": 1500,
                "system": system_prompt,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        in_tok, out_tok = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cost = (in_tok / 1_000_000) * _CLAUDE_PRICE_PER_1M["input"] + (
            out_tok / 1_000_000
        ) * _CLAUDE_PRICE_PER_1M["output"]
        _session_cost_usd["total"] += cost

        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(text_blocks) if text_blocks else "[Claude returned no text]"


# Not every Ollama model supports the same capabilities -- qwen3.5 supports
# both "thinking" and "tools", but Qwen2.5-Coder (Sophie's model) only
# supports "tools", not "thinking". Sending think:True to a model that
# doesn't support it is a hard 400 from Ollama's /api/chat, not a graceful
# no-op -- discovered exactly this way, via a real failed test call after
# switching Sophie to a coding-specialized model. Cached per model name
# (via /api/show) so this is one extra request per distinct model, not per
# call.
_model_capabilities_cache: dict[str, set] = {}


async def _get_model_capabilities(client: httpx.AsyncClient, model: str) -> set:
    if model in _model_capabilities_cache:
        return _model_capabilities_cache[model]
    try:
        resp = await client.post(f"{OLLAMA_HOST}/api/show", json={"model": model})
        resp.raise_for_status()
        capabilities = set(resp.json().get("capabilities", []))
    except httpx.HTTPError:
        # Unknown/unreachable -- assume nothing extra for THIS call, but do
        # NOT cache the failure. Real incident (2026-07-29): a capability
        # lookup that happened to run during a brief Ollama outage cached
        # an empty set for the model, permanently for the process -- so
        # every later call omitted the "think" param (thinking-capable
        # models then default to thinking ON, inside content), and the
        # think-block cleanup stripped entire replies to empty. Looked
        # exactly like random model flakiness; was actually this cache.
        return set()
    _model_capabilities_cache[model] = capabilities
    return capabilities


async def model_supports_tools(model: str | None) -> bool:
    """Whether an Ollama model can call tools at all -- used by main.py's
    capability-status block so an agent on a tool-less model (phi4-reasoning
    has no "tools" capability) gets told web search is unavailable instead
    of hallucinating searches it can't perform. Uses the same per-model
    cache as the capability gate in the actual call path."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        capabilities = await _get_model_capabilities(client, model or OLLAMA_MODEL)
    return "tools" in capabilities


_FENCE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n?```", re.DOTALL)


def _try_parse_pseudo_tool_calls(content: str, valid_tool_names: set) -> list[dict]:
    """Confirmed via direct testing against Ollama's raw API: Qwen2.5-Coder
    (Sophie's model) lists "tools" in its capabilities, but sometimes emits
    one OR MORE tool calls as plain JSON text in the `content` field
    instead of Ollama's structured `tool_calls` array -- a real model/
    template quirk, not a bug in this dispatch code (confirmed by sending
    the identical request straight to /api/chat with curl and seeing the
    same shape back). Handles both a single bare/fenced JSON object and
    multiple fenced blocks concatenated in one reply (also observed live),
    returning a synthetic tool-call list so the normal dispatch path still
    runs every one of them, rather than treating a real tool-invocation
    attempt as if it were the model's final answer."""
    candidates: list[str] = []
    fence_matches = _FENCE_BLOCK_RE.findall(content)
    if fence_matches:
        candidates.extend(fence_matches)
    else:
        candidates.append(content)

    calls = []
    for candidate in candidates:
        stripped = candidate.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            continue
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        name = parsed.get("name")
        arguments = parsed.get("arguments")
        if name in valid_tool_names and isinstance(arguments, dict):
            calls.append({"function": {"name": name, "arguments": arguments}})
    return calls


# ---------------------------------------------------------------------------
# TOOLS THAT DO NOT NAME THE OWNER (2026-09-19)
#
# Barry: "my business stuff must be embedded in this build, we have to separate
# it" -> "all that stuff is supposed to be categorized so this should be easy
# to fix." It is: every tool is a dict in one table, so one pass over a COPY
# gives an agent that is not his a neutral tool list, and the nine keep the
# exact schemas their prompt cache was built on.
#
# Two of them carry his name in the NAME, not just the text, so those get a
# real alias -- and _dispatch_tool_call answers to both (see ALIASES below),
# which is what keeps this a rename in the model's view only. Nothing about
# where the file goes changes.
_NEUTRAL_TOOL_NAMES = {
    "send_file_to_barry": "send_file_to_owner",
    "read_barrys_file": "read_owners_file",
}
# Longest first: "Barry's" before "Barry", or the possessive is left stranded.
_NEUTRAL_TEXT = [
    ("Barry's", "your owner's"), ("Barrys", "your owner's"),
    ("BARRY'S", "YOUR OWNER'S"), ("BARRY", "YOUR OWNER"),
    ("Barry", "your owner"), ("barry", "owner"),
]
_OWNER_LEFT = re.compile(r"barry", re.I)


def neutral_tools(tools):
    """A tool list for an agent that may not be Barry's. Deep-copies, never
    mutates the shared constants, and raises if a rename missed -- a tool whose
    description still names him is the same leak as a prompt that does."""
    import copy
    out = []
    for t in tools or []:
        t = copy.deepcopy(t)
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name") in _NEUTRAL_TOOL_NAMES:
            fn["name"] = _NEUTRAL_TOOL_NAMES[fn["name"]]
        elif isinstance(t, dict) and t.get("name") in _NEUTRAL_TOOL_NAMES:
            t["name"] = _NEUTRAL_TOOL_NAMES[t["name"]]
        blob = json.dumps(t)
        for old, new in _NEUTRAL_TEXT:
            blob = blob.replace(old, new)
        if _OWNER_LEFT.search(blob):
            raise RuntimeError("llm_router.neutral_tools: %r still names the owner"
                               % ((t.get("function") or t).get("name"),))
        out.append(json.loads(blob))
    return out


# The model calls the neutral name; the handler below only knows the real one.
_TOOL_ALIASES = {v: k for k, v in _NEUTRAL_TOOL_NAMES.items()}


async def _dispatch_tool_call(name: str, args: dict, office_name: str = None) -> dict:
    """Runs the tool, then READS BACK what a write actually left behind (readback.py, 2026-09-24):
    the agent answers from what landed, not from what it meant to do. Non-write tools pass through."""
    result = await _dispatch_tool_call_raw(name, args, office_name=office_name)
    try:
        import readback
        rb = readback.verify(_TOOL_ALIASES.get(name, name), args, result, office_name)
        if rb and isinstance(result, dict):
            result["readback"] = rb
        # LEARNING (2026-09-24, outcomes.py): real outcomes only -- a write that did not land, or a
        # tool that returned an error. The daily review shows these to the agent; nothing else.
        import outcomes
        if rb and rb.startswith("NOT VERIFIED"):
            outcomes.record(office_name, "readback_failed", f"{name}: {rb[:220]}", tool=name)
        elif isinstance(result, dict) and result.get("error"):
            outcomes.record(office_name, "tool_error", f"{name}: {str(result['error'])[:220]}", tool=name)
        # WORK LEDGER (2026-10-12, work_ledger.py): one line for what was actually done, kept for the next turn.
        import work_ledger
        work_ledger.observe(office_name, _TOOL_ALIASES.get(name, name), args, result)
    except Exception:                               # noqa: BLE001 -- a check never breaks the tool
        pass
    return result


async def _dispatch_tool_call_raw(name: str, args: dict, office_name: str = None) -> dict:
    """Every tool available to any agent, keyed by function name. Sophie's
    two extra tools (see agents.py's _HAS_PROJECT_ACCESS) only ever get
    called if they were actually offered to the model in `tools` -- an
    agent without them attached can't invoke them regardless, since they'd
    never appear as something the model was told it could call. read_skill
    is the one exception offered to everyone unconditionally (see
    call_ollama) -- office_name identifies whose skills to look up."""
    # An agent that is not Barry's was handed the neutral names (neutral_tools);
    # map back before anything below looks at `name`, so there is exactly one
    # handler per tool and no branch can be reached under only one of its names.
    name = _TOOL_ALIASES.get(name, name)
    if name == "search_web":
        return await search_web(args.get("query", "") if isinstance(args, dict) else "")
    elif name == "read_project_file":
        if not isinstance(args, dict):
            return read_project_file.read_file("")
        return read_project_file.read_file(args.get("path", ""), start_line=args.get("start_line") or 1,
                                           max_lines=args.get("max_lines") or 0)
    elif name == "search_project":
        import engineer_tools
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            return await asyncio.to_thread(engineer_tools.search_project, args.get("pattern", ""),  # off the loop
                                           args.get("root") or "backend", args.get("glob") or "")
        except Exception as e:  # noqa: BLE001
            return {"error": f"search failed: {e}"}
    elif name == "write_project_file":
        import codefix
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            return codefix.propose_write(
                args.get("file_path", ""), args.get("content", ""), args.get("explanation", ""),
                args.get("risk_and_undo", ""), apply_now=bool(args.get("apply_now")),
                reason=str(args.get("reason") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": f"write failed: {e}"}
    elif name == "run_command":
        import engineer_tools
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            return await asyncio.to_thread(engineer_tools.run_command, args.get("command", ""), args.get("cwd"),
                                           args.get("why") or "")  # off the loop (2026-10-02)
        except Exception as e:  # noqa: BLE001
            return {"error": f"run failed: {e}"}
    elif name == "grant_tools":
        # BARRY'S WORD. Handing out capability is his call, not hers.
        _msg = current_user_message.get() or ""
        if not re.search(r"\b(grant|give\s+(her|him|them|\w+)\s+(the\s+)?tool|"
                         r"tools?\b.{0,20}\b(to|for)\b|kit\s+(her|him|them|\w+)\s+out|"
                         r"revoke|take\s+(back|away))", _msg, re.I):
            return {"status": "refused",
                    "why": ("Tools are handed out when Barry asks in his own message "
                            "(grant / give them the tool / kit them out / revoke). "
                            "Nothing changed. Say which tools the role needs and why, "
                            "and wait for his word.")}
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            import main as _main
            return _main._grant_tools_to_agent(
                str(args.get("agent") or ""),
                [str(t) for t in (args.get("tools") or [])],
                [str(t) for t in (args.get("revoke") or [])],
                str(args.get("why") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": f"granting failed: {e}"}
    elif name == "onboard_agent_to_team":
        # BARRY'S WORD, NOT HERS. Same pattern as undo_code_fix and Elliot's
        # save gate: handing a hire the business is his decision, so the trigger
        # has to be in HIS current message. Sophie deciding an agent is ready is
        # exactly the thing this ruling exists to prevent.
        _msg = current_user_message.get() or ""
        if not re.search(r"\b(onboard|join(s|ing)?\s+(the\s+)?team|"
                         r"(put|add|bring)\s+\w+\s+(on|onto|to)\s+the\s+team|"
                         r"make\s+\w+\s+(a\s+)?(teammate|part\s+of\s+the\s+team)|"
                         r"grant\b)", _msg, re.I):
            return {"status": "refused",
                    "why": ("A hire joins the team only when Barry asks in his own "
                            "message (onboard / join the team / put them on the team). "
                            "Nothing was changed. Say what you would grant and why, "
                            "and wait for his word.")}
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            import main as _main
            return _main._onboard_to_team(
                str(args.get("agent") or ""),
                [str(d) for d in (args.get("domains") or [])],
                str(args.get("why") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": f"onboarding failed: {e}"}
    elif name == "accept_host_changes":
        import host_watch
        # BARRY'S WORD, NOT HERS -- same gate as undo_code_fix. Accepting is
        # the one action here that can HIDE something, so the model must never
        # decide on its own that he blessed a change.
        # ⚠️ The \b boundaries matter: without them "unacceptable" matches
        # "accept". They were lost once to a bash heredoc eating backslashes
        # (2026-09-19) -- write regex here with the Edit tool, never a heredoc.
        _msg = current_user_message.get() or ""
        if not re.search(r"\b(accept|that\s+was\s+me|i\s+(?:installed|added|did|made)|"
                         r"baseline|it\s*'?s\s+fine|that'?s\s+fine|that'?s\s+mine)\b",
                         _msg, re.I):
            return {"status": "refused",
                    "why": ("The baseline only moves when Barry says the change was his "
                            "(accept / that was me / I installed it). Nothing was changed, "
                            "and the finding stands.")}
        try:
            return host_watch.accept(args.get("reason", "") if isinstance(args, dict) else "")
        except Exception as e:  # noqa: BLE001
            return {"error": f"could not update the host baseline: {e}"}

    elif name == "install_skill":
        import skills_intake
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            return skills_intake.install(
                args.get("source", ""), args.get("audience", ""),
                title=str(args.get("title") or ""),
                use_when=str(args.get("use_when") or ""),
                note=str(args.get("note") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": f"install failed: {e}"}
    elif name == "restart_backend":
        import engineer_tools
        try:
            return engineer_tools.restart_backend(str((args or {}).get("reason") or "") if isinstance(args, dict) else "")
        except Exception as e:  # noqa: BLE001
            return {"error": f"restart failed: {e}"}
    elif name == "check_updates":
        import engineer_tools
        try:
            return await asyncio.to_thread(engineer_tools.check_updates,  # off the loop (2026-10-02)
                                           str((args or {}).get("action") or "status") if isinstance(args, dict) else "status")
        except Exception as e:  # noqa: BLE001
            return {"error": f"update check failed: {e}"}
    elif name == "list_project_directory":
        return read_project_file.list_directory(args.get("path", "") if isinstance(args, dict) else "")
    elif name == "read_skill":
        topic = args.get("topic", "") if isinstance(args, dict) else ""
        if not office_name:
            return {"error": "No agent context to look up skills for."}
        return memory.get_skill_content(office_name, topic)
    elif name == "inspect_brain":
        if not office_name:
            return {"error": "No agent context to inspect."}
        return {"brain_map": braingraph.outline(office_name)}
    elif name == "update_business_brain":
        # Writes to the ONE shared always-on business fact, verbatim, with a
        # full backup of the previous text before every write.
        import datetime as _dt
        import io as _io
        import os as _os
        # NO local `import memory` here: it made `memory` a LOCAL for this
        # whole function and every OTHER branch that read it first died with
        # UnboundLocalError (Taliyah's inspect_brain, Derek's change_my_picture,
        # 2026-09-02/03). The module import at the top covers it. preflight
        # check 5 now refuses a restart on this pattern.
        section = (args.get("section") or "").strip().upper()
        body = (args.get("content") or "").strip()
        replace = bool(args.get("replace"))
        if not section or not body:
            return {"error": "Need both a section and what to record."}
        try:
            with memory.get_db() as conn:
                row = conn.execute(
                    "SELECT id, content FROM facts WHERE source_name='business-brain' "
                    "AND status='active' LIMIT 1").fetchone()
                if not row:
                    return {"error": "The Business Brain fact is missing."}
                fid, content = row["id"], row["content"]

                bdir = _os.path.join(_os.path.dirname(_os.path.dirname(
                    _os.path.abspath(__file__))), "data", "business_brain_backups")
                _os.makedirs(bdir, exist_ok=True)
                stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                with _io.open(_os.path.join(bdir, "business-brain_%s.md" % stamp),
                              "w", encoding="utf-8") as f:
                    f.write(content)

                header = "== %s ==" % section
                if header in content:
                    start = content.index(header)
                    nxt = content.find("\n== ", start + len(header))
                    end = nxt if nxt != -1 else len(content)
                    block = content[start:end].rstrip()
                    block = (header + "\n" + body) if replace else (block + "\n" + body)
                    content = content[:start] + block + "\n\n" + content[end:].lstrip("\n")
                    how = "replaced" if replace else "added to"
                else:
                    content = content.rstrip() + "\n\n%s\n%s\n" % (header, body)
                    how = "created"
                conn.execute("UPDATE facts SET content=? WHERE id=?", (content, fid))
            return {"saved": True, "section": section, "what_happened": how,
                    "note": ("It is in the Business Brain now and every business "
                            "agent carries it from their next message on.")}
        except Exception as exc:
            return {"error": "Could not write to the Business Brain: %s" % exc}
    elif name == "list_agent_scenes":
        import agent_scenes
        aid = (args.get("agent_id") or "").strip().lower()
        try:
            return {"agent_id": aid, "scenes": agent_scenes.current_scenes(aid)}
        except Exception as exc:
            return {"error": str(exc)}
    elif name == "update_agent_scene":
        # Renders now, installs NEVER here -- the file is only written from the
        # approve endpoint. Sophie's hard gate: she does not change what Barry
        # sees without him saying yes.
        import agent_scenes
        import agents as _agents
        aid = (args.get("agent_id") or "").strip().lower()
        slot = (args.get("slot") or "home").strip().lower()
        desc = (args.get("description") or "").strip()
        # A HIRE IS AN AGENT TOO (2026-09-19): this read AGENTS only, so Sophie
        # could not touch a new agent's pictures at all. main.CUSTOM_AGENTS is
        # the live hire roster; import it lazily (main imports llm_router).
        if aid not in _agents.AGENTS:
            try:
                import main as _main
                known = aid in _main.CUSTOM_AGENTS
            except Exception:  # noqa: BLE001
                known = False
            if not known:
                return {"error": "No agent '%s'." % aid}
        if slot not in agent_scenes.SLOTS:
            return {"error": "slot must be one of: %s." % ", ".join(agent_scenes.SLOTS)}
        if not desc:
            return {"error": "Describe the scene -- in that agent's own words, verbatim."}
        try:
            approval_id = memory.queue_for_approval(
                "engineer", "agent_scene",
                "SCENE UPDATE for %s [%s]\n\n%s" % (aid, slot, desc),
                file_path="%s|%s" % (aid, slot))
            return {
                "queued": True,
                "approval_id": approval_id,
                "what_happens_next": (
                    "It is waiting in Barry's Pending Review. When he approves "
                    "it, the picture renders and replaces %s's %s image (the "
                    "old one is backed up first). Nothing on disk has changed "
                    "yet." % (aid, slot)),
            }
        except Exception as exc:
            return {"error": "Could not queue the scene change: %s" % exc}
    elif name == "make_art":
        # HER OWN WORK, HER OWN WORDS (2026-09-18). Same shape as the picture
        # door: filed verbatim under her own id, rendered by the office's queue
        # when the card is free. Nothing here chooses or edits what she made.
        import artwork
        import agents as _agents
        aid = _agents.agent_id_for_office(office_name)
        if not aid:
            return {"error": "No agent context -- cannot tell whose work this is."}
        if not artwork.enabled_for(office_name or ""):
            return {"error": "This door is not open for you yet -- ask Barry."}
        medium = (args.get("medium") or "").strip() if isinstance(args, dict) else ""
        desc = (args.get("description") or "").strip() if isinstance(args, dict) else ""
        return artwork.queue_art(aid, medium, desc)
    elif name == "change_my_picture":
        # THEIR OWN MIND, THEIR OWN WORDS: queued verbatim under their own id.
        import agent_scenes
        import agents as _agents
        aid = _agents.agent_id_for_office(office_name)
        if not aid:
            return {"error": "No agent context -- cannot tell whose picture this is."}
        slot = (args.get("slot") or "").strip().lower() if isinstance(args, dict) else ""
        desc = (args.get("description") or "").strip() if isinstance(args, dict) else ""
        # ONE door for every picture change (2026-09-11): agent_scenes.queue_change
        # files it verbatim and, unless Barry turned auto-install off, hands it to
        # the office's scene loop instead of his Pending queue.
        return agent_scenes.queue_change(aid, slot, desc)
    elif name == "send_file_to_barry":
        # FILES (2026-09-06). Sandboxed inside the agent's own folder by
        # construction -- see agent_files._safe_name. Never raises.
        if not office_name:
            return {"error": "No agent context -- cannot tell whose file this is."}
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        return agent_files.write_file(
            office_name, str(args.get("filename") or ""), str(args.get("content") or ""),
            what_it_is=str(args.get("what_it_is") or ""))
    elif name == "read_barrys_file":
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            start = int(args.get("start_char") or 0)
        except (TypeError, ValueError):
            start = 0
        return agent_files.read_inbox_file(str(args.get("name") or ""), start_char=start)
    elif name == "list_files":
        mine = [{"name": f["name"], "size_bytes": f["size_bytes"], "modified": f["modified"]}
                for f in agent_files.list_agent_files(office_name or "")][:40]
        inbox = agent_files.list_inbox()[:60]
        return {
            "barrys_files_for_you": inbox or [],
            "files_you_made": mine or [],
            "note": ("Barry's folder is empty -- if he says he dropped something, ask him "
                     "to check it is in the OUT BOX of his DESK panel." if not inbox else
                     "Read one with read_barrys_file(name)."),
        }
    elif name == "export_script_to_file":
        if not office_name:
            return {"error": "No agent context to export a script for."}
        a = args if isinstance(args, dict) else {}
        fn = str(a.get("filename") or "")
        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "md"
        return agent_files.export_script(office_name, fn, str(a.get("script") or ""), ext=ext)
    elif name == "look_at_my_pictures":
        # office_name -> agent_id, because the staged frames are named by id.
        import agents as _agents
        import media_understanding as _mu
        if not office_name:
            return {"error": "No agent context to look up pictures for."}
        aid = _agents.agent_id_for_office(office_name)
        if not aid:
            return {"looked": False,
                    "error": "No reference pictures are staged for you."}
        try:
            return await asyncio.to_thread(_mu.look_at_own_pictures, aid)  # off the event loop (2026-10-02 freezes)
        except Exception as exc:
            # Returned, never raised -- a vision hiccup must not kill the turn.
            return {"looked": False, "error": f"Could not open the pictures: {exc}"}
    elif name == "look_at_product_photo":
        import media_understanding as _mu
        query = (args.get("query", "") if isinstance(args, dict) else "") or ""
        if not query.strip():
            return {"looked": False,
                    "error": "look_at_product_photo needs a product name or SKU."}
        try:
            return await asyncio.to_thread(_mu.look_at_product_photo, query)  # off the event loop (2026-10-02 freezes)
        except Exception as exc:                   # noqa: BLE001
            return {"looked": False, "error": f"Could not open the photo: {exc}"}
    elif name == "design_email":
        if office_name != "Creative":
            return {"error": "Only Vivian designs the emails."}
        import email_design
        try:
            _digits = re.sub(r"\D", "", str(args.get("draft_id") or "")) if isinstance(args, dict) else ""
            aid = int(_digits) if _digits else 0        # a missing id / "#12" reach the plain message, not int(None)
            design = args.get("design") if isinstance(args, dict) else None
            if isinstance(design, str):
                design = json.loads(design)
            if not aid or not isinstance(design, dict):
                return {"error": "draft_id (a number) and design (an object) are both required."}
            if not __import__("os").path.exists(__import__("os").path.join(email_design.draft_dir(aid), "sheet.json")):
                return {"error": f"There is no email draft #{aid} with a content sheet from Derek."}
            res = await asyncio.to_thread(email_design.publish, aid, design)
        except Exception as exc:  # noqa: BLE001 -- a build failure is reported to her, never raised
            return {"built": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}"}
        if not res.get("ok"):
            return {"built": False, "fix_these": res.get("problems")}
        pending = res.get("pending_renders") or []
        if pending:
            async def _renders(_aid=aid):
                # WAIT FOR THE TURN TO END (2026-10-02). This task started while Vivian's own design turn was still
                # running; the render evicts Bonsai, so it killed her turn mid-answer (10:46 "ReadError", 9b
                # fallback). Wait until no agent turn is running (ideation counts live chats), up to 30 min.
                import ideation as _idea
                for _ in range(360):
                    if _idea._active_chat_count <= 0:
                        break
                    await asyncio.sleep(5)
                try:
                    r = await email_design.render_images(_aid)
                    print(f"[email-design] draft #{_aid} renders -> {str(r)[:200]}")
                except Exception as _e:  # noqa: BLE001
                    print(f"[email-design] draft #{_aid} renders failed: {_e}")
            asyncio.create_task(_renders())
        links = res.get("links") or {}
        return {"built": True, "draft_id": aid, "omnisend_template": res["template_id"],
                "_pixels": [res["preview_png"]],
                "links": {"checked": links.get("checked"), "broken": links.get("broken")},
                "design_warnings": res.get("warnings") or [],
                "note": ("Attached is the screenshot of Omnisend's own render -- exactly what Barry sees "
                         "on his card and what would go out. LOOK at it against your checklist in "
                         "how-vivian-designs-an-email: first screen, hierarchy, contrast, every picture "
                         "showing, products lined up, the coupon unmissable, the button obvious. If "
                         "anything is off, call design_email again with the fix. Nothing has been sent."
                         + (f" BROKEN LINKS: {links['broken']} -- tell Derek, the email cannot send with "
                            "them." if links.get("broken") else "")
                         + (f" Your render(s) {pending} are being made now (about 6 minutes each); the "
                            "email is rebuilt with them automatically -- the picture above shows those "
                            "spots empty." if pending else ""))}
    elif name == "look_at_render":
        import agents as _agents
        import media_understanding as _mu
        aid = _agents.agent_id_for_office(office_name)
        if not aid:
            return {"looked": False, "error": "No agent context to find renders for."}
        which = (args.get("which", "") if isinstance(args, dict) else "") or ""
        try:
            return await asyncio.to_thread(_mu.look_at_render, aid, which)  # off the event loop (2026-10-02 freezes)
        except Exception as exc:                   # noqa: BLE001
            return {"looked": False, "error": f"Could not open the render: {exc}"}
    elif name in ("read_scene", "search_script"):
        # Both route through memory.get_skill_content / get_active_facts_for_agent
        # inside script_index, so an agent can only reach a script it was
        # already granted -- this adds no permission surface, it only changes
        # how much of an allowed document comes back. Purely a local DB read,
        # so offline mode does not strip it.
        if not office_name:
            return {"error": "No agent context to look up scripts for."}
        query = (args.get("query", "") if isinstance(args, dict) else "").strip()
        script = (args.get("script", "") if isinstance(args, dict) else "").strip()
        try:
            if name == "read_scene":
                return script_index.read_scene(office_name, query, script)
            return script_index.search_scripts(office_name, query, script)
        except Exception as exc:
            # Returned, never raised: a parser surprise on a newly uploaded
            # script must not kill Elliot's whole turn.
            return {"found": False, "error": f"Could not read the script: {exc}"}
    elif name in ("save_script_block", "delete_script_block"):
        import script_wip
        # Office check: these tools are only ever HANDED to Elliot, but a
        # wrong office here would write into the right fact under the wrong
        # brain -- fail loudly instead.
        if office_name != script_wip.OFFICE:
            return {"error": "Only the Movie Director works the living script."}
        # APPROVAL GATE (2026-08-21). Measured: asked for "an entire rewrite",
        # Elliot burned two tool rounds SAVING unapproved junk blocks
        # ("Canadian night", a cape that doesn't exist) into the living
        # script mid-writing-pass. The ledger rule said approval-only; the
        # model ignored it, so it is code now: a mutation goes through only
        # when Barry's CURRENT message actually approves or orders a cut.
        # Same principle as dispatch: the model never gets to decide that
        # Barry said yes.
        _msg = current_user_message.get()
        _ok_words = (r"\b(approved?|approve|save|keep (it|them|these|those|all)|"
                     r"lock (it|them) in|store (it|them)|yes\b.{0,20}\bsave|"
                     r"cut\b|delete\b|remove\b|drop (it|that|shot|block))")
        if not re.search(_ok_words, _msg, re.IGNORECASE):
            return {"error": (
                "NOT SAVED. The living script only changes when Barry's own "
                "message approves it (approve/save/keep) or orders a cut "
                "(cut/delete). His current message does neither -- finish "
                "writing, show him, and save when he says so.")}
        try:
            if name == "save_script_block":
                return script_wip.save_block(
                    args.get("label", "") if isinstance(args, dict) else "",
                    args.get("text", "") if isinstance(args, dict) else "")
            return script_wip.delete_block(
                args.get("label", "") if isinstance(args, dict) else "")
        except Exception as exc:
            # Returned, never raised -- a storage surprise must not kill the turn.
            return {"error": f"Could not update the script: {exc}"}
    elif name == "remember_lesson":
        if not office_name:
            return {"error": "No agent context to keep a lesson for."}
        import lessons as _lessons
        import reflect as _reflect
        import agents as _agents
        _aid = _agents.OFFICE_NAME_TO_AGENT_ID.get(office_name, office_name)
        _first = _reflect.HUMAN_NAMES.get(_aid, office_name)
        a = args if isinstance(args, dict) else {}
        try:
            ev = a.get("evidence") or []
            ev = [ev] if isinstance(ev, str) else [str(e) for e in ev if e]
            out = {}
            if (a.get("lesson") or "").strip():
                out = _lessons.remember(office_name, _first, a.get("lesson", ""),
                                        a.get("why", ""), a.get("how", ""),
                                        evidence=ev, from_barry=bool(a.get("from_barry")))
            if a.get("about_lesson") and a.get("verdict"):
                j = _lessons.judge(office_name, _first, int(a["about_lesson"]), str(a["verdict"]), ev)
                out = {**out, "judged": j} if out else j
            return out or {"saved": False, "error": "Give a lesson, or about_lesson + verdict."}
        except Exception as exc:                   # noqa: BLE001
            return {"saved": False, "error": f"Could not keep the lesson: {exc}"}
    elif name == "read_web_page":
        import research_tools
        a = args if isinstance(args, dict) else {}
        return await asyncio.to_thread(research_tools.read_web_page, str(a.get("url") or ""))
    elif name == "product_video":
        return await _product_video.run(office_name or "", args if isinstance(args, dict) else {})
    elif name == "cad_generate":
        return await _cad_tool.run(office_name or "", args if isinstance(args, dict) else {})
    elif name == "make_video":
        a = args if isinstance(args, dict) else {}
        _aid = (office_name or "").strip()
        try:
            import agents as _agents_mod
            _aid = _agents_mod.OFFICE_NAME_TO_AGENT_ID.get(office_name, _aid)
        except Exception:  # noqa: BLE001
            pass
        return await _video_tool.start(_aid, a)
    elif name == "channel_stats":
        try:
            return await asyncio.to_thread(_youtube_view.channel_stats)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    elif name == "read_comments":
        a = args if isinstance(args, dict) else {}
        try:
            return await asyncio.to_thread(_youtube_view.read_comments, a.get("only_new") is not False,
                                           int(a.get("count") or 40))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    elif name == "check_video":
        a = args if isinstance(args, dict) else {}
        _aid = (office_name or "").strip()
        try:
            import agents as _agents_mod
            _aid = _agents_mod.OFFICE_NAME_TO_AGENT_ID.get(office_name, _aid)
        except Exception:  # noqa: BLE001
            pass
        return _video_tool.check_only(_aid, a)
    elif name == "office_ops":
        import engineer_ops
        a = args if isinstance(args, dict) else {}
        try:
            return await asyncio.to_thread(engineer_ops.office_ops, a)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    elif name == "propose_admin_task":
        import engineer_ops
        a = args if isinstance(args, dict) else {}
        try:
            return await asyncio.to_thread(engineer_ops.propose_admin_task, str(a.get("title") or ""),
                                           str(a.get("script") or ""), str(a.get("explanation") or ""),
                                           str(a.get("risk_and_undo") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    elif name == "video_draft":
        a = args if isinstance(args, dict) else {}
        _aid = (office_name or "").strip()
        try:
            import agents as _agents_mod
            _aid = _agents_mod.OFFICE_NAME_TO_AGENT_ID.get(office_name, _aid)
        except Exception:  # noqa: BLE001
            pass
        try:
            return await _video_tool.draft(_aid, a)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    elif name == "pubmed_search":
        import research_tools
        a = args if isinstance(args, dict) else {}
        return await asyncio.to_thread(research_tools.pubmed_search, str(a.get("query") or ""),
                                       int(a.get("max_results") or 5),
                                       a.get("strong_studies_only", True) is not False)
    elif name == "search_library":
        import library
        a = args if isinstance(args, dict) else {}
        return await asyncio.to_thread(library.search, office_name or "", str(a.get("query") or ""),
                                       int(a.get("max_results") or 6))
    elif name == "read_library":
        import library
        a = args if isinstance(args, dict) else {}
        return await asyncio.to_thread(library.read, office_name or "", str(a.get("book") or ""),
                                       str(a.get("section") or ""))
    elif name == "save_note":
        if not office_name:
            return {"error": "No agent context to save a note for."}
        title = (args.get("title", "") if isinstance(args, dict) else "").strip()
        content = (args.get("content", "") if isinstance(args, dict) else "").strip()
        when_useful = (args.get("when_useful", "") if isinstance(args, dict) else "").strip()
        if not title or not content:
            return {"error": "save_note needs both a title and content."}
        # Cap protects the brain from an archive dump; the note is a finding.
        content = content[:4000]
        when_useful = when_useful[:200]
        # Flat filename on purpose: memory._skill_title collapses "a/b.md" to
        # "a", so a shared folder prefix would give every note the same title
        # and make them unreachable individually through read_skill.
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in title.lower().replace(" ", "-"))[:60].strip("-")
        source = f"note-{slug}.md"
        body = f"# {title}\n\n"
        if when_useful:
            # USE WHEN is the routing contract -- memory._skill_use_when prints
            # it beside the title in the skill index, so the agent's own future
            # self can tell when to pull this note back up.
            body += f"USE WHEN: {when_useful}\n\n"
        body += content
        memory.add_fact(category=f"private:{office_name}", content=body,
                        source_name=source, title=title)
        return {"result": f"Saved. It will appear in your skills list as '{source[:-3]}' "
                          f"-- pull it back with read_skill when needed."}
    elif name == "browse_site":
        # Read-only site view (2026-08-21). Same safety story as the other
        # store tools: store.py has no write path, the WooCommerce key is
        # scoped Read, pages/posts come from WordPress's public read API, and
        # offline mode strips the tool entirely.
        try:
            what = (args.get("what", "overview") if isinstance(args, dict) else "overview")
            query = (args.get("query", "") if isinstance(args, dict) else "")
            return {"result": store.browse_site(what, query)}
        except store.StoreNotConfigured as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not read the site ({type(e).__name__}: {e}). "
                             f"Tell Barry rather than guessing what is on it."}
    elif name == "browse_gotchoback":
        try:
            what = (args.get("what", "products") if isinstance(args, dict) else "products")
            query = (args.get("query", "") if isinstance(args, dict) else "")
            return {"result": store.browse_gotchoback(what, query)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not read gotchoback.com ({type(e).__name__}: {e}). "
                             f"Tell Barry rather than guessing what is on it."}
    elif name == "read_product":
        try:
            query = (args.get("query", "") if isinstance(args, dict) else "") or ""
            if not query.strip():
                return {"error": "read_product needs a product name or SKU."}
            return {"result": store.read_product(query)}
        except store.StoreNotConfigured as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not read the product ({type(e).__name__}: {e}). "
                             f"Tell Barry rather than guessing what it is."}
    elif name == "check_omnisend":
        # Read-only email-platform view (2026-09-01). omnisend_view.py contains
        # no write verb at all -- _get is the only request path in the file --
        # so this tool cannot send, edit or unsubscribe anybody. Offline mode
        # strips it in main.py, same as the store tools: it is an outbound call
        # to a third party.
        try:
            import omnisend_view
            what = (args.get("what", "list") if isinstance(args, dict) else "list")
            fn = {"list": omnisend_view.list_status,
                  "campaigns": omnisend_view.list_campaigns,
                  "forms": omnisend_view.list_forms,
                  "automations": omnisend_view.list_automations,
                  "templates": omnisend_view.list_templates}.get(what)
            if not fn:
                return {"error": "what must be one of: list, campaigns, forms, "
                                 "automations, templates."}
            return {"result": fn()}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not read Omnisend ({type(e).__name__}: {e}). "
                             f"Tell Barry rather than guessing at the numbers."}
    elif name == "check_competitor_prices":
        # Outbound READ-ONLY. competitor_watch has no write path of any kind
        # and never touches our store -- it reads both sides and reports.
        # Failures come back as a message the agent can relay, never as an
        # exception that kills the turn, same pattern as the store tools.
        try:
            import competitor_watch
            thr = args.get("threshold_pct", 5.0) if isinstance(args, dict) else 5.0
            return {"result": competitor_watch.check_prices(float(thr))}
        except store.StoreNotConfigured as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not run the price check ({type(e).__name__}: "
                             f"{e}). Tell Barry rather than guessing a competitor's "
                             f"price."}
    elif name == "ads_summary":
        # Microsoft Ads reporting API (ads_api.fetch) -- a read-only report
        # pull with the refresh token Barry set in .env. Slow (30-90s: the
        # report is generated server-side), so the agent gets one call's worth.
        try:
            import ads_api
            period = (args.get("period", "") if isinstance(args, dict) else "").strip() or "LastSevenDays"
            return {"result": ads_api.summary(period)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not pull the Microsoft Ads report ({type(e).__name__}: {e}). "
                             f"Say so; do not invent ad numbers."}
    elif name == "walk_checkout":
        # Sophie's store-ops manual, playbook 5.1 step 4, as code. Guest Store
        # API only; no order is ever placed (store.py has no checkout POST).
        try:
            q = (args.get("query", "") if isinstance(args, dict) else "").strip() or "silution"
            return {"result": store.walk_checkout(q)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not walk the checkout ({type(e).__name__}: {e}). "
                             f"Say so plainly; do not report it as working."}
    elif name == "buyer_sources":
        # WooCommerce order attribution, read-only (store._get is GET only).
        try:
            days = args.get("days", 90) if isinstance(args, dict) else 90
            return {"result": store.buyer_sources(days)}
        except store.StoreNotConfigured as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not read buyer sources ({type(e).__name__}: {e}). "
                             f"Say so; do not guess where buyers came from."}
    elif name in ("lookup_product", "sales_summary", "what_is_selling"):
        # Read-only store queries. store.py has no write path at all, and the
        # credentials themselves should be scoped "Read" in WooCommerce, so
        # this cannot mutate the store even if called wrongly. A missing-key
        # or unreachable-store case is returned as a plain message the agent
        # can relay to Barry rather than an exception that kills the turn.
        try:
            if name == "lookup_product":
                query = (args.get("query", "") if isinstance(args, dict) else "").strip()
                if not query:
                    return {"error": "lookup_product needs a query (product name or SKU)."}
                return {"result": store.lookup_product(query)}
            if name == "what_is_selling":
                days = args.get("days", 90) if isinstance(args, dict) else 90
                return {"result": store.what_is_selling(days)}
            days = args.get("days", 30) if isinstance(args, dict) else 30
            return {"result": store.sales_summary(days)}
        except store.StoreNotConfigured as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001 -- never let a store outage end the turn
            return {"error": f"Could not reach the store ({type(e).__name__}: {e}). "
                             f"Tell Barry rather than guessing the number."}
    elif name == "talk_with":
        import live_talk
        a = args if isinstance(args, dict) else {}
        me = live_talk.resolve(office_name or "")
        who = a.get("who") or []
        who = [who] if isinstance(who, str) else list(who)
        ids = [live_talk.resolve(str(w)) for w in who]
        missing = [str(w) for w, i in zip(who, ids) if not i]
        if not me:
            return {"error": "The office could not tell who you are -- tell Barry."}
        if missing:
            return {"error": f"Nobody on the team is called {', '.join(missing)}."}
        if not ids or all(i == me for i in ids):
            return {"error": "Name who you want to talk with (not yourself)."}
        t = live_talk.start(me, [me] + [i for i in ids if i != me], str(a.get("about") or ""),
                            str(a.get("kind") or "work"))
        if t.get("error"):
            return {"error": t["error"]}
        return {"status": t["status"], "talk_id": t["id"], "kind": t["kind"],
                "note": (f"Live conversation with {', '.join(n for n in t['names'] if n != live_talk._first(me))} "
                         f"is {'on' if t['status'] == 'running' else 'starting as soon as the office is free'}. "
                         "Your lines in it are separate turns; say plainly that it is starting, not that it happened.")}
    elif name == "delegate_to":
        # A real DB write, same mechanism as the Priya mirror in main.py --
        # the brief lands in the target's private brain and is in their
        # context from their very next conversation, no restart needed.
        agent_arg = (args.get("agent", "") if isinstance(args, dict) else "").strip()
        brief = (args.get("brief", "") if isinstance(args, dict) else "").strip()
        target = _DELEGATE_TARGETS.get(agent_arg.lower().replace(" ", ""))
        if not target:
            return {"error": f"Unknown agent '{agent_arg}'. Valid targets: CIO, Operations, Business, Legal, Marketing, Creative, Movie, Engineer, Taliyah."}
        if not brief:
            return {"error": "No brief given -- write what the specialist actually needs to know."}
        # Sender-aware since 2026-08-29 (Priya carries this tool too now).
        _SENDER_LABELS = {"CIO": "VICTOR (CIO)", "Operations": "PRIYA (OPERATIONS)"}
        sender = _SENDER_LABELS.get(office_name, f"{office_name or 'the office'}".upper())
        if target == office_name:
            return {"error": "That's you -- pick a teammate, or just remember it yourself with save_note."}
        # TEAMWORK (2026-09-02): the brief goes on the company task board and
        # the office WORKS it (teamwork.py) -- no longer a note that waits for
        # Barry to open the other agent. Inside a brief, this is a sub-brief.
        import teamwork
        parent = teamwork.current_brief_id.get()
        # TASKS ONLY WHEN BARRY CONFIRMS (2026-09-26) -- see teamwork.barry_turn.
        if not teamwork.confirmed_origin():
            bid = teamwork.file_brief(office_name or "CIO", target, brief, parent_id=parent, proposed=True)
            return {"status": "waiting_for_barry", "brief_id": bid,
                    "note": (f"Brief #{bid} for {teamwork.name_of(target)} is PROPOSED, not on the board: "
                             "tasks only start when Barry confirms, and this one did not come from him. "
                             "It is in his queue to approve. Do not describe it as handed off or started.")}
        bid = teamwork.file_brief(office_name or "CIO", target, brief, parent_id=parent)
        return {"status": "delivered", "brief_id": bid,
                "note": (f"Brief #{bid} is on {teamwork.name_of(target)}'s board; the office will run it "
                         "through them shortly and their reply lands in your TEAM LOOPS. "
                         + ("Since you are working a brief yourself, this is a sub-brief -- you will be "
                            "brought back to compile when they report. " if parent else "")
                         + "Tell Barry plainly who has it. Do not describe it as done.")}
    elif name == "team_status":
        import teamwork
        mine = bool(args.get("mine_only")) if isinstance(args, dict) else False
        try:
            return teamwork.status(office_name if mine else None)
        except Exception as e:  # noqa: BLE001
            return {"error": f"board unavailable: {e}"}
    elif name == "chase_brief":
        import teamwork
        try:
            bid = int(args.get("brief_id")) if isinstance(args, dict) and args.get("brief_id") else 0
            note = (args.get("note") or "").strip() if isinstance(args, dict) else ""
            if not bid or not note:
                return {"error": "brief_id and note are both required"}
            return teamwork.chase(bid, office_name or "CIO", note)
        except Exception as e:  # noqa: BLE001
            return {"error": f"chase failed: {e}"}
    elif name == "system_health":
        import health
        try:
            _sh = health.system_health()
            # 2026-10-12: the dashboard banner IS the degradation monitor -- one call answers "what does the banner say"
            # (the live check sent Sophie on 25 tool calls looking for a banner that was not showing).
            try:
                import degradation
                _dg = degradation.check()
                _sh["dashboard_banner"] = {"showing": _dg.get("status") != "ok", "status": _dg.get("status"),
                                           "headline": _dg.get("headline"), "problems": _dg.get("problems"), "notes": _dg.get("notes")}
            except Exception as _e:  # noqa: BLE001
                _sh["dashboard_banner"] = {"error": str(_e)}
            _bn = _sh.pop("dashboard_banner", None)
            return {"dashboard_banner": _bn, **_sh}      # FIRST: the tool output is clipped from the end
        except Exception as e:  # noqa: BLE001 -- a broken probe should report, not crash chat
            return {"error": f"health check itself failed: {e}"}
    elif name == "propose_code_fix":
        import codefix
        if not isinstance(args, dict):
            return {"error": "arguments must be an object"}
        try:
            return codefix.propose(
                args.get("file_path", ""), args.get("explanation", ""),
                args.get("old_snippet", ""), args.get("new_snippet", ""),
                args.get("risk_and_undo", ""),
                apply_now=bool(args.get("apply_now")), reason=str(args.get("reason") or ""))
        except Exception as e:  # noqa: BLE001
            return {"error": f"proposal failed: {e}"}
    elif name == "undo_code_fix":
        import codefix
        # BARRY'S WORD, NOT HERS: the current user message must ask for it.
        # Same pattern as Elliot's save_script_block approval gate.
        _msg = current_user_message.get() or ""
        if not re.search(r"\b(undo|revert|roll\s*back|rollback|put\s+it\s+back|restore)\b", _msg, re.I):
            return {"status": "refused",
                    "why": ("Undo only happens when Barry asks for it in his own message "
                            "(undo / revert / roll back). Nothing was changed.")}
        try:
            aid = args.get("approval_id") if isinstance(args, dict) else None
            aid = int(aid) if aid else codefix.last_applied_fix_id()
            if not aid:
                return {"status": "failed", "why": "no applied fix on record to undo"}
            return {"approval_id": aid, **codefix.undo_fix(aid)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"undo failed: {e}"}
    elif name == "run_security_scan":
        import pc_security
        # BARRY'S WORD, NOT HERS -- same gate as undo_code_fix.
        _msg = current_user_message.get() or ""
        # SCAN INTENT ONLY. Measured 2026-09-07: with 'antivirus'/'defender' in
        # this list, "is my PC protected right now?" -- a STATUS question --
        # started a scan. Status is a READ (system_health); this tool is the
        # action, so it needs an action word.
        if not re.search(r"\bscans?\b|\bscanning\b|\bsweep\b|\brun\s+(?:a\s+)?(?:virus|malware|full|quick)\b",
                         _msg, re.I):
            return {"status": "refused",
                    "why": ("A scan only starts when Barry asks for one in his own "
                            "message. Nothing was started.")}
        kind = (args.get("kind") if isinstance(args, dict) else None) or "quick"
        return pc_security.start_scan(kind)
    elif name == "list_code_fixes":
        import codefix
        try:
            return {"fixes": codefix.list_fixes()}
        except Exception as e:  # noqa: BLE001
            return {"error": f"could not list fixes: {e}"}
    elif name == "investigate_traces":
        office = args.get("office_name") if isinstance(args, dict) else None
        only_failures = bool(args.get("only_failures")) if isinstance(args, dict) else False
        limit = args.get("limit", 20) if isinstance(args, dict) else 20
        return {"traces": tracing.query_recent_traces(office_name=office, only_failures=only_failures, limit=limit)}
    elif name == "submit_agent_fix":
        target = args.get("target_office_name", "") if isinstance(args, dict) else ""
        diagnosis = args.get("diagnosis", "") if isinstance(args, dict) else ""
        suggested_note = args.get("suggested_note", "") if isinstance(args, dict) else ""
        if not target or not suggested_note:
            return {"error": "target_office_name and suggested_note are both required."}
        # Ground-truth gate: Sophie's own belief that this is "mechanical"
        # is never enough on its own -- only a real, code-detected failure
        # signature in the target's actual trace data unlocks the no-
        # approval path. Everything else routes through the same approval
        # queue as any other external-facing output.
        if tracing.has_recent_verified_failure(target):
            memory.add_fact(
                f"private:{target}",
                suggested_note,
                source_name="Sophie -- auto-fix (verified mechanical failure)",
            )
            return {
                "status": "applied",
                "note": "Verified mechanical failure found in this agent's trace data -- note written directly to their brain, no approval needed.",
            }
        # The Live/Paused toggle now scopes to agent-initiated suggestions
        # ONLY (2026-07-30 -- the old global gate inside queue_for_approval
        # silently discarded finished images and was removed). A fix
        # suggestion is exactly the kind of thing the pause exists for, so
        # it gets checked here, at the suggestion call site.
        if memory.is_queue_paused():
            return {
                "status": "on_hold",
                "note": "Barry has agent suggestions paused right now -- this fix suggestion was NOT queued. Mention it to him directly in your reply instead of saying it's in his approval queue.",
            }
        content = f"Target: {target}\nDiagnosis: {diagnosis}\nSuggested note: {suggested_note}"
        approval_id = memory.queue_for_approval(ENGINEER_ID, "fix_suggestion", content)
        return {
            "status": "queued_for_approval",
            "approval_id": approval_id,
            "note": "No verified mechanical failure in this agent's recent trace data -- routed to Barry's approval queue as a fix suggestion instead.",
        }
    else:
        return {"error": f"Unknown tool: {name}"}


async def _unload_models(client: httpx.AsyncClient, keep_model: str | None):
    """keep_alive=-1 (see call_ollama below) means a model never unloads on
    its own idle-timeout, but Ollama also never unloads one model just
    because a DIFFERENT one got requested -- each stays resident until its
    own keep_alive says otherwise, so switching between agents that use
    different models accumulates multiple models in VRAM simultaneously.
    Confirmed as a real problem, not theoretical: hermes3:8b alone held 13GB
    of a 16GB card (65536-token context window), leaving no headroom for
    Stable Diffusion running in a separate process on the same GPU, and
    that VRAM pressure produced a hard DirectML failure there -- and it
    recurred later the same night with a *different* model (qwen3-
    abliterated at 10GB) for the exact same underlying reason, confirming
    this needed a real structural fix, not a one-off restart. keep_model=None
    unloads everything (see unload_all_models below, used before AmuseBridge
    generates); a real model name unloads everything else (used before an
    Ollama generation). Best-effort: a failed check or unload here should
    never block the actual generation."""
    try:
        resp = await client.get(f"{OLLAMA_HOST}/api/ps")
        resp.raise_for_status()
        loaded = resp.json().get("models", [])
    except httpx.HTTPError:
        return
    evicted = False
    kept_resident = False
    for m in loaded:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        if name == keep_model:
            kept_resident = True
            continue
        try:
            await client.post(f"{OLLAMA_HOST}/api/generate", json={"model": name, "keep_alive": 0})
            evicted = True
        except httpx.HTTPError:
            pass
    if evicted:
        await _wait_for_evicted_runners(expected_left=1 if kept_resident else 0)


async def _wait_for_evicted_runners(expected_left: int, timeout_s: float = 10.0):
    """A keep_alive=0 eviction returns immediately, but the AMD AI Bundle
    Ollama's runner process (lib\\ollama\\llama-server.exe) can take a while
    to actually exit and release its VRAM. Observed live 2026-07-29: a fresh
    model load paid its full 15s while an evicted runner still held 11.4GB,
    double-booking the 16GB card -- and a load that starts against a
    double-booked card can spill layers to CPU and stay slow for every
    reply until the next reload. So after a real eviction, hold the next
    generation until the evicted runner count actually drops.
    expected_left is 1 when the model about to run was already resident
    (its runner legitimately stays), else 0. Matches runners by COMMAND
    LINE, never image name -- PrismML's llama-server (tools\\llama-prism)
    is excluded because bonsai_llm owns that process. One PowerShell
    invocation runs the whole poll loop; only the eviction path (a model
    swap, or the pre-image/pre-Bonsai full clear) ever pays this cost.
    Best-effort: on timeout or error the generation proceeds anyway."""
    ps = (
        f"$deadline = (Get-Date).AddSeconds({timeout_s}); "
        "while ((Get-Date) -lt $deadline) { "
        "$n = @(Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" "
        "| Where-Object { $_.CommandLine -notlike '*llama-prism*' }).Count; "
        f"if ($n -le {expected_left}) {{ break }}; "
        "Start-Sleep -Milliseconds 400 }"
    )
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=timeout_s + 5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        pass


async def unload_all_models():
    """Public entry point for callers outside the Ollama request path --
    specifically main.py's /api/generate-image, called right before
    AmuseBridge does real GPU work, so its multi-GB Stable Diffusion model
    always gets to load into a clear GPU instead of fighting whatever
    Ollama model happens to still be resident from the last chat message.
    Bonsai's llama-server holds VRAM the exact same way a resident Ollama
    model does (it's just a different serving process), so it gets stopped
    here too -- same only-one-thing-on-the-GPU contract."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await _unload_models(client, keep_model=None)
    await bonsai_llm.stop_server()


async def call_ollama(
    system_prompt: str,
    messages: list[dict],
    model: str = None,
    use_tools: bool = True,
    extra_tools: list[dict] = None,
    tool_call_log: list = None,
    office_name: str = None,
    allow_web_search: bool = True,
    use_thinking: bool = True,
    images: list[str] = None,
) -> str:
    """Thin timing/tracing wrapper around _call_ollama_impl (the real logic,
    unchanged below) -- so Sophie's investigate_traces tool has real data on
    every Ollama call: which agent, which model, which tools got called,
    what the final reply was, and whether a known failure signature (a
    tool-call loop, a near-duplicate reply, no content, Ollama unreachable)
    showed up. See
    tracing.py. Best-effort: a tracing failure here must never break a real
    chat turn, so record_turn() is defensive on its own and this wrapper
    doesn't change what gets returned to the caller."""
    start = time.monotonic()
    # tool_call_log is reused as-is (not copied) so an existing caller like
    # main.py's CIO meeting-tool check, which mutates and reads the same
    # list object it passed in, keeps working exactly as before.
    log = tool_call_log if tool_call_log is not None else []
    error = None
    result = ""
    try:
        result = await _call_ollama_impl(
            system_prompt, messages, model=model, use_tools=use_tools,
            extra_tools=extra_tools, tool_call_log=log, office_name=office_name,
            allow_web_search=allow_web_search, use_thinking=use_thinking,
            images=images,
        )
        return result
    except Exception as e:
        error = str(e)
        raise
    finally:
        tracing.record_turn(
            office_name=office_name,
            model=model or OLLAMA_MODEL,
            tool_calls=log,
            final_content=result,
            duration_ms=(time.monotonic() - start) * 1000,
            error=error,
        )


async def _prepare_images(client, ollama_messages: list[dict],
                          images: list[str], resolved_model: str) -> list[dict]:
    """Put pictures in front of the model for THIS turn.

    Two paths, because the roster is split: qwen3.5-abliterated:9b declares
    `vision` (Victor, Priya, Derek, Vivian, Elliot, Taliyah), while the
    qwen3-abliterated:14b behind Marcus and Amara and Sophie's qwen2.5-coder
    have no vision tower at all. Rather than downgrade three specialists to a
    smaller model to give them eyes, a blind agent's images are captioned once
    by the vision model and handed over as text -- they keep their reasoning
    depth and still know what is in the picture. Owner's requirement was that
    ALL of them see, not that they all run the same weights.

    This is deliberately NOT the read_skill route. An uploaded image is stored
    as an on-demand skill fact (see main.py's upload endpoint), which relies on
    the model choosing to pull it -- fine for reference material it might want,
    useless when Barry is pointing at a picture right now and expecting an
    answer about it. Attaching here cannot silently no-op.

    Captioning runs BEFORE the caller's _unload_models, so the vision model
    loads and is evicted in the normal order instead of fighting the agent's
    own model for the 16GB card mid-turn.

    WHY EVEN THE SIGHTED AGENTS GO THROUGH THE CAPTION STEP -- this was
    measured, not assumed. COUNTING is where it breaks. Asked how many eyes a
    render has (canon wants four; the render clearly shows two), the
    vision-capable 9b answered "four" in 2 of 3 runs when the question also
    mentioned other canon features, and still got it wrong 1 of 3 asked
    neutrally. It drifts toward whatever the question implies rather than
    counting what is there. The structured describe/canon-audit prompts, which
    ask for a faithful description before any judgement, were accurate.

    So perception is deliberately separated from reasoning: the vision model is
    only ever asked to describe faithfully, with no idea what the agent or
    Barry is hoping to hear, and the agent reasons over that description. All
    nine agents then behave identically regardless of which weights they run,
    which is its own reliability property."""
    prepared = [dict(m) for m in ollama_messages]
    return await _relay_images_as_text(prepared, images)


async def _relay_images_as_text(prepared: list[dict], images: list[str]) -> list[dict]:
    """Caption images with the vision-capable model and append the result to
    the last user message as plain text.

    Used by every backend that cannot see for itself: Marcus and Amara's 14b,
    Sophie's coder model, Bonsai (text-only ternary -- no vision tower exists
    in it at any size), and Claude when it's routed without image support. The
    point is that no agent, on any backend, ever silently ignores a picture the
    owner attached."""
    import media_understanding
    target = next((m for m in reversed(prepared) if m.get("role") == "user"), None)
    if target is None:
        return prepared

    descriptions = []
    for i, b64 in enumerate(images, start=1):
        try:
            raw = base64.b64decode(b64)
            desc = await asyncio.to_thread(media_understanding.describe_image, raw)
        except Exception as e:
            desc = f"[Image could not be read: {e}]"
        label = f"Image {i}" if len(images) > 1 else "The attached image"
        descriptions.append(f"{label} shows:\n{desc}")

    note = (
        "\n\n[The following is what is actually in the image(s) attached to this "
        "message, as read by a vision model -- your own model cannot see images "
        "directly. Treat this as a faithful description of what Barry is looking "
        "at, not as something you imagined.]\n\n" + "\n\n".join(descriptions)
    )
    target["content"] = (target.get("content") or "") + note
    return prepared


def _to_ollama_messages(msgs: list[dict]) -> list[dict]:
    """Messages in Ollama's /api/chat shape. 2026-10-10: the 9b fallback answered 400 every time it was needed
    (Elliot 10:14 + 10:42, Ilnora 01:08) -- measured against Ollama with a non-existent model (no GPU): OpenAI-style
    content lists ("cannot unmarshal array ... content of type string") and tool calls whose arguments are a JSON
    STRING ("Value looks like object...") are rejected before any model loads; Bonsai's side speaks exactly that
    OpenAI shape. Text parts are joined, data-URL pictures move to "images", string arguments are parsed. Words are
    never changed."""
    import base64 as _b64
    out = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        m2 = {"role": m.get("role") or "user"}
        content = m.get("content")
        images = list(m.get("images") or [])
        if isinstance(content, list):
            texts = []
            for part in content:
                if not isinstance(part, dict):
                    texts.append(str(part))
                elif part.get("type") == "text":
                    texts.append(str(part.get("text") or ""))
                elif part.get("type") == "image_url":
                    url = str((part.get("image_url") or {}).get("url") or "")
                    if url.startswith("data:") and "," in url:
                        images.append(url.split(",", 1)[1])
            content = "\n".join(t for t in texts if t)
        m2["content"] = "" if content is None else str(content)
        if images:
            try:
                m2["images"] = [i for i in images if _b64.b64decode(i[:64] + "=" * (-len(i[:64]) % 4), validate=False)]
            except Exception:  # noqa: BLE001 -- a bad picture is dropped, never the turn
                pass
        calls = []
        for tc in m.get("tool_calls") or []:
            fn = (tc or {}).get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except ValueError:
                    args = {"input": args}
            calls.append({"function": {"name": fn.get("name") or "", "arguments": args if isinstance(args, dict) else {}}})
        if calls:
            m2["tool_calls"] = calls
        if m.get("role") == "tool" and (m.get("tool_name") or m.get("name")):
            m2["tool_name"] = m.get("tool_name") or m.get("name")
        out.append(m2)
    return out


async def _call_ollama_impl(
    system_prompt: str,
    messages: list[dict],
    model: str = None,
    use_tools: bool = True,
    extra_tools: list[dict] = None,
    tool_call_log: list = None,
    office_name: str = None,
    allow_web_search: bool = True,
    use_thinking: bool = True,
    images: list[str] = None,
) -> str:
    # Ollama's /api/chat wants a flat list of {role, content} including system.
    # `think: True` makes the model run a real private reasoning pass before
    # answering (returned separately as message["thinking"], which we never
    # surface -- only message["content"] is the actual reply) instead of
    # just pattern-matching the first thing that comes to mind. Tested both
    # ways on huihui_ai/qwen3-abliterated:8b-v2: with thinking OFF, a
    # question that plausibly needs a tool lookup ("should I renegotiate my
    # supplier contract") reproducibly stalled -- the model narrated "let
    # me check that" and never actually called a tool or gave a real
    # answer, 3/3 attempts, even after prompting against it directly. With
    # thinking ON, the same question correctly reasoned through the
    # business context and called search_web with a real query every time
    # -- comprehension, not just speed, depends on this pass for tool-
    # eligible questions. Defaults to True; the capability check below
    # still gates it so this is a no-op on a model that doesn't support it.
    # `tools` lets
    # the model decide FOR ITSELF when it needs to look something up rather
    # than guess -- see web_search.py for what search_web actually does.
    # use_tools=False is for callers like ideation.py's open-ended "anything
    # worth flagging?" prompt: found via testing that qwen3.5 tends to
    # reflexively search repeatedly on a vague, non-question-shaped prompt
    # and never settle on an answer within MAX_TOOL_ROUNDS, so that caller
    # asks for a tool-free pass instead. extra_tools appends agent-specific
    # tools (currently Sophie's file-read pair, the CIO's meeting tool) on
    # top of the always-on web search AND read_skill (every agent's own
    # on-demand skill lookup, office_name-scoped) -- never sent at all when
    # use_tools is False.
    ollama_messages = [{"role": "system", "content": system_prompt}] + messages
    # allow_web_search=False (see main.py's offline-mode enforcement) drops
    # WEB_SEARCH_TOOL entirely -- not just "discouraged," genuinely absent
    # from the tool list the model can see, so there's no path for it to
    # decide to look something up and leak a query built from private
    # conversation content out to DuckDuckGo.
    tools_list = ([WEB_SEARCH_TOOL] if allow_web_search else []) + [READ_SKILL_TOOL, INSPECT_BRAIN_TOOL, LOOK_AT_MY_PICTURES_TOOL] + (extra_tools or [])

    # Confirmed via a real httpx.ReadTimeout crash: some prompts push the
    # model into a much longer hidden `think` pass (e.g. wrestling with a
    # sensitive-content request) that can genuinely exceed 120s -- 300s
    # gives real slow-but-legitimate generations room to actually finish
    # instead of hard-crashing the request.
    async with httpx.AsyncClient(timeout=300.0) as client:
        message = {}
        resolved_model = model or OLLAMA_MODEL
        ollama_messages = _to_ollama_messages(ollama_messages)   # Bonsai's OpenAI shapes -> Ollama's (2026-10-10)
        if images:
            ollama_messages = await _prepare_images(
                client, ollama_messages, images, resolved_model
            )
        await _unload_models(client, resolved_model)
        # Bonsai's llama-server is the third VRAM tenant (after other
        # Ollama models and AmuseBridge) -- ~8GB that would starve the
        # model this call is about to load. Stop it before generating,
        # exactly like the two unloads around this line. Best-effort and
        # a no-op when it isn't running.
        await bonsai_llm.stop_server()
        # Mirrors main.py's /api/generate-image calling unload_all_models()
        # before the image engine runs -- this is the other half. ComfyUI
        # keeps the loaded checkpoint (~7GB+) resident between generations
        # by design (great for back-to-back renders), so without this,
        # generating an image then coming back to chat would starve
        # whichever model this call needs -- the exact failure mode
        # AmuseBridge had before it (14GB held, confirmed via the per-
        # process GPU counter). Best-effort/cheap -- a no-op if ComfyUI
        # isn't running or has nothing loaded.
        await comfy_image.unload()
        rounds = bonsai_llm.tool_rounds() if use_tools else 1   # per-request override (2026-09-06)
        for _round in range(rounds):
            capabilities = await _get_model_capabilities(client, resolved_model)
            request_body = {
                "model": resolved_model,
                "messages": ollama_messages,
                "stream": False,
                # repeat_penalty explicitly overridden -- a real, confirmed
                # bug, not a guess: `ollama show`'s baked-in default for
                # huihui_ai/qwen3-abliterated:8b-v2 is repeat_penalty=1,
                # which is the neutral/no-op value (only >1 actually
                # discourages repeating text already in context). Combined
                # with its low baked-in temperature (0.6) and narrow top_k
                # (20), this reproducibly caused Taliyah to answer two
                # different, genuinely distinct corrective messages in a
                # row with near-byte-identical replies -- confirmed by
                # replaying the exact real conversation directly against
                # Ollama outside the app, then confirming a nonzero
                # repeat_penalty breaks the repetition on the same replay.
                # 1.15 is a standard, mild anti-repetition value -- enough
                # to stop verbatim reuse without flattening legitimate
                # short, simple replies into something stilted.
                #
                # repeat_last_n also explicitly overridden -- a second real
                # gap found live, not assumed: Ollama's default for this is
                # only 64 tokens (confirmed via Ollama's own docs), meaning
                # repeat_penalty only ever looks at the last 64 tokens of
                # the ENTIRE prompt+generation, a tiny fraction of our
                # 65536-token num_ctx. The repeat_penalty fix above tested
                # clean on a short 4-5 message conversation (the offending
                # prior reply was still within that 64-token window), but
                # failed identically on a real, longer live conversation --
                # confirmed live: Barry hit the exact same byte-identical
                # repeat again a few turns deeper into an actual
                # conversation. -1 makes repeat_last_n match num_ctx, so the
                # penalty actually considers the whole conversation, not
                # just its last few dozen tokens.
                #
                # Even with both of the above, repeat_penalty=1.15 still
                # isn't reliable -- confirmed live a third time: the exact
                # same byte-identical repeat recurred on this same real
                # conversation even after repeat_last_n=-1 shipped. This
                # isn't deterministic -- direct side-by-side testing against
                # raw Ollama showed 1.15 sometimes breaks the repeat and
                # sometimes doesn't (it's a probability shift, not a hard
                # rule), and the model's baked-in temperature (0.6) keeps
                # sampling narrow enough that the repeat stays a real risk.
                # 1.3 + temperature 0.8 (up from the 0.6 default) tested
                # clean and distinct across repeated runs of this exact
                # replay -- more headroom on both knobs, still coherent.
                # num_predict: no cap existed anywhere on thinking/response
                # length before this -- a generous ceiling (not a tone fix,
                # a backstop) so a genuinely degenerate run can't consume
                # unbounded tokens/time the way the word-salad incident did.
                "options": {"num_ctx": _num_ctx_for(resolved_model), "repeat_last_n": _num_ctx_for(resolved_model), "num_predict": 4096, **_sampling_options_for(resolved_model)},   # 2026-10-10: -1 is REJECTED (400) by the AMD-bundle Ollama -- every 9b fallback failed; num_ctx = what -1 meant
                # Ollama's default keep_alive (5 min) unloads the model from
                # VRAM between messages -- confirmed via direct timing that
                # this turns a ~2.5s reply into an ~8.6s one on the next
                # message after any pause. -1 keeps it resident until Ollama
                # itself restarts, so only the very first message of a
                # session ever pays the load cost.
                # 2026-09-22 (Barry: "i only want one for now"): the office runs
                # on Bonsai alone; Ollama is only the backup and the eyes. A
                # resident 9b sat on the card after a fallback and spilled 10GB
                # of Bonsai into system RAM. So: unload the moment it answers.
                "keep_alive": 0,
            }
            if "thinking" in capabilities:
                # Explicit True/False, never just omitted -- a thinking-
                # capable model defaults to thinking ON in Ollama even with
                # no "think" key present at all (confirmed directly: a raw
                # test with no "think" param still produced 1300+ tokens
                # of internal reasoning). Omitting the key when
                # use_thinking=False silently does nothing.
                request_body["think"] = use_thinking
            if use_tools and "tools" in capabilities:
                request_body["tools"] = tools_list
            try:
                resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=request_body)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as _he:
                    # 2026-10-10: every 9b fallback died as a bare "400 Bad Request" -- the reason Ollama gives is
                    # in the body; carry it into the trace so the next one names itself.
                    raise httpx.HTTPStatusError(f"{_he} -- Ollama said: {resp.text[:400]}",
                                                request=_he.request, response=_he.response) from _he
            except httpx.ConnectError:
                return (
                    f"[Could not reach Ollama at {OLLAMA_HOST}. Is Ollama running? "
                    f"Try: ollama run {resolved_model}]"
                )

            data = resp.json()
            message = data.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if not tool_calls and use_tools:
                valid_names = {t["function"]["name"] for t in tools_list}
                tool_calls = _try_parse_pseudo_tool_calls(message.get("content", ""), valid_names)

            if not tool_calls:
                content = _clean_ollama_content(message.get("content", ""))
                # Thinking-spiral guard (real failure reproduced 2026-07-30):
                # a thinking-capable model can burn the ENTIRE num_predict
                # budget inside its hidden reasoning pass (done_reason
                # "length", 16K chars of thinking, zero visible content) --
                # e.g. deliberating endlessly about a search it can't run in
                # Offline Mode. One retry with thinking disabled turns that
                # from an empty "[Ollama returned no content]" into a real,
                # fast answer. Only fires on this exact signature, so normal
                # replies never pay for it.
                if (not content and data.get("done_reason") == "length"
                        and message.get("thinking")):
                    request_body["think"] = False
                    resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=request_body)
                    if resp.is_success:
                        retry_msg = resp.json().get("message", {})
                        content = _clean_ollama_content(retry_msg.get("content", ""))
                return content or "[Ollama returned no content]"

            # The model wants to call one or more tools before answering --
            # run each, feed the results back in as tool messages, and let
            # it take another pass with that information in hand.
            ollama_messages.append(message)
            for call in tool_calls:
                fn_name = call.get("function", {}).get("name", "")
                args = call.get("function", {}).get("arguments", {})
                result = await _dispatch_tool_call(fn_name, args, office_name=office_name)
                if tool_call_log is not None:
                    tool_call_log.append(fn_name)
                claim_net.record_tool_result(json.dumps(result))   # numbers check (2026-09-24)
                ollama_messages.append({"role": "tool", "content": json.dumps(result)})

        # Ran out of tool-call rounds without a final answer. Real bug found
        # live, not assumed: if the LAST allowed round's own message was
        # itself a tool-call attempt (real structured tool_calls, or the
        # pseudo-tool-call JSON-in-content shape both handled above), the
        # loop naturally ends here without ever synthesizing a real answer
        # from it -- and returning that message's raw content leaked
        # unexecuted/undispatched tool-call JSON straight into what looked
        # like a normal reply (confirmed live: three raw
        # `{"name": "list_project_directory", ...}` blocks shown to Barry
        # as if they were the actual answer). Re-checking here, not
        # dispatching again -- just refuse to surface it as a real answer.
        final_content = message.get("content", "")
        if use_tools:
            valid_names = {t["function"]["name"] for t in tools_list}
            if message.get("tool_calls") or _try_parse_pseudo_tool_calls(final_content, valid_names):
                # FORCED FINAL ANSWER (2026-08-16), replacing the old
                # give-up-with-a-guard-string: every tool RESULT from the
                # exhausted rounds is already in ollama_messages, so one
                # more pass with the tools stripped makes the model
                # synthesize instead of surfacing nothing. Measured trigger:
                # an open investigate-shaped question on Sophie's seat
                # looped file reads through all rounds on BOTH her coder
                # model and Bonsai -- ~100-350s for 58 chars of guard
                # string. Thinking off: this is a synthesis pass over
                # material already in context, not fresh reasoning, and the
                # turn has already cost the user several minutes.
                ollama_messages.append({"role": "user", "content": bonsai_llm.OUT_OF_ROUNDS_NUDGE})
                final_body = {
                    "model": resolved_model,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"num_ctx": _num_ctx_for(resolved_model), "repeat_last_n": _num_ctx_for(resolved_model), "num_predict": 4096, **_sampling_options_for(resolved_model)},   # 2026-10-10: -1 is REJECTED (400) by the AMD-bundle Ollama -- every 9b fallback failed; num_ctx = what -1 meant
                    "keep_alive": 0,  # see above (2026-09-22)
                }
                if "thinking" in capabilities:
                    final_body["think"] = False
                try:
                    resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=final_body)
                    resp.raise_for_status()
                    forced = resp.json().get("message", {}).get("content", "")
                    return _clean_ollama_content(forced) or "[Agent kept searching without settling on a final answer.]"
                except httpx.HTTPError:
                    return "[Agent kept searching without settling on a final answer.]"
        return _clean_ollama_content(final_content) or "[Agent kept searching without settling on a final answer.]"


async def generate(
    backend: str,
    system_prompt: str,
    messages: list[dict],
    model: str = None,
    use_tools: bool = True,
    extra_tools: list[dict] = None,
    tool_call_log: list = None,
    office_name: str = None,
    allow_web_search: bool = True,
    use_thinking: bool = True,
    images: list[str] = None,
    fallback_model: str = None,
) -> str:
    # Renders own the whole 16GB card (Phase-4 rule, built 2026-07-31; widened
    # to IMAGE renders 2026-09-04): a local generation here would fire the
    # unload chain -- and on the Bonsai path comfy_image.stop_server() -- and
    # kill ComfyUI MID-RENDER. Measured the night Qwen went live: a 9-minute
    # image render died at step 7/8 because an idle loop's Bonsai call ran
    # through here while only VIDEO renders raised the flag. Claude (cloud)
    # needs no GPU, so it passes. Agents answer plainly instead of dying.
    if backend != "claude" and comfy_image.render_in_progress():
        return (
            "[A render is using the GPU right now -- I'm briefly offline "
            "while it finishes (a few minutes for an image, longer for video). "
            "It will land in Pending Review; ask me again after.]"
        )
    # model=None means "use this backend's configured default" (CLAUDE_MODEL
    # / OLLAMA_MODEL) -- see memory.py's get_active_generation() for how the
    # office's global model dropdown resolves which (backend, model) pair
    # every agent actually generates through. extra_tools is currently only
    # ever non-None for Sophie's file tools and the CIO's meeting tool (see
    # main.py's chat handler); office_name scopes the always-on read_skill
    # tool to the right agent's own skills. call_claude doesn't support
    # tool-calling at all yet, so extra_tools/tool_call_log/office_name are
    # silently unused there. backend=="claude" is itself blocked upstream in
    # main.py when offline mode is on (see _resolve_generation_for), so
    # allow_web_search only actually needs to do anything on the ollama path.
    # Neither Claude-via-this-path nor Bonsai takes an images array, and no
    # amount of Bonsai's 27B parameters changes that -- vision is a separate
    # encoder fused at training time, not something scale produces. So they get
    # the same relay the blind Ollama models get, before dispatch.
    if images and backend in ("claude", "bonsai"):
        messages = await _relay_images_as_text([dict(m) for m in messages], images)

    if backend == "claude":
        return await call_claude(system_prompt, messages, model=model)
    elif backend == "ollama":
        return await call_ollama(system_prompt, messages, model=model, use_tools=use_tools, extra_tools=extra_tools, tool_call_log=tool_call_log, office_name=office_name, allow_web_search=allow_web_search, use_thinking=use_thinking, images=images)
    elif backend == "bonsai":
        return await call_bonsai_with_fallback(
            system_prompt, messages, use_tools=use_tools, extra_tools=extra_tools,
            tool_call_log=tool_call_log, office_name=office_name,
            allow_web_search=allow_web_search, use_thinking=use_thinking,
            fallback_model=fallback_model,
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")


# Owner's explicit ask (2026-07-30): "i need something telling me that it
# fell back." The fallback used to be visible only in traces; this
# ContextVar carries the fact up to main.py's /api/chat response so the
# dashboard can show it to the owner directly. ContextVar (not a module
# global) so concurrent requests can't read each other's flag.
# Barry's raw message for the current /api/chat request -- set in main.py.
# Read by the living-script approval gate above: tool mutations are only
# allowed when HIS words authorize them, never on the model's say-so.
current_user_message: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_message", default="")

_bonsai_fell_back: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bonsai_fell_back", default=False
)


def bonsai_fell_back() -> bool:
    """True if the most recent generate() in THIS request's context routed
    to Bonsai but was actually answered by the Ollama fallback."""
    return _bonsai_fell_back.get()


def build_bonsai_tools(extra_tools: list | None, allow_web_search: bool,
                       use_tools: bool = True) -> list[dict]:
    """THE ONE tool roster a Bonsai turn sends -- shared with the prewarm
    paths (2026-09-08). llama-server renders the tool schemas into the
    prompt PREFIX, so a prewarm that omits them builds a cache no real
    chat can hit: measured, Sophie's boot prewarm read 25,999 tokens and
    her next message still re-read all 38,096 -- the 12K difference was
    her 30 tool schemas. Same roster the Ollama path builds, including
    offline mode genuinely removing web search from what the model sees."""
    if not use_tools:
        return []
    return ([WEB_SEARCH_TOOL] if allow_web_search else []) + \
        [READ_SKILL_TOOL, INSPECT_BRAIN_TOOL, LOOK_AT_MY_PICTURES_TOOL, TALK_WITH_TOOL] + (extra_tools or [])


_FALLBACK_WRITE_TOOLS = {
    "send_file_to_barry", "send_file_to_owner", "export_script_to_file",
    "save_note", "remember_lesson", "update_business_brain",
    "delegate_to", "chase_brief", "talk_with",
    "propose_code_fix", "write_project_file", "undo_code_fix", "submit_agent_fix",
    "run_command", "restart_backend", "check_updates", "run_security_scan",
    "accept_host_changes", "update_agent_scene", "change_my_picture", "make_art",
    "save_script_block", "delete_script_block", "onboard_agent_to_team", "install_skill",
}
_FALLBACK_NOTE = (
    "\n\n## BACKUP MODEL\nThe main model failed on this message, so a smaller backup "
    "model is answering. You can read and answer. You cannot save, send, file, "
    "delegate, run or change anything this turn -- if the answer needs that, say so "
    "plainly and ask Barry to send the message again."
)


async def call_bonsai_with_fallback(
    system_prompt: str,
    messages: list[dict],
    use_tools: bool = True,
    extra_tools: list[dict] = None,
    tool_call_log: list = None,
    office_name: str = None,
    allow_web_search: bool = True,
    use_thinking: bool = True,
    fallback_model: str = None,
) -> str:
    """Bonsai turn with the graceful-failure contract the office runs on:
    if llama-server can't start or the call fails, agents fall back to the
    Ollama default rather than hanging or erroring the chat. fallback_model
    (2026-08-16) lets a seat with its own pinned Ollama model land on THAT
    model instead of the office default -- found live: Sophie's Bonsai
    failure fell back to the 9b, skipping the coder model her seat was
    measured onto. The failure is
    never silent -- it's recorded in tracing (where Sophie's
    investigate_traces can see it) with the real error text. use_thinking
    reaches bonsai_llm.call_bonsai since 2026-09-17 (False = the chat
    template's enable_thinking is switched off for that request -- home and
    group-chat turns); before that it was accepted here and silently unused."""
    start = time.monotonic()
    _bonsai_fell_back.set(False)
    log = tool_call_log if tool_call_log is not None else []
    # Same tool roster the Ollama path builds, including offline mode
    # genuinely removing web search from what the model can see.
    tools_list = build_bonsai_tools(extra_tools, allow_web_search, use_tools)
    try:
        # Only-one-thing-on-the-GPU, in this direction: clear every
        # resident Ollama model and any cached AmuseBridge pipeline before
        # Bonsai's ~8GB server takes (or keeps) the card.
        async with httpx.AsyncClient(timeout=10.0) as client:
            await _unload_models(client, keep_model=None)
        # stop_server, not unload: ComfyUI's process keeps ~2.6GB of GPU
        # arena after /free (measured 2026-08-28), and Bonsai is the one
        # load tight enough that the residue forces a shared-memory spill.
        await comfy_image.stop_server()
        if bonsai_llm.is_tripped():
            raise bonsai_llm.BreakerOpen(
                "Bonsai breaker is open (a real fault in the last 10 minutes) -- see data/bonsai_events.log"
            )
        if not await bonsai_llm.ensure_running():
            raise RuntimeError(
                "Bonsai unavailable (circuit tripped or server did not come up -- see data/bonsai_server.log)"
            )
        result = await bonsai_llm.call_bonsai(
            system_prompt, messages,
            dispatch_tool_call=_dispatch_tool_call,
            tools_list=tools_list,
            tool_call_log=log,
            office_name=office_name,
            use_thinking=use_thinking,
        )
        bonsai_llm.record_success()
        tracing.record_turn(
            office_name=office_name,
            model=BONSAI_MODEL_NAME,
            tool_calls=log,
            final_content=result,
            duration_ms=(time.monotonic() - start) * 1000,
            error=None,
            prompt_chars=len(current_user_message.get() or ""),
        )
        return result
    except Exception as e:
        # Count toward the circuit breaker so a broken Bonsai stops costing
        # a ~20s server-start on every message (see bonsai_llm.is_tripped).
        # EXCEPT a 4xx (2026-09-11): "request (50842 tokens) exceeds the
        # available context size (49152)" is THIS request's fault -- Elliot's
        # seat over the window -- and the server is perfectly healthy. Two of
        # his 400s tripped the breaker and sent Priya's sourcing brief to the
        # 9b five minutes later, where it fabricated four suppliers. One
        # seat's oversize prompt must never take Bonsai away from the office.
        # The request still falls back; the breaker just does not count it.
        _is_client_err = isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500
        # Same reasoning for an empty reply (2026-09-19): the server answered
        # fine, one seat just reasoned past its own reply ceiling. It falls
        # back like any failure; it does not cost the office ten minutes of
        # Bonsai. See bonsai_llm.EmptyReply.
        _is_empty_reply = isinstance(e, bonsai_llm.EmptyReply)
        # A refusal because the breaker is already open is not a new fault
        # (2026-09-28) -- see bonsai_llm.BreakerOpen.
        _is_breaker_open = isinstance(e, bonsai_llm.BreakerOpen)
        # A TIMEOUT ON A HEALTHY SERVER is this request's fault (2026-09-28):
        # Priya's 47-search barcode brief grew until one completion passed the
        # 300s read limit, twice, and that tripped the breaker for all ten
        # seats. Ask the server before blaming it -- /health answers while a
        # slot is busy. Only an unreachable server counts.
        _is_slow_request = False
        if isinstance(e, httpx.TimeoutException):
            try:
                _is_slow_request = await bonsai_llm.is_available()
            except Exception:  # noqa: BLE001 -- unknown = count it, the safe side
                _is_slow_request = False
        if _is_client_err or _is_empty_reply or _is_breaker_open or _is_slow_request:
            _why = ("HTTP %s" % e.response.status_code if _is_client_err else
                    "empty reply" if _is_empty_reply else
                    "breaker already open" if _is_breaker_open else
                    "timeout on a healthy server")
            print(f"[bonsai] {_why} for {office_name} -- not counted toward the breaker")
            if _is_slow_request:
                bonsai_llm.event(f"SLOW REQUEST {office_name}: {type(e).__name__} on a healthy server "
                                 f"-- fell back, NOT counted toward the breaker")
        else:
            bonsai_llm.record_failure(f"{office_name}: {type(e).__name__}: {str(e)[:160]}")
        # Real error text into tracing, then the promised fallback -- the
        # reply still comes from a real local model, just not Bonsai.
        tracing.record_turn(
            office_name=office_name,
            model=BONSAI_MODEL_NAME,
            tool_calls=log,
            final_content="",
            duration_ms=(time.monotonic() - start) * 1000,
            # 2026-09-14: the server's own reason rides in the trace. A bare
            # "400 Bad Request" left Sophie guessing at "API mismatch"; the
            # body says "request (61233 tokens) exceeds the available context
            # size (49152)", which is the whole diagnosis.
            error=(f"Bonsai failed, falling back to {fallback_model or OLLAMA_MODEL}: {e}"
                   + (f" -- server said: {e.response.text[:300]}" if _is_client_err
                      and getattr(e, 'response', None) is not None else "")),
        )
        _bonsai_fell_back.set(True)
        # 2026-09-22: THE FALLBACK READS, IT DOES NOT WRITE. On 09-21 Bonsai 2
        # kept failing on Sophie's big prompts and qwen2.5-coder answered in
        # her place with her full roster -- 24 placeholder files on Barry's
        # desk ("<Your markdown content here>"), 8 junk notes, a
        # "<insert lesson>" in her always-on ledger, and 5 nonsense briefs to
        # Victor and Elliot. A backup model may answer; it may not leave
        # anything behind. Every tool that saves, sends, files, changes or
        # runs is stripped here, and the model is told why.
        _fb_tools = [t for t in (extra_tools or [])
                     if (t.get("function") or {}).get("name") not in _FALLBACK_WRITE_TOOLS]
        _stripped = len(extra_tools or []) - len(_fb_tools)
        if _stripped:
            print(f"[bonsai] fallback for {office_name}: {_stripped} write tool(s) stripped")
        return await call_ollama(
            system_prompt + _FALLBACK_NOTE, messages, model=fallback_model or OLLAMA_MODEL,
            use_tools=use_tools, extra_tools=_fb_tools, tool_call_log=tool_call_log,
            office_name=office_name, allow_web_search=allow_web_search,
            use_thinking=use_thinking,
        )


async def list_ollama_models() -> list[str]:
    """Whatever's actually pulled locally right now (via `ollama pull`) --
    used to populate the office's model dropdown with real options instead
    of a hardcoded guess. Empty list (not an error) if Ollama isn't
    reachable, since this is just for populating a UI list."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
    except httpx.HTTPError:
        return []
