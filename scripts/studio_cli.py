"""Every Studio control, from the command line. For batch work and scripting.

Why this rather than saved ComfyUI workflows: ComfyUI's sidebar needs UI-format
JSON (node positions, link arrays, a schema version). Everything in workflows/
is API-format. Hand-authoring UI format means guessing at a schema that changes
between releases, and a malformed file simply fails to load -- so it would be
effort spent on files that might not work, duplicating buttons the Studio now
has for real.

This goes through the BACKEND (not ComfyUI directly), so every render lands in
the Out box and obeys the same approval rules as the dashboard. Nothing here
can auto-publish anything.

Examples:
    # one render, character + height + reference
    python scripts/studio_cli.py "close-up portrait, soft studio lighting" \
        --character vorshara --pose pose_vorshara.png --reference ref_shara_face.png

    # sweep seeds to find a look worth keeping
    python scripts/studio_cli.py "full body standing, sheer gown" \
        --character vorshara --seeds 11,42,77,123

    # sweep reference weight to tune identity vs LoRA
    python scripts/studio_cli.py "close-up portrait" --character vorshara \
        --reference ref_shara_face.png --ref-weights 0.5,0.7,0.85,1.0
"""
import argparse
import json
import time
import urllib.error
import urllib.request

BACKEND = "http://127.0.0.1:8420"


def post(path, body, timeout=900):
    req = urllib.request.Request(
        f"{BACKEND}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:  # noqa: BLE001 - surfacing any transport failure is the point
        return {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--negative", default="cartoon, anime, watermark, plastic skin, "
                                          "closed eyes, blurry, low quality, elderly")
    ap.add_argument("--character", help="prepends the @mention; backend resolves the LoRA")
    ap.add_argument("--pose", help="pose file in ComfyUI/input ROOT (see pose_skeleton.py)")
    ap.add_argument("--pose-strength", type=float, default=0.6)
    ap.add_argument("--reference", help="IP-Adapter reference in ComfyUI/input ROOT")
    ap.add_argument("--ref-preset", default="PLUS (high strength)",
                    help="PLUS for the aliens; 'PLUS FACE (portraits)' only for B Dubb")
    ap.add_argument("--detail", type=float, default=0.0, help="-3..3")
    ap.add_argument("--upscale", choices=["commercial", "movie"],
                    help="commercial=Real-ESRGAN (BSD-3), movie=UltraSharp (NON-COMMERCIAL)")
    ap.add_argument("--seeds", help="comma list, e.g. 11,42,77")
    ap.add_argument("--ref-weights", help="comma list to sweep, e.g. 0.5,0.85")
    args = ap.parse_args()

    prompt = args.prompt
    if args.character and f"@{args.character}" not in prompt.lower():
        prompt = f"@{args.character}, {prompt}"

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else [None]
    weights = ([float(w) for w in args.ref_weights.split(",")]
               if args.ref_weights else [0.85])

    runs = 0
    for seed in seeds:
        for w in weights:
            body = {"prompt": prompt, "negative_prompt": args.negative,
                    "agent_id": "owner", "detail": args.detail,
                    "pose_strength": args.pose_strength,
                    "reference_preset": args.ref_preset}
            if seed is not None:
                body["seed"] = seed
            if args.pose:
                body["pose_image"] = args.pose
            if args.upscale:
                body["upscale"] = args.upscale
            if args.reference:
                body["reference_image"] = args.reference
                body["reference_weight"] = w
            label = f"seed={seed if seed is not None else 'random'}"
            if args.reference and len(weights) > 1:
                label += f" refw={w}"
            t0 = time.time()
            r = post("/api/generate-image", body)
            runs += 1
            if "error" in r:
                print(f"  {label:<28} FAILED  {r['error'][:160]}")
            else:
                fn = r.get("path", "").replace("\\", "/").split("/")[-1]
                x = r.get("extras", {})
                bits = [b for b in (
                    f"ref@{x['reference_weight']}" if x.get("reference") else None,
                    f"pose {x['pose']}" if x.get("pose") else None,
                    f"detail {x['detail']}" if x.get("detail") else None,
                    "upscaled" if x.get("upscale") else None) if b]
                print(f"  {label:<28} {time.time()-t0:5.0f}s  seed {r.get('seed')}  "
                      f"{fn}  {' '.join(bits)}")
                if not r.get("commercial_use", True):
                    print(f"       ⚠ {r.get('licence_note','')}")
    print(f"\n{runs} render(s). All queued in the Out box.")


if __name__ == "__main__":
    main()
