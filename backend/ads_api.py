"""LIVE MICROSOFT ADS NUMBERS -- submit, poll, download, publish.

Barry, 2026-08-30: "i dont want to drop a file. it should be automatic and
totally live."

Microsoft's Reporting service is not a query API -- you SUBMIT a report, POLL
until it is built, then DOWNLOAD a zipped CSV. That is three round trips for
one number, which is why this is a module and not a one-liner.

The neat part: the download IS a CSV, so it feeds straight into the parser
already written for his manual exports (ads_feed.parse_csv). Both routes end
in the same place -- the always-on `business-pulse` fact the commercial seats
carry -- so nothing downstream cares which one produced the numbers.

- Auth comes from ads_auth (refresh-token flow, no secret -- the Ads API has
  no app-only path; see that module).
- ⚠️ Real outbound call, so Offline Mode is checked by the caller.
- Read-only by construction: the only operations here are SubmitGenerateReport
  / PollGenerateReport / download. Nothing in this file can change a campaign,
  a budget or a bid.
"""
from __future__ import annotations

import io
import os
import re
import time
import zipfile

import httpx

import ads_auth

REPORTING = ("https://reporting.api.bingads.microsoft.com/Api/Advertiser/"
             "Reporting/v13/ReportingService.svc")
NS = "https://bingads.microsoft.com/Reporting/v13"
ARRAYS = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"

COLUMNS = ("TimePeriod", "CampaignName", "Impressions", "Clicks", "Spend",
           "Conversions", "Revenue")


def _envelope(action: str, body: str, tok: str, dev: str,
              customer_id: str, account_id: str) -> bytes:
    return f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
<s:Header xmlns="{NS}">
<Action mustUnderstand="1">{action}</Action>
<AuthenticationToken>{tok}</AuthenticationToken>
<DeveloperToken>{dev}</DeveloperToken>
<CustomerId>{customer_id}</CustomerId>
<CustomerAccountId>{account_id}</CustomerAccountId>
</s:Header>
<s:Body>{body}</s:Body></s:Envelope>""".encode()


def _post(action: str, body: str, tok: str, dev: str, cid: str, aid: str) -> str:
    r = httpx.post(REPORTING, timeout=90,
                   content=_envelope(action, body, tok, dev, cid, aid),
                   headers={"Content-Type": "text/xml; charset=utf-8",
                            "SOAPAction": action})
    return r.text


def _fault(text: str) -> str | None:
    if "Fault" not in text:
        return None
    code = re.search(r"<(?:a:)?Code>(\d+)</(?:a:)?Code>", text)
    msg = re.search(r"<(?:a:)?Message>([^<]*)</(?:a:)?Message>", text)
    return f"{code.group(1) if code else '?'}: {msg.group(1) if msg else text[:200]}"


# ReportTimePeriod is a strict enum -- "LastThirtyDays" is NOT a member and
# fails deserialization. Valid ones include Today, Yesterday, LastSevenDays,
# LastFourWeeks, ThisMonth, LastMonth.
def fetch(period: str = "LastFourWeeks", timeout_s: int = 240) -> dict:
    """Pull a campaign performance report. Returns {'ok', 'csv'|'why'}."""
    tok, err = ads_auth.access_token()
    if not tok:
        return {"ok": False, "why": err}
    dev = ads_auth._env("MSADS_DEVELOPER_TOKEN")
    cid = ads_auth._env("MSADS_CUSTOMER_ID")
    aid = ads_auth._env("MSADS_ACCOUNT_ID")
    if not (dev and cid and aid):
        return {"ok": False, "why": "MSADS_DEVELOPER_TOKEN / CUSTOMER_ID / "
                                    "ACCOUNT_ID not all set in .env"}

    cols = "".join(
        f"<CampaignPerformanceReportColumn>{c}</CampaignPerformanceReportColumn>"
        for c in COLUMNS)
    submit = f"""<SubmitGenerateReportRequest xmlns="{NS}">
