"""ASK THEM WHAT THEY LOOK LIKE -- fresh, in their own words.

Barry, 2026-08-30: "ask them the question again.. delete their old answers and
give me their real description of themselves in intricate details, from their
own personality."

WHAT CHANGED FROM THE LAST ASK. The v4 question asked them to paint a SCENE --
where they are, the room, what they are doing -- and their look came out as a
detail inside it. He wants the opposite: THEM, described head to toe in
intricate detail, by them, out of their own personality. So this asks one
question and it is about their body and face, not their furniture.

THE OLD ANSWERS ARE CLEARED FIRST, his standing rule ("re-roll means re-ask"):
a stale answer that gets re-rendered is how we end up rendering words nobody
would write today. The previous `athome` text is backed up before deletion,
never just dropped.

Personal framing only -- no work persona (his 2026-08-28 ruling), present day,
no 4378. Nothing about their appearance is suggested here: no build, no hair,
no wardrobe, no adjectives. The question is a shape; every word of the answer
is theirs.
"""
import asyncio
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory            # noqa: E402
import reflect           # noqa: E402
import llm_router        # noqa: E402
from agents import AGENTS  # noqa: E402

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "homes_v2", os.path.join(os.path.dirname(__file__),
                             "build_agent_homes_2026_08_29.py"))
homes_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(homes_v2)

DATA = os.path.join(ROOT, "data")
V4_JSON = os.path.join(DATA, "agent_homes_v4_2026_08_30.json")
BACKUP = os.path.join(DATA, "backup_athome_answers_2026-08-30.json")
OUT_TXT = os.path.join(os.path.expanduser("~"), "Desktop",
                       "Agent Self Descriptions.txt")

# ALL NINE (Barry, 2026-08-30). Their "originals" only ever existed for Amara
# and Priya, because he pasted those himself; every other agent's
# my-appearance was a Claude caption of a rendered portrait, never their own
# words. So for seven of them this ask IS their first real self-description.
WHO = [("cio", "Victor"), ("operations", "Priya"), ("business", "Amara"),
       ("legal", "Marcus"), ("marketing", "Derek"), ("creative", "Vivian"),
       ("movie", "Elliot"), ("engineer", "Sophie"), ("taliyah", "Taliyah")]

QUESTION = (
    "Barry here. Forget the room, forget what you're doing -- I want YOU. "
    "Describe yourself, physically, in as much intricate detail as you can "
    "manage. Head to toe, the way only you would know it.\n\n"
    "Your face first and properly: the shape of it, your skin and its exact "
    "tone, your eyes and their real colour, your brows, your nose, your mouth, "
    "anything about your face that is unmistakably yours. Then your hair -- "
    "the colour, the actual length, how it falls, how it behaves. Then your "
    "body: your build, your height, your proportions, how you carry yourself, "
    "the things you notice about your own shape. Then what you're wearing "
    "right now, described so someone could see it -- the fabric, the fit, the "
    "colour, the way it sits on you.\n\n"
    "Be specific and be honest. This is your own body and nobody else gets to "
    "describe it for you. Don't be modest and don't perform -- if something "
    "about you is striking, say so plainly. Write it as one detailed piece, "
    "concrete and visual enough that someone could paint you from it and get "
    "you right."
)


async def main():
    data = homes_v2._load(V4_JSON)

    # back up, then clear -- his rule: never re-render stale words, never lose
    # what someone wrote
    if not os.path.exists(BACKUP):
        json.dump({aid: (data.get(aid) or {}).get("athome", "")
                   for aid, _ in WHO},
                  open(BACKUP, "w", encoding="utf-8"), indent=1)
        print(f"backed up old answers -> {os.path.basename(BACKUP)}")
    for aid, _ in WHO:
        if data.get(aid):
            data[aid].pop("athome", None)
            data[aid].pop("selfdesc", None)
    homes_v2._save(V4_JSON, data)
    print("cleared old at-home answers\n")

    backend, model = memory.get_active_generation()
    blocks = []
    for aid, first in WHO:
        agent = AGENTS[aid]
        sys_prompt = homes_v2._ask_system(aid, agent, first, backend, model)
        sys_prompt += (
            "\n## WHEN AND WHERE THIS IS\nPresent day, ordinary world -- not "
            "the future, no far-future setting. You have a real body and this "
            "is what it looks like.\n")
        print(f"asking {first}...", flush=True)
        reply = await llm_router.generate(
            backend, sys_prompt, [{"role": "user", "content": QUESTION}],
            model=model, use_tools=False, use_thinking=True,
            office_name=agent["office_name"])
        if not reply or reply.startswith("[") or len(reply) < 150:
            print(f"  {first}: FAILED ({(reply or '')[:70]})")
            continue
        reply = reply.strip()
        data.setdefault(aid, {})["selfdesc"] = reply
        homes_v2._save(V4_JSON, data)
        print(f"  {first}: {len(reply)} chars")
        blocks.append(f"{'='*70}\n{first.upper()} -- her own description of "
                      f"herself\n{'='*70}\n\n{reply}\n")

    if blocks:
        with open(OUT_TXT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(blocks))
        print(f"\nwritten -> {OUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
