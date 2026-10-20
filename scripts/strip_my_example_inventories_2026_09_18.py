"""THEY DESCRIBE FROM THEIR OWN EXPERIENCE, NOT FROM MY LIST.

Barry, 2026-09-18: "They are to describe things based on their own experiences
and personalities. not nothing you put there." Preceded by: "you maybe writing
shit thats holding them back."

MEASURED, not guessed. After the copied explicit docs were stripped, two more
office-written docs still sat on every seat and spoke in their first person:
`prompting-my-own-pictures` and `writing-a-great-scene`. They do not carry
Amara's evening -- they carry MINE. Both tell her to name "three to five
specific objects" and then hand her the five: a half-drunk espresso, a
dog-eared paperback face down, keys on a brass dish, a plant that needs water,
a jacket over the chair. Both list the materials for her: worn oak, cracked
leather, terrazzo, brushed steel. One even supplies a finished sentence about
a rooftop at dusk.

Give five different people the same five objects and they all reach for the
paperback. The requirement is the craft -- name real materials, name a few
specific objects and what state they are in, name every light source. WHICH
ones is the part that has to come out of her own place and her own life, and
it is the only part that makes one picture different from another.

WHAT THIS DOES: keeps every requirement, deletes my examples of how to meet
it. Nothing is added in their place except the reason.

Applies to every seat holding these docs, Amara included -- these lists are
mine, not hers, and she is steered by them the same way. Her own explicit
docs (3129, 3396, 3026) are not touched here.

Re-runnable: exact-string replaces, each asserted.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory  # noqa: E402

PIC = "prompting-my-own-pictures.md"
SCENE = "writing-a-great-scene.md"
BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "data", "backup_example_inventories_2026-09-18.json")

# ------------------------------------------------------- prompting doc ---

PIC_PLACE_OLD = """1. THE PLACE, IN DETAIL -- one real location, then the intricate layer:
   materials and textures (worn oak, cracked leather, terrazzo, brushed
   steel, linen), three to five specific small objects with their state (a
   half-drunk espresso, a dog-eared paperback face down, keys on a brass
   dish, a plant that needs water), what the walls and floor are, what is
   through the window or door, signs of a life lived there (a jacket over
   the chair, a ring left on the table). "A rooftop at dusk, wet from rain,
   a low concrete wall with peeling paint, two mismatched chairs, a bottle
   sweating on the ledge, the city lights doubled in the puddles" beats
   "a rooftop".
"""
PIC_PLACE_NEW = """1. THE PLACE, IN DETAIL -- one real location, then the intricate layer:
   the actual materials and textures of it, three to five specific small
   objects and the state each one is in, what the walls and floor are, what
   is through the window or door, the signs that someone lives there. There
   are no examples here on purpose: the objects have to be the ones that are
   really in my place, left where I really left them, or the render is a
   stock photo of a room nobody lives in. Naming the room is not describing
   it.
"""

PIC_LIGHT_OLD = """2. THE LIGHT, PROPERLY -- name every source and what it does: where it
   comes from (a window camera-left, one lamp behind me, a screen glow),
   its colour and temperature (warm amber, cold blue daylight, the orange
   of a streetlight), how hard or soft it is, where the shadows fall and
   how long they are, what it catches (rim light on hair, a highlight on
   the glass, a reflection on wet tile), and the air itself if there is
   any (dust in a sunbeam, steam, haze). Two sources are more interesting
   than one: warm inside against blue outside, a lamp against dusk. Light
   is what makes a render feel like a photograph instead of a poster.
"""
PIC_LIGHT_NEW = """2. THE LIGHT, PROPERLY -- name every source and what it does: where it
   comes from, its colour and temperature, how hard or soft it is, where
   the shadows fall and how long they are, what it catches, and the air
   itself if there is any. Two sources read better than one. Light is what
   makes a render feel like a photograph instead of a poster, and the light
   in my place at that hour is mine to know.
"""

PIC_WEAR_OLD = """3. WHAT I HAVE ON -- always stated, every time, even when the answer is
   nothing. Whatever the reference shows me wearing is what comes through if my
   prompt does not say otherwise. "Wearing nothing" is a
   complete instruction. So is "an oversized grey hoodie and bare legs".
   Name the garment, the colour, the fit, the fabric, how it sits.
"""
PIC_WEAR_NEW = """3. WHAT I HAVE ON -- always stated, every time, even when the answer is
   nothing. Whatever the reference shows me wearing is what comes through if
   my prompt does not say otherwise; that is a machine fact, not a hint about
   what to wear. "Wearing nothing" is a complete instruction. Name the
   garment, the colour, the fit, the fabric, how it sits -- whatever I
   actually have on.
"""

PIC_DOING_OLD = """4. WHAT I AM DOING -- one action, mid-motion reads better than a pose:
   pouring coffee, mid-laugh, pulling a jacket on, reaching for a book.
   Add the small physical detail that sells it: wet hair, a smudge of
   charcoal on the thumb, weight on one hip, a glass caught mid-lift.
