"""Append Barry's multi-character cuts rule to Elliot's stills lesson (fact 3954)."""
import sqlite3, os
DB = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")
ADD = """

## Several characters in one scene -- use cuts (Barry, 2026-09-23)
Your opening picture holds ONE character, two at most -- never three or more.
Open on whoever the moment belongs to. Bring the others in with CUTS in your
timed beats: "CUT TO: close on @Tazz...", an over-the-shoulder, a reaction
shot. Each cut says who is now in frame. A crowded opening picture is the
render that has frozen Barry's PC, and coverage cut between people reads
better on screen anyway.
"""
c = sqlite3.connect(DB)
row = c.execute("select content from facts where id=3954 and status='active'").fetchone()
assert row, "fact 3954 not active"
if "use cuts (Barry, 2026-09-23)" not in row[0]:
    c.execute("update facts set content=? where id=3954", (row[0] + ADD,))
    c.commit()
print("ok", len(c.execute("select content from facts where id=3954").fetchone()[0]))
