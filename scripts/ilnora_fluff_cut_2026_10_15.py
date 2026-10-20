"""2026-10-15, Barry: "If Ilnora has a bunch of overlap, thats fluff, we get rid of fluff". Deletes the repeated sections
across her four pinned craft docs (4702 make-video-masterfully, 4904 make-epic-videos, 5052 my-filmmaking, 4919 my-toolkit).
Rules: only true repeats or stale mechanics (now contradicted by my-toolkit) go; every Barry quote that exists nowhere else
stays; Elliot's notes (5469) untouched. One checklist (in make-epic-videos) gathers the unique items of the three it replaces.
Everything removed is written to data/ilnora_fluff_cut_2026-10-15/removed.md. Backs up the brain; every cut must match once."""
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "data/brain.db"
OUT = "data/ilnora_fluff_cut_2026-10-15/removed.md"


def between(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start)) if end else len(text)
    return text[i:j]


con = sqlite3.connect(DB)
doc = {fid: con.execute("SELECT content FROM facts WHERE id=? AND status='active'", (fid,)).fetchone()[0]
       for fid in (4702, 4904, 5052, 4919)}
con.close()
removed = []
new = dict(doc)


def cut(fid: int, piece: str, why: str, replace: str = "") -> None:
    if new[fid].count(piece) != 1:
        sys.exit(f"fact {fid}: piece not found exactly once ({why}) -- nothing changed")
    new[fid] = new[fid].replace(piece, replace, 1)
    removed.append(f"## fact {fid} -- {why}\n\n{piece.strip()}\n" + (f"\n(replaced with: {replace.strip()})\n" if replace.strip() else ""))


M, E, F, T = 4702, 4904, 5052, 4919

# ---- make-video-masterfully -------------------------------------------------------------------------------------
mech = between(doc[M], "## How the tool works (the real mechanics)", "## Directing your own parts")
keep_short_long = between(mech, "- **Short or Long.**", "- **It checks you instantly.**")
keep_budget = between(mech, "- **Card time is your budget.**", "- **When you make videos.**")
keep_when = between(mech, "- **When you make videos.**", None)
cut(M, mech, "tool mechanics: my-toolkit is the one source (parts, me, motion, pictures, plants, check_video, captions, "
    "lengths, checks); several lines were stale",
    replace="## Short, Long, budget, when\n\n" + keep_short_long + keep_budget + keep_when + "\n")
cut(M, " The picture of you does not know plant species -- a plant in your hands comes out generic -- so the plant gets "
       "its own picture.", "stale: her shots now carry the real plant photo (my-toolkit)")
cut(M, "- **Easy on the candles.** Barry: \"she uses a lotof candals, even some of the plants were candals\" -- a candle in "
       "almost every picture got old, and a plant picture that mentions a candle can come out half candle. Let the plant "
       "be the plant.\n", "repeat: candles quote is in make-epic-videos (camera and light) and her rules list")
cut(M, between(doc[M], "- Barry, 2026-10-14: \"we need other people", "- **Your own face is the hook.**"),
    "repeat: the 2026-10-14 quotes are in make-epic-videos (the scenes tell the story) and her rules list")
cut(M, between(doc[M], "- **Open loops:**", "- **Change what's on screen"), "repeat: open loops are in make-epic-videos")
cut(M, between(doc[M], "- **Specifics beat summaries:**", "- **End strong, then stop.**"),
    "repeat: 'concrete beats general' and the shape of a Short are in make-epic-videos")
cut(M, between(doc[M], "## What to put on screen", "## Caption and hashtags"),
    "repeat: what is on screen is in my-toolkit; picture writing is my-filmmaking's realism pass")
cut(M, between(doc[M], "## Before you call make_video: quick check", "## Picking the next video"),
    "merged into the one checklist in make-epic-videos")
cut(M, between(doc[M], "## Barry's words for your videos", None),
    "repeat: every line is word for word in office_note (FROM BARRY, on every video turn)")

# ---- make-epic-videos -------------------------------------------------------------------------------------------
cut(E, between(doc[E], "## Your own parts", "## Before you send it"),
    "repeat: directing her own parts is in make-video-masterfully")
old_check = between(doc[E], "## Before you send it", None)
cut(E, old_check, "replaced by the one checklist (this list + the unique items of the other two)", replace=(
    "## Before you send it -- the one checklist\n\n"
    "1. Every plant in it is one you have never made a video about.\n"
    "2. The first 3 seconds would stop a thumb.\n"
    "3. One topic, one promise -- kept at the end.\n"
    "4. With the sound off, the pictures alone tell the story; every picture shows what you are saying in that part.\n"
    "5. It climbs: each beat bigger than the last, a turn, a payoff. The last image and line echo the first.\n"
    "6. Something new on screen every 10 to 20 seconds; every place established before its close-ups.\n"
    "7. True and legend labeled honestly, with a quick warning where it matters.\n"
    "8. Every \"me\" part has a shot: outfit (first shot only), real place, hands, framing.\n"
    "9. One line in your notes on what the field already did -- and yours is different.\n"
    "10. Every picture passes the realism pass (my-filmmaking).\n"
    "11. A Long: every chapter has its own hook in and hook out.\n"
    "12. check_video passes (it counts the words for you) -- then make_video.\n"))

# ---- my-filmmaking -----------------------------------------------------------------------------------------------
cut(F, between(doc[F], "## Your crew: what makes each picture", "## 1. Different from everyone else"),
    "repeat + stale: what makes each picture is in my-toolkit (this said 5-second clips and 'cannot draw a plant')")
cut(F, "- Light changes when the story changes: dawn and gold for wonder, blue dusk and moonlight for mystery, storm light "
       "for danger, warm lamplight for the old ways. Inside one scene, the light stays the same.\n"
       "- Candles sparingly (Barry: \"she uses a lotof candals\").\n",
    "repeat: light moods and candles are in make-epic-videos", replace="- Inside one scene, the light stays the same.\n")
cut(F, between(doc[F], "## 5. Your own parts", "## 7. Longs"),
    "repeat: her own parts (make-video-masterfully) and the Short arc (make-epic-videos)")
cut(F, between(doc[F], "## Before you send", None), "merged into the one checklist in make-epic-videos")

# ---- my-toolkit --------------------------------------------------------------------------------------------------
cut(T, "It is checked again, then waits in line and builds after 6pm (my build slot), and lands",
    "stale: builds start as soon as the card is free (no 6pm slot since 2026-10-10)",
    replace="It is checked again, then waits in line and builds as soon as the card is free, and lands")

bak = f"data/brain_backup_before_ilnora_fluff_cut_{datetime.now():%Y-%m-%d_%H%M}.db"
shutil.copy2(DB, bak)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("# Removed from Ilnora's pinned docs, 2026-10-15 (Barry: \"we get rid of fluff\")\n\n" + "\n".join(removed))
con = sqlite3.connect(DB)
with con:
    for fid, text in new.items():
        if text != doc[fid]:
            con.execute("UPDATE facts SET content=? WHERE id=?", (text.replace("\n\n\n", "\n\n"), fid))
con.close()
print("backup:", bak)
for fid in (M, E, F, T):
    print(fid, len(doc[fid]), "->", len(new[fid]))
print("total", sum(len(doc[f]) for f in doc), "->", sum(len(new[f]) for f in new))