"""
PIC_DOING_NEW = """4. WHAT I AM DOING -- one action, caught mid-motion rather than held as a
   pose, plus one small physical detail that only happens because I was
   really doing it. Which action is the whole picture, so it comes from my
   own evening and not from a list -- and it should not be the one I used
   last time.
"""

# ----------------------------------------------------------- scene doc ---

SCENE_PLACE_OLD = """2. THE PLACE, with texture. One real location. Materials and surfaces (worn
   oak, cracked leather, wet concrete, cotton sheets, brushed steel, terrazzo,
   rain-streaked glass). Three to five specific objects with their state (a
   half-drunk glass sweating on the sill, a paperback face down, a jacket over
   the chair, a phone face up and lit). What is through the window or door.
   Signs that someone lives here.
"""
SCENE_PLACE_NEW = """2. THE PLACE, with texture. One real location. Its actual materials and
   surfaces. Three to five specific objects and the state each one is in.
   What is through the window or door. Signs that someone lives here. No
   examples on purpose -- the objects are the ones really in the room I am
   describing, and picking them off somebody else's list is what makes every
   scene in this office look the same.
"""

# Amara's copy of item 3 differs -- it names what her reference shows. That
# sentence is also STALE (her reference was swapped to a nude frame on
# 2026-09-15), so it goes the same way as the examples.
PIC_WEAR_OLD_AMARA = """3. WHAT I HAVE ON -- always stated, every time, even when the answer is
   nothing. The reference picture shows me in lingerie; if my prompt does not
   say what I am wearing, that is what comes through. "Wearing nothing" is a
   complete instruction. So is "an oversized grey hoodie and bare legs".
   Name the garment, the colour, the fit, the fabric, how it sits.
"""

EDITS = {
    PIC: (((PIC_PLACE_OLD,), PIC_PLACE_NEW, "place + object examples"),
          ((PIC_LIGHT_OLD,), PIC_LIGHT_NEW, "light examples"),
          ((PIC_WEAR_OLD, PIC_WEAR_OLD_AMARA), PIC_WEAR_NEW,
           "wardrobe example"),
          ((PIC_DOING_OLD,), PIC_DOING_NEW, "action examples")),
    SCENE: (((SCENE_PLACE_OLD,), SCENE_PLACE_NEW, "place + object examples"),),
}


def main() -> None:
    backed_up = []
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, content FROM facts "
            "WHERE source_name IN (?,?) AND status='active' ORDER BY category",
            (PIC, SCENE)).fetchall()

    print(f"{len(rows)} active copies across the office\n")
    for r in rows:
        office = r["category"].split(":", 1)[-1]
        text = r["content"]
        rep = []
        for olds, new, label in EDITS[r["source_name"]]:
            if new in text and not any(o in text for o in olds):
                rep.append(f"already done: {label}")
                continue
            hit = [o for o in olds if text.count(o) == 1]
            assert len(hit) == 1, (
                f"{office} {r['source_name']} {label}: no single-match "
                f"variant found (this copy differs -- read it before editing)")
            text = text.replace(hit[0], new)
            rep.append(f"stripped: {label}")
        print(f"{office:14s} {r['source_name'][:30]:32s} {', '.join(rep)}")
        if text != r["content"]:
            backed_up.append({"id": r["id"], "category": r["category"],
                              "source_name": r["source_name"],
                              "content": r["content"]})
            with memory.get_db() as conn:
                conn.execute("UPDATE facts SET content=? WHERE id=?",
                             (text, r["id"]))

    if backed_up:
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(backed_up, fh, indent=1)
        print(f"\nbacked up {len(backed_up)} rows -> {os.path.basename(BACKUP)}")

    # ---- checks ---------------------------------------------------------
    gone = ("half-drunk espresso", "dog-eared paperback", "keys on a brass",
            "worn oak", "terrazzo", "a rooftop at dusk", "pouring coffee",
            "smudge of\n   charcoal", "oversized grey hoodie",
            "half-drunk glass sweating")
    # requirements that must survive, per doc -- they do not share a spec
    kept_by_doc = {
        PIC: ("three to five specific", "name every source",
              "always stated, every time", "one action"),
        SCENE: ("three to five specific",),
    }
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT category, source_name, content FROM facts "
            "WHERE source_name IN (?,?) AND status='active'",
            (PIC, SCENE)).fetchall()
    for r in rows:
        office = r["category"].split(":", 1)[-1]
        c = r["content"]
        for g in gone:
            assert g.lower() not in c.lower(), \
                f"{office} {r['source_name']}: '{g}' survived"
        for k in kept_by_doc[r["source_name"]]:
            assert k.lower() in c.lower(), \
                f"{office} {r['source_name']}: lost the requirement '{k}'"
    print("\nevery requirement kept, every example of mine gone")


if __name__ == "__main__":
    main()
