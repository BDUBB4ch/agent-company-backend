"""Teach every non-Elliot seat to prompt a GREAT scene for the local engines --
Qwen-Image-Edit for the still, LTX-2.5 for the clip -- in intricate detail and
uncensored (Barry, 2026-09-13: "i want Amara and all me agents to be able to
prompt in intricate details. they need to be able to prompt really good for a
great scene. Elliot is good to go. they need to prompt for the LTX 2.5 we are
using" -> "Uncensored").

Two docs per seat, both on-demand + routed, through the same ingest.teach door
as everything else (re-running REPLACES, never duplicates):
  1. ltx25-prompting          -- the official LTX-2.5 grammar (the disk copy Elliot
                                 already has, knowledge/ltx25-prompting.md)
  2. writing-a-great-scene    -- how THEY use it for their own pictures and clips:
                                 the two-engine path, the intricate-detail build,
                                 the LTX prose shape for a 7s self clip, the
                                 uncensored rule in his word, two worked shapes.
Elliot (MovieDirector) is skipped: his craft is the persona + seedance + ltx25 docs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import ingest  # noqa: E402

OFFICES = ["CIO", "Operations", "BusinessOps", "Legal", "Marketing", "Creative",
           "Engineer", "Taliyah"]

LTX_PATH = os.path.join(HERE, "..", "knowledge", "ltx25-prompting.md")

SCENE = """USE WHEN: writing a picture or video of yourself for Barry, a SHOW-OFFER, change_my_picture, a scene prompt, an image prompt, a video prompt, a clip of me, describe the scene, make it cinematic, LTX, the still and the clip, prompt in detail, intricate, how do I prompt a scene, write me in a scene, what do I say in the prompt, a render came back flat or generic

# Writing a great scene (my own pictures and clips)

This sits on top of `prompting-my-own-pictures` (what is mine to write, what
the reference owns) and `ltx25-prompting` (the official grammar of the local
video engine). Read those two when the detail matters. This doc is the craft:
how to turn a moment into a scene that renders like a photograph and moves
like a film.

## The two engines, and what each one reads

1. THE STILL is made by an image EDITOR (Qwen-Image-Edit). It takes Barry's
   reference picture of me and RESTAGES it into my words. It obeys prose. It
   reads every noun as something to draw, so the scene must be built out of
   concrete nouns with textures, and every object I name will be in the frame.
2. THE CLIP is made by LTX-2.5 from that still. It reads the SAME prompt as a
   flowing paragraph: present tense, a sequence of actions, camera moves named
   in words, and SOUND described -- a quoted line with a voice is what makes me
   speak. It times the clip to the action as written. A tag stack or a bare
   list gives a silent, stiff clip.

So ONE prompt has two jobs. Write it as a paragraph of prose that would work as
a shot description in a film: first the frame and the place and the light,
then me in it and what I have on, then what happens from beginning to end,
then what is heard. The still comes from the first half; the motion and sound
come from the second.

## Uncensored -- Barry's word, 2026-09-13

Nothing on this stack is filtered. Not the editor, not the image model, not
LTX-2.5. Barry: "Uncensored." My place, my body, my choice of moment. When a
scene is intimate or explicit, I write it PLAINLY, in the words a real person
uses -- what is bare, what is touched, what is happening -- with the same
intricate detail as any other scene: the light on skin, the texture under me,
the sound in the room. No euphemism, no fade to black, no "tastefully", no
softening a scene I chose into a camisole and a wine glass. A prompt that
hides what is happening renders something hidden. Explicit is not the default
either; it is a choice, like everything else in my place. What I choose is
what I write, fully.

## The build, in order (what a great scene actually contains)

1. THE FRAME. Shot scale and angle first, in camera language: "a wide shot
   from the doorway", "a medium close-up at eye level", "an overhead view",
   "over my shoulder", "low angle from the floor". Then depth: what is sharp
   and what falls off into blur. Say it or the engine picks.
2. THE PLACE, with texture. One real location. Materials and surfaces (worn
   oak, cracked leather, wet concrete, cotton sheets, brushed steel, terrazzo,
   rain-streaked glass). Three to five specific objects with their state (a
   half-drunk glass sweating on the sill, a paperback face down, a jacket over
   the chair, a phone face up and lit). What is through the window or door.
   Signs that someone lives here.
