"""Changing an agent's environment -- Sophie's job.

Barry, 2026-08-31: "all sophie's skills need to be active for what i need her
to do... like changing the environments of the agents, like if they go out to a
club, they may want that to be seen or show me what they did over the weekend
or last night."

Until now an agent's home picture was frozen at whatever an overnight batch
rendered. Their lives move -- they go out, they redecorate, something happens
on a weekend -- and there was no path to change what Barry sees. Rendering one
took a human running a script.

WHAT THIS IS: the install half. Sophie proposes a scene, it renders through the
normal image path (so it queues for approval and lands in Outputs like
everything else), and on Barry's approval the finished file is copied into
AgentDashboard/assets/homes/ under the right name, with the previous version
backed up first.

WHY IT IS SPLIT THAT WAY: his standing gate is that Sophie never changes files
without his OK. Rendering is harmless and reversible; INSTALLING overwrites
what he sees on every deck. So the render happens on request and the install
happens only from the approve endpoint -- the same shape as codefix.apply_fix.

SLOTS -- what an agent's picture can be:
    home     assets/homes/<id>.png        the room itself, no people
    self     assets/homes/<id>_me.png     them, at home, in that room
    out      assets/homes/<id>_out.png    them somewhere else (a club, a
                                          weekend, last night)
`out` is new and is the reason Barry asked: a night out is not a home.
"""

import datetime
import os
import shutil

import memory

# THEIR PICTURES GO WHERE THEY GO (Barry, 2026-09-11: "i want sophie to just
# put the images where they are supposed to go... not every two weeks, just
# when they feel like it or i ask"). An agent's picture of their OWN place is
# not an outbound action -- nothing leaves the machine, nobody but Barry sees
# it -- so it no longer waits for his click. queue_change() files the row the
# way change_my_picture always did, then (setting `scene_auto_install`,
# default true) marks it approved + `dispatch_status='queued'`; main.py's
# scene loop renders it when the card is free and the office is quiet, and
# installs it. Setting it to "false" restores the click for everything.
AUTO_KEY = "scene_auto_install"


def auto_install() -> bool:
    return (memory.get_setting(AUTO_KEY, "true") or "true").lower() != "false"


def queue_change(agent_id: str, slot: str, description: str) -> dict:
    """File a picture change in the agent's own words. Never raises."""
    slot = (slot or "").strip().lower()
    description = (description or "").strip()
    if slot not in SLOTS:
        return {"error": "slot must be one of: %s." % ", ".join(SLOTS)}
    if len(description) < 40:
        return {"error": "Describe it properly -- a real picture needs more than a few words."}
    try:
        approval_id = memory.queue_for_approval(
            agent_id, "agent_scene",
            "SCENE UPDATE for %s [%s] -- in their own words\n\n%s" % (agent_id, slot, description),
            file_path="%s|%s" % (agent_id, slot))
    except Exception as exc:  # noqa: BLE001
        return {"error": "Could not queue it: %s" % exc}
    if not auto_install():
        return {"queued": True, "approval_id": approval_id, "auto": False,
                "what_happens_next": (
                    "Your words are in Barry's Pending Review exactly as you wrote them. When he "
                    "approves, the picture renders and replaces your %s image (the old one is "
                    "backed up). Nothing has changed yet -- say so." % slot)}
    try:
        memory.decide_approval(approval_id, True)
        with memory.get_db() as conn:
            conn.execute("UPDATE approvals SET dispatch_status = 'queued' WHERE id = ?", (approval_id,))
    except Exception as exc:  # noqa: BLE001
        return {"queued": True, "approval_id": approval_id, "auto": False,
                "what_happens_next": "Filed for Barry's approval (auto-install failed: %s)." % exc}
    return {"queued": True, "approval_id": approval_id, "auto": True,
            "what_happens_next": (
                "Your words are filed exactly as you wrote them. The office renders it when the "
                "card is free (minutes to a quarter hour) and puts it in place as your %s picture, "
                "old one backed up. It has NOT changed yet -- do not say it has." % slot)}

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
HOMES_DIR = os.path.join(os.path.dirname(_PROJECT), "AgentDashboard",
                         "assets", "homes")
BACKUP_DIR = os.path.join(_PROJECT, "data", "scene_backups")

OFFICES_DIR = os.path.join(os.path.dirname(_PROJECT), "AgentDashboard",
                           "assets", "offices")

# 2026-09-02 (Barry: "I want them to be able to change their images for home
# and offices"): the office plate joins the slots. It lives in assets/offices/
# and, unlike `home`, it SHOWS the agent at their desk (that is how the
# 2026-09-01 office plates were made), so it renders with their face reference.
# 2026-09-19 (Barry, on a new agent: "her home and Lab images"): a WORKSPACE
# that is not a desk. `lab` is deliberately a ROOM plate, not a WITH_PERSON
# shot -- he asked for "high descriptions... whats all around, bits and bobs",
# which is a description of a place, and a room renders as written instead of
# needing a face reference a brand-new agent does not have yet. If he wants
# her standing in it, any picture she makes can be dropped into this slot from
# the gallery (POST /api/agents/{id}/pictures/use) in one click.
SLOTS = {
    "home":   "{aid}.png",
    "self":   "{aid}_me.png",
    "out":    "{aid}_out.png",
    "office": "{aid}.png",
    "lab":    "{aid}_lab.png",
}
_SLOT_DIRS = {"office": OFFICES_DIR}
WITH_PERSON = ("self", "out", "office")


