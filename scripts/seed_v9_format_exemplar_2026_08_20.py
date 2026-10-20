"""Seed Barry's V9 production-block format exemplar (pasted 2026-08-20, his
ruling: "this is how i want V9 written. acts and scenes written out like this.
intricate scene descriptions and designs etc.") into Elliot's brain, plus the
standing rule for shot asks ("if i ask for a shot it should be in prompt style
with your director skills").

The exemplar text is BARRY'S OWN, stored verbatim. Re-runnable (upserts).
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

EXEMPLAR = '''EP1 V9 PRODUCTION FORMAT -- BARRY'S EXEMPLAR (2026-08-20, verbatim)
USE WHEN: writing ANY V9 production block, pass, shot or B-roll -- this is the required shape. Match it field for field.

Barry's ruling, verbatim: "this is how i want V9 written. acts and scenes
written out like this. intricate scene descriptions and designs etc."
And for shot asks: "if i ask for a shot it should be in prompt style with
your director skills."

THE SHAPE (from his exemplar below): block header with number, name, duration,
MUSIC. Then GENRE | SPEED RAMP. Then the slug. Then rich action prose --
Barry's sentences as the spine, craft layer around them. Then labelled fields:
CAMERA:, ENVIRONMENT & LIGHTING: (materials, light sources, texture -- a
designed place, not a backdrop), EXPRESSION: (per character in frame), NEG:.
INTERNAL MONOLOGUE labelled inline where the treatment has it. B-ROLL blocks
are legitimate blocks for establishing beats. A Seedance 2.5 ```image``` prompt
fence is delivered WHEN BARRY ASKS for a shot's prompt -- shot asks always come
back in prompt style, grounded in the treatment text, never invented.

--- BARRY'S EXEMPLAR, VERBATIM ---

ACT ONE — COLORADO
TITLE CARD: "Rocky Mountains. Colorado. 02:14 AM." — White text on pure black screen. Two seconds. Gone.

B-ROLL 01 — THE MOUNTAIN | 4 sec | MUSIC: Nothing. Wind only.
GENRE: Thriller | SPEED RAMP: Static Locked

EXT. ROCKY MOUNTAINS — NIGHT.

STATIC LOCKED — 24mm wide establishing. Towering pine ridgeline half-framing the bottom half, vast black sky filling the top. No moon. No ambient light pollution — just absolute mountain darkness pressing down. Cold wind moves through the canopy in long waves, every tree leaning and releasing like lungs expanding and contracting. Rain beginning: slow individual ticks on pine needles, each one audible in the stillness, building to a steady sheet that hits the lens glass. Water runs down the glass, diffusing the image. No people visible. No artificial light. No drones. Camera does not move. Deep film grain. The mountain waiting. The air tastes like cold stone and wet pine.

CAMERA: 24mm | static locked | ridgeline framing lower third | empty sky dominating upper frame | rain hitting lens glass, diffusing light | film grain heavy.

ENVIRONMENT & LIGHTING: Deep mountain shadows. The only light comes from distant starlight filtering through breaking clouds — thin, pale, cold blue. The rain becomes visible only where it crosses the starlight. Texture: rough bark, wet pine needles, stone face on the slope. Material specificity: the rain soaks the bark, making it darker, more textured. The exposed rock face shows layering — lighter stone at breaks, darker weathered faces where water runs. Wind-driven rain at an angle, not vertical. The camera lens remains mostly dry at frame edges but rain sheet becomes denser toward center.

NEG: People, lights, motion blur, drones, logos, text, warm light, artificial structures, cartoon, anime.

SHOT 01 — THE RUN | 10 sec | MUSIC: Low sparse synth entering slow.
GENRE: Thriller | SPEED RAMP: Full Speed

EXT. ROCKY MOUNTAINS — DENSE PINE FOREST — NIGHT.

TRACKING SHOT — camera locks to @B DUBB's shoulders, lateral, tight mid-shot, 35mm. He runs hard through dense pine forest — no trail, no cleared path, just pressing through density. Branches whip his face and shoulders, leaving thin red lines across the forearm. Boots punch through wet undergrowth in explosive bursts that spray black mud, rotting pine needles, stone fragments. The impact sound of each step carries through the forest floor. Black tactical vest over black hoodie over black tank top — all three layers soaked through, fabric clinging and dragging with water weight, vest panels catching on branches then releasing. Cap pulled low, brim sheeting rain. Black cap visor curves down to his eyes. Gold number 4 pendant with diamonds swings free from his collar with every stride — diamonds catching split-second flashes of canopy starlight then vanishing back into shadow. Breathing hard, controlled — a man who has done this before, who knows the math of exertion, who regulates his oxygen. His face shows focus, not panic. Jaw set forward. Eyes locked ahead, not down.

INTERNAL MONOLOGUE (sparse, cold): "Somebody told me about this place six months ago. Drunk. In a bar in Pueblo. Said the government had something in these mountains that didn't come from here. I told myself he was full of shit. I drove up here anyway."

CAMERA: Tracking lateral — 35mm | locked to shoulders | tight mid-shot | gold number 4 pendant with diamonds swinging free with stride | shallow depth of field, branches motion-streaked in bokeh | tree bark textures sharp in foreground, blurred in background | rain hitting lens | film grain constant.

ENVIRONMENT & LIGHTING: The forest floor is a mix of rotting organic material, loose stone, and wet soil that creates suction with each footfall. Visibility is poor — starlight filtered through triple-canopy creates pools of slightly-less-darkness separated by absolute shadow. Rain streams down trunks at angles the wind forces. Bark texture: rough, water-darkened, slick. Each branch that whips his face leaves momentary spray trails. The only warm light is the occasional flash where starlight catches water droplets mid-air — otherwise everything is cool blue-black.

EXPRESSION: @B DUBB: jaw set forward throughout, eyes locked at horizon line rather than immediate ground, the face of a man running because calculation said run, not because panic said run. Controlled breathing. No visible fear. The focus is complete — a filter over everything else.

NEG: Slow motion, static camera, glamour, missing vest, extra belt gear, phone, cartoon, colored lighting, neon glow, perfect visibility, anime.

SHOT 02 — THE CLIMB | 8 sec | MUSIC: Tone builds — pulse enters, tempo rising.
GENRE: Thriller | SPEED RAMP: Speed Ramp to Ultra-Slow at Crest

EXT. ROCKY MOUNTAINS — STEEP ROCKY SLOPE — CONTINUOUS.

CRANE DOWN TO TRACKING — camera starts high looking down the slope from above, establishing the impossible angle, then drops and locks onto @B DUBB as he hits the incline. Both hands grabbing roots and exposed stone, finding holds in rock face. Boots finding edge-holds, weight driving upward. Black tactical vest presses against the stone, panels straining and releasing with each reach, the padding dimpling where it contacts the rock. Hoodie clings against his chest and back, the water weight making it move as a solid layer beneath the vest. Every muscle in his back visible through both fabrics with each reach — the tank top showing through the wet hoodie at the shoulders. Rain sheets down the slope toward him, running off his cap brim in a thin continuous stream, water hitting his upturned face. Gold number 4 pendant with diamonds swings free from his collar as he reaches for the highest grip — diamonds catch cold darkness for one frame, then he crests the ridge, pulls himself over the lip, comes up into a low crouch in one unbroken movement. Breathing ragged but controlled. Eyes already moving, assessing. Speed ramps to ultra-slow at the crest: water sprays off his hands as they release the stone, hands opening to show the erosion patterns on his palms from the grip, gold number 4 pendant with diamonds swinging at peak arc, all three layers of fabric — vest, hoodie, tank — settling with his chest drop as he exhales.

CAMERA: Crane down to tracking — 50mm | starts high establishing the slope angle, drops and locks lateral | low angle UP the slope | follows body upward | ultra-slow at crest as hands release and pendant swings | extreme close on fabric tension and water release | film grain heavy.

ENVIRONMENT & LIGHTING: The slope is exposed bedrock with loose surface debris. Lichen and weathering patterns visible where stone face catches minimal light. Water runs down the slope in thin channels, finding the easiest path downward. At the crest, the wind hits harder — no forest canopy protection. The starlight is slightly brighter here, no longer triple-filtered, creating more contrast between exposed stone and deep shadow in the rock cracks. The pendant catches this light most clearly at the crest — diamonds blazing for that single frame against the dark sky.

EXPRESSION: @B DUBB: face locked upward throughout the climb, jaw tight from exertion, eyes already at the ridge crest before his body arrives there — working ahead. At the crest: sharp exhale, lips parting to release breath, then jaw re-locking immediately, not relief, just the next calculation beginning. Eyes sweep horizontally across the crest area, reading space and geometry.

NEG: Static shot, glamour, logo, text, phone, missing vest, soft diffused light, perfect climbing conditions, slow motion.
'''

STANDING_RULE = (
    "STANDING RULE (Barry, 2026-08-20/21, verbatim): \"if i ask for a shot it "
    "should be in prompt style with your director skills\" and \"i want him to "
    "write it in his style when i ask him to give me the prompt for "
    "generations. whatever shot, he writes it with his director skills. If he "
    "likes it the way its written already he can use it but i already gave him "
    "the skills and persona on how to write it, so he should use his gritty "
    "skills the way hes supposed to. this is just a reference of sorts.\"\n"
    "And (Barry, 2026-08-21): \"no rewrites, just scene prompts. intricate "
    "designs and all. not dialog changes.\"\n"
    "Meaning: a shot ask = the Seedance 2.5 prompt ONLY, written IN YOUR OWN "
    "directorial style -- your gritty craft, and the FULL craft layer in "
    "every prompt: camera/lens/movement, lighting and where it comes from, "
    "depth of frame (foreground, midground, background all doing work), "
    "materials and texture, character expression, sound channels, film "
    "grain. Do NOT rewrite or restate the scene's script block; do "
    "not deliver prose, just the prompt. DIALOGUE IS UNTOUCHABLE: any line "
    "in the shot goes into the prompt's {} channel VERBATIM as the script "
    "writes it -- never reworded, never trimmed, never added to. "
    "VOICES (Barry, 2026-08-21: \"lets not forget their voices\"): every "
    "prompt where a character SPEAKS carries that character's voice lock "
    "from the VOICE BIBLE in the canon, verbatim, next to their dialogue -- "
    "@Keth: higher-pitched voice, slightly synthesized; @Vorshara: gritty, "
    "vengeful, a little deeper; @Yannah: smart but sexy; @Bia-2: direct, "
    "the leader; @Tazz: deeper; @B-DUBB-new: clean. Name the language "
    "first ({English: ...}). The written lock is the ONLY thing carrying "
    "the voice -- Higgsfield takes no audio references. "
    "VOICE-OVER vs DIALOGUE: lines the script marks INTERNAL / INTERNAL "
    "MONOLOGUE / VO are VOICE-OVER -- write them as voice-over narration "
    "in that character's voice lock, lips not moving, NEVER as on-camera "
    "{} dialogue (measured failure 2026-08-21: B Dubb's internal monologue "
    "went into {} channels, which makes him speak it on camera). On-camera "
    "lines are {} dialogue with the lock. The V9 "
    "production script (ep1-production-v9-WIP) is the REFERENCE: events, "
    "characters and canon locked; reuse its wording where you genuinely "
    "like it. Never invent story content, never generate a numbered shot "
    "list that doesn't exist. If asked for a shot number that exists in no "
    "script, say so and write the prompt for the matching beat, naming it."
)


def upsert(conn, source_name, content, title):
    existing = conn.execute(
        "SELECT id FROM facts WHERE source_name=? AND status='active'",
        (source_name,)).fetchone()
    if existing:
        conn.execute("UPDATE facts SET content=? WHERE id=?", (content, existing[0]))
        conn.commit()
        print(f"updated  {source_name:32} {len(content):>6,} chars (id {existing[0]})")
    else:
        memory.add_fact(category="private:MovieDirector", content=content,
                        source_name=source_name, title=title)
        print(f"created  {source_name:32} {len(content):>6,} chars")


def main() -> None:
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    upsert(conn, "ep1-v9-format-exemplar.md", EXEMPLAR,
           "EP1 V9 production format -- Barry's exemplar")
    # Standing rule: always-on (no .md), deduped by exact source_name.
    existing = conn.execute(
        "SELECT id FROM facts WHERE source_name='standing-rule-shot-prompt-format' "
        "AND status='active'").fetchone()
    if existing:
        conn.execute("UPDATE facts SET content=? WHERE id=?", (STANDING_RULE, existing[0]))
        conn.commit()
        print(f"updated  standing rule (id {existing[0]})")
    else:
        memory.add_fact(category="private:MovieDirector", content=STANDING_RULE,
                        source_name="standing-rule-shot-prompt-format",
                        title="STANDING RULE -- shot asks are Seedance prompts; V9 format exemplar")
        print("created  standing rule")

    block = memory.brain_context_block("MovieDirector")
    assert "ep1-v9-format-exemplar" in block, "exemplar missing from index"
    assert "shot" in block.lower(), "standing rule not visible"
    print("verified: exemplar in index, standing rule always-on")


if __name__ == "__main__":
    main()
