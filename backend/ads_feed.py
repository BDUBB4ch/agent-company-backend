"""SEMI-LIVE ADS FEED FROM CSV EXPORTS.

Barry, 2026-08-30: "do the csv thing with amara for a semi live ads feed. Make
it go twice a day" -- after Amara told him she has no live ads data and wants
it.

WHY CSV AND NOT THE API. The Microsoft Advertising API needs a developer token
that requires Barry's own clicks at developers.ads.microsoft.com, plus an OAuth
build. Until that exists the honest middle ground is his own export: he drops
the CSV, this reads it, and the agents cite REAL numbers WITH the date they
were exported. Nothing is invented and nothing is guessed.

HOW IT WORKS, and every part of it is deliberate:
- **He drops a CSV in `drop/ads/`.** Desktop shortcut territory -- the same
  drop-folder idea as TEACH DROP, no coding, no dashboard, no chat.
- **Column matching is by NAME, not position.** Microsoft's export column order
  and exact wording vary by report type and locale, so anything positional
  would silently mis-read. Unmatched columns are ignored, not guessed at.
- **NO MODEL CALLS ANYWHERE.** Same rule as bizwatch: this can never trip the
  VRAM eviction chain, and it can run while a render owns the GPU.
- **The file is kept, not consumed.** Processed CSVs move to `drop/ads/_done/`
  so a bad parse is always re-runnable against the original.
- **Twice a day** (his instruction) -- and a fresh drop is picked up on the
  next check regardless, so he never has to wait twelve hours.
- **The date is part of the data.** Every published line says which export it
  came from, so an agent quoting it can say how old it is. A stale number
  presented as live is worse than no number.

Output goes through `bizwatch.set_ads_note()` -> the always-on `business-pulse`
fact, which the seven commercial seats already carry. Amara reads it without
any new plumbing.
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import io
import os
import re
import shutil
import time

import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADS_DROP = os.path.join(_ROOT, "drop", "ads")
ADS_DONE = os.path.join(ADS_DROP, "_done")
STATE_KEY = "ads_feed_state"          # app_settings: last file + when

# Twice a day, his instruction. The loop checks far more often than that so a
# CSV he drops at 10am is live by 10:15, not at midnight.
REFRESH_INTERVAL_SECONDS = 12 * 3600
CHECK_EVERY_SECONDS = 15 * 60
STARTUP_DELAY_SECONDS = 180

# Column aliases. Microsoft exports differ between the UI download, the
# scheduled-report email and the Editor, so every field lists the spellings
# actually seen rather than one canonical name.
FIELDS = {
    "campaign": ("campaign", "campaign name"),
    "impressions": ("impressions", "impr", "impr."),
    "clicks": ("clicks",),
    "spend": ("spend", "cost", "amount spent"),
    "conversions": ("conversions", "conv.", "conv"),
    "revenue": ("revenue", "conversion revenue", "conv. value", "sales"),
    "ctr": ("ctr", "click-through rate"),
    "cpc": ("avg. cpc", "average cpc", "cpc", "avg cpc"),
    "date": ("date", "day", "gregorian date"),
}


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower()).strip(":")


def _num(v) -> float:
    """Parse a spreadsheet cell into a number. Handles $1,234.56, 12%, (45)
    for negatives, and the em-dash/blank cells Microsoft uses for 'no data'."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s or s in {"-", "--", "—", "N/A", "n/a"}:
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {"-", ".", "-."}:
        return 0.0
    try:
        n = float(s)
    except ValueError:
        return 0.0
    return -n if neg else n


