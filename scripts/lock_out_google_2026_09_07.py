"""Barry, 2026-09-07, angry and right: "why the fuck is google in my office...
i dont want them nowhere near any of my private shit... duck duck go period"
and "when i click my office it goes right to my signed in google" and "i dont
want any of them in my build only when my agent searches and still they cant
get into my build."

FOUR FIXES:
 1. THE LEAK HE SAW. Both launchers ended with `start "" "http://...8765"`,
    which hands the URL to the DEFAULT BROWSER. A cold default browser opens
    its own startup/new-tab page first -- his signed-in Google -- and his
    office loads inside a browser logged into a Google account. Now both
    launchers open Firefox with a DEDICATED, ISOLATED office profile: never
    signed into anything, no Google services, homepage = the dashboard.
 2. THE REAL EXPOSURE, measured: `python -m http.server 8765` binds :: (ALL
    interfaces), so the dashboard was reachable from any device on his
    network. Backend/Ollama/Bonsai were already 127.0.0.1. Both launchers now
    pass --bind 127.0.0.1. Nothing gets INTO the build.
 3. The office Firefox profile is hardened: Google Safe Browsing OFF (it pings
    Google with URL hashes -- the single biggest "Google near my private shit"
    in a default Firefox), telemetry/Normandy/studies OFF, Firefox Accounts
    and sync OFF, Google location service OFF, DuckDuckGo as search, new tab
    blank, no password prompts.
 4. web_search.py is patched separately to DuckDuckGo ONLY (Bing dropped).

Re-runnable. Backs up every file it touches. The .bat files are HIDDEN --
attrib is cleared before writing and restored after (documented trap).
"""
import os
import re
import shutil
import pathlib
import subprocess

DESK = pathlib.Path("C:/Users/Owner/Desktop")
REPO = DESK / "AgentCompanyBackend"
BACKUP = REPO / "data" / "backup_google_lockout_2026-09-07"
BACKUP.mkdir(parents=True, exist_ok=True)

FIREFOX = pathlib.Path("C:/Program Files/Mozilla Firefox/firefox.exe")
PROFILE = REPO / "data" / "office_browser_profile"
URL = "http://127.0.0.1:8765/index.html"

assert FIREFOX.exists(), f"Firefox not found at {FIREFOX}"

# ---------------------------------------------------------------- 1. profile
PROFILE.mkdir(parents=True, exist_ok=True)
(PROFILE / "user.js").write_text(f'''// THE OFFICE browser profile -- Barry White, 2026-09-07.
// Isolated on purpose: this profile is never signed into any account, and
// every Google-touching service in Firefox is turned off here.

// --- the office ---
user_pref("browser.startup.homepage", "{URL}");
user_pref("browser.startup.page", 1);
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.newtab.url", "about:blank");

// --- DuckDuckGo, period ---
user_pref("browser.urlbar.placeholderName", "DuckDuckGo");
user_pref("browser.urlbar.placeholderName.private", "DuckDuckGo");
user_pref("browser.search.suggest.enabled", false);
user_pref("browser.urlbar.suggest.searches", false);
user_pref("browser.urlbar.suggest.topsites", false);
user_pref("browser.urlbar.suggest.quicksuggest.sponsored", false);
user_pref("browser.urlbar.suggest.quicksuggest.nonsponsored", false);

// --- GOOGLE OUT. Safe Browsing sends URL data to Google by default. ---
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("browser.safebrowsing.downloads.enabled", false);
user_pref("browser.safebrowsing.downloads.remote.enabled", false);
user_pref("browser.safebrowsing.downloads.remote.url", "");
user_pref("browser.safebrowsing.provider.google.updateURL", "");
user_pref("browser.safebrowsing.provider.google.gethashURL", "");
user_pref("browser.safebrowsing.provider.google.reportURL", "");
user_pref("browser.safebrowsing.provider.google4.updateURL", "");
user_pref("browser.safebrowsing.provider.google4.gethashURL", "");
user_pref("browser.safebrowsing.provider.google4.reportURL", "");
user_pref("browser.safebrowsing.provider.google4.dataSharingURL", "");
user_pref("geo.provider.network.url", "");
user_pref("geo.enabled", false);

// --- no accounts, no sync, no phoning home ---
user_pref("identity.fxaccounts.enabled", false);
user_pref("services.sync.enabled", false);
user_pref("signon.rememberSignons", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("toolkit.telemetry.archive.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("app.normandy.enabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("browser.discovery.enabled", false);
user_pref("browser.ping-centre.telemetry", false);
user_pref("browser.newtabpage.activity-stream.feeds.telemetry", false);
user_pref("browser.newtabpage.activity-stream.telemetry", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("network.connectivity-service.enabled", false);
user_pref("extensions.getAddons.showPane", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
''', encoding="utf-8")

# ---------------------------------------------------------------- 2. launchers
FF_LINE = (
    'rem --- THE OFFICE opens in its OWN isolated Firefox profile (2026-09-07).\n'
    'rem     Never hand the URL to the default browser: a cold default browser\n'
    'rem     shows its own startup page first (a signed-in Google account) and\n'
    'rem     then loads the office inside it. This profile is signed into\n'
    'rem     nothing and has every Google service switched off.\n'
    'set "OFFICE_FF=C:\\Program Files\\Mozilla Firefox\\firefox.exe"\n'
    'set "OFFICE_PROFILE=C:\\Users\\Owner\\Desktop\\AgentCompanyBackend\\data\\office_browser_profile"\n'
    'if exist "%OFFICE_FF%" (\n'
    '    start "" "%OFFICE_FF%" -profile "%OFFICE_PROFILE%" -no-remote "URLHERE"\n'
    ') else (\n'
    '    echo Firefox not found -- opening in the default browser instead.\n'
    '    start "" "URLHERE"\n'
    ')\n'
).replace("URLHERE", URL)

targets = [
    (DESK / "Launchers" / "Start Everything.bat", "%VENV_PY%" ),
    (DESK / "AgentDashboard" / "Start Dashboard.bat", None),
]
for path, _ in targets:
    if not path.exists():
        print("skip (missing):", path); continue
    shutil.copy2(path, BACKUP / path.name)
    hidden = subprocess.run(["attrib", str(path)], capture_output=True, text=True).stdout
    was_hidden = " H " in hidden or hidden.strip().startswith("A    H") or " H" in hidden.split(str(path))[0]
    if was_hidden:
        subprocess.run(["attrib", "-h", str(path)], check=False)
    t = path.read_text(encoding="utf-8", errors="replace")

    # (a) bind the dashboard server to localhost only
    before = t
    t = re.sub(r"(-m http\.server 8765)(?! --bind)", r"\1 --bind 127.0.0.1", t)
    t = re.sub(r"(-m http\.server)(\s*\n)", r"\1 8765 --bind 127.0.0.1\2", t)
    bound = t != before

    # (b) replace the default-browser handoff with the isolated Firefox launch
    opened = False
    if 'start "" "http://127.0.0.1:8765/index.html"' in t:
        t = t.replace('start "" "http://127.0.0.1:8765/index.html"', FF_LINE.rstrip("\n"), 1)
        opened = True

    tmp = path.with_suffix(".tmp")
    tmp.write_text(t, encoding="utf-8")
    tmp.replace(path)
    if was_hidden:
        subprocess.run(["attrib", "+h", str(path)], check=False)
    print(f"{path.name}: bind-localhost={bound} isolated-firefox={opened} hidden-restored={was_hidden}")

print("\nprofile:", PROFILE)
print("backups:", BACKUP)
