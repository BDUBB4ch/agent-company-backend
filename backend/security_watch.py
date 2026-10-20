"""Sophie's standing security check -- Barry, 2026-09-07: "i dont want any of
them in my build only when my agent searches and still they cant get into my
build. fix it or allow sophie to do security at all time."

So she checks it every 15 minutes, forever, mechanically. NO MODEL CALL: this
is all local reads (netstat, source files, settings), so it can never trip the
VRAM eviction chain and can never hallucinate a breach.

WHAT IT WATCHES, and why each one is here rather than a nice idea:

1. EXPOSED PORTS. Measured 2026-09-07: `python -m http.server 8765` binds ::
   (every interface), so the dashboard was reachable from any device on his
   network while the backend, Ollama and Bonsai were correctly on 127.0.0.1.
   That is exactly "they can get into my build", and it was true for months.
   Anything of his listening on a non-loopback address is a finding.

2. BANNED SEARCH ENGINES IN THE SOURCE. "duck duck go period." Bing was
   deleted, not disabled, so this fires if any engine host reappears in the
   backend -- a re-added fallback, a pasted snippet, a bad merge.

3. GOOGLE ANYWHERE IN THE BUILD. "i hate google, i dont want them nowhere near
   any of my private shit." Any google/gstatic/googleapis/analytics host in
   the backend or the dashboard front end is a finding. Business FACTS that
   discuss Google Ads policy are not code and are not scanned.

4. THE OFFICE BROWSER PROFILE. The isolated Firefox profile is what keeps his
   signed-in Google out of the office window. If its user.js goes missing or
   Safe Browsing (which pings Google) is switched back on, that is a finding.

5. OUTBOUND HOST DRIFT. A snapshot of every external host the backend can
   reach is kept in data/security_baseline.json. A NEW host appearing is a
   finding -- not automatically wrong, but he decides, not the code.
"""
import json
import os
import re
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_DATA = os.path.join(_REPO, "data")
_DASH = os.path.join(os.path.dirname(_REPO), "AgentDashboard")
_BASELINE = os.path.join(_DATA, "security_baseline.json")
_PROFILE = os.path.join(_DATA, "office_browser_profile", "user.js")

# His ports. Anything here on a non-loopback address is exposed.
_OUR_PORTS = {8420: "backend", 8765: "dashboard", 8811: "bonsai",
              11434: "ollama", 8188: "comfyui", 8189: "mystudio comfyui",
              8009: "kev"}
_LOOPBACK = {"127.0.0.1", "::1"}

# Banned outright -- his standing rule, not a preference.
_BANNED = re.compile(
    r"google|gstatic|googleapis|googletagmanager|google-analytics|doubleclick|"
    r"youtube\.com/embed|bing\.com|search\.yahoo|yandex", re.I)

# Allowed to appear in code: his own Microsoft ADS account (his business data,
# his instruction) and the schema URLs its SOAP client needs. Not search.
_ADS_OK = re.compile(r"(ads|bingads|reporting\.api\.bingads|login\.microsoftonline|"
                     r"schemas)\.(microsoft|xmlsoap|microsoftonline)\.com", re.I)


def _listening() -> list[dict]:
    """Every listener on one of his ports, with its bind address."""
    ps = ("Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
          "Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        rows = json.loads(out) if out else []
        if isinstance(rows, dict):
            rows = [rows]
    except Exception:  # noqa: BLE001
        return []
    return [r for r in rows if int(r.get("LocalPort", 0)) in _OUR_PORTS]


def _source_files() -> list[str]:
    files = []
    for root in (_HERE, _DASH):
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "venv", "node_modules",
                                        "assets", "_full", "_v1_offices",
                                        "avatars_robots_backup")]
            for fn in filenames:
                if fn.endswith((".py", ".js", ".html", ".css")):
                    files.append(os.path.join(dirpath, fn))
    return files


def _hosts_in(text: str) -> set[str]:
    return {h.lower() for h in re.findall(r"https?://([a-zA-Z0-9._-]+)", text)}


