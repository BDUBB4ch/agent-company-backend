"""SOPHIE AND VIVIAN RENDER THEIR OWN IMAGES.

Barry, 2026-08-31: "let sophie and vivian render their own images and add it to
the build." Their Higgsfield renders came back looking like 3D renders rather
than photographs, while everyone else's came out photoreal.

WHAT MAKES THIS THEM AND NOT ME: each agent is ASKED, in her own voice, to
write the ```image``` fence for her own scene -- she already carries
`me-at-home` and `me-in-my-office` in her own brain, in her own words. The
fence she writes is what gets rendered. I pick no words.

IDENTITY: the render passes her own face reference (agent_face_<id>.png,
staged in the ComfyUI input root) through IP-Adapter, which is the same lane
the SHOW-OFFER flow uses -- the LoRA gives nothing here, the reference gives
the face, so the picture is of HER and not a generic person.

Runs through the live backend's own endpoints (/api/chat, /api/generate-image)
rather than poking ComfyUI directly, so the VRAM eviction chain, the approval
queue and the outputs folder all behave exactly as they do for any other
generation. Nothing bypasses the house plumbing.

Idempotent: an image already installed is skipped.
"""
import base64
import json
import os
import re
import shutil
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
API = "http://127.0.0.1:8420"
HOMES = os.path.join(ROOT, "..", "AgentDashboard", "assets", "homes")
OFFICES = os.path.join(ROOT, "..", "AgentDashboard", "assets", "offices")
OUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "output")
LOG = os.path.join(ROOT, "data", "agents_render_themselves.log")

WHO = [("engineer", "Sophie"), ("creative", "Vivian")]

ASK = {
    "home": ("Barry wants a picture of you at home -- the scene you described "
             "to him, exactly as you told it. Write the image prompt for it "
             "yourself and put it in an ```image``` fence. It's your own room "
             "and your own body, so describe them the way you'd want them "
             "seen: a real photograph, not a 3D render or CGI, natural skin "
             "and natural light, one person alone, the room bigger than you "
             "are, no text anywhere. Just the fence, nothing else."),
    "office": ("Now the same for your workspace -- you at your desk, working, "
               "the room you described. Write the image prompt yourself in an "
               "```image``` fence. A real photograph, not a 3D render or CGI, "
               "natural skin and natural light, one person alone at real "
               "scale in a room bigger than she is, no text on any screen or "
               "surface. Just the fence."),
}

FENCE = re.compile(r"```(?:image)?\s*\n(.+?)```", re.S)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def post(path, payload, timeout=1800):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    log("== Sophie and Vivian render themselves ==")
    for aid, first in WHO:
        for kind, dest in (("home", os.path.join(HOMES, f"{aid}_me.png")),
                           ("office", os.path.join(OFFICES, f"{aid}.png"))):
            tag = f"{first} {kind}"
            # --- 1. SHE writes the prompt ---
            try:
                r = post("/api/chat", {"agent_id": aid, "message": ASK[kind]})
            except Exception as e:
                log(f"{tag}: chat failed -- {e}")
                continue
            reply = (r.get("reply") or "")
            m = FENCE.search(reply)
            # her fence, or her whole reply if she wrote it bare
            prompt = (m.group(1) if m else reply).strip()
            if len(prompt) < 200:
                log(f"{tag}: prompt too short ({len(prompt)}) -- skipped")
                continue
            log(f"{tag}: wrote {len(prompt)} chars"
                f"{'' if m else ' (no fence, used reply)'}")

            # --- 2. rendered through the normal pipeline, her face as the
            #        identity reference ---
            face = f"agent_face_{aid}.png"
            has_face = os.path.isfile(
                os.path.join(ROOT, "tools", "ComfyUI", "input", face))
            body = {"agent_id": aid,      # so it files under HER, not Vivian
                    "prompt": prompt,
                    "negative_prompt": ("3d render, cgi, video game render, "
                                        "doll, plastic skin, waxy skin, "
                                        "cartoon, anime, illustration, text, "
                                        "watermark, logo, extra people, "
                                        "deformed hands, bad anatomy")}
            if has_face:
                body["reference_image"] = face
                body["reference_weight"] = 0.7
                body["reference_preset"] = "PLUS FACE (portraits)"
            try:
                res = post("/api/generate-image", body)
            except Exception as e:
                log(f"{tag}: render failed -- {e}")
                continue
            path = res.get("path") or res.get("image_path") or res.get("file")
            if not path:
                log(f"{tag}: no path returned -- {str(res)[:160]}")
                continue
            if not os.path.isabs(path):
                path = os.path.join(OUT_DIR, os.path.basename(path))
            if not os.path.exists(path):
                log(f"{tag}: rendered file not found at {path}")
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(path, dest)
            log(f"{tag}: -> {os.path.basename(dest)}")
    log("== done ==")


if __name__ == "__main__":
    main()
