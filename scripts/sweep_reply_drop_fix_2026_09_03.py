"""Sweep the reply-drop fix from neo-chamber to the remaining neo-* decks.

Barry, 2026-09-03: "i ask a question and instead of waiting on rply, i go to a new
agent screen, but the last one just drops their responce" -- plus his standing
"fix all, all the time" rule, so every deck gets it, not just the one he was on.

WHAT WAS WRONG (measured in-browser on chamber, not guessed):
  * `busy` was ONE GLOBAL flag, so while one agent answered the send button was
    disabled on EVERY other agent's screen. Walking off to another agent to get on
    with something meant he could not type at all, with no explanation.
  * pick() wipes #con-log, destroying the PROCESSING/RESONATING line, so returning
    mid-answer showed his question sitting alone.
The reply was never actually lost -- saveMsg files it under whoever said it and
pick() re-renders it -- but invisible and lost are the same thing from his seat.

SERIALIZED, not parallel: one GPU and one Bonsai slot. Two live turns collide there
and one silently falls back to the 9b (that collision produced Priya's fabricated
numbers on 2026-09-02). So a message typed while someone else is answering is
ACCEPTED, shown, and sent when the slot frees.

⚠️ WHY THIS SCRIPT IS SHAPED THIS WAY: in-place python patching of these deck files
has broken them TWICE (2026-08-29: one truncated a file to 0 bytes on a mid-write
encoding error, another over-cut a function and killed the whole script block). So:
every anchor is asserted before any write, the write goes to a temp file and is
renamed, a per-file backup is taken first, and the caller MUST node --check after.
"""
import io, os, shutil, sys

DECK_DIR = r"C:\Users\Owner\Desktop\AgentDashboard"
BACKUP_DIR = os.path.join(r"C:\Users\Owner\Desktop\AgentCompanyBackend", "data",
                          "backup_decks_before_replyfix_2026-09-03")

# label differs per deck; everything else is byte-identical across the four
DECKS = {
    "neo-v4.html": "PROCESSING",
    "neo-roll6.html": "PROCESSING",
    "neo-holo.html": "RESONATING",
    "neo-chamber-v1.html": "RESONATING",
}

OLD_HEAD = '''async function send() {
  const input = $("con-input");
  const text = input.value.trim();
  if (!text || busy || !current) return;
  input.value = "";
  busy = true; $("con-send").disabled = true;
  $("card-" + current.id).classList.add("thinking");'''

NEW_HEAD = '''/* ONE TURN AT A TIME, BUT NEVER SWALLOW A MESSAGE (Barry, 2026-09-03: "i ask a
   question and instead of waiting on rply, i go to a new agent screen, but the
   last one just drops their responce"). Swept from neo-chamber under his standing
   "fix all, all the time" rule.
   `busy` was ONE GLOBAL flag, so while one agent answered the send button was dead
   on EVERY other agent's screen -- and pick() wipes #con-log, so returning
   mid-answer showed his question sitting alone with no indicator. The reply was
   never actually lost; invisible and lost are just the same thing from his seat.
   SERIALIZED, not parallel: one GPU, one Bonsai slot -- two live turns collide
   there and one silently falls back to the 9b. */
let inflight = null;   /* { agentId, think } */
const queued = [];     /* [{agentId, text}] typed while the slot was busy */

function refreshSendBtn() {
  const b = $("con-send");
  if (b) b.disabled = !!(inflight && current && inflight.agentId === current.id);
}
/* Rebuild the pending line after a channel switch so an answer in progress never
   looks abandoned. Called from pick(). */
function showPending() {
  if (!inflight || !current || inflight.agentId !== current.id) return;
  inflight.think = addMsg("think", "__LABEL__", false);
}

function send() {
  const input = $("con-input");
  const text = input.value.trim();
  if (!text || !current) return;
  const agentId = current.id;
  if (inflight) {
    if (inflight.agentId === agentId) return;   /* same agent already answering */
    input.value = "";
    saveMsg(agentId, "user", text);             /* accepted, on the record */
    queued.push({ agentId, text });
    addMsg("user", text, false);
    addMsg("sys", "QUEUED >> " + ((FIRST[inflight.agentId] || inflight.agentId).toUpperCase())
      + " STILL ANSWERING \\u2014 THIS GOES NEXT", false);
    return;
  }
  input.value = "";
  deliver(agentId, text);
}

async function deliver(agentId, text, alreadyLogged) {
  inflight = { agentId: agentId, think: null };
  busy = true;                        /* kept -- drives this deck's own visuals */
  refreshSendBtn();
  $("card-" + agentId).classList.add("thinking");'''

