"""Load the 2026-09-26 email training shelf into the brain (Derek + Vivian).

Barry, 2026-09-26: "i need you to train vivian on how to do it" / "derek needs real skill on this
too" / "did we give Derek real modern day writing and marketing skills?" / "i need high Level every time".

CATEGORIES (his rule: categorize everything, scope by capability):
  how-vivian-designs-an-email.md      -> private:Creative   (names her design_email tool -- only she has it)
  email-design-that-sells.md          -> domain:creative    (design craft; Vivian + Ilnora's creative shelf)
  writing-the-email-content-sheet.md  -> private:Marketing  (Derek's own process -- "you write the sheet")
  email-marketing-now-what-changed.md -> domain:marketing   (market knowledge; the marketing shelf)
Each is an on-demand skill (source_name ends .md): title in the index, body via read_skill / recall.
Re-running supersedes the previous copy instead of stacking duplicates.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

SHELF = {
    "how-vivian-designs-an-email.md": "private:Creative",
    "email-design-that-sells.md": "domain:creative",
    "writing-the-email-content-sheet.md": "private:Marketing",
    "email-marketing-now-what-changed.md": "domain:marketing",
    # Barry: "she needs to be a high level visual artist and design engineer" / "not just for emails,
    # for anything i want her to do" -> her main creative shelf, all her work.
    "creative/visual-artistry-at-a-master-level.md": "domain:creative",
    "creative/photographic-render-engineering.md": "domain:creative",
    "creative/design-engineering-systems-and-production.md": "domain:creative",
    # Barry approved (2026-09-26): Elliot's own film cinematography doc, knowledge only.
    "film/cinematography-for-the-crew.md": "private:MovieDirector",
}


def main() -> None:
    for fname, cat in SHELF.items():
        path = os.path.join(ROOT, "knowledge", *(fname.split("/") if "/" in fname else ("email", fname)))
        fname = fname.split("/")[-1]
        if not os.path.exists(path):
            print(f"MISSING {fname} -- not loaded")
            continue
        text = open(path, encoding="utf-8").read().strip()
        head = text.splitlines()[:2]
        if len(head) < 2 or not head[1].startswith("USE WHEN:"):
            print(f"BAD FORMAT {fname}: line 2 must be the USE WHEN: routing line -- not loaded")
            continue
        with memory.get_db() as conn:
            n = conn.execute("UPDATE facts SET status='superseded' WHERE source_name=? AND status='active'",
                             (fname,)).rowcount
        memory.add_fact(cat, text, source_name=fname)
        with memory.get_db() as conn:
            fid = conn.execute("SELECT id FROM facts WHERE source_name=? AND status='active' ORDER BY id DESC LIMIT 1",
                               (fname,)).fetchone()["id"]
        print(f"loaded {fname} -> {cat} as fact {fid} ({len(text):,} chars){' (superseded ' + str(n) + ')' if n else ''}")


if __name__ == "__main__":
    main()
