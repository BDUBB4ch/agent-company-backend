r"""One-off patch (2026-10-08, Barry: "i need every deck to be accurate with the others. i have old messages in
different decks"): the neo decks replay each chat from the office's DB (/api/agents/{id}/transcript) instead of
their own localStorage copy. The local copy is rewritten from the server on every open and is only the fallback
when the backend is down. Three open paths: neo-chamber (1), neo-holo (2). Anchored edits, node --check after."""
import os

D = r"C:\Users\Owner\Desktop\AgentDashboard"

LOADER = r'''
/* ONE RECORD FOR EVERY DECK (2026-10-08, Barry: "i need every deck to be accurate
   with the others. i have old messages in different decks"). The chat is replayed
   from the office's DB (/api/agents/{id}/transcript) -- the same rows the agent
   actually remembers -- not from this browser's own copy, which was written as
   messages flew by and never reconciled (a thread cleared in the DB, or a message
   sent from another deck or another origin, left every deck with a different past).
   The local copy is rewritten from the server on every open and is only the
   fallback when the backend is down. Home-window rows are tagged [home]. */
async function loadTranscript(id, fallback, afterLoad) {
  let rows = null;
  try {
    const r = await fetch(API + "/api/agents/" + id + "/transcript?limit=300");
    if (r.ok) rows = (await r.json()).turns || [];
  } catch (e) { rows = null; }
  if (rows === null) {
    for (const m of fallback) addMsg(m.who, m.text, false, m.t || 0);
    if (!fallback.length) addMsg("sys", "— channel open (office offline: local copy) —", false);
  } else {
    $("con-log").innerHTML = "";
    const mirror = [];
    for (const t of rows) {
      const who = t.role === "user" ? "user" : "agent";
      const stamp = t.timestamp ? (Date.parse(t.timestamp) || 0) : 0;
      const text = (t.channel === "personal" ? "[home] " : "") + (t.content || "");
      addMsg(who, text, false, stamp);
      mirror.push({ who: who, text: text, t: stamp });
    }
    try { localStorage.setItem("neo_" + id, JSON.stringify(mirror.slice(-300))); } catch (e) {}
    if (!rows.length) addMsg("sys", "— channel open · " + (FIRST[id] || "").toLowerCase() + " on deck —", false);
  }
  if (afterLoad) afterLoad();
}
'''


def patch(name, pairs):
    p = os.path.join(D, name)
    t = open(p, encoding="utf-8").read()
    for a, b, n in pairs:
        assert t.count(a) == n, (name, a[:50], t.count(a))
        t = t.replace(a, b)
    open(p, "w", encoding="utf-8").write(t)
    print("ok", name)


# neo-chamber: one open path
patch("neo-chamber.html", [
(r'''  const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
  for (const m of hist) addMsg(m.who, m.text, false, m.t || 0);''',
 r'''  const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
  loadTranscript(id, hist, function () { if (window.bwFold) window.bwFold($("con-log")); });''', 1),
(r'''  if (window.bwFold) window.bwFold($("con-log"));
  if (!hist.length) addMsg("sys", "— channel open · " + (FIRST[id] || "").toLowerCase() + " on deck —", false);
  /* THE MESSAGE ARRIVES IN THE CHAT''',
 r'''  /* (fold + the empty-channel line now happen inside loadTranscript, after the server replay) */
  /* THE MESSAGE ARRIVES IN THE CHAT''', 1),
(r'''function addMsg(who, text, save, stamp) {''', LOADER + r'''function addMsg(who, text, save, stamp) {''', 1),
])

# neo-holo: two open paths
patch("neo-holo.html", [
(r'''  const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
  for (const m of hist) addMsg(m.who, m.text, false, m.t || 0);''',
 r'''  const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
  loadTranscript(id, hist, function () { if (window.bwFold) window.bwFold($("con-log")); });''', 1),
(r'''  if (window.bwFold) window.bwFold($("con-log"));
  /* mid-answer? put the pending line back, or a switch looks like a drop */
  setTimeout(function () { showPending(); refreshSendBtn(); }, 0);
  if (!hist.length) addMsg("sys", "— channel open · " + (FIRST[id] || "").toLowerCase() + " on deck —", false);''',
 r'''  /* mid-answer? put the pending line back, or a switch looks like a drop */
  setTimeout(function () { showPending(); refreshSendBtn(); }, 0);
  /* (fold + the empty-channel line now happen inside loadTranscript, after the server replay) */''', 1),
(r'''    const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
    for (const m of hist) addMsg(m.who, m.text, false);
    if (!hist.length) addMsg("sys", "— channel open · " + (FIRST[id] || "").toLowerCase() + " on deck —", false);''',
 r'''    const hist = JSON.parse(localStorage.getItem("neo_" + id) || "[]");
    loadTranscript(id, hist, null);''', 1),
(r'''function addMsg(who, text, save, stamp) {''', LOADER + r'''function addMsg(who, text, save, stamp) {''', 1),
])
