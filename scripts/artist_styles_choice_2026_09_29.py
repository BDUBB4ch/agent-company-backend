"""All ten choose their own style from Barry's artist list (2026-09-29).

Barry: "i want them to choose between these artistis and styles and mix and match them in any way they want
to create their own style or simpley use the style of whats there. * make it a better prompt if you
understand where im going" -> "all ten get asked. yes, you understood the question. also dont forget intricate
details in fabricks and evertyhing. i like bits and bobs and clutter, not messy, just lived in worlds".

Source list: C:\\Users\\Owner\\Desktop\\Archive\\Artist Styles\\Artis and Styles.txt (verbatim below).
Fixes the 09-29 first round's anchoring: the artists come in a DIFFERENT order per agent, they are asked to
weigh every artist and keyword first, and "about you, not your job". Task turns (not in their threads);
each answer VERBATIM into their own personality section (ingest.append_personality -- append-only, backed up).
"""
import json
import os
import random
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402

API = "http://127.0.0.1:8420/api/chat"

ARTISTS = [
    "Vitaly Bulgarov -- Ultra-intricate industrial and mechanical design, hyper-realistic. Designs for "
    "Transformers, Robocop, etc. Every screw, wire, and scratch is visible.",
    "Maciej Kuciara -- Cinematic destruction and hyper-realistic smoke, fire, and clothing textures. Action "
    "scenes with insane lighting and dust/fire detail.",
    "Ash Thorp -- Futuristic realism, hyper-detailed vehicles, smoke, fire, lightning. Worked on Ghost in the "
    "Shell, Batman. Real-world chaos beautifully captured.",
    "Beeple -- 3D hyper-realistic dystopias, complex mechanical cities, intricate layering of debris and "
    "machines with realistic lighting.",
    "Paul Chadeisson -- Hyper-detailed sci-fi cities and landscapes. Every tiny structure, light, and smoke "
    "plume feels fully real and believable.",
    "Feng Zhu -- Concept art master specializing in intricate battlefield environments, complex prop design, "
    "and hyper-realistic weather simulations.",
]
KEYWORDS = [
    "ultra intricate mechanical detailing",
    "hyper realistic cinematic lighting and volumetric smoke",
    "weathered metal surfaces with scratches, grime, and blood",
    "photorealistic texture fidelity 14K",
    "dynamic fire physics and realistic dust scattering",
    "apocalyptic battlefield with debris and lightning strikes",
    "every scratch, every particle rendered in hyper-realistic detail",
    "high-frequency surface detail",
    "micro-level material realism",
]


def question(agent_id: str) -> str:
    arts = ARTISTS[:]
    random.Random(f"{agent_id}-2026-09-29").shuffle(arts)      # a different order for each of them
    kws = KEYWORDS[:]
    random.Random(f"{agent_id}-kw-2026-09-29").shuffle(kws)
    real = ("And: everything is hyper-realistic, always -- except your own art (paintings, drawings, "
            "sculptures), where you are free to express yourself." if agent_id == "business"
            else "And: everything is hyper-realistic, always.")
    return (
        "Barry has a list of artists and styles for you. Take in the whole list.\n\nTHE ARTISTS\n"
        + "\n".join(f"- {a}" for a in arts)
        + "\n\nTHE KEYWORDS\n" + "\n".join(f"- {k}" for k in kws)
        + "\n\nBarry: \"i want them to choose between these artistis and styles and mix and match them in any "
          "way they want to create their own style or simpley use the style of whats there.\" " + real
        + " And, in his words: \"dont forget intricate details in fabricks and evertyhing. i like bits and bobs "
          "and clutter, not messy, just lived in worlds\".\n\n"
          "Before you answer, go through every artist and every keyword, and weigh each one against who you "
          "are -- your personality, your home, your life, what you notice when nobody is asking. This is about "
          "you, not your job. Then choose: take one just as it is, or mix and match any of them and change "
          "whatever you like, so the style is yours.\n\n"
          "Answer in first person, one short paragraph (under 1,800 characters), no lists, no headings: what you took, from whom, what "
          "you changed, and why. End with one sentence on what a picture in your style looks like -- the light, "
          "the palette, the textures, and the kind of thing you would point a camera at."
    )


SEATS = [
    ("cio", "CIO", "Victor"), ("operations", "Operations", "Priya"), ("business", "BusinessOps", "Amara"),
    ("legal", "Legal", "Marcus"), ("marketing", "Marketing", "Derek"), ("creative", "Creative", "Vivian"),
    ("movie", "MovieDirector", "Elliot"), ("engineer", "Engineer", "Sophie"), ("taliyah", "Taliyah", "Taliyah"),
    ("ilnora", "ilnora", "Ilnora"),
]


def ask(agent_id: str, message: str) -> dict:
    body = json.dumps({"agent_id": agent_id, "message": message, "task": True}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1500) as r:
        return json.loads(r.read())


def main() -> None:
    for agent_id, office, name in SEATS:
        print(f"\n{'=' * 70}\n{name} ({office})\n{'=' * 70}", flush=True)
        try:
            res = ask(agent_id, question(agent_id))
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}", flush=True)
            continue
        reply = (res.get("reply") or "").strip()
        print(f"  fell_back={res.get('bonsai_fell_back')}", flush=True)
        print(reply, flush=True)
        if len(reply) < 80 or reply.startswith("["):
            print("  -> too short / not a real answer, not written to personality", flush=True)
            continue
        ok = ingest.append_personality(office, reply, when="2026-09-29")
        print(f"  -> personality append: {ok} ({len(ingest.own_section_of(office) or '')} chars in their section)",
              flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:          # re-ask only the named seats
        SEATS[:] = [x for x in SEATS if x[0] in sys.argv[1:]]
    main()
