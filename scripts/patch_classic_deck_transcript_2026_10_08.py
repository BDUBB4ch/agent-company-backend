r"""One-off patch (2026-10-08, Barry: "i need every deck to be accurate with the others"): the classic deck
(index.html / app.js) replays each chat from the office's DB on agent select, same as the neo decks now do."""
import os
import subprocess

D = r"C:\Users\Owner\Desktop\AgentDashboard"


def patch(name, pairs):
    p = os.path.join(D, name)
    t = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (name, a[:50], t.count(a))
        t = t.replace(a, b)
    open(p, "w", encoding="utf-8").write(t)
    print("ok", name)


patch("app.js", [
(r'''function selectAgent(agentId) {
  state.currentAgentId = agentId;
  const agent = state.agents.find((a) => a.id === agentId);
  if (!agent) return;
''',
r'''function selectAgent(agentId) {
  state.currentAgentId = agentId;
  const agent = state.agents.find((a) => a.id === agentId);
  if (!agent) return;
  /* ONE RECORD FOR EVERY DECK (2026-10-08, Barry: "i need every deck to be
     accurate with the others. i have old messages in different decks"). The
     chat is replayed from the office's DB (/api/agents/{id}/transcript) -- the
     rows the agent actually remembers -- not from this browser's own copy.
     Skipped while a reply is in flight for this agent (the pending line would
     be lost); the local copy is rewritten from the server and is only the
     fallback when the backend is down. Home-window rows are tagged [home]. */
  if (!state.inFlight.has(agentId)) {
    fetch(BACKEND_URL + "/api/agents/" + agentId + "/transcript?limit=300")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j || !j.turns || state.currentAgentId !== agentId || state.inFlight.has(agentId)) return;
        state.chats[agentId] = j.turns.map((t) => ({
          role: t.role === "user" ? "user" : "agent",
          text: (t.channel === "personal" ? "[home] " : "") + (t.content || ""),
        }));
        persistChats();
        renderChatLog();
      })
      .catch(() => {});
  }
'''),
])
patch("index.html", [(r'''<script src="app.js?v=20260919a"''', r'''<script src="app.js?v=20261008a"''')])
r = subprocess.run(["node", "--check", os.path.join(D, "app.js")], capture_output=True, text=True)
print("node --check app.js:", "OK" if r.returncode == 0 else r.stderr[:400])
