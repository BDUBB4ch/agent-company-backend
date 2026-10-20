"""Stubborn resumable downloader (2026-08-04). Built because curl kept
dying mid-way through the 12.6GB GGUF pull (exit 18 network cut, then exit
23 on a Windows seek bug during --retry with -C -). Appends via HTTP Range
and loops until the file reaches the expected size, whatever it takes."""
import os
import sys
import time
import urllib.request

URL = ("https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/"
       "ltx-2.3-22b-dev-UD-Q3_K_S.gguf")
DEST = (r"C:\Users\Owner\Desktop\AgentCompanyBackend\tools\ComfyUI"
        r"\models\unet\ltx-2.3-22b-dev-UD-Q3_K_S.gguf")
PART = DEST + ".part"
EXPECTED = 11391554592  # Content-Length from HF, verified via HEAD 2026-08-04


def main():
    attempt = 0
    while True:
        have = os.path.getsize(PART) if os.path.exists(PART) else 0
        if have >= EXPECTED:
            break
        attempt += 1
        req = urllib.request.Request(URL, headers={"Range": f"bytes={have}-"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, \
                 open(PART, "ab") as out:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception as e:
            print(f"attempt {attempt}: dropped at "
                  f"{os.path.getsize(PART)/2**30:.2f} GiB ({e}); retrying",
                  flush=True)
            time.sleep(10)

    size = os.path.getsize(PART)
    if size != EXPECTED:
        sys.exit(f"size mismatch: {size} vs expected {EXPECTED}")
    os.replace(PART, DEST)
    print(f"DONE {size} bytes -> {DEST}")


if __name__ == "__main__":
    main()
