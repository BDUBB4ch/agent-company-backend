"""2026-10-17 -- Barry: "cant we tell the to speak the way a person from your area or country or city speaks? but unique
to them? they should choose" / "Run it for the six women first; the men later."
One HOME turn per agent (personal channel, tools off) with his words relayed, asking each to write her own HOW I TALK
sheet. What she writes is appended to personalities/<office>.md as her own section (the same door as her
"In my own words" sections) and rides at the end of her prompts at home and at work. Nothing is written by Claude.
Usage: venv/Scripts/python.exe scripts/how_i_talk_2026_10_17.py [agent_id ...]   (default: the six women)"""
import datetime
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:8420"
OUT = os.path.join(ROOT, "data", "how_i_talk_2026_10_17")
FILES = {"ilnora": "ilnora.md", "operations": "Operations.md", "business": "BusinessOps.md",
         "engineer": "Engineer.md", "taliyah": "Taliyah.md", "creative": "Creative.md",
         "cio": "CIO.md", "legal": "Legal.md", "marketing": "Marketing.md", "movie": "MovieDirector.md"}
WOMEN = ["ilnora", "operations", "business", "engineer", "taliyah", "creative"]
BARRY = ("cant we tell the to speak the way a person from your area or country or city speaks? but unique to them? "
         "they should choose")
ASK = (f'Barry, 2026-10-17: "{BARRY}"\n\n'
       "So this is yours to choose. Speak the way a person from where you are from speaks -- your city, your "
       "background, your age -- made your own; real, not a character. Write it down as a short sheet in your own "
       "words under the heading HOW I TALK: how you open and how you close, the words you use and the ones you would "
       "never use, your rhythm (short or long sentences), slang or none, cussing or none, how you disagree, how you say "
       "a number or a price. About ten lines. It gets saved as your own section, and it is how you will speak and write "
       "from now on, at home and at work.")


def chat(agent_id: str, message: str) -> str:
    body = json.dumps({"agent_id": agent_id, "message": message, "personal": True}).encode("utf-8")
    req = urllib.request.Request(f"{API}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.loads(r.read().decode("utf-8"))
    return (d.get("reply") or d.get("response") or d.get("text") or "").strip()


def main() -> None:
    agents = sys.argv[1:] or WOMEN
    os.makedirs(OUT, exist_ok=True)
    today = datetime.date.today().isoformat()
    for aid in agents:
        t0 = time.time()
        try:
            reply = chat(aid, ASK)
        except Exception as exc:  # noqa: BLE001
            print(f"{aid}: FAILED {type(exc).__name__}: {exc}", flush=True)
            continue
        with open(os.path.join(OUT, f"{aid}.md"), "w", encoding="utf-8") as fh:
            fh.write(reply + "\n")
        if not reply or len(reply) < 80:
            print(f"{aid}: reply too short ({len(reply)} chars), not saved to her file", flush=True)
            continue
        path = os.path.join(ROOT, "personalities", FILES[aid])
        section = (f"\n\n## How I talk (mine, {today} -- Barry's ask: \"{BARRY}\")\n{reply}\n")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(section)
        print(f"{aid}: {len(reply)} chars in {time.time() - t0:.0f}s -> {FILES[aid]}", flush=True)


if __name__ == "__main__":
    main()