<ReportRequest i:type="CampaignPerformanceReportRequest">
<ExcludeColumnHeaders>false</ExcludeColumnHeaders>
<ExcludeReportFooter>true</ExcludeReportFooter>
<ExcludeReportHeader>true</ExcludeReportHeader>
<Format>Csv</Format>
<ReportName>agent-pulse</ReportName>
<ReturnOnlyCompleteData>false</ReturnOnlyCompleteData>
<Aggregation>Daily</Aggregation>
<Columns>{cols}</Columns>
<Scope><AccountIds xmlns:a="{ARRAYS}"><a:long>{aid}</a:long></AccountIds></Scope>
<Time><PredefinedTime>{period}</PredefinedTime></Time>
</ReportRequest></SubmitGenerateReportRequest>"""

    t = _post("SubmitGenerateReport", submit, tok, dev, cid, aid)
    f = _fault(t)
    if f:
        return {"ok": False, "why": f"submit failed -- {f}"}
    m = re.search(r"<ReportRequestId>([^<]+)</ReportRequestId>", t)
    if not m:
        return {"ok": False, "why": f"no report id returned: {t[:200]}"}
    req_id = m.group(1)

    deadline = time.time() + timeout_s
    url = None
    while time.time() < deadline:
        time.sleep(6)
        poll = (f'<PollGenerateReportRequest xmlns="{NS}">'
                f"<ReportRequestId>{req_id}</ReportRequestId>"
                f"</PollGenerateReportRequest>")
        t = _post("PollGenerateReport", poll, tok, dev, cid, aid)
        f = _fault(t)
        if f:
            return {"ok": False, "why": f"poll failed -- {f}"}
        status = re.search(r"<Status>([^<]+)</Status>", t)
        status = status.group(1) if status else "?"
        if status == "Error":
            return {"ok": False, "why": "Microsoft reported an error building "
                                        "the report"}
        if status == "Success":
            u = re.search(r"<ReportDownloadUrl[^>]*>([^<]+)</ReportDownloadUrl>", t)
            # a Success with no URL legitimately means NO DATA in the window
            if not u:
                return {"ok": True, "csv": "", "empty": True,
                        "why": "report built but held no rows for this period"}
            url = u.group(1).replace("&amp;", "&")
            break
    if not url:
        return {"ok": False, "why": f"timed out after {timeout_s}s"}

    r = httpx.get(url, timeout=120, follow_redirects=True)
    if r.status_code != 200:
        return {"ok": False, "why": f"download failed ({r.status_code})"}
    data = r.content
    # Microsoft returns a zip; be tolerant if that ever changes to raw CSV
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = z.namelist()[0]
            csv_text = z.read(name).decode("utf-8-sig", errors="replace")
    except zipfile.BadZipFile:
        csv_text = data.decode("utf-8-sig", errors="replace")
    return {"ok": True, "csv": csv_text, "rows": csv_text.count("\n")}


def refresh_pulse(period: str = "LastFourWeeks") -> dict:
    """Pull live numbers and publish them to the agents' business pulse."""
    import memory
    import bizwatch
    import ads_feed
    if memory.is_offline_mode():
        return {"ok": False, "why": "offline mode is on -- this is a real "
                                    "outbound call, so it is skipped"}
    got = fetch(period)
    if not got.get("ok"):
        return got
    if got.get("empty"):
        return {"ok": False, "why": got.get("why")}

    tmp = os.path.join(ads_feed.ADS_DROP, "_live_report.csv")
    os.makedirs(ads_feed.ADS_DROP, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(got["csv"])
    parsed = ads_feed.parse_csv(tmp)
    os.remove(tmp)
    if not parsed:
        return {"ok": False, "why": "report downloaded but could not be parsed"}

    note = ads_feed._fmt(parsed).replace(
        "Source: his own Microsoft Ads CSV export (_live_report.csv) -- cite "
        "it with that date; it is a snapshot, not a live API.",
        "Source: pulled LIVE from the Microsoft Advertising API just now.")
    bizwatch.set_ads_note(note)
    if not bizwatch.refresh(force=True):
        bizwatch.refresh_ads_section()
    return {"ok": True, "total": parsed["total"],
            "campaigns": list(parsed["per_campaign"])}


if __name__ == "__main__":
    import json
    print(json.dumps(refresh_pulse(), indent=1, default=str))


def summary(period: str = "LastSevenDays") -> str:
    """Plain-English totals + per-day lines from fetch(). For the agents'
    ads_summary tool (2026-09-08). Read-only reporting; nothing is changed."""
    import csv, io
    r = fetch(period)
    if not r.get("ok"):
        return f"Microsoft Ads report failed: {r.get('why') or r}"
    rows = list(csv.DictReader(io.StringIO(r.get("csv", ""))))
    if not rows:
        return f"Microsoft Ads: no rows for {period}."
    def n(v):
        try:
            return float(str(v).replace(",", "") or 0)
        except ValueError:
            return 0.0
    imp = sum(n(x.get("Impressions")) for x in rows); clk = sum(n(x.get("Clicks")) for x in rows)
    spend = sum(n(x.get("Spend")) for x in rows); conv = sum(n(x.get("Conversions")) for x in rows)
    rev = sum(n(x.get("Revenue")) for x in rows)
    camps = sorted({x.get("CampaignName", "?") for x in rows})
    out = [f"MICROSOFT ADS -- {period} (live API, {len(rows)} day-rows, campaign(s): {', '.join(camps)})",
           f"impressions {imp:,.0f} | clicks {clk:,.0f} (CTR {100*clk/imp if imp else 0:.2f}%) | "
           f"spend ${spend:,.2f} (CPC ${spend/clk if clk else 0:.2f}) | conversions {conv:,.0f} | revenue ${rev:,.2f}"]
    # WHEN it last spent (Barry, 2026-09-26). Sophie read a 7-day total as
    # "ads are running" when every dollar was spent before his 09-22 pause.
    import datetime as _dt
    spent_days = sorted(str(x.get("TimePeriod", ""))[:10] for x in rows if n(x.get("Spend")) > 0)
    if spent_days:
        last = spent_days[-1]
        try:
            idle = (_dt.date.today() - _dt.date.fromisoformat(last)).days
        except ValueError:
            idle = 0
        if idle >= 2:
            out.append(f"LAST SPEND: {last} ({idle} days ago). NOTHING has spent since -- the campaigns are "
                       f"NOT running now; these totals are history, not current activity.")
        else:
            out.append(f"LAST SPEND: {last} -- the campaigns are spending now.")
    if clk and not conv:
        out.append("READ: clicks landed and nothing converted -- the leak is on the site or the "
                   "offer, not reach. Walk the checkout and look at what the landing pages show.")
    for x in rows[-14:]:
        out.append(f"  {x.get('TimePeriod')} [{x.get('CampaignName', '?')}]: {n(x.get('Impressions')):.0f} impr, "
                   f"{n(x.get('Clicks')):.0f} clicks, ${n(x.get('Spend')):.2f}, {n(x.get('Conversions')):.0f} conv")
    return "\n".join(out)