# THE REAL SEARCH ENGINE (2026-09-07, Barry: "No google EVER!! duck duck go
# ONLY!!!!"). user.js's `browser.urlbar.placeholderName = "DuckDuckGo"` is only
# the grey TEXT in the URL bar -- the earlier check read that and called the
# browser clean while `search.json.mozlz4` had Google as the live default.
# This decodes that file (mozLz4 = 8-byte magic + LE32 size + LZ4 block) and
# reads the recorded default engine. Pure python, no dependency.
_SEARCH_STORE = os.path.join(_DATA, "office_browser_profile", "search.json.mozlz4")
_POLICIES = r"C:\Program Files\Mozilla Firefox\distribution\policies.json"


def _lz4_block(src: bytes, out_size: int) -> bytes:
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = token & 0x0F
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        for k in range(ml):
            out.append(out[start + k])
    return bytes(out[:out_size])


def office_default_engine() -> str | None:
    """The engine id Firefox will actually search with in the office profile."""
    try:
        raw = open(_SEARCH_STORE, "rb").read()
        if raw[:8] != b"mozLz40\0":
            return None
        import struct
        size = struct.unpack("<I", raw[8:12])[0]
        data = json.loads(_lz4_block(raw[12:], size).decode("utf-8"))
        return data.get("metaData", {}).get("defaultEngineId")
    except Exception:  # noqa: BLE001
        return None