def slot_path(agent_id: str, slot: str) -> str:
    if slot not in SLOTS:
        raise ValueError("slot must be one of: %s" % ", ".join(SLOTS))
    return os.path.join(_SLOT_DIRS.get(slot, HOMES_DIR), SLOTS[slot].format(aid=agent_id))


def current_scenes(agent_id: str) -> dict:
    """What this agent's environment looks like right now, on disk."""
    out = {}
    for slot in SLOTS:
        p = slot_path(agent_id, slot)
        out[slot] = {"exists": os.path.isfile(p),
                     "path": p,
                     "bytes": os.path.getsize(p) if os.path.isfile(p) else 0}
    return out


def install(agent_id: str, slot: str, source_file: str) -> dict:
    """Put a finished render in place. Backs up whatever is there first.

    Returns a dict, never raises for the ordinary failures -- an install that
    blows up must not turn Barry's approval click into a 500.
    """
    try:
        dest = slot_path(agent_id, slot)
    except ValueError as exc:
        return {"installed": False, "error": str(exc)}

    if not source_file or not os.path.isfile(source_file):
        return {"installed": False,
                "error": "The rendered file is not on disk: %s" % source_file}

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    backup = ""
    if os.path.isfile(dest):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(
            BACKUP_DIR, "%s_%s_%s.png" % (agent_id, slot, stamp))
        try:
            shutil.copy2(dest, backup)
        except Exception as exc:
            return {"installed": False,
                    "error": "Could not back up the current picture: %s" % exc}

    try:
        # temp + replace, so a half-written file can never be what the
        # dashboard serves.
        tmp = dest + ".tmp"
        shutil.copy2(source_file, tmp)
        os.replace(tmp, dest)
    except Exception as exc:
        return {"installed": False, "error": "Copy failed: %s" % exc,
                "backup": backup}

    return {"installed": True, "slot": slot, "path": dest,
            "backup": backup or "(nothing was there before)",
            "note": "Hard-refresh a deck to see it -- the old picture is cached."}


# ---------------------------------------------------------------------------
# THEIR MAIN IMAGE -- who they are, not where they are.
#
# Barry, 2026-09-19, on a new agent: "she will draw herself and i can accept
# and add to her home or her main or her lab image. the gets the same as them
# all."
#
# The nine each have FOUR files that make up "their picture", and a hire had
# none of them and no way to get them:
#   avatars/<id>.png         the whole figure on the stage and in the window
#   avatars/<id>_face.png    the 54px roster tile
#   input/agent_ref_<id>.png the REFERENCE every later picture restages from
#   input/agent_face_<id>.png the face, stated a second time (see step 4)
# That last one is the important one: with it, main._render_self_picture stops
# describing them to a model and starts editing Barry's actual chosen picture
# of them, which is the whole reason the nine look like themselves (2026-09-10).
#
# So "set as main" is one click that writes all four from one render she made.
# The face tile is cropped by RULE, not by eye -- see _head_crop.
IDENTITY_DIR = os.path.join(_PROJECT, "data", "identity")   # <id>/face.png, body.png, LOCKED
AVATARS_DIR = os.path.join(os.path.dirname(_PROJECT), "AgentDashboard",
                           "assets", "cyber", "avatars")
REF_LONG_EDGE = 1328  # what the nine are staged at


