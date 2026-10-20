"""Record the 2026-08-13 EH/Silution repricing in the GG price-list skill (disk + fact)."""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
path = os.path.join(ROOT, "knowledge", "bdubb-products", "global-garden-wholesale-pricelist.md")
s = open(path, encoding="utf-8").read()

OLD = ("A store-wide price-vs-SRP audit is the\n"
       "obvious Amara project; surface per-product math, Barry decides.")
NEW = """A store-wide audit ran 2026-08-13 and THE WORST WERE FIXED THE SAME DAY with
Barry's approval (restore files: data/restore/cali_pro_* and eh_kits_3part_*):
Cali Pro Grow+Bloom (qt 8.00->12.95, 1gal 23->24.95, 2.5gal->56.95, 6gal->97.95,
AB pairs 23.95/47.95/109.95/189.95), both Kickstarter kits 136/139->149.95, EH
3-part Grow/Bloom 12.95/24.95/55.95/107.95 and Micro 14.95/28.95/64.95/124.95,
Silution 250ml 55.95->68.00 (Barry's number; he had it at 80 before Winter's
low anchor). Prices were set MID-MARKET, verified against Hydrobuilder (gal
24.65, 6gal sale 92.54), Growers Depot (qt 12.99, gal 25.99) and Global Garden's
own PUBLIC retail site -- which sells Cali Pro at 8/23/52/95, i.e. AT OR BELOW
the wholesale it charges Barry. GG retails against its own wholesale customers;
do not try to beat GG's site on EH price, it is impossible above cost. The SRP
column in this list proved FICTION for EH online (real market runs ~50-60
percent of SRP) -- never price to SRP without a live web check first. Remaining
audit still open: the Bionova line vs Barry's Oct plan, and small Rediroot items."""

if OLD in s:
    s = s.replace(OLD, NEW)
    open(path, "w", encoding="utf-8").write(s)
    print("disk updated")
elif "FIXED THE SAME DAY" in s:
    print("already recorded")
else:
    raise SystemExit("anchor not found -- inspect the file")

db = sqlite3.connect(memory.DB_PATH if hasattr(memory, "DB_PATH")
                     else os.path.join(ROOT, "data", "brain.db"))
row = db.execute("SELECT id FROM facts WHERE source_name='global-garden-wholesale-pricelist.md' "
                 "AND status='active'").fetchone()
db.execute("UPDATE facts SET content=? WHERE id=?", (s, row[0]))
db.commit()
print(f"fact {row[0]} updated, {len(s)} chars")
