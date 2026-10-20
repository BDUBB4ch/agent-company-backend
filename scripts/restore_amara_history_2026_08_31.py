"""Barry's call, 2026-08-31: put the history back.

I had edited text inside HIS OWN message (turn 1997), inside Amara's stored
turns, and inside her permanent journal -- then deleted turns. The standing
rule for his scripts has always been SUBSTITUTE, NEVER EDIT; it applies to
history too and I ignored it.

This restores, byte-for-byte, from data/backup_amara_body_2026-08-31/:
  * facts 1635, 1813, 1823  -> original content
  * turns 1994, 1997        -> original text (1997 is HIS message)
  * turns 2003, 2004, 2008  -> re-inserted at their original ids

DELIBERATELY NOT RESTORED, per his option 2 ("leave the body ruling in the
appearance fact where a correction actually belongs"):
  * fact 1682 my-appearance -- keeps his 2026-08-31 ruling and the wardrobe
    block. That is the ONE place a correction lives now.
  * fact 1825 -- content was never edited, only status flipped to superseded.
    It is intact and reactivatable from the Brain tab.

Backups are not deleted. Re-running is safe.
"""

import io
import json
import os
import sqlite3
import sys

DB = "data/brain.db"
BK = "data/backup_amara_body_2026-08-31"
RESTORE_FACTS = ("1635", "1813", "1823")


def _load(name):
    with io.open(os.path.join(BK, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()

    # ---- facts -----------------------------------------------------------
    facts = _load("facts_before.json")
    for fid in RESTORE_FACTS:
        original = facts[fid]["content"]
        cur.execute("update facts set content=? where id=?", (original, int(fid)))
        (now,) = cur.execute("select content from facts where id=?", (int(fid),)).fetchone()
        assert now == original, "fact %s did not restore byte-for-byte" % fid
        print("fact %-5s restored  (%d chars)" % (fid, len(original)))

    # ---- turns that were EDITED -------------------------------------------
    # NOTE: ids 1989-1998 no longer exist at all -- the 20-message thread
    # auto-summarizer fired during testing and reset the raw log. So these are
    # re-inserted, not updated.
    for row in _load("conversations_before.json"):
        if cur.execute("select 1 from conversations where id=?", (row["id"],)).fetchone():
            cur.execute("update conversations set content=? where id=?",
                        (row["content"], row["id"]))
        else:
            ts = cur.execute(
                "select timestamp from conversations where agent_id=? and id>? "
                "order by id asc limit 1", (row["agent_id"], row["id"])).fetchone()
            cur.execute(
                "insert into conversations (id, agent_id, role, content, timestamp) "
                "values (?,?,?,?,?)",
                (row["id"], row["agent_id"], row["role"], row["content"],
                 ts[0] if ts else ""))
        got = cur.execute("select content from conversations where id=?",
                          (row["id"],)).fetchone()
        assert got and got[0] == row["content"], "turn %s did not restore" % row["id"]
        print("turn %-5s restored  (%s)" % (row["id"], row["role"]))

    # ---- turns that were DELETED ------------------------------------------
    deleted = [r for r in _load("thread_tail_before_cleanup.json")
               if r["id"] in (2003, 2004)]
    deleted.append(_load("turn_2008_slender_reply.json"))
    for row in deleted:
        if cur.execute("select 1 from conversations where id=?", (row["id"],)).fetchone():
            print("turn %-5s already present" % row["id"])
            continue
        # Timestamps were not captured in the backup. Borrow the nearest
        # surviving turn's timestamp so ordering stays correct -- the text is
        # what matters and it is exact.
        ts = cur.execute(
            "select timestamp from conversations where agent_id=? and id<? "
            "order by id desc limit 1", (row["agent_id"], row["id"])).fetchone()
        cur.execute(
            "insert into conversations (id, agent_id, role, content, timestamp) "
            "values (?,?,?,?,?)",
            (row["id"], row["agent_id"], row["role"], row["content"],
             ts[0] if ts else ""))
        print("turn %-5s re-inserted (%s)" % (row["id"], row["role"]))

    db.commit()

    left = cur.execute(
        "select count(*) from conversations where agent_id='business' "
        "and id between 1990 and 2010").fetchone()[0]
    print("\nturns present in her thread 1990-2010:", left)


if __name__ == "__main__":
    sys.exit(main())
