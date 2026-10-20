"""Append the #442 Vor'Shara prompt (Barry: 'absolutely perfect in every way') to Elliot's exemplars, verbatim."""
import sqlite3, os
DB = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")
ADD = """

--- APPROVED (#442 -- Barry, 2026-09-23: "this was absolutely perfect in every way") ---
Place the woman from image 1 in her sanctum: an interior garden atrium with a reflecting pool, dark green marble columns banded in gold and wrapped in living vines, a veined marble slab desk, lush plants, warm golden light, distant hooded guards. She stands beside the pool, one hand trailing in the water, looking toward the camera. Keep her exact face, her four electric-blue eyes stacked in two vertical pairs, her long organic tendrils with gold rings, her greyish-white skin, her gold nose ring and chain, and her sheer pale-purple couture gown exactly as in image 1. Cinematic, hyper-realistic skin and fabric, film grain.
(That is the prompt exactly as the engine saw it: ONE picture of her, one place built from named materials, ONE warm light source, her canon details restated, one pose, a camera word. In your fence you write @lady-vor-shara-vel; the office turns the handle into "the woman from image 1". The render is approval 442 -- open it with look_at_render and study the light and the surfaces.)
"""
c = sqlite3.connect(DB)
row = c.execute("select content from facts where id=3953 and status='active'").fetchone()
assert row, "fact 3953 not active"
if "#442" not in row[0]:
    c.execute("update facts set content=? where id=3953", (row[0] + ADD,)); c.commit()
print("ok", len(c.execute("select content from facts where id=3953").fetchone()[0]))