OLD_MID = '''  addMsg("user", text);
  const think = addMsg("think", "__LABEL__", false);
  const agentId = current.id;'''

NEW_MID = '''  if (!alreadyLogged) {
    saveMsg(agentId, "user", text);
    if (current && current.id === agentId) addMsg("user", text, false);
  }
  showPending();
  const dropThink = () => {
    if (inflight && inflight.think) { inflight.think.remove(); inflight.think = null; }
  };'''

OLD_TAIL = '''  busy = false; $("con-send").disabled = false;
  const card = $("card-" + agentId);
  if (card) card.classList.remove("thinking");'''

NEW_TAIL = '''  const card = $("card-" + agentId);
  if (card) card.classList.remove("thinking");
  inflight = null;
  busy = false;
  refreshSendBtn();
  /* Drain whatever he typed while this turn held the slot. */
  {
    const nxt = queued.shift();
    if (nxt) {
      if (current && current.id === nxt.agentId) addMsg("sys", "SENDING NOW", false);
      else toast("\\u2192 sending your message to " + ((FIRST[nxt.agentId] || nxt.agentId).toUpperCase()));
      setTimeout(function () { deliver(nxt.agentId, nxt.text, true); }, 0);
    }
  }'''

OLD_PICK = "  for (const m of hist) addMsg(m.who, m.text, false);"
NEW_PICK = ("  for (const m of hist) addMsg(m.who, m.text, false);\n"
            "  /* mid-answer? put the pending line back, or a switch looks like a drop */\n"
            "  setTimeout(function () { showPending(); refreshSendBtn(); }, 0);")

# a failed send must land in the transcript too -- a toast is gone in seconds, and
# on return the turn would otherwise show a question with no answer and no reason
OLD_CATCH = '''  } catch (e) {
    think.remove();'''
NEW_CATCH = '''  } catch (e) {
    dropThink();
    saveMsg(agentId, "sys", "-- transmission failed: " + e.message + " --");'''


def one(fn, label):
    path = os.path.join(DECK_DIR, fn)
    src = io.open(path, encoding="utf-8").read()

    head = OLD_HEAD
    mid = OLD_MID.replace("__LABEL__", label)
    checks = [("head", head), ("mid", mid), ("tail", OLD_TAIL),
              ("catch", OLD_CATCH), ("pick", OLD_PICK)]
    for name, anchor in checks:
        n = src.count(anchor)
        if n != 1:
            return "SKIP  %-22s anchor '%s' found %d times (want 1)" % (fn, name, n)
    if src.count("think.remove();") < 1:
        return "SKIP  %-22s no think.remove() to rewrite" % fn

    out = src
    out = out.replace(head, NEW_HEAD.replace("__LABEL__", label), 1)
    out = out.replace(mid, NEW_MID, 1)
    out = out.replace(OLD_CATCH, NEW_CATCH, 1)
    out = out.replace("think.remove();", "dropThink();")   # the remaining success-path one
    out = out.replace(OLD_TAIL, NEW_TAIL, 1)
    out = out.replace(OLD_PICK, NEW_PICK, 1)

    # post-conditions -- prove the rewrite actually landed, never trust "it ran"
    for must in ["let inflight = null;", "async function deliver(", "showPending();",
                 "queued.push({ agentId, text });"]:
        if must not in out:
            return "FAIL  %-22s post-check missing: %s" % (fn, must)
    if "|| busy ||" in out:
        return "FAIL  %-22s global busy guard still present" % fn
    if "think.remove()" in out:
        return "FAIL  %-22s stale think.remove() left behind" % fn

    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(path, os.path.join(BACKUP_DIR, fn))
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    os.replace(tmp, path)
    return "OK    %-22s %+d chars (backup taken)" % (fn, len(out) - len(src))


if __name__ == "__main__":
    for fn, label in DECKS.items():
        print(one(fn, label))
    print("\nNow run node --check on each deck's extracted script. A clean exit "
          "here is NOT proof the page runs.")
