"""Phase 2 of the character-restage door (2026-09-14, Barry: "all of it"):
one still with a WEAPON + LOCATION reference (Bia, pistol, black site), one
still with a LOCATION reference (Yannah, the Talia bridge), and one CHARACTER
VIDEO (Keth, 5s) through /api/generate-video, which now restages the still
itself and runs LTX i2v from it. Sequential, waits for the card, records to
data/restage_phase2_results_2026-09-14.json. Re-runnable."""
import json, time, urllib.request, os

API = "http://127.0.0.1:8420"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "restage_phase2_results_2026-09-14.json")

JOBS = [
    ("bia_pistol_blacksite", "/api/generate-image", {
        "agent_id": "movie",
        "prompt": "@Bia-2 stands at the perimeter fence of the black site at night, grey and black form-fitting tactical suit, @Bia's-Pistol* held two-handed at the ready, hazel-green eyes fixed on the compound gate, flood lights behind her, wide cinematic shot, film grain"}),
    ("yannah_bridge", "/api/generate-image", {
        "agent_id": "movie",
        "prompt": "@Yannah sits at the pilot station on the bridge of the Talia, black fitted tactical jumpsuit with teal piping, gold ear cuff on her exposed pointed ear, hands on the controls, teal console light on her face, wide cinematic shot, film grain"}),
    # Barry: "why are you even doing stills? just use the ones i have already"
    # -- the wide Keth still (approval 274) staged as the start frame, so this
    # tests the i2v half alone. Without start_frame the door renders a still
    # first (or reuses a matching recent one).
    ("keth_video", "/api/generate-video", {
        "agent_id": "movie", "duration_s": 5,
        "start_frame": "startframe_movie_keth_test.png",
        "prompt": "@Keth walks slowly down a dim black-site service corridor toward the camera, worn gray facility jumpsuit, barefoot on cold concrete, his large dark green eyes scanning the walls, a single overhead flood light flickering, the camera holding steady as he approaches, quiet hum of ventilation"}),
]


def post(path, body, timeout):
    data = json.dumps(body).encode()
    req = urllib.request.Request(API + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_idle():
    for _ in range(720):
        try:
            with urllib.request.urlopen(API + "/api/generate/status", timeout=10) as r:
                st = json.loads(r.read())
            if not st.get("busy") and not st.get("video_render_holding_gpu"):
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)


def main():
    results = json.load(open(OUT, encoding="utf-8")) if os.path.isfile(OUT) else {}
    for key, path, body in JOBS:
        if key in results and "path" in results[key]:
            continue
        wait_idle()
        t0 = time.time()
        try:
            res = post(path, body, 5400)
        except Exception as e:  # noqa: BLE001
            res = {"error": str(e)[:400]}
        res["seconds"] = round(time.time() - t0)
        results[key] = res
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
        print(key, res.get("path") or res.get("error"), res["seconds"], "s", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
