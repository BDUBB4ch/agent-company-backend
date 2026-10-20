"""Sweep the cross-channel reply-bleed fix (neo-chamber, 2026-08-29) into
every other deck that carries the same send()/addMsg() pattern.

Barry: "fix all, all the time." The bug: a reply that lands after switching
agents rendered AND saved under whichever channel was open. Fix per deck:
  1. addMsg's save goes through saveMsg(current.id, ...) -- one write path.
  2. send() files the reply under the ANSWERING agent (saveMsg(agentId, ...)),
     renders only if that channel is still on screen, else toasts.
  3. The error line renders only if still on screen, else toasts.

Every replacement is asserted to land exactly once per file; writes go to a
temp file then os.replace (never truncate-in-place -- neo-v4 died that way
once). classic app.js was checked and is already correct; neo-chamber.html
already fixed by hand.
"""
import os

FILES = ["neo.html", "neo-v4.html", "neo-roll6.html", "neo-holo.html",
         "neo-chamber-v1.html"]

OLD_SAVE = """  if (save !== false && current && who !== "think") {
    const key = "neo_" + current.id;
    const hist = JSON.parse(localStorage.getItem(key) || "[]");
    hist.push({ who, text });
    localStorage.setItem(key, JSON.stringify(hist.slice(-60)));
  }"""
NEW_SAVE = """  if (save !== false && current && who !== "think") saveMsg(current.id, who, text);"""

SAVEMSG_FN = """/* Transcript write for a SPECIFIC agent -- so an in-flight reply files
   under who actually said it, not whichever channel is open when it lands
   (swept from neo-chamber, 2026-08-29). */
function saveMsg(agentId, who, text) {
  const key = "neo_" + agentId;
  const hist = JSON.parse(localStorage.getItem(key) || "[]");
  hist.push({ who, text });
  localStorage.setItem(key, JSON.stringify(hist.slice(-60)));
}
function addMsg(who, text, save) {"""
ADDMSG_ANCHOR = "function addMsg(who, text, save) {"

OLD_REPLY = """    think.remove();
    addMsg("agent", data.reply || "[no reply]");"""
NEW_REPLY = """    think.remove();
    /* Reply files under WHO SAID IT; renders only if their channel is still
       on screen (cross-channel bleed fix, 2026-08-29). */
    saveMsg(agentId, "agent", data.reply || "[no reply]");
    if (current && current.id === agentId) {
      addMsg("agent", data.reply || "[no reply]", false);
    } else {
      toast("\\u2709 " + ((typeof FIRST !== "undefined" && FIRST[agentId]) || agentId).toUpperCase()
        + " answered \\u2014 reply saved in their channel");
    }"""

# The catch-line wording differs per deck; handle each variant.
# NOTE: the dashes in the JS sources are LITERAL em-dash characters.
_EM = "—"
ERR_VARIANTS = [
    '    addMsg("sys", "SYSTEM ALERT >> TRANSMISSION FAILED: " + e.message, false);',
    '    addMsg("sys", "' + _EM + ' TRANSMISSION FAILED: " + e.message + " ' + _EM + '", false);',
    '    addMsg("sys", "' + _EM + ' transmission failed: " + e.message + " ' + _EM + '", false);',
]

for fname in FILES:
    s = open(fname, encoding="utf-8").read()
    orig = s

    if "function saveMsg" in s:
        print(f"skip {fname} (already patched)")
        continue

    assert s.count(OLD_SAVE) == 1, f"{fname}: addMsg save block not found once"
    s = s.replace(OLD_SAVE, NEW_SAVE)

    assert s.count(ADDMSG_ANCHOR) == 1, f"{fname}: addMsg anchor not found once"
    s = s.replace(ADDMSG_ANCHOR, SAVEMSG_FN)

    assert s.count(OLD_REPLY) == 1, f"{fname}: reply block not found once"
    s = s.replace(OLD_REPLY, NEW_REPLY)

    err_hits = [(v, s.count(v)) for v in ERR_VARIANTS if s.count(v)]
    assert len(err_hits) == 1 and err_hits[0][1] == 1, \
        f"{fname}: error line variants found: {err_hits}"
    old_err = err_hits[0][0]
    new_err = ("    if (current && current.id === agentId) {\n"
               "  " + old_err.strip() + "\n"
               "    } else {\n"
               "      toast(\"\\u26a0 \" + ((typeof FIRST !== \"undefined\" && FIRST[agentId]) || agentId) + \": transmission failed\");\n"
               "    }")
    s = s.replace(old_err, new_err)

    assert s != orig
    tmp = fname + ".tmp"
    open(tmp, "w", encoding="utf-8").write(s)
    os.replace(tmp, fname)
    print(f"patched {fname} (+{len(s) - len(orig)} chars)")

print("sweep complete")
