"""Contest: Claude's Yannah prompt vs Elliot's, same door, same seed, same settings."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
SEED = 4242

CLAUDE = ("@Yannah fires @Yannah's-Machine-Pistol one-handed across the black site compound yard at night, "
          "between black steel hangars on wet asphalt, a razor-wire fence and snow-dusted pines on the mountainside "
          "behind her. One tall white floodlight high behind her rakes across the yard and rims her locs; the only "
          "other light is her own fire -- thin forest-green tracer streaks with a faint white core ripping away from "
          "the muzzle, throwing green across her cheekbone and the wet ground, a wisp of grey smoke at the barrel. "
          "Her right arm is locked out with the compact pistol in one hand, left hand up for balance, knees bent, "
          "moving. Her head is turned in three-quarter profile away from the camera, eyes narrowed down the line of "
          "fire toward a hangar door, jaw clenched, lips pulled back mid-shout. Keep her warm brown skin, faint gold "
          "freckles on her cheeks only, noticeably pointed ears, emerald-green-over-brown double-ringed eyes, the small "
          "jewel stud under her right eye, twisted locs with copper-auburn tips swept up with one side shaved, the gold "
          "ear cuff, and her black fitted tactical jumpsuit with teal piping, reinforced knees and thigh holster rig. "
          "Medium shot, 35mm, low angle from her side. Cinematic, hyper-realistic skin and fabric, film grain.")

ASK = ("Round 2 of the contest with Claude -- Barry judges. Round 1 both lost: your pistol rendered rifle-sized and "
       "she was posing, Claude's rounds came out as white blobs and she looked at the camera. Barry's rules for round 2: "
       "(1) a TRUE environment from the show only -- a place that is actually in the script, named the way the script "
       "names it (the black site is the floodlit compound at night: black hangars, razor wire, mountains; the Talia is a "
       "clean, well-kept ship). (2) Her machine pistol is compact, Uzi-sized, fired ONE-HANDED -- the size it is in its "
       "thigh holster. (3) Her rounds are thin forest-green tracer streaks, never blobs. (4) She is fighting, not "
       "posing: state where her head is turned and where her eyes point -- at the target, not the camera. Write ONE still "
       "prompt, a single ```image``` fence of @Yannah firing @Yannah's-Machine-Pistol: epic, real facial expression, "
       "light effects, in the style of the #442 Vor'Shara prompt on your shelf. Reply with the fence only.")

def render(label, prompt):
    t = time.time()
    g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": prompt, "seed": SEED},
                   timeout=7200).json()
    print(f"{label} {round(time.time()-t)}s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path", "extras")},
          default=str), flush=True)

t = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": ASK, "task": True}, timeout=1500).json()
m = re.search(r"```image\s*\n(.*?)```", r.get("reply", ""), re.S)
ELLIOT = m.group(1).strip() if m else ""
open("data/_contest_elliot_prompt.txt", "w", encoding="utf-8").write(ELLIOT or r.get("reply", ""))
print(f"ELLIOT wrote in {round(time.time()-t)}s fell_back={r.get('bonsai_fell_back')} tools={r.get('tool_calls')}", flush=True)
print("ELLIOT PROMPT:", ELLIOT, flush=True)
render("CLAUDE", CLAUDE)
if ELLIOT:
    render("ELLIOT", ELLIOT)
