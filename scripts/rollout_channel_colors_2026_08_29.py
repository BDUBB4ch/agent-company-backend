"""Roll the chamber's channel-identity polish to the other decks.

Barry 2026-08-29: fixed channel colors ("business is always green") + the
green reply-waiting card pulse; then "yea, i may want to switch up my view
sometimes" -- so every deck he can land in behaves the same.

Per deck: append an override <style> chunk (never edits existing rules) with
--biz vars, the reply-waiting pulse for that deck's card class, and -- where
the deck isn't already green-native -- a green edge on agent messages and a
green target label. JS: the swept else-branch gains the card glow, pick()
clears it. neo.html (light) uses a deeper green so it reads on white.

Idempotent (skips files already containing 'bizpulse'); every anchor asserted;
temp-file + os.replace. The gold PERSONAL channel exists only in the chamber
(and its v1 checkpoint) by design -- nothing to recolor elsewhere.
"""
import os

DECKS = {
    # file: (card_class, biz, biz_dim, extra_css)
    "neo.html": (".trooper", "#12b76a", "rgba(18,183,106,.35)", ""),
    "neo-roll6.html": (".trooper", "#3ef58a", "rgba(62,245,138,.35)", ""),
    "neo-v4.html": (".card", "#3ef58a", "rgba(62,245,138,.35)",
        "  .msg.agent { border-color: rgba(62,245,138,.35) !important; box-shadow: inset 2px 0 0 var(--biz); }\n"
        "  #con-composer::before { color: var(--biz) !important; text-shadow: 0 0 10px var(--biz-dim); }\n"),
    "neo-holo.html": (".comp", "#3ef58a", "rgba(62,245,138,.35)",
        "  .msg.agent { border-color: rgba(62,245,138,.35) !important; box-shadow: inset 2px 0 0 var(--biz); }\n"
        "  #in-body::before { color: var(--biz) !important; text-shadow: 0 0 10px var(--biz-dim); }\n"),
    "neo-chamber-v1.html": (".comp", "#3ef58a", "rgba(62,245,138,.35)",
        "  .msg.agent { border-color: rgba(62,245,138,.35) !important; box-shadow: inset 2px 0 0 var(--biz); }\n"
        "  #in-body::before { color: var(--biz) !important; text-shadow: 0 0 10px var(--biz-dim); }\n"),
}

GLOW_ANCHOR = '      toast("\\u2709 " + ((typeof FIRST !== "undefined" && FIRST[agentId]) || agentId).toUpperCase()'
GLOW_LINE = '      const wcard = $("card-" + agentId); if (wcard) wcard.classList.add("reply-waiting");\n'

PICK_ANCHOR = """function pick(id) {
  current = agents.find((a) => a.id === id);
  if (!current) return;"""
PICK_NEW = PICK_ANCHOR + """
  const pkc = $("card-" + id); if (pkc) pkc.classList.remove("reply-waiting");"""

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "AgentDashboard")

for fname, (card, biz, dim, extra) in DECKS.items():
    path = os.path.join(BASE, fname)
    s = open(path, encoding="utf-8").read()
    if "bizpulse" in s:
        print(f"skip {fname} (already rolled)")
        continue
    orig = s

    css = ("\n  /* business-green channel identity + reply-waiting pulse "
           "(rolled out 2026-08-29) */\n"
           "  :root { --biz: " + biz + "; --biz-dim: " + dim + "; }\n"
           + extra +
           "  " + card + ".reply-waiting { border-color: var(--biz) !important; "
           "animation: bizpulse 1.6s ease-in-out infinite; }\n"
           "  @keyframes bizpulse { 0%, 100% { box-shadow: 0 0 6px var(--biz-dim); } "
           "50% { box-shadow: 0 0 16px var(--biz); } }\n")
    assert "</style>" in s, f"{fname}: no style block"
    s = s.replace("</style>", css + "</style>", 1)

    assert s.count(GLOW_ANCHOR) == 1, f"{fname}: toast anchor not found once"
    s = s.replace(GLOW_ANCHOR, GLOW_LINE + GLOW_ANCHOR)

    assert s.count(PICK_ANCHOR) == 1, f"{fname}: pick anchor not found once"
    s = s.replace(PICK_ANCHOR, PICK_NEW)

    assert s != orig
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(s)
    os.replace(tmp, path)
    print(f"rolled {fname} (+{len(s) - len(orig)} chars)")

print("rollout complete")