def check() -> list[str]:
    """Plain-English findings. Empty list means clean. Never raises."""
    findings: list[str] = []

    # 1. exposed ports
    try:
        for r in _listening():
            addr = str(r.get("LocalAddress", ""))
            port = int(r.get("LocalPort", 0))
            if addr not in _LOOPBACK and addr not in ("", None):
                findings.append(
                    f"EXPOSED PORT -- {_OUR_PORTS.get(port, port)} is listening on "
                    f"{addr}:{port}, not 127.0.0.1. Anyone on the network can reach it. "
                    f"Bind it to 127.0.0.1.")
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY CHECK ERROR -- could not read listening ports: {e}")

    # 2 + 3. banned hosts in code
    hosts_seen: set[str] = set()
    try:
        for path in _source_files():
            try:
                text = open(path, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            hosts_seen |= _hosts_in(text)
            rel = os.path.relpath(path, os.path.dirname(_REPO))
            for m in set(_BANNED.findall(text)):
                # These files mention the banned hosts only to explain the ban
                # (research_tools.py's blocklist, the channel-label data labels
                # in llm_router.py and store.py) -- not to call them.
                if os.path.basename(path) in (
                    "web_search.py", "security_watch.py", "research_tools.py",
                    "llm_router.py", "store.py",
                    # 2026-10-07: the test panel QUOTES results (e.g. his Merchant Center "Google free Shopping
                    # listings" numbers, which he allowed) -- content, not a call
                    "test-panel.html",
                    # 2026-10-10: Ilnora's channel view -- READ-ONLY YouTube Data API (GET + API key, no OAuth, cannot
                    # write), approved 2026-10-07 ("read-only stats ... so the audience can steer her"; "google is ok,
                    # just dont let it write nothing")
                    "youtube_view.py",
                ):
                    continue
                findings.append(
                    f"BANNED SERVICE IN CODE -- '{m}' appears in {rel}. "
                    f"Barry's standing rule: DuckDuckGo only, no Google anywhere.")
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY CHECK ERROR -- could not scan source: {e}")

    # 4. the office browser profile
    try:
        if not os.path.exists(_PROFILE):
            findings.append(
                "OFFICE BROWSER -- the isolated Firefox profile (data/office_browser_profile/"
                "user.js) is missing. Without it the office opens in the default browser, "
                "which is signed into a Google account.")
        else:
            js = open(_PROFILE, "r", encoding="utf-8", errors="replace").read()
            if 'safebrowsing.malware.enabled", false' not in js:
                findings.append(
                    "OFFICE BROWSER -- Google Safe Browsing is no longer switched off in the "
                    "office Firefox profile; it sends URL data to Google.")
            if 'browser.search.hiddenOneOffs' not in js:
                findings.append(
                    "OFFICE BROWSER -- the hiddenOneOffs pref is gone from user.js, so Google "
                    "and Bing are pickable again in the office URL bar.")
            # The REAL engine, from the store Firefox actually reads.
            if os.path.exists(_SEARCH_STORE):
                eng = office_default_engine()
                if eng is not None and eng != "ddg":
                    findings.append(
                        f"OFFICE BROWSER -- the LIVE default search engine is '{eng}', not "
                        f"DuckDuckGo. Run scripts/force_ddg_office_browser_2026_09_07.py.")
            # The network-level lock lives INSIDE the profile (Barry: "i dont
            # want to instal nothing"): a proxy rule in user.js sends every
            # Google/Bing host to a dead port. If it goes missing, Google is
            # reachable again from the office window.
            if 'network.proxy.type", 2' not in js or "127.0.0.1:9" not in js:
                findings.append(
                    "OFFICE BROWSER -- the Google block (proxy rule in user.js) is gone. "
                    "google.com is reachable from the office window again.")
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY CHECK ERROR -- could not read the office profile: {e}")

    # 5. outbound host drift
    try:
        external = {h for h in hosts_seen
                    if not h.startswith("127.0.0.1") and h not in ("localhost",)
                    and "." in h}
        known = set()
        if os.path.exists(_BASELINE):
            known = set(json.load(open(_BASELINE, "r", encoding="utf-8")).get("hosts", []))
        else:
            json.dump({"hosts": sorted(external),
                       "note": "Baseline taken 2026-09-07. A NEW host here is a finding."},
                      open(_BASELINE, "w", encoding="utf-8"), indent=2)
            known = external
        for h in sorted(external - known):
            findings.append(
                f"NEW OUTBOUND HOST -- the build can now reach {h}, which was not in the "
                f"security baseline. If that is wanted, say so and it goes in the baseline.")
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY CHECK ERROR -- host baseline: {e}")

    # 6. THE PC ITSELF -- Defender, firewall, threats (2026-09-07, Barry: "i
    #    want her to keep my pc safe"). Defender is the antivirus; she watches it.
    try:
        import pc_security
        # detections he was already told about are not re-reported (2026-10-07, Barry: "do the other")
        _ack = ""
        try:
            _ack = json.load(open(_BASELINE, "r", encoding="utf-8")).get("threats_acknowledged_until", "")
        except (OSError, ValueError):
            pass
        findings.extend(pc_security.check(since=_ack))
    except Exception as e:  # noqa: BLE001
        findings.append(f"PC SECURITY -- check could not run: {e}")

    # 7. SOMETHING TRIED TO GET IN (2026-09-07, Barry: "sophie should be
    #    watching and blocking anything that tries to get into my build").
    #    main.py's refuse_non_local middleware 403s any request that is not
    #    from this machine and records it. New refusals since the last check
    #    are a finding -- the block already happened, this is Sophie naming it.
    try:
        import json as _json
        refused_path = os.path.join(_DATA, "refused_connections.jsonl")
        state_path = os.path.join(_DATA, "security_watch_seen.json")
        if os.path.exists(refused_path):
            seen = 0
            try:
                seen = int(_json.load(open(state_path, encoding="utf-8")).get("refused_lines", 0))
            except Exception:
                seen = 0
            lines = open(refused_path, "r", encoding="utf-8", errors="replace").read().splitlines()
            fresh = lines[seen:] if seen <= len(lines) else lines
            if fresh:
                hosts: dict[str, int] = {}
                for ln in fresh:
                    try:
                        hosts[_json.loads(ln).get("from", "?")] = \
                            hosts.get(_json.loads(ln).get("from", "?"), 0) + 1
                    except Exception:
                        pass
                if hosts:
                    who = ", ".join(f"{h} ({n}x)" for h, n in sorted(hosts.items(), key=lambda kv: -kv[1])[:5])
                    findings.append(
                        f"BLOCKED INTRUSION -- {len(fresh)} request(s) from off this machine "
                        f"were refused since the last check: {who}. They were denied everything; "
                        f"this is a record, not a breach.")
            try:
                _json.dump({"refused_lines": len(lines)}, open(state_path, "w", encoding="utf-8"))
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY CHECK ERROR -- refused-connection log: {e}")

    return findings


def status() -> dict:
    """For system_health -- a one-line answer Sophie can read out."""
    f = check()
    return {"clean": not f, "findings": f,
            "summary": "no security findings" if not f else f"{len(f)} security finding(s)"}
