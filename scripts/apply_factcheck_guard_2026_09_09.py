"""Wire factcheck into email_cadence (draft) and dispatch (send). One-shot,
asserts anchors, refuses to run twice. Barry, 2026-09-09: "he should only post
real stuff and only for whats there, dont make up shit."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, "backend")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    s = open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, f"{fn}: anchor not found exactly once: {old[:70]!r}"
        s = s.replace(old, new)
    tmp = p + ".tmp"
    open(tmp, "w", encoding="utf-8").write(s)
    os.replace(tmp, p)
    print(f"  patched {fn}")


if "factcheck" in open(os.path.join(B, "dispatch.py"), encoding="utf-8").read():
    sys.exit("already applied")

patch("email_cadence.py", [
    (
        "import dispatch\n",
        "import dispatch\nimport factcheck\n",
    ),
    (
        '''    reply = (r.json() or {}).get("reply") or ""
    parsed = _parse_reply(reply)
    if not parsed:
        _log(f"{kind}: reply did not parse as subject+body ({len(reply)} chars) -- skipped")
        return {"ok": False, "why": "unparseable", "reply": reply[:300]}
    subject, body = parsed
    content = f"{subject}\\n\\n{body}"
    aid = memory.queue_for_approval(AGENT_ID, "email", content)''',
        '''    data = r.json() or {}
    reply = data.get("reply") or ""
    tool_calls = data.get("tool_calls") or []
    parsed = _parse_reply(reply)
    if not parsed:
        _log(f"{kind}: reply did not parse as subject+body ({len(reply)} chars) -- skipped")
        return {"ok": False, "why": "unparseable", "reply": reply[:300]}
    subject, body = parsed
    content = f"{subject}\\n\\n{body}"

    # ONLY REAL STUFF (Barry, 2026-09-09, after #207 told customers Microlife
    # was back in stock while it was out): the draft is checked against the
    # LIVE store before it is queued. A draft written with no tool calls is
    # not accepted at all -- #207's trace was tool_calls [] despite the brief.
    # One re-run with the report in front of him; if it still fails it is
    # queued with the FACT-CHECK banner on top, which dispatch refuses to send.
    check = factcheck.check_email(content)
    if not tool_calls or not check["ok"]:
        why = ("You called NO tools -- nothing in this draft was read from the store. "
               if not tool_calls else "")
        _log(f"{kind}: draft rejected by fact-check "
             f"(tools={len(tool_calls)}, problems={len(check['problems'])}) -- re-running once")
        nudge = ("\\n\\n[OFFICE FACT-CHECK -- your draft was NOT accepted. " + why
                 + "Findings:\\n" + factcheck.report(check)
                 + "\\nRewrite it. Only real stuff, and only what is there: every product "
                   "you name must be read with read_product NOW and described as in stock "
                   "only if the store shows instock; say nothing about a 'new guide' unless "
                   "you link the real post from browse_site what='posts'; no percentages or "
                   "figures you did not read from the store or the offer codes. Return the "
                   "corrected email in the same format, subject line first.]")
        async with httpx.AsyncClient(timeout=600) as cx:
            r2 = await cx.post("http://127.0.0.1:8420/api/chat",
                               json={"agent_id": AGENT_ID, "message": prompt + nudge, "task": True})
        r2.raise_for_status()
        data2 = r2.json() or {}
        parsed2 = _parse_reply(data2.get("reply") or "")
        if parsed2:
            subject, body = parsed2
            content = f"{subject}\\n\\n{body}"
            tool_calls = data2.get("tool_calls") or []
            check = factcheck.check_email(content)
        if not tool_calls or not check["ok"]:
            _log(f"{kind}: STILL failing after re-run -- queued with the fact-check banner")
            content = factcheck.banner(check) + content
        else:
            _log(f"{kind}: re-run passed the fact-check ({len(tool_calls)} tool calls)")
    aid = memory.queue_for_approval(AGENT_ID, "email", content)''',
    ),
])

patch("dispatch.py", [
    (
        "import omnisend_client\n",
        "import omnisend_client\nimport factcheck\n",
    ),
    (
        '''    # THE CAP. Tests are exempt (they reach only Barry). A refusal is recorded''',
        '''    # ONLY REAL STUFF (Barry, 2026-09-09). Approved bytes still go out verbatim,
    # but not if they are false: #207 told customers Microlife was back in
    # stock while the store said outofstock. Re-checked HERE, at send time,
    # against the live store -- stock can change between draft and send day.
    # A banner from the drafting check is a hard stop too. Tests are exempt
    # (they reach only Barry). Nothing is marked dispatched, so a corrected
    # approval can go later.
    if not test_to and row.get("action_type") == "email":
        if (row.get("content") or "").lstrip().startswith(factcheck.BANNER):
            return _record(approval_id, destination, "blocked",
                           "Not sent: this draft carries the office fact-check banner. "
                           "Fix the claims and approve a corrected draft.")
        chk = factcheck.check_email(row.get("content") or "")
        if not chk["ok"]:
            return _record(approval_id, destination, "blocked",
                           "Not sent -- fact-check failed at send time:\\n" + factcheck.report(chk))

    # THE CAP. Tests are exempt (they reach only Barry). A refusal is recorded''',
    ),
])
print("done")
