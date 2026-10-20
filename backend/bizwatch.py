"""bizwatch -- the business agents' standing awareness of the store.

Barry, 2026-08-29: "build out agents monitoring the business... they should
even tell me if i need to update my plugs." And his ruling the same day:
business NEVER enters the personal channel -- so this writes to the WORK side
only: one always-on fact in business:bdubbgrows that Victor, Priya, Amara,
Marcus, Derek and Vivian carry into every message (Taliyah and Elliot are
excluded from that category already).

Design rules, in the order they'd hurt if broken:
- NO model calls anywhere in this module. It is a mechanical snapshot, so it
  can never trip the one-big-thing VRAM eviction chain, and it can run while
  Barry is mid-conversation. The AGENTS do the analyzing when asked (the
  ads-performance-analysis skill tells them how); this module only reports.
- ONE fact, upserted in place by (source_name, category). It must never
  accumulate copies -- an always-on shelf that grows daily is the exact
  failure the 2026-08-03 brain cleanup existed to fix.
- Offline Mode skips the refresh entirely (two outbound HTTPS calls live
  here). The previous snapshot stays in the brain, clearly dated.
- Failures degrade to a log line and keep the old fact. A dead store API at
  3am must never break chat at 9am.

Data sources (both via store.py's read-only WooCommerce key, no new creds):
- /orders        -> 30-day and 7-day revenue, AOV, top sellers
- /system_status -> WP/WC versions + plugins with updates available
  (verified 2026-08-29: the Read key sees active_plugins with version and
  version_latest -- probe: scripts/probe_system_status_2026_08_29.py)
"""

import asyncio
import json
import sqlite3
import re
import time

import memory
import store

SOURCE_NAME = "business-pulse"          # no .md on purpose: ALWAYS-ON
CATEGORY = "business:bdubbgrows"
LAST_REFRESH_KEY = "bizwatch_last_refresh"   # app_settings, unix seconds
JSON_KEY = "bizwatch_json"              # same snapshot, structured, for the dashboard desk card
# Manually-verified ads status (no ads API access yet -- Bing Ads needs a
# developer token Barry hasn't set up). Until then, a HUMAN-verified dated
# note is the honest middle ground between "no radar" and pretending: the
# agents cite it WITH its date instead of assuming. Set via set_ads_note().
ADS_NOTE_KEY = "bizwatch_ads_note"


def set_ads_note(text: str):
    """Record a dated, human-verified ads status line for the pulse.
    Refresh the pulse afterwards (refresh(force=True)) to publish it."""
    stamped = f"[verified {time.strftime('%Y-%m-%d')}] {text.strip()}"
    memory.set_setting(ADS_NOTE_KEY, stamped)
    return stamped
REFRESH_INTERVAL_SECONDS = 24 * 3600
CHECK_EVERY_SECONDS = 3600
STARTUP_DELAY_SECONDS = 120              # let the stack settle first
MAX_FACT_CHARS = 2600                    # always-on budget discipline
# 25, was 10 (Barry, 2026-08-28: "maybe the agents should give me the
# updates as well" -- an agent that says "...and 3 more" can't actually
# give him the updates). 25 rows ~= +450 chars worst case, inside the cap.
MAX_PLUGINS_LISTED = 25


def _plugin_updates():
    """(wp_version, wc_version, [(name, current, latest), ...]) or raises."""
    data = store._get("/system_status")
    env = data.get("environment", {}) or {}
    behind = []
    for p in data.get("active_plugins", []) or []:
        cur, latest = p.get("version"), p.get("version_latest")
        if cur and latest and cur != latest:
            behind.append((p.get("name", "?"), cur, latest))
    behind.sort(key=lambda t: t[0].lower())
    return env.get("wp_version"), env.get("version"), behind


def _sales_stats(days: int) -> dict:
    """Structured mirror of store.sales_summary's counting rules (completed +
    processing only -- this store's failed orders are mostly card-testing
    fraud). Kept here rather than refactoring store.py: don't break what works.
    Day-precision 'after' means store._get's TTL cache dedupes these calls
    against sales_summary's within the same run."""
    after = time.strftime("%Y-%m-%dT00:00:00", time.gmtime(time.time() - days * 86400))
    orders = []
    page = 1
    while page <= 5:
        batch = store._get("/orders", {"after": after, "per_page": 100, "page": page})
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    counted_statuses = {"completed", "processing"}
    revenue, counted, by_status, product_totals = 0.0, 0, {}, {}
    for o in orders:
        status = o.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if status not in counted_statuses:
            continue
        counted += 1
        revenue += store._money(o.get("total"))
        for item in (o.get("line_items") or []):
            name = item.get("name", "?")
            entry = product_totals.setdefault(name, {"qty": 0, "revenue": 0.0})
            entry["qty"] += int(item.get("quantity") or 0)
            entry["revenue"] += store._money(item.get("total"))

    top = sorted(product_totals.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:5]
    return {
        "days": days,
        "since": after[:10],
        "revenue": round(revenue, 2),
        "orders": counted,
        "aov": round(revenue / counted, 2) if counted else 0.0,
        "status_mix": by_status,
        "top": [{"name": n, "revenue": round(t["revenue"], 2), "qty": t["qty"]} for n, t in top],
    }


def _first_lines(text: str, n: int) -> str:
    return "\n".join(text.splitlines()[:n])