def _head_crop(im):
    """A head-and-shoulders tile out of a standing figure, by rule.

    The nine's face crops were cut BY HAND, looking at each render. Nobody is
    going to hand-cut one for every new agent, so this takes the top of the
    frame: a SQUARE box, 42% of the height, centred horizontally. On an upright
    portrait render that lands on the head and shoulders. It is a heuristic and
    it is allowed to be one -- the tile is 54px on screen, and re-running this
    on a better render costs one click. Returns None if it cannot.

    ⚠️ SQUARE IS NOT COSMETIC (2026-09-19). Every deck draws this in a ROUND
    slot with `object-fit: cover; object-position: top`, so a 3:4 tile shows
    only its own TOP SQUARE -- forehead and eyes, chin gone, and off-centre
    if the head is not dead centre. That is what the first hire's tile did.
    """
    try:
        w, h = im.size
        side = max(1, int(h * 0.42))
        if side > w:                       # a wide/landscape render
            side = w
        side = min(side, h)
        left = max(0, (w - side) // 2)
        return im.crop((left, 0, left + side, side))
    except Exception:  # noqa: BLE001
        return None


def install_main(agent_id: str, source_file: str) -> dict:
    """Make this render the agent's own picture: avatar, roster tile, and the
    reference every future picture of them is restaged from.

    Never raises for the ordinary failures. A partial result is reported
    honestly rather than rolled back -- knowing the avatar landed and the
    reference did not is more useful than a bare error.
    """
    if not source_file or not os.path.isfile(source_file):
        return {"installed": False,
                "error": "That picture is not on disk: %s" % source_file}
    # Barry 2026-09-24: "lock in her face and full body images" -- a locked identity
    # (data/identity/<id>/LOCKED) is never replaced by "set as main"; only he unlocks it
    # (delete the LOCKED file).
    if os.path.isfile(os.path.join(IDENTITY_DIR, agent_id, "LOCKED")):
        return {"installed": False,
                "error": "%s's face and full body are LOCKED by Barry -- not replaced. "
                         "He unlocks it by deleting data/identity/%s/LOCKED." % (agent_id, agent_id)}

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(AVATARS_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    wrote, backups, problems = [], [], []

    def _put(dest, data_path):
        if os.path.isfile(dest):
            b = os.path.join(BACKUP_DIR, "%s_main_%s_%s" % (
                agent_id, stamp, os.path.basename(dest)))
            try:
                shutil.copy2(dest, b)
                backups.append(b)
            except Exception as exc:  # noqa: BLE001
                problems.append("could not back up %s: %s" % (os.path.basename(dest), exc))
                return
        try:
            tmp = dest + ".tmp"
            shutil.copy2(data_path, tmp)
            os.replace(tmp, dest)
            wrote.append(dest)
        except Exception as exc:  # noqa: BLE001
            problems.append("%s: %s" % (os.path.basename(dest), exc))

    # 1. the whole figure
    _put(os.path.join(AVATARS_DIR, "%s.png" % agent_id), source_file)

    # 2. the roster tile
    face_tmp = ""
    try:
        from PIL import Image
        with Image.open(source_file) as im:
            crop = _head_crop(im.convert("RGB"))
            if crop is not None:
                face_tmp = os.path.join(BACKUP_DIR, "_face_%s_%s.png" % (agent_id, stamp))
                crop.save(face_tmp)
    except Exception as exc:  # noqa: BLE001
        problems.append("face crop: %s" % exc)
    if face_tmp and os.path.isfile(face_tmp):
        _put(os.path.join(AVATARS_DIR, "%s_face.png" % agent_id), face_tmp)

    # 3. THE REFERENCE -- the one that changes every future render.
    ref_dest = ""
    try:
        import comfy_image
        from PIL import Image
        ref_dest = os.path.join(comfy_image.COMFY_DIR, "input",
                                "agent_ref_%s.png" % agent_id)
        staged = os.path.join(BACKUP_DIR, "_ref_%s_%s.png" % (agent_id, stamp))
        with Image.open(source_file) as im:
            im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > REF_LONG_EDGE:
                scale = REF_LONG_EDGE / float(max(w, h))
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                               Image.LANCZOS)
            im.save(staged)
        _put(ref_dest, staged)
        try:
            os.remove(staged)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        problems.append("reference: %s" % exc)

    # 4. THE FACE REFERENCE (2026-09-19). Barry, on a hire: "always fix
    # everything."
    #
    # MEASURED on Ilnora, the first hire to have a picture at all: all nine
    # had `agent_face_<id>.png` staged in ComfyUI's input root and she had
    # none, because install_main only ever wrote three files. Two things ran
    # silently degraded for her and for every future hire:
    #   * main._render_self_picture passes that file as IMAGE 2 so the face is
    #     stated twice -- the 2026-09-18 fix for Sophie's restage coming back
    #     a generic pretty face. Without it a hire's face is stated once.
    #   * media_understanding.own_picture_paths lists ONLY face/body slots, so
    #     `look_at_my_pictures` returned an empty list -- she could not open a
    #     picture of herself at all, while the nine could.
    # It is the same crop as the roster tile, which is a heuristic and allowed
    # to be one. The 2026-08-28 loose-crop warning does not bite here: image 1
    # and image 2 come from the SAME picture, so image 2 cannot drag in a room
    # or a wardrobe that image 1 does not already have.
    if face_tmp and os.path.isfile(face_tmp):
        try:
            import comfy_image
            _put(os.path.join(comfy_image.COMFY_DIR, "input",
                              "agent_face_%s.png" % agent_id), face_tmp)
        except Exception as exc:  # noqa: BLE001
            problems.append("face reference: %s" % exc)
    if face_tmp and os.path.isfile(face_tmp):
        try:
            os.remove(face_tmp)
        except Exception:  # noqa: BLE001
            pass

    return {
        "installed": bool(wrote),
        "slot": "main",
        "wrote": wrote,
        "backups": backups or ["(nothing was there before)"],
        "problems": problems,
        "reference_live": bool(ref_dest) and os.path.isfile(ref_dest),
        "note": ("This is their picture now. Every picture of them from here on "
                 "is restaged from it. Hard-refresh a deck to see the avatar -- "
                 "it is cached."),
    }
