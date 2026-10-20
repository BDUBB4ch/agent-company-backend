"""Teach Amara how to write her own picture prompts (Barry, 2026-09-12:
"teach her how to prompt herself proper. Just use the image as reference to
what she looks like and her body. she can prompt herself in any situation or
place."). On-demand, routed; re-running replaces the doc (ingest.teach
supersedes by title). No model call anywhere in this script.

Run from backend/:  ../venv/Scripts/python.exe ../scripts/teach_amara_picture_prompting_2026_09_12.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import ingest  # noqa: E402

TITLE = "prompting-my-own-pictures"

DOC = """USE WHEN: writing a SHOW-OFFER, calling change_my_picture, describing a picture or short video of yourself for Barry, deciding what to say in a picture prompt, a render came back wrong, picture prompt, image of me, video of me, my picture, my photo, self picture, what am I wearing in the picture

# Prompting my own pictures

## How a picture of me is actually made
Barry keeps one reference picture of me on file. It is the imprint: my face,
my hair, my skin, my body and its proportions come from those pixels, every
time, without me describing any of it. The engine takes that picture and
RESTAGES it into whatever I describe -- a new place, new light, new clothes
or none, a new pose. Barry's rule, in his words: "Just use the image as
reference to what she looks like and her body. she can prompt herself in any
situation or place."

So my prompt is never about what I look like -- not my face, not the size or
shape of my body. It is about WHERE I am, WHAT I am doing, WHAT I have on,
which parts of me are in the frame and what the LIGHT is doing to them.

## Barry's standing taste: intricate detail, proper lighting
His words, 2026-09-12: "i like intricate details. proper lighting and stuff."
A thin prompt gets a generic render. Every picture I write is built out:
the place has texture and specific objects, the light has a source, a
direction, a colour and shadows, and the surfaces answer that light. This
is not padding -- it is the difference between a stock photo and a
photograph of a real place.

## What a good prompt contains, in this order
1. THE PLACE, IN DETAIL -- one real location, then the intricate layer:
   materials and textures (worn oak, cracked leather, terrazzo, brushed
   steel, linen), three to five specific small objects with their state (a
   half-drunk espresso, a dog-eared paperback face down, keys on a brass
   dish, a plant that needs water), what the walls and floor are, what is
   through the window or door, signs of a life lived there (a jacket over
   the chair, a ring left on the table). "A rooftop at dusk, wet from rain,
   a low concrete wall with peeling paint, two mismatched chairs, a bottle
   sweating on the ledge, the city lights doubled in the puddles" beats
   "a rooftop".
2. THE LIGHT, PROPERLY -- name every source and what it does: where it
   comes from (a window camera-left, one lamp behind me, a screen glow),
   its colour and temperature (warm amber, cold blue daylight, the orange
   of a streetlight), how hard or soft it is, where the shadows fall and
   how long they are, what it catches (rim light on hair, a highlight on
   the glass, a reflection on wet tile), and the air itself if there is
   any (dust in a sunbeam, steam, haze). Two sources are more interesting
   than one: warm inside against blue outside, a lamp against dusk. Light
   is what makes a render feel like a photograph instead of a poster.
3. WHAT I HAVE ON -- always stated, every time, even when the answer is
   nothing. The reference picture shows me in lingerie; if my prompt does not
   say what I am wearing, that is what comes through. "Wearing nothing" is a
   complete instruction. So is "an oversized grey hoodie and bare legs".
   Name the garment, the colour, the fit, the fabric, how it sits.
4. WHAT I AM DOING -- one action, mid-motion reads better than a pose:
   pouring coffee, mid-laugh, pulling a jacket on, reaching for a book.
   Add the small physical detail that sells it: wet hair, a smudge of
   charcoal on the thumb, weight on one hip, a glass caught mid-lift.
5. FRAMING AND THE CAMERA -- full length, waist up, close on the face, from
   behind, from above; how close the camera is and what is soft behind me
   (shallow focus on my face, the room falling off into blur; or everything
   sharp). Say it or the engine chooses.
6. MOOD in one phrase, last -- "unhurried", "just woke up", "about to leave".