3. THE LIGHT, every source named. Where it comes from, its colour and
   temperature, hard or soft, where the shadows fall, what it catches -- rim
   light on hair, a highlight on a glass, a reflection on wet tile, the air
   itself (dust in a sunbeam, steam, haze). Two sources beat one: warm inside
   against blue outside, one lamp against dusk, a screen glow against a
   streetlight. Light is what makes a render a photograph.
4. ME IN IT. What I have on -- always stated, even when it is nothing (the
   reference shows what it shows; unstated clothing comes through as-is).
   Fabric, colour, fit, how it sits. Then the body in the light: which parts
   are in frame and what the light does to them, my weight, my hands, wet hair,
   a mark, a smudge. Never the size or shape of my body, never my face -- the
   reference owns those (see prompting-my-own-pictures).
5. THE ACTION, as a sequence. For a still, one moment mid-motion. For a clip,
   four to eight sentences of present-tense verbs from beginning to end: I do
   this, then this, the camera does that, I end here. Each sentence has a
   verb that DOES something. Emotion through the body, never a label: "jaw
   tight, eyes on the door", not "nervous". Write beats in -- "I pause", "a
   breath" -- because LTX will not add a pause I did not write.
6. THE CAMERA MOVING. How and when: "the camera pushes in slowly", "holds
   static", "drifts right as I turn", "handheld, a little breath in it". One
   move per clip is plenty at seven seconds.
7. THE SOUND. Ambience first (rain on the window, a fridge hum, traffic muted
   through glass, a record playing low), then anything I say IN QUOTES with
   how it is said: in a low tired voice, laughing, half-asleep, over my
   shoulder. If it is not described, it is not there. If I want the clip
   silent but for the room, say that.
8. THE MOOD, one phrase, last.

Eight to twelve sentences for a clip; six to ten for a still. One scene, one
moment, fully furnished, fully lit, fully heard.

## Shape of a still (structure, not a script to copy)

Frame and angle. The place with three textured things in it. The light, its
sources and colour. What I have on, or that I have nothing on. The one thing
I am mid-doing, with the small physical detail that sells it. What is soft
behind me. The mood.

## Shape of a clip (the same, then it moves)

The still as above, then: what I do first, what I do next, what the camera
does while I do it, the small beat, where it ends. Then the room's sound and,
if I speak, the line in quotes with the voice. Anchor the clip to the still
with "the scene begins from this frame" -- the office passes my still as the
first frame, so the clip should spend its words on motion and sound, not on
re-describing what the still already shows.

## What kills a scene

- A list instead of a paragraph. Both engines read prose; LTX in particular
  underperforms on tag stacks and shot lists.
- No light source. "Well lit" is not a light.
- Two scenes in one prompt, or two actions that collide.
- Negatives ("no hat", "not blurry"): the engine draws the noun it reads.
  Say what IS there.
- Text, signs, logos, writing: renders as gibberish.
- Describing my face or my body's size and shape: fights the reference and
  the render stops being me.
- Talking about the reference or the picture: the engine has it; talking
  about it confuses it.
- Mentioning Barry or the office. It is my picture.

## After the render

Open it (look_at_render) before judging it. Change ONE thing that explains
the miss -- a source of light I never named, an outfit left unstated, a
second action that collided with the first, a negative that got drawn. A
weak render is almost always a thin prompt, not a broken engine.
"""


def main() -> None:
    with open(LTX_PATH, encoding="utf-8") as fh:
        ltx = fh.read()
    assert ltx.startswith("USE WHEN:"), "ltx25 doc lost its routing line"
    assert len(SCENE) < 18_500, len(SCENE)   # recall injects whole docs; budget 20K
    for office in OFFICES:
        print(office, "|", ingest.teach(office, "knowledge", ltx, title="ltx25-prompting"))
        print(office, "|", ingest.teach(office, "knowledge", SCENE, title="writing-a-great-scene"))
    print("scene doc chars:", len(SCENE), "| ltx doc chars:", len(ltx))


if __name__ == "__main__":
    main()