def build_pulse() -> str:
    """Compose the snapshot text. Raises on failure; caller decides."""
    today = time.strftime("%Y-%m-%d")
    sales30 = store.sales_summary(30)
    sales7 = store.sales_summary(7)
    wp_ver, wc_ver, behind = _plugin_updates()

    ads_note = memory.get_setting(ADS_NOTE_KEY)

    lines = [
        f"BUSINESS PULSE -- auto-refreshed {today} (mechanical snapshot; no agent wrote this)",
        "Live operational data for the whole business team. When Barry asks how things",
        "are going, ANALYZE it -- what it means, what changed, what to watch -- never",
        "just recite the numbers.",
        "",
        "== MICROSOFT ADS ==",
        (ads_note if ads_note else "No ads data yet."),
        "This is a SNAPSHOT, not a live API -- it comes from a Microsoft Ads CSV",
        "Barry exports himself (ads_feed.py reads drop/ads/ twice a day). The numbers",
        "are real; they are only as fresh as the export date shown, so SAY the date",
        "when you cite them and never imply you are watching ads in real time.",
        "",
        "== SALES, LAST 30 DAYS ==",
        # First 7 lines = revenue/AOV/status mix/top sellers; drops the long footnote.
        _first_lines(sales30, 7),
        "",
        "== SALES, LAST 7 DAYS ==",
        _first_lines(sales7, 3),
        "",
        f"== SITE HEALTH == (WordPress {wp_ver}, WooCommerce {wc_ver})",
    ]
    if behind:
        lines.append(
            f"{len(behind)} active plugins have updates available -- worth telling Barry"
            " when the site comes up. Updates are HIS to run, never ours:"
        )
        for name, cur, latest in behind[:MAX_PLUGINS_LISTED]:
            lines.append(f"  - {name}: {cur} -> {latest}")
        if len(behind) > MAX_PLUGINS_LISTED:
            lines.append(f"  ...and {len(behind) - MAX_PLUGINS_LISTED} more.")
    else:
        lines.append("All active plugins are current.")

    pulse = "\n".join(lines)
    if len(pulse) > MAX_FACT_CHARS:
        pulse = pulse[: MAX_FACT_CHARS - 15].rstrip() + "\n[truncated]"
    return pulse


def _upsert(content: str):
    db = sqlite3.connect(memory.DB_PATH)
    try:
        row = db.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
            (SOURCE_NAME, CATEGORY),
        ).fetchone()
        if row:
            db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
            db.commit()
            return row[0]
    finally:
        db.close()
    memory.add_fact(
        category=CATEGORY,
        content=content,
        source_name=SOURCE_NAME,
        title="BUSINESS PULSE -- live store + site health snapshot",
    )
    return None


def refresh_ads_section() -> bool:
    """Rewrite ONLY the ads section of the existing pulse fact, no network.

    Why this exists (2026-08-30): `refresh()` bails out entirely under Offline
    Mode because it pulls the store API -- correct for sales, wrong for ads.
    Ads data now comes from a CSV Barry exports himself (ads_feed.py), which is
    a local file read, so it must still reach the agents when the privacy
    switch is on. This edits the section in place from the fact already stored;
    it never calls out, and it never touches the sales half.
    """
    note = memory.get_setting(ADS_NOTE_KEY)
    if not note:
        return False
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT content FROM facts WHERE source_name = 'business-pulse' "
            "AND status = 'active' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return False
    text = row["content"]
    marker = "== MICROSOFT ADS =="
    if marker not in text:
        text = text.rstrip() + f"\n\n{marker}\n{note}\n"
    else:
        head, _, tail = text.partition(marker)
        # the ads block runs to the next "== SECTION ==" or end of document
        rest = re.split(r"\n(?==\= )", tail, maxsplit=1)
        text = head + marker + "\n" + note + "\n" + \
            ("\n" + rest[1] if len(rest) > 1 else "")
    if len(text) > MAX_FACT_CHARS:
        text = text[:MAX_FACT_CHARS]
    _upsert(text)
    print(f"[bizwatch] ads section updated in place ({len(text)} chars)")
    return True


def refresh(force: bool = False) -> bool:
    """One refresh attempt. Returns True if the fact was rewritten."""
    if memory.is_offline_mode():
        print("[bizwatch] offline mode -- skipping refresh, keeping last snapshot")
        return False
    if not store.is_configured():
        print("[bizwatch] store keys not set -- skipping")
        return False
    if not force:
        last = memory.get_setting(LAST_REFRESH_KEY)
        if last and (time.time() - float(last)) < REFRESH_INTERVAL_SECONDS:
            return False
    try:
        pulse = build_pulse()
        snapshot = {
            "refreshed_at": time.strftime("%Y-%m-%d %H:%M"),
            "sales30": _sales_stats(30),
            "sales7": _sales_stats(7),
        }
        wp_ver, wc_ver, behind = _plugin_updates()
        snapshot["site"] = {
            "wp": wp_ver,
            "wc": wc_ver,
            "updates": [{"name": n, "current": c, "latest": l} for n, c, l in behind],
        }
    except Exception as e:
        print(f"[bizwatch] refresh failed, keeping previous snapshot: {type(e).__name__}: {e}")
        return False
    _upsert(pulse)
    memory.set_setting(JSON_KEY, json.dumps(snapshot))
    memory.set_setting(LAST_REFRESH_KEY, str(time.time()))
    print(f"[bizwatch] pulse refreshed ({len(pulse)} chars)")
    return True


def latest_snapshot() -> dict | None:
    """The structured snapshot for the dashboard desk card, or None."""
    raw = memory.get_setting(JSON_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def run_bizwatch_loop():
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await asyncio.to_thread(refresh)
        except Exception as e:
            print(f"[bizwatch] loop error: {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