def _read_rows(path: str):
    """Rows as dicts keyed by normalised header.

    Microsoft prepends report metadata lines before the real header, so the
    header row is FOUND rather than assumed to be line 1 -- a fixed index here
    would parse the title line as column names and yield nothing.
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read()
    lines = text.splitlines()
    header_i, header = None, None
    for i, line in enumerate(lines[:25]):
        cells = next(csv.reader(io.StringIO(line)), [])
        norm = [_norm(c) for c in cells]
        # a real header carries at least one metric column plus a label column
        if any(n in FIELDS["impressions"] + FIELDS["clicks"] + FIELDS["spend"]
               for n in norm) and len(norm) >= 2:
            header_i, header = i, norm
            break
    if header_i is None:
        return [], []
    reader = csv.reader(io.StringIO("\n".join(lines[header_i + 1:])))
    rows = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue
        rows.append({header[j]: cells[j] for j in range(min(len(header), len(cells)))})
    return header, rows


def _col(header: list[str], key: str):
    for alias in FIELDS[key]:
        if alias in header:
            return alias
    return None


def parse_csv(path: str) -> dict | None:
    """Totals + per-campaign lines from one export. None if unreadable."""
    header, rows = _read_rows(path)
    if not rows:
        return None
    c_camp = _col(header, "campaign")
    c_imp, c_clk = _col(header, "impressions"), _col(header, "clicks")
    c_spend, c_conv = _col(header, "spend"), _col(header, "conversions")
    c_rev, c_date = _col(header, "revenue"), _col(header, "date")
    if not (c_imp or c_clk or c_spend):
        return None

    total = {"impressions": 0.0, "clicks": 0.0, "spend": 0.0,
             "conversions": 0.0, "revenue": 0.0}
    per: dict[str, dict] = {}
    dates = []
    for r in rows:
        # skip the export's own "Total" line -- adding it would double count
        label = (r.get(c_camp) or "").strip() if c_camp else ""
        if label.lower().startswith(("total", "grand total")):
            continue
        vals = {"impressions": _num(r.get(c_imp)) if c_imp else 0.0,
                "clicks": _num(r.get(c_clk)) if c_clk else 0.0,
                "spend": _num(r.get(c_spend)) if c_spend else 0.0,
                "conversions": _num(r.get(c_conv)) if c_conv else 0.0,
                "revenue": _num(r.get(c_rev)) if c_rev else 0.0}
        for k, v in vals.items():
            total[k] += v
        if label:
            d = per.setdefault(label, dict.fromkeys(vals, 0.0))
            for k, v in vals.items():
                d[k] += v
        if c_date and (r.get(c_date) or "").strip():
            dates.append(r[c_date].strip())
    if not any(total.values()):
        return None
    return {"total": total, "per_campaign": per, "rows": len(rows),
            "dates": (min(dates), max(dates)) if dates else None,
            "source": os.path.basename(path)}


def _fmt(d: dict) -> str:
    t = d["total"]
    imp, clk, spend = t["impressions"], t["clicks"], t["spend"]
    ctr = (clk / imp * 100) if imp else 0.0
    cpc = (spend / clk) if clk else 0.0
    conv, rev = t["conversions"], t["revenue"]
    lines = []
    if d.get("dates"):
        lines.append(f"Covers {d['dates'][0]} to {d['dates'][1]}.")
    lines.append(
        f"{imp:,.0f} impressions, {clk:,.0f} clicks ({ctr:.2f}% CTR), "
        f"${spend:,.2f} spent (${cpc:.2f} CPC), {conv:,.0f} conversions"
        + (f", ${rev:,.2f} revenue" if rev else "") + ".")
    if rev and spend:
        lines.append(f"ROAS {rev / spend:.2f}x on this export.")
    top = sorted(d["per_campaign"].items(), key=lambda kv: -kv[1]["spend"])[:4]
    for name, v in top:
        c = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        lines.append(f"  - {name}: ${v['spend']:,.2f}, {v['clicks']:,.0f} "
                     f"clicks ({c:.2f}% CTR), {v['conversions']:,.0f} conv.")
    lines.append("Source: his own Microsoft Ads CSV export "
                 f"({d['source']}) -- cite it with that date; it is a "
                 "snapshot, not a live API.")
    return "\n".join(lines)


def _newest_csv() -> str | None:
    os.makedirs(ADS_DROP, exist_ok=True)
    files = [os.path.join(ADS_DROP, f) for f in os.listdir(ADS_DROP)
             if f.lower().endswith(".csv")]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def ingest_once(force: bool = False) -> dict:
    """Read the newest dropped CSV, publish it into the pulse, archive it."""
    import bizwatch
    os.makedirs(ADS_DONE, exist_ok=True)
    path = _newest_csv()
    if not path:
        return {"ok": False, "why": "no CSV in drop/ads"}

    if not force:
        try:
            import json
            st = json.loads(memory.get_setting(STATE_KEY) or "{}")
        except Exception:
            st = {}
        if (st.get("last_file") == os.path.basename(path)
                and time.time() - float(st.get("at", 0)) < REFRESH_INTERVAL_SECONDS):
            return {"ok": False, "why": "already ingested recently"}

    parsed = parse_csv(path)
    if not parsed:
        # keep it where it is -- an unreadable file is a thing to look at,
        # not to quietly file away
        return {"ok": False, "why": f"could not read {os.path.basename(path)}"}

    note = _fmt(parsed)
    bizwatch.set_ads_note(note)
    try:
        # Full refresh pulls the store API and is skipped under Offline
        # Mode; reading a CSV off disk is not a network action, so fall
        # back to updating just the ads section in place. Without this
        # the numbers never reach Amara whenever the privacy switch is on
        # -- and it was on when this was built.
        if not bizwatch.refresh(force=True):
            bizwatch.refresh_ads_section()
    except Exception as e:
        print(f"[ads] pulse publish failed: {type(e).__name__}: {e}")

    import json
    memory.set_setting(STATE_KEY, json.dumps(
        {"last_file": os.path.basename(path), "at": time.time(),
         "total": parsed["total"]}))
    try:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(path, os.path.join(
            ADS_DONE, f"{stamp}_{os.path.basename(path)}"))
    except OSError:
        pass
    print(f"[ads] published {os.path.basename(path)}: "
          f"{parsed['total']['clicks']:.0f} clicks, "
          f"${parsed['total']['spend']:.2f}")
    return {"ok": True, "source": parsed["source"], "total": parsed["total"],
            "note": note}


LIVE_EVERY_SECONDS = 30 * 60      # "she should see every change that happens"


async def run_ads_loop():
    """LIVE FIRST, CSV as the fallback.

    Barry, 2026-08-30: "no csv, live, she should see every change that
    happens." So every 30 minutes this pulls the real numbers straight from
    the Microsoft Advertising API (ads_api) -- no file, no export, nothing
    for him to do. Microsoft's own reporting lags roughly 1-3 hours behind
    clicks regardless of how often anyone asks, so 30 minutes is already
    finer-grained than the data itself.

    The CSV path stays as the safety net: if the token ever expires, the
    API is down, or Offline Mode is on, a dropped export still works.
    """
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        live_ok = False
        try:
            import ads_api
            r = await asyncio.to_thread(ads_api.refresh_pulse)
            live_ok = bool(r.get('ok'))
            if live_ok:
                t = r['total']
                print(f"[ads] live: {t['clicks']:.0f} clicks, "
                      f"${t['spend']:.2f} spend")
            else:
                print(f"[ads] live pull unavailable: {r.get('why')}")
        except Exception as e:
            print(f"[ads] live error: {type(e).__name__}: {e}")
        if not live_ok:
            try:
                await asyncio.to_thread(ingest_once)   # CSV fallback
            except Exception as e:
                print(f"[ads] csv fallback error: {type(e).__name__}: {e}")
        await asyncio.sleep(LIVE_EVERY_SECONDS)
