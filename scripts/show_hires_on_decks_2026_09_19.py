"""Make a HIRED agent visible on the chamber and holo decks.

Barry, 2026-09-19: "I do not see ilnora in chamber or holo."

WHY SHE WAS INVISIBLE, measured rather than guessed: both decks build their
roster as

    const roster = agents.filter((x) => COLOR[x.id]);

and COLOR is a hardcoded map of his original nine. Anything the factory adds is
filtered out of the rail, the MINDS pane and the group-chat list -- the backend
was returning her the whole time (/api/agents has always listed her).

Three things, per deck, all additive:
  1. the six roster filters become plain `agents` -- the deck shows whoever
     the backend says exists;
  2. every COLOR[...] lookup goes through colorOf(), which gives an agent with
     no entry a stable colour derived from its id (same id, same colour, every
     load) instead of `undefined`;
  3. a capture-phase image-error handler swaps a missing portrait for an
     initials tile. A hire has no rendered avatar until Barry makes one, and a
     broken-image icon reads as "this agent is broken".

Everything else already fell back on its own (FIRST[id] || a.name,
CLASS[id] || ""), which is why only these three things needed doing.

Re-runnable: asserts each edit landed, skips a deck already patched, and writes
temp+rename (the 2026-08-29 truncation lesson).
"""
import io
import os
import re
import sys

DECKS = [
    r"C:\Users\Owner\Desktop\AgentDashboard\neo-chamber.html",
    r"C:\Users\Owner\Desktop\AgentDashboard\neo-holo.html",
]

MARKER = "/* --- hires show up too (2026-09-19) --- */"

HELPERS = MARKER + """
/* A hire made through the factory has no entry in FIRST/CLASS/COLOR and no
   rendered portrait. Rather than filter it out of the deck (which is what hid
   Ilnora), give it a stable colour off its id and an initials tile. */
function colorOf(id) {
  if (COLOR[id]) return COLOR[id];
  var s = String(id || ""), h = 0;
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return "hsl(" + (h % 360) + " 72% 63%)";
}
/* Image errors do not bubble -- this has to be capture phase. */
document.addEventListener("error", function (e) {
  var t = e.target;
  if (!t || t.tagName !== "IMG" || t.getAttribute("data-fellback")) return;
  var m = /avatars\\/([A-Za-z0-9_]+?)(_face)?\\.png/.exec(t.getAttribute("src") || "");
  if (!m) return;
  t.setAttribute("data-fellback", "1");
  var id = m[1];
  var rec = (typeof agents !== "undefined" && agents || []).filter(function (x) { return x.id === id; })[0] || {};
  var who = String(FIRST[id] || rec.name || id).trim();
  var ini = (who.slice(0, 2) || "?").toUpperCase();
  var c = colorOf(id);
  t.src = "data:image/svg+xml;utf8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256">' +
    '<rect width="256" height="256" rx="18" fill="#0b1116"/>' +
    '<circle cx="128" cy="128" r="98" fill="none" stroke="' + c + '" stroke-width="5" opacity="0.85"/>' +
    '<text x="128" y="132" font-family="Segoe UI,system-ui,sans-serif" font-size="90" font-weight="600" fill="' + c +
    '" text-anchor="middle" dominant-baseline="middle">' + ini + '</text></svg>');
}, true);
"""

ANCHOR = 'const NINEB = "huihui_ai/qwen3.5-abliterated:9b";'
FILTER = "agents.filter((x) => COLOR[x.id])"


def patch(path: str) -> str:
    src = io.open(path, encoding="utf-8").read()
    if MARKER in src:
        return "already patched"

    # 1. the roster filters (6 per deck)
    # SIX, not three: the rail, MINDS, the group-chat list, the HOMES and
    # OFFICES pickers and the MESSAGES chooser each filter the same way. The
    # first run of this script asserted 3 and stopped -- which is the whole
    # reason for asserting counts instead of replacing blind.
    n_filter = src.count(FILTER)
    if n_filter != 6:
        raise SystemExit(f"{path}: expected 6 roster filters, found {n_filter}")
    out = src.replace(FILTER, "agents")

    # 2. every COLOR[...] read -> colorOf(...). The map itself is untouched.
    out, n_color = re.subn(r"COLOR\[([^\]]+)\]", r"colorOf(\1)", out)
    if n_color < 5:
        raise SystemExit(f"{path}: only {n_color} COLOR lookups rewritten")

    # 3. the helpers, right after the maps they fall back on
    if ANCHOR not in out:
        raise SystemExit(f"{path}: anchor line not found")
    out = out.replace(ANCHOR, ANCHOR + "\n" + HELPERS, 1)

    # asserts: the thing we came to fix is actually gone
    assert FILTER not in out, path
    # The only COLOR[...] left in the file is the one inside colorOf itself.
    assert out.count("COLOR[") == HELPERS.count("COLOR["), path
    assert "function colorOf" in out, path

    tmp = path + ".tmp"
    io.open(tmp, "w", encoding="utf-8", newline="").write(out)
    os.replace(tmp, path)
    return f"filters {n_filter}, COLOR lookups {n_color}, helpers added"


if __name__ == "__main__":
    for deck in DECKS:
        print(os.path.basename(deck), "->", patch(deck))
    print("\nNow bump the deck cache tag and hard-refresh.")
