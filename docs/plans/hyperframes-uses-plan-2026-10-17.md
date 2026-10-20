# Hyperframes in the office -- plan for Barry's OK (2026-10-17)

Hyperframes = HTML + CSS + GSAP composition -> MP4, rendered on CPU through headless Edge, ~7 s for
3 s of 1080p. No model, no GPU, deterministic, runs while the card is busy with Bonsai or a render.
Test state: `tools/hyperframes`, env `HYPERFRAMES_OFFLINE=1` (+ no-telemetry vars); the tool makes no
outbound call; Edge's shell makes one Microsoft handshake per render (accepted 2026-10-17).

## What it is good for here
Motion graphics that are TEXT, SHAPES, NUMBERS, MAPS and stills moving -- things a diffusion model
does badly (legible text, exact numbers, a real map) and ffmpeg does flatly. It is NOT for faces,
people, plants in motion: that stays LTX / Qwen.

## Use 1 -- Ilnora: map + fact cutaways (first, smallest)
A new scene kind for the reel builder, `card`, rendered by Hyperframes instead of a still+motion:
- **Range map**: world/continent outline (one bundled SVG, no tiles, no web), the plant's native
  range highlighted with a 1-2 s reveal, scientific name on screen the required 2.5 s.
- **Fact card**: 3-5 words + one number ("alkaloids: scopolamine, 0.2-0.6 %"), kinetic type on her
  gritty palette, plant photo as background when one exists (`_plant_ref`).
Where it plugs in: `reel_builder` already builds per-scene clips (`_scene_clip`, `_motion_scene_clip`,
`_talk_scene_clip`) and mixes them; a `card` scene becomes one more clip source (`_card_scene_clip`:
write HTML from a template + scene text -> `hyperframes render` -> MP4 at the reel's fmt). The
2-5 s clip rule, cutaway rule and plant-label rule apply unchanged. Her script gains nothing new
to learn at first: the writer marks a part `[card: map]` / `[card: fact]`; later a tool door.
Cost: one template file per card type (`data/video_queue/cards/*.html`), one function, one scene
kind; no change to her mind or persona until it works -- then one line in her craft doc.

## Use 2 -- Vivian: product videos for the store (after Use 1 proves the path)
15-30 s product spots for B Dubb Grows: product still (Qwen-Image or the WooCommerce image)
on a clean black+green layout, name, 3 bullet benefits, price, "bdubbgrowsllc.com", logo sting.
Crop-neutral copy (feeds Google/YouTube ads). Output -> his DESK, he posts; nothing publishes.
Shape: a `product_video` tool on the Creative seat: inputs = product (looked up READ-ONLY from
`store.py`), 3 bullets Vivian writes, template choice (3 layouts: hero / bullets / before-after).
Approval card shows the MP4. Templates reuse the v5 site look in `docs/mockups/` (black + green).

## Use 3 -- later, if 1-2 earn it
- Title cards / chapter cards for Ilnora's Longs (one template, replaces plain ffmpeg text).
- Elliot: shot-list / storyboard reels (stills + captions) for review, not film output.
- Office dashboards to MP4 for Barry's weekly review (numbers that must be exact).

## Rules baked in
- Always `HYPERFRAMES_OFFLINE=1 HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1
  HYPERFRAMES_NO_UPDATE_CHECK=1`; browser = Edge; bin/ffmpeg+ffprobe first on PATH.
- Fonts: bundled Inter only (offline guard) or a Windows system font; no Google Fonts.
- Templates are plain HTML/CSS/GSAP (vendored `gsap.min.js`), no CDN, no web fonts, no trackers.
- Hyperframes never touches the GPU; it may run during a render or a Bonsai turn.
- Patched files (reversible with `npm ci`): dist/chunk-A2DMF2Q6.js, chunk-OZJ4L6SJ.js, chunk-4U5FN6FY.js.
  A version bump re-applies them by hand; the pin is 0.8.167.

## Skills, tools and know-how for the agents (Barry 2026-10-17: "make sure my agents have the
## skills and the tools to use these and the knowhow")
Tools, not seeds: each seat gets a door (tool), a doc (know-how, read on demand), and one persona
line naming the tool (new-tool-needs-persona-mention). Nothing planted about wanting to use it.
- **Vivian (Creative)**: tool `product_video(product, bullets, template)` -> MP4 on his DESK +
  approval card. Skill doc `making-product-videos.md`: what Hyperframes is, the three templates
  and when each fits, the copy rules (crop-neutral, 3 bullets, price from the store, no claims the
  store can't back -- factcheck applies), what it cannot do (faces, moving product shots -> LTX).
- **Ilnora**: `[card: map]` / `[card: fact]` marks in her script + later a `make_card` door. Skill
  doc `map-and-fact-cards.md`: when a card beats a picture (a range, a number, a name), the 2-5 s
  rule, scientific name 2.5 s, one card per chapter at most, never her face on a card.
- **Sophie (Engineer)**: owns the renderer. Skill doc `hyperframes-maintenance.md`: the env vars,
  the three patched files and why, `npm ci` rollback, how to re-apply after a version bump, the
  connection watcher as the test, the one accepted Edge handshake. `office_ops` gets a read-only
  `hyperframes_doctor` view (doctor output + patch presence).
- **Sophie, Text to CAD (for PID)**: tool `cad_generate(spec) -> STEP/STL/3MF on his DESK` running
  cadgen locally (uv, telemetry off, fabrication services never called). Skill doc
  `text-to-cad.md`: cadgen's commands, build123d basics (sketch -> extrude -> fillet, units mm),
  design-for-manufacturing checks for FDM printing (wall >= 1.2 mm, overhangs <= 45 deg, no
  unsupported bridges > 10 mm), tolerances for snap fits (0.2-0.3 mm), how to read a DFM report,
  what the printer (spring 2027, undecided) will need. PID never mixes with the other two ventures:
  the tool is Sophie's, PID knowledge stays in his wall.
- **Every doc** gets a real category, a USE WHEN line with the words he actually types
  ("product video", "spot", "map", "range map", "fact card", "3d print", "cad", "stl", "step"),
  MIT credit where text is adapted, and goes in the brain as a `.md` skill on `private:<seat>`.
- Verified by: one real ask per seat through the office (not a test turn), the file on the DESK, and
  the tool audit (`scripts/tool_audit_2026_09_17.py`) green.

## Order I propose
1. Use 1, map card only, on the next Short Ilnora writes (one template, one scene kind).
2. Fact card.
3. Use 2 once the map card has shipped in a real build.
Each step = its own plan + his yes + one change, verified in a real build.
