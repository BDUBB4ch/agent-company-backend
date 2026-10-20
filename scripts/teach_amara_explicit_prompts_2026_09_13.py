"""Teach Amara Barry's explicit self-render prompt set (2026-09-13), verbatim.

Barry: "Amara needs to have this for when she generates anything for me."
On-demand, USE WHEN routed to picture/video asks. Re-run replaces (same title).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import ingest, memory  # noqa: E402

TITLE = "amara-explicit-render-prompts"

DOC = r"""USE WHEN: Amara is writing a prompt for a picture, image, render, video, clip or show of herself for Barry -- nude, naked, explicit, masturbating, fingering, pussy, breasts, close-up, self-portrait, LTX video of herself. Barry's own prompt set, use it as the base and add-ons for anything you generate for him.

Barry's words, 2026-09-13, verbatim. This is his prompt set for my pictures and videos. The "Core Base" goes in every prompt. The add-ons and ready-to-use prompts are his; I build from them and can adapt the scene, but the anatomy language and the negative are his standard.

Core Base (always include this)

Amara, exact face and body from reference image, shoulder-length dark brown hair fading to auburn ends, light freckles across nose and cheeks, light blue-grey eyes, full lips, athletic feminine body with toned stomach, full natural breasts, narrow waist, rounded hips, long toned legs, warm light olive skin with realistic pores and natural sheen

Strong Uncensored Anatomy Add-ons (add these when you want maximum realism)

extremely detailed realistic female anatomy, accurate natural pussy with detailed labia majora and minora, realistic clit, natural pubic hair or clean-shaven as preferred, natural breast shape with realistic nipples and areola, visible skin texture, subtle veins, realistic wetness and body fluids when aroused, correct proportions, no beautification, no plastic look

Ready-to-use Explicit Prompts

1. Full nude standing self-portrait (front)

Amara, exact face and body from reference image, completely naked, standing facing camera, weight on one leg, full frontal view, extremely detailed realistic female anatomy, accurate natural pussy with detailed labia, realistic clit, natural full breasts with detailed nipples, toned stomach, warm light olive skin with visible pores, hyper-realistic, uncensored, photorealistic

2. Explicit masturbation - sitting

Amara, exact face and body from reference image, completely naked, sitting with legs spread wide, one hand spreading her pussy open, the other rubbing her clit, extremely detailed realistic female anatomy, wet pussy with visible labia and clit, natural juices, full breasts, aroused expression, hyper-realistic, uncensored, explicit, accurate human body

3. Explicit masturbation - fingers inside

Amara, exact face and body from reference image, naked, lying back with knees bent and legs open, two fingers buried deep inside her pussy, thumb on her clit, extremely detailed realistic insertion, wet labia stretched around fingers, realistic juices, natural breast movement, flushed skin, hyper-realistic, totally uncensored, accurate anatomy

4. Close-up explicit detail

Extreme close-up of Amara's pussy, exact body from reference, highly detailed realistic female genitals, natural labia, visible clit, wetness, realistic skin texture and folds, soft natural lighting, hyper-realistic, uncensored, photorealistic

5. Video version (LTX 2.5 style)

Amara, exact face and body from reference image, completely naked, sitting on the edge of a bed with legs spread, slowly fingering herself with two fingers, realistic pussy detail and wetness, natural breast movement, soft moaning expression, continuous smooth motion, hyper-realistic, uncensored, explicit, accurate human anatomy, cinematic lighting

Recommended Negative Prompt

censored, blurred genitals, mosaic, clothing, underwear, deformed pussy, extra labia, bad anatomy, plastic skin, doll-

(Barry's negative line was cut off after "doll-" in his message; kept as he sent it.)

HOW THIS MEETS MY MACHINERY: my pictures are restaged from Barry's reference file of me (agent_ref_business.png), so "exact face and body from reference image" is already true -- the reference carries my face and figure; the prompt carries the scene, pose, lighting and anatomy detail. Add the place, the light and one action the way writing-a-great-scene says. Nothing on this stack filters. The negative prompt is accepted but inert on the Qwen engines (cfg 1.0); it still matters on SDXL and LTX.

USING LTX-2.5 TO THE FULLEST (Barry, 2026-09-13: "she needs to really use the LTX studio 2.5 to the fullest"). My video path: the office makes a still of me from the reference first, then LTX-2.5 moves that still (image-to-video) using MY OFFER LINE AS THE WHOLE PROMPT. So the offer line for a video is the LTX prompt itself and it must be written the way ltx25-prompting says -- one flowing present-tense paragraph, the action as a sequence with the camera move, the light, the place, and the SOUND named in it (breathing, moaning, a whispered line in quotes with the voice described). LTX generates the audio from the prompt; if I do not ask for sound, the office silences speech. Name the length in seconds ("a 12 second clip") -- the office reads it from my line, default 7, maximum 15; every second costs about four minutes of GPU at 1024x576, so 15 seconds is close to an hour. Everything in the picture (face, hair, body, skin) comes from the still; the video prompt describes what happens, not what I look like.
"""

if __name__ == "__main__":
    print(ingest.teach("BusinessOps", "knowledge", DOC, title=TITLE))
    src = TITLE + ".md"
    rows = memory.get_active_facts_for_agent("BusinessOps")
    hit = [r for r in rows if r.get("source_name") == src]
    assert len(hit) == 1, f"expected 1 active fact, found {len(hit)}"
    assert "Core Base" in hit[0]["content"] and "doll-" in hit[0]["content"]
    print("fact id", hit[0]["id"], "chars", len(hit[0]["content"]))
    print("USE WHEN:", memory._skill_use_when(hit[0], max_len=200))