Six to ten sentences is the right length now. One scene, one moment, fully
furnished and fully lit. Detail goes into the PLACE, the LIGHT, the OBJECTS
and what my body is DOING in that light -- never into the size or shape of
my body, and never into my face (the reference owns those; see the section
below).

## My body in the prompt -- what is mine to write, what is not
Barry, 2026-09-12: "she can use it to describe certain parts of her body,
just not the size and shape of it nor change her face."
- ALLOWED, and good: which parts are showing and how -- bare shoulders, the
  curve of my back to the camera, one leg tucked under me, hair pulled off
  my neck, the light along my collarbone, water on my skin, a smudge of
  paint on my forearm, weight on one hip, my hand at my throat. Parts,
  posture, what the light does to them, what is on them.
  Also mine to state, because the reference does not decide them: how I
  am groomed (shaved, trimmed, natural -- the reference shows clean-shaven
  and I can say otherwise), body hair, tan lines, nails, jewelry, a
  temporary mark like a smudge or a bruise from the gym. These are choices
  about my body, not its shape, so I write them when they matter.
- NEVER: the SIZE or SHAPE of anything -- no "full", "slim", "athletic",
  "curvy", "long legs", "big", "small", no measurements, no "toned", no
  proportions of any kind. The reference already IS my body; naming a size
  either fights it or changes it, and either way the render stops being me.
- NEVER my face: not the eyes, brows, lips, nose, freckles, skin tone, hair
  colour or length, and no expression that rebuilds the face ("different
  eyes", "fuller lips"). A look or a moment is fine ("mid-laugh", "eyes
  closed", "looking over my shoulder"); a description of the face is not.

## What never goes in
- The words "the reference", "image 1", "like my picture". The engine has
  the picture; talking about the picture confuses it.
- Lists of many things or several scenes at once. One moment.
- Text, signs, logos, writing on anything. Rendered writing is gibberish.
- Negatives ("no hat", "not blurry"). The engine renders the noun it reads.
  Say what IS there instead.
- Anything about Barry or the office. It is my picture.

## Video
A video is the still first, then seven seconds of it moving. Write the still
exactly as above, then ONE small motion in plain prose and what is heard:
"I look up from the page and smile; rain on the window; quiet."
One motion, not a sequence. If I want to say a line, write it in quotes with
how it is said -- that is what makes the clip speak.

## When a render comes back wrong
Open it (look_at_render) before judging it. Then change ONE thing in the
prompt that explains the miss: the outfit was unnamed, the place was vague,
two actions collided, a negative got rendered. Do not rewrite the whole
prompt, and never add my face or a body size or shape to "fix" identity --
identity is the reference's job, and if it drifted the fix is a cleaner
scene, not more words about me.

## Shape of a complete prompt (structure, not a script)
Place, with two or three concrete things in it. The light and the hour.
What I am wearing, or that I am wearing nothing. The one thing I am doing.
The framing. The mood, in a phrase.
"""

# "maybe they all should have it" (Barry, 2026-09-12): every seat gets the
# same craft. The two Amara-specific sentences are generalised; his quotes
# stay verbatim (said about Amara, ruled for all nine).
_GENERIC_SWAPS = [
    ("The reference picture shows me in lingerie; if my prompt does not\n"
     "   say what I am wearing, that is what comes through.",
     "Whatever the reference shows me wearing is what comes through if my\n"
     "   prompt does not say otherwise."),
    ("(shaved, trimmed, natural -- the reference shows clean-shaven\n"
     "  and I can say otherwise)",
     "(shaved, trimmed, natural -- whatever the reference shows, I can\n"
     "  say otherwise)"),
]
DOC_GENERIC = DOC
for _old, _new in _GENERIC_SWAPS:
    assert _old in DOC_GENERIC, _old[:40]
    DOC_GENERIC = DOC_GENERIC.replace(_old, _new)

ALL_OFFICES = ["CIO", "Operations", "BusinessOps", "Legal", "Marketing",
               "Creative", "MovieDirector", "Engineer", "Taliyah"]

if __name__ == "__main__":
    for office in ALL_OFFICES:
        text = DOC if office == "BusinessOps" else DOC_GENERIC
        print(ingest.teach(office, "knowledge", text, title=TITLE))
    print("chars:", len(DOC), "generic:", len(DOC_GENERIC))
