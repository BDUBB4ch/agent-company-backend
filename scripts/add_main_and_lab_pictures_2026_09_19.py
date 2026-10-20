"""SET AS MAIN + SET AS LAB, on both decks (2026-09-19).

Barry, on a new agent: "she will draw herself and i can accept and add to her
home or her main or her lab image. the gets the same as them all."

Two things were missing from the gallery lightbox, which is the only place a
picture she makes can become something permanent:

  MAIN -- her avatar, her roster tile AND her reference (input/agent_ref_<id>
          .png). Without the reference every later picture of her is a
          stranger; with it, main._render_self_picture restages the exact
          picture he accepted. That is what the nine have and a new agent had
          no way to get.
  LAB  -- a workspace plate that is not a desk. New slot in agent_scenes.

Plus a LAB button in the home window, so an installed lab plate is actually
visible instead of only existing on disk.

Re-runnable: every replace is asserted and already-patched decks are skipped.
Backups land in data/backup_decks_before_mainlab_2026-09-19/.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
DECKS_DIR = os.path.join(os.path.dirname(PROJECT), "AgentDashboard")
BACKUP = os.path.join(PROJECT, "data", "backup_decks_before_mainlab_2026-09-19")
DECKS = ["neo-chamber.html", "neo-holo.html"]

# --- 1. the two buttons in the lightbox row --------------------------------
BTN_ANCHOR = ('<button id="pic-light-office" title="Make this their office '
              'picture">SET AS OFFICE</button>')
BTN_NEW = BTN_ANCHOR + (
    '<button id="pic-light-lab" title="Make this their lab / workspace '
    'picture">SET AS LAB</button>'
    '<button id="pic-light-main" title="Make this THEIR picture -- avatar, '
    'roster tile, and the reference every future picture of them is restaged '
    'from">◉ SET AS MAIN</button>')

# --- 2. show them for stills only ------------------------------------------
SHOW_ANCHOR = '$("pic-light-office").style.display = isStill ? "" : "none";'
SHOW_NEW = SHOW_ANCHOR + (
    '\n  $("pic-light-lab").style.display = isStill ? "" : "none";'
    '\n  $("pic-light-main").style.display = isStill ? "" : "none";')

# --- 3. wire them ----------------------------------------------------------
WIRE_ANCHOR = '$("pic-light-office").onclick = () => use("office", "office");'
WIRE_NEW = WIRE_ANCHOR + (
    '\n  $("pic-light-lab").onclick = () => use("lab", "lab");'
    # MAIN is not a scene -- it changes who she IS in every later render, so
    # it asks differently and says what it actually did.
    '\n  $("pic-light-main").onclick = async () => {'
    '\n    if (!confirm("Make this " + (FIRST[id] || id) + "\'s MAIN picture?'
    '\\n\\nIt becomes their avatar, their roster tile, and the reference every'
    ' future picture of them is restaged from. The old ones are backed up."))'
    ' return;'
    '\n    try {'
    '\n      const r = await apiPost("/api/agents/" + id + "/pictures/use",'
    ' { approval_id: p.id, slot: "main" });'
    '\n      toast("\\u25c9 " + (FIRST[id] || id) + " \\u2014 main picture set"'
    ' + (r && r.reference_live ? " (they restage from it now)" : ""), 6000);'
    '\n      $("pic-light-x").onclick();'
    '\n    } catch (e) { toast("\\u26a0 " + e.message, 6000); }'
    '\n  };')

# --- 4. the LAB button in the home window ----------------------------------
LABBTN_ANCHOR = ('<button id="pchat-switch" title="Switch to someone else">'
                 '⌂ SWITCH</button>')
LABBTN_NEW = (
    '<button id="pchat-lab" title="Their lab / workspace" '
    'style="display:none">⚗ LAB</button>' + LABBTN_ANCHOR)

# Toggle: swap the room panel to the lab plate and back. Probed with an Image
# load because a missing plate is the normal case -- most agents have no lab.
LABJS_ANCHOR = '  homeEl.style.backgroundImage = "url(\'" + room + "\')";'
LABJS_NEW = LABJS_ANCHOR + """
  /* ⚗ LAB (2026-09-19) -- a workspace that is not a desk. The button only
     appears when a lab plate actually exists on disk; clicking it swaps the
     room panel to it and back. The plate is a ROOM, so the portrait stage
     hides while it is up, same rule as the office plate. */
  (function () {
    const labBtn = $("pchat-lab");
    if (!labBtn) return;
    labBtn.style.display = "none";
    let showingLab = false;
    const labUrl = "assets/homes/" + id + "_lab.png";
    const probe = new Image();
    probe.onload = () => { labBtn.style.display = "inline-block"; };
    probe.onerror = () => { labBtn.style.display = "none"; };
    probe.src = labUrl + "?t=" + Date.now();
    labBtn.onclick = (e) => {
      e.stopPropagation();
      showingLab = !showingLab;
      if (showingLab) {
        homeEl.style.backgroundImage = "url('" + labUrl + "?t=" + Date.now() + "')";
        stageEl.style.display = "none";
        labBtn.textContent = "⌂ BACK";
      } else {
        homeEl.style.backgroundImage = "url('" + room + "')";
        stageEl.style.display = isWork ? "none" : "";
        labBtn.textContent = "⚗ LAB";
      }
    };
  })();"""

# The drag handler swallows clicks on the header -- LAB has to be excluded the
# same way SWITCH and the close X already are, or the button does nothing.
DRAG_ANCHOR = ('if (e.target.closest("#pchat-x") || '
               'e.target.closest("#pchat-switch")) return;')
DRAG_NEW = ('if (e.target.closest("#pchat-x") || '
            'e.target.closest("#pchat-switch") || '
            'e.target.closest("#pchat-lab")) return;')

# Style it like SWITCH so it belongs to the same row, in both channel colours.
CSS_ANCHOR = "  #pchat-switch { display: none; margin-left: auto; cursor: pointer;"
CSS_NEW = """  #pchat-lab { cursor: pointer; margin-left: auto; font: inherit;
    font-size: .62rem; letter-spacing: .1em; padding: 3px 9px; border-radius: 3px;
    background: rgba(255,190,80,.14); color: #ffd79a;
    border: 1px solid rgba(255,190,80,.42); }
  #pchat-lab:hover { background: rgba(255,190,80,.3); }
  #pchat.workchan #pchat-lab { background: rgba(62,245,138,.14); color: #bdf6d6;
    border-color: rgba(62,245,138,.45); }
  #pchat-switch { display: none; margin-left: auto; cursor: pointer;"""

