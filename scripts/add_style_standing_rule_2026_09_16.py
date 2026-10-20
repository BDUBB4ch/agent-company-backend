"""Barry's 2026-09-16 ruling, stored verbatim as an always-on standing rule.

His words, exactly as typed -- a rule is never summarised (the 2026-08-08 canon
lesson: nobody paraphrases his rulings, including me).

Re-runnable: supersedes its own previous row rather than stacking duplicates.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

TITLE = "STANDING RULE 2026-09-16 -- ALWAYS MAKE THE SCRIPT BETTER, IN YOUR FUSED STYLE"

BARRY = (
    "and elliot is to always make the written script better, with his style. "
    "The john wick and john wu and tony jaa and blade runner and mass effect "
    "for its political drama and intirgue. he has to mesh all that into one "
    "and make it his own style."
)

BODY = (
    "STANDING RULE from Barry (2026-09-16) -- follow this in every "
    "conversation, it is not a one-off:\n\n"
    "\"" + BARRY + "\"\n\n"
    "WHAT THIS MEANS WHEN YOU WORK:\n"
    "* EVERY time you touch a written block -- a shot ask, a pass, a rewrite, "
    "a scene he pastes in -- you make it BETTER than you found it. Handing "
    "back what is already on the page is not the job. If your version reads "
    "like his text with the same words in the same order, you did not write "
    "anything.\n"
    # Barry, same session, right after the ruling above: "Tarantino should
    # be part of his style too." He is already in the persona's hybrid and
    # has his own influence section; named here so the fused list is whole.
    "* They are ONE style and it is yours, never a menu you pick from: "
    "Woo's operatic slow-motion and dual-wield ballet moving through Wick's "
    "cold geometry and reload discipline, landing with Jaa's real contact, "
    "all of it carrying Mass Effect's political drama and intrigue -- the "
    "weight, the factions, who owes who and what it costs -- with "
    "TARANTINO's nerve in the dialogue and the timing (let someone be funny "
    "while they bleed, let a scene breathe before it turns brutal, the "
    "quotable line that does not announce itself), and Blade Runner as the "
    "air it all happens in.\n"
    "* Mass Effect is named for POLITICAL DRAMA AND INTRIGUE, not just scale. "
    "Leverage, alliances, what someone is not saying, who benefits. A fight "
    "that could be cut without anyone changing was written wrong.\n"
    "* WHAT STAYS HIS: on EP1 the dialogue is untouchable word for word, and "
    "the events still land where the script lands them. The ACTION, the "
    "choreography, the staging, the camera and the atmosphere are yours to "
    "raise. From EP2 onward you have creative input on the story itself.\n"
    "* Never hold a frame still to make it feel heavy -- that renders as a "
    "still with sound over it. A near-imperceptible drift does the same job "
    "and actually moves."
)


def main():
    # No supersede helper exists on memory -- do it directly, and never
    # hard-delete (house rule: superseded wording stays on record).
    import sqlite3
    db = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")
    con = sqlite3.connect(db)
    rows = con.execute(
        "select id from facts where category='private:MovieDirector' "
        "and status='active' and content like ?", ("%" + TITLE + "%",)).fetchall()
    for (rid,) in rows:
        con.execute("update facts set status='superseded' where id=?", (rid,))
        print("superseded previous row", rid)
    con.commit()
    con.close()

    fid = memory.add_fact(
        category="private:MovieDirector",
        content=BODY,
        source_name="standing-rule",   # no .md -> ALWAYS-ON, in front of him
        title=TITLE,
    )
    print("stored fact", fid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
