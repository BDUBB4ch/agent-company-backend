"""One canon test still per Bia-crew character through the OFFICE endpoint
(/api/generate-image, Elliot's seat), sequentially -- the character-restage
door built 2026-09-14. Results land as Elliot approvals; this file records
the ids/paths in data/restage_results_2026-09-14.json. Re-runnable."""
import json, time, urllib.request, os

API = "http://127.0.0.1:8420/api/generate-image"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "restage_results_2026-09-14.json")

SHOTS = {
    # keth's wide-canvas test was submitted by hand before this run (its
    # client was killed but the server-side render completed as
    # char_keth_00002_.png); left out here so it is not rendered twice.
    "bia": "@Bia-2 crouches behind a matte-black cargo crate in the black-site shipping bay, grey and black form-fitting tactical suit, multi-tool holstered on her right hip, @Bia's-Pistol* drawn and low, hazel-green eyes scanning the dark, wide cinematic shot, hard flood light from above, gritty film grain",
    "tazz": "@Tazz walks down the Talia's main corridor, all-black sleeveless form-fitting one-piece tactical jumpsuit, two long dark braids secured tight, @Tazz's-Weapon held two-handed across her chest, pale turquoise running lights along the walls, wide cinematic shot, film grain",
    "yannah": "@Yannah leans over the bridge console of the Talia, black fitted tactical jumpsuit with teal piping, utility belt and thigh holster rig, compact comms unit at her hip, gold ear cuff on her exposed pointed ear, screens glowing in front of her, wide cinematic shot, film grain",
    "bdubb": "@b-dubb crouches at a rocky ridge line in the Colorado mountains at dusk, black hoodie with a black tactical vest over it, black cargo pants, black boots, black baseball cap pulled low, gold number 4 pendant catching the last light, watching a warehouse in the valley below, wide cinematic shot, film grain",
    "vorshara": "@lady-vor-shara-vel stands beside the reflecting pool in her garden atrium sanctum, dark green marble columns with gold bands and living vines, warm golden light, fully sheer pale-purple couture gown with gold filigree, four electric-blue eyes turned toward the camera, wide cinematic shot, film grain",
}


def render(agent_id, prompt):
    body = json.dumps({"agent_id": agent_id, "prompt": prompt}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1700) as r:
        return json.loads(r.read())


def wait_idle():
    """Never submit under a live render -- the flag guard would refuse and
    the run would record a false error. Waits up to 30 min."""
    for _ in range(360):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8420/api/generate/status", timeout=10) as r:
                st = json.loads(r.read())
            if not st.get("busy") and not st.get("video_render_holding_gpu"):
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)


def main():
    results = {}
    if os.path.isfile(OUT):
        results = json.load(open(OUT, encoding="utf-8"))
    for key, prompt in SHOTS.items():
        if key in results and "path" in results[key]:
            continue
        wait_idle()
        t0 = time.time()
        try:
            res = render("movie", prompt)
        except Exception as e:  # noqa: BLE001
            res = {"error": str(e)[:400]}
        res["seconds"] = round(time.time() - t0)
        results[key] = res
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
        print(key, res.get("path") or res.get("error"), res["seconds"], "s", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
