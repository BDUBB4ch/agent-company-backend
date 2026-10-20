"""Teach Elliot how the Qwen-Image 2.1 character door works (2026-09-22).

Barry: "the images look great, so we need to teach Elliot the settings so he
can generate great videos as well with this accuracy of my characters."
On-demand, USE WHEN routed, private:MovieDirector, through ingest.teach (no
model in the path; re-running replaces the same title). Run from backend/.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import ingest  # noqa: E402

TITLE = "qwen21-character-stills-and-video"
DOC = """USE WHEN: rendering a still or a video clip of Bia, Yannah, Tazz, Keth, Vor'Shara or B Dubb locally -- character still, character render, character clip, start frame, generate video, generate image, restage, reference, Qwen 2.1, qwen21, how the character engine works, why a render came out wrong, weapon plate, location plate

# Character stills and video with Qwen-Image 2.1 (the local character engine since 2026-09-22)

## What happens when you write a fence with ONE character handle
1. The office finds Barry's reference picture of that character (`char_ref_<name>.png` -- his own whole-body frame, weapon holstered as canon says).
2. Your fence is rewritten for the engine: every mention of that character becomes "the character from image 1"; the character's FRONT-FACE close-up (`char_<name>_face.png`) rides as image 2 so the face is right whenever they look at the camera; a weapon handle with a staged plate and a named place with a staged plate (black site, the Talia bridge, the common area, the sanctum, the market, Araxys, the ship) take the next images. A preservation clause is added for you: keep the face, head shape, eyes, skin, build, height and proportions of image 1, drop image 1's background and framing, stage the character as YOU described.
3. Qwen-Image 2.1 renders it from the reference: 25 steps, guidance-free, about 20 seconds of sampling once the models are warm (a cold start adds ~2 minutes to load the two models). The output takes the reference's aspect unless the ask is wider.
4. It lands in Barry's queue as an approval. Measured on his card the day it went in: Vor'Shara kept all four eyes in two pairs, her tendrils, chain and gown; Keth kept the cranium, stone skin, torn-collar jumpsuit and bare feet.

## What happens when Barry hits Generate Video after that
The video door takes your LAST image fence. If a still of that character was just made from the SAME fence text, that still becomes the LTX-2.5 start frame (no second render). If not, it renders the still first through the door above, then the clip. LTX then animates from that frame, so the identity in the clip is the identity in the still.

## How to write the still so the clip is good
- ONE to THREE characters per fence. One character gets every angle Barry supplied. Two or three go through the GROUP door: each person gets their own labelled pictures (Character A, B, C) and the engine is told never to mix their features -- fewer pictures per person, so singles are still the most accurate. Four or more leave this door (older SDXL path) and identity suffers: shoot the scene as a wide on Higgsfield plus singles and two-shots here.
- COVERAGE for a big scene: one wide establishing shot with no dialogue, then singles for every line and reaction, and two-shots where two people interact directly. Group lip-sync in video is unreliable -- keep spoken lines in singles.
- Describe the SCENE, the ACTION as a held position, the LIGHT and the CAMERA. Do not re-describe the face, skin, eyes or build -- the reference carries them and re-describing fights it. Wardrobe you may state (it is canon), a weapon by its handle, a place by its name so its plate rides along.
- A start frame must already be AT the pose the clip begins from. If the character will face the camera in the clip, have them facing it in the still: LTX only knows the face the start frame shows, and a head turn from profile makes it invent the front. A still whose pose cannot get to the action produces a frozen clip.
- State the framing you want ("full figure", "waist up", "close on the face"). The engine defaults to the reference's framing.
- Wet, worn, cluttered, lit: name materials and the junk in the room. The engine renders what it is told and invents little.

## How to write the video prompt (the fence text is ALSO what LTX reads)
LTX speaks its prompt: chronological prose, present tense, one continuous action with an end state, the camera doing something (slow push, drift, handheld follow -- never "static", never "the frame holds"), a quoted line with its voice if anyone speaks ("she says in a low, tired voice, \\"...\\""). Character handles are turned into "the character" for LTX automatically, so write them normally. About 5 seconds of clip is 16-25 minutes of rendering.

## Settings that exist (Barry's, not yours to change -- but know them)
- `character_engine` (live setting): `qwen21` is the default; `qwen-edit` puts the door back on the older editor. If a character render ever looks wrong, say which engine stamped the approval (`qwen21-restage` vs `qwen-edit-restage`).
- A ```model``` fence of `qwen21` forces 2.1 for a plain (no-character) still; `qwen21-detail` adds the detailer LoRA at 0.8. Qwen-Image 2.1 is NON-COMMERCIAL: film and personal work only, never a B Dubb Grows or Gotcho Back image.

## When it goes wrong
- Eyes read the wrong colour or ears too pointed: that is the reference frame's own look at that angle. Ask Barry for a better reference frame; do not pile adjectives into the prompt.
- A clip that does not move: the still's camera line or a "holding" pose. Rewrite the beat with an action and a moving camera.
- A weapon rendered generic: name it by handle so its plate rides as image 2.
"""


def main() -> None:
    fid = ingest.teach("MovieDirector", "knowledge", DOC, title=TITLE)
    print("taught:", fid)


if __name__ == "__main__":
    main()
