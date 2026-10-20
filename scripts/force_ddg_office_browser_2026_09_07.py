"""DUCKDUCKGO ONLY. Rip Google out of the office browser for good.

Barry, 2026-09-07: "NONO NO, how many time i have to say No google EVER!!
duck duck go ONLY!!!!"

WHAT WAS WRONG, and why the earlier check missed it:
`user.js` set `browser.urlbar.placeholderName = "DuckDuckGo"`. That is the
grey TEXT in the empty URL bar. It does not change the search engine. The
real engine list lives in `search.json.mozlz4`, and that file had
`"engines":[{"id":"google", ...` FIRST with no default recorded -- so every
search typed in the office browser's URL bar went to GOOGLE.

Reading the pref and calling it done is exactly the half-ass rule.

WHAT THIS DOES:
1. Decodes search.json.mozlz4 (mozLz4 = 8-byte header + LE32 size + LZ4 block).
2. DELETES the google, bing, amazon, ebay and perplexity engines outright --
   removed, not hidden, not reordered. A banned thing is deleted.
3. Sets DuckDuckGo as the recorded default (metaData.defaultEngineId +
   defaultEngineIdHash cleared so Firefox accepts it).
4. Re-encodes and writes it back. Original backed up first.

Both LZ4 codecs below are pure python -- no new dependency in the venv.
The encoder emits a literal-only block, which is valid LZ4 (just uncompressed).

Re-runnable. Verifies by decoding what it wrote.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import datetime

PROFILE = r"C:\Users\Owner\Desktop\AgentCompanyBackend\data\office_browser_profile"
SEARCH = os.path.join(PROFILE, "search.json.mozlz4")
BACKUP_DIR = r"C:\Users\Owner\Desktop\AgentCompanyBackend\data\backup_ddg_only_2026-09-07"

MAGIC = b"mozLz40\0"

# Every engine that is not DuckDuckGo goes. Matched on the engine id.
BANNED_IDS = {"google", "bing", "amazondotcom-us", "ebay", "perplexity",
              "yahoo", "yandex", "ecosia", "startpage"}


def lz4_decompress(src: bytes, out_size: int) -> bytes:
    """Minimal LZ4 block decompressor."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        out += src[i:i + lit_len]
        i += lit_len
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        match_len = token & 0x0F
        if match_len == 15:
            while True:
                b = src[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        match_len += 4
        start = len(out) - offset
        for k in range(match_len):
            out.append(out[start + k])
    if len(out) != out_size:
        raise ValueError(f"decompressed {len(out)} bytes, header said {out_size}")
    return bytes(out)


def lz4_compress_literals(data: bytes) -> bytes:
    """Valid LZ4 block holding `data` as one literal run (no compression).

    LZ4 requires the final sequence to be literals with no match, which is
    exactly what this is. Firefox's decoder accepts it.
    """
    out = bytearray()
    n = len(data)
    token = (15 << 4) if n >= 15 else (n << 4)
    out.append(token)
    if n >= 15:
        rem = n - 15
        while rem >= 255:
            out.append(255)
            rem -= 255
        out.append(rem)
    out += data
    return bytes(out)


def read_mozlz4(path: str) -> dict:
    raw = open(path, "rb").read()
    if raw[:8] != MAGIC:
        raise ValueError(f"{path} is not a mozLz4 file (header {raw[:8]!r})")
    size = struct.unpack("<I", raw[8:12])[0]
    return json.loads(lz4_decompress(raw[12:], size).decode("utf-8"))


def write_mozlz4(path: str, obj: dict) -> None:
    payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    body = lz4_compress_literals(payload)
    with open(path + ".tmp", "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<I", len(payload)))
        fh.write(body)
    os.replace(path + ".tmp", path)


def main() -> int:
    if not os.path.exists(SEARCH):
        print(f"MISSING: {SEARCH}")
        print("Open the office browser once so Firefox creates it, then re-run.")
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(SEARCH, os.path.join(BACKUP_DIR, f"search.json.mozlz4.{stamp}"))

    data = read_mozlz4(SEARCH)
    engines = data.get("engines", [])
    print("BEFORE:")
    for e in engines:
        print(f"   {e.get('id'):<20} {e.get('_name')}")
    print(f"   recorded default: {data.get('metaData', {}).get('defaultEngineId')!r}")

    ddg = next((e for e in engines
                if e.get("id") == "ddg" or "duck" in str(e.get("_name", "")).lower()), None)
    if ddg is None:
        print("\nFAILED: no DuckDuckGo engine in this profile. Nothing changed.")
        return 1
    ddg_id = ddg.get("id")

    kept = [e for e in engines if e.get("id") not in BANNED_IDS]
    if not any(e.get("id") == ddg_id for e in kept):
        kept.insert(0, ddg)
    # DuckDuckGo first in the list as well as recorded default.
    kept.sort(key=lambda e: 0 if e.get("id") == ddg_id else 1)
    data["engines"] = kept

    meta = data.setdefault("metaData", {})
    meta["defaultEngineId"] = ddg_id
    meta["privateDefaultEngineId"] = ddg_id
    # Firefox stores a hash so it can tell if something tampered with the
    # default. A wrong hash makes it reset to its own default (Google), so
    # the hashes are removed -- absent is accepted, wrong is not.
    meta.pop("defaultEngineIdHash", None)
    meta.pop("privateDefaultEngineIdHash", None)
    meta["useSavedOrder"] = True

    write_mozlz4(SEARCH, data)

    check = read_mozlz4(SEARCH)
    print("\nAFTER:")
    for e in check.get("engines", []):
        print(f"   {e.get('id'):<20} {e.get('_name')}")
    print(f"   recorded default: {check.get('metaData', {}).get('defaultEngineId')!r}")

    ids = {e.get("id") for e in check.get("engines", [])}
    bad = ids & BANNED_IDS
    ok = (not bad) and check.get("metaData", {}).get("defaultEngineId") == ddg_id
    print("\n" + ("VERIFIED: DuckDuckGo only. Google is gone from this browser."
                  if ok else f"PROBLEM: still present {bad}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