EDITS = [
    ("lightbox buttons", BTN_ANCHOR, BTN_NEW, 'id="pic-light-main"'),
    ("stills-only gating", SHOW_ANCHOR, SHOW_NEW, 'pic-light-main").style.display'),
    ("button wiring", WIRE_ANCHOR, WIRE_NEW, 'pic-light-main").onclick'),
    ("lab button", LABBTN_ANCHOR, LABBTN_NEW, 'id="pchat-lab"'),
    ("lab toggle", LABJS_ANCHOR, LABJS_NEW, 'const labBtn = $("pchat-lab")'),
    ("drag exclusion", DRAG_ANCHOR, DRAG_NEW, '#pchat-lab")) return'),
    ("lab styling", CSS_ANCHOR, CSS_NEW, "#pchat-lab { cursor: pointer"),
]


def check_scripts(path: str) -> list:
    """node --check every inline <script> -- a mangled literal breaks the whole
    block silently and the page still renders (the 2026-08-25 lesson)."""
    bad = []
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    for i, m in enumerate(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                      html, re.S)):
        tmp = os.path.join(BACKUP, "_check_%d.js" % i)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(m.group(1))
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        if r.returncode != 0:
            bad.append("block %d: %s" % (i, (r.stderr or "").strip()[:300]))
        os.remove(tmp)
    return bad


def main() -> int:
    os.makedirs(BACKUP, exist_ok=True)
    failed = False
    for deck in DECKS:
        path = os.path.join(DECKS_DIR, deck)
        if not os.path.isfile(path):
            print("SKIP %s -- not on disk" % deck)
            continue
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        original = src
        for label, anchor, new, marker in EDITS:
            if marker in src:
                print("  %-18s already there" % label)
                continue
            if src.count(anchor) != 1:
                print("  %-18s ANCHOR MISS (%d hits) -- not patched"
                      % (label, src.count(anchor)))
                failed = True
                continue
            src = src.replace(anchor, new, 1)
            assert marker in src, label
            print("  %-18s patched" % label)
        if src == original:
            print("%s: nothing to do\n" % deck)
            continue
        shutil.copy2(path, os.path.join(BACKUP, deck))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(src)
        os.replace(tmp, path)
        bad = check_scripts(path)
        if bad:
            shutil.copy2(os.path.join(BACKUP, deck), path)
            print("%s: SYNTAX BROKEN, reverted:\n   %s" % (deck, "\n   ".join(bad)))
            failed = True
        else:
            print("%s: written, all inline scripts parse\n" % deck)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
