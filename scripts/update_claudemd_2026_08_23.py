"""Record the 2026-08-22/23 session in CLAUDE.md (Barry's maintenance rule:
the file documents the entire build and must never go stale)."""
import io

P = r"C:\Users\Owner\.claude\CLAUDE.md"
ANCHOR = "## Planned, not started"

BLOCK = """## SESSION 2026-08-22/23 -- SPEED, THE STUDIO, VIVIAN, ELLIOT'S IDENTITY

**THE REAL SPEED FIX -- CACHE-STABLE PROMPTS (Barry: "i need snappy responses").**
Measured from `data/bonsai_server.log`: EVERY reply re-read the whole ~50K-token prompt
(61-70s) before writing a word. Cause: per-message content (recall, shot-ask injections,
the presence block, product context) mutated the SYSTEM prompt, and llama-server only
reuses an UNCHANGED prefix. Fix, per the industry rule (static first and frozen, dynamic
last -- a published case went 7%->84% cache hits): the system prompt is byte-stable within
a session now, and everything per-message rides at the END of the USER turn via
`_deferred_parts` in main.py. **Measured: prefill 65s -> ~11s.** None of it is logged to
history, so threads and summaries stay clean. If replies drag again, check
`prompt eval time` in the server log FIRST -- a full-token-count prefill on a follow-up
means something volatile crept back into the PREFIX.
- Also `--kv-unified` + `--cache-idle-slots` (evicted prompts save/restore via RAM, so
  switching agents costs ~1s instead of a full re-read) and **BONSAI_NUM_CTX 98304 ->
  49152**. `-np 2` was tried and REVERTED: two live sequences dropped generation to
  14-29 tok/s.
- Long replies are the only thing still slow, and only while the GPU sits in the degraded
  state (12.6 tok/s vs 41 healthy) that a REBOOT clears. Barry confirmed short replies
  feel fine: "it wasnt really slow just now."

**ELLIOT: CANON DIET, THE FUSION, AND HIS OWN WORK.**
- `barry-character-canon` (~100K, a third history/superseded records) is **UNPINNED**;
  `character-anchors-card` (21.5K VERBATIM extraction -- six anchors + names roster +
  weapon pairing) is pinned in its place, built by
  `scripts/build_anchors_card_2026_08_21.py` (re-run whenever canon changes; the card is
  DERIVED, never hand-edited). Full canon stays active and on-demand. Always-on 169K -> 92K.
- **THE FUSION** (Barry: "blend his directing style with his seedance prompting... it
  should just be the way he does it" -> "build it into his being"). Fine-tuning is CLOSED
  OFF: Bonsai is a ternary Q2_0 GGUF (cannot be trained) and 27B QLoRA needs ~22-24GB vs
  his 16GB. So it is stated as IDENTITY inside the persona block in agents.py, right after
  his verbatim "Now direct." -- "You do not have a directing mode and a prompt-writing
  mode" -- plus a worked exemplar injected on shot asks. **His persona text is untouched
  and verbatim.**
- **HIS OWN WORK SHAPES HIM:** when Barry blesses a prompt, main.py saves that fence into
  `prompt-exemplars.md` (private:MovieDirector, newest 8) and injects it AHEAD of any
  Claude-written example on later shot asks. Capture is CODE -- the model never decides it
  was approved. Anti-poisoning guards: praise only counts in a message <=60 chars, any
  but/except/change/instead cancels it, explicit "save that"/"bless" always works.
  **That corpus is also the dataset a future fine-tune would need.**
- **VO vs DIALOGUE** (measured: he put B Dubb's INTERNAL monologue in `{}`). `{}` is SPOKEN
  dialogue and drives LIP-SYNC. INTERNAL/VO lines stay OUT of the fence, delivered under it
  labelled for post: `VO (@B-DUBB-new, clean voice): "..."`. SFX glyph is `<>` exactly (he
  emitted `<[]>`). The fence carries ONLY the paste-ready prompt -- SHOT header, CAMERA:,
  ENVIRONMENT:, EXPRESSION:, NEG: are SCRIPT format and never go to the generator. Written
  into `seedance-prompting` (pinned) and the shot-ask directive.
- Shot asks inject the named shot's real block from the V9 WIP as source material; the
  fence-strip no longer eats correct fences (short follow-ups such as "redo it" after a
  fence-bearing reply are protected).

**THE FULL V9 PRODUCTION SCRIPT IS INSTALLED.** Barry pasted both halves; stitched verbatim
to `data/ep1_production_v9_verbatim.md` and installed as the living WIP -- **38 blocks**
(B-ROLL 01-02, SHOT 01-23, SCENE A-H). `script_index` discovers it, so read_scene, the
verbatim gate and whole-script asks all serve it; the ledger lists all 38.
`script_index._first_line` now strips markdown so `### **SHOT 01 ...**` parses.

**VIVIAN: READ-ONLY SITE ACCESS + PRODUCT PHOTOS** (Barry: "she needs to be able to see my
site, but not write. Not yet anyways, because you need to help me build all this right,
first").
- `store.browse_site(what, query)` -- overview | categories | products | pages | posts.
  Products/categories via WooCommerce, pages/posts via WordPress public wp/v2 (`_wp_get`,
  deliberately separate so a marketing question never travels with store credentials).
  HTML entities decoded. store.py still contains NO write verb.
- `lookup_product` now returns THE REAL PRODUCT PHOTO URL, and **118 product photos are
  downloaded to `data/product-images/`** with `_index.json`.
- Granted to Vivian plus Derek/Amara/Victor. **PINNED skill `working-from-the-live-store`**
  (`scripts/seed_vivian_store_skill_2026_08_21.py`) teaches the tools, the read-only
  boundary, a validation loop, and the rule that costs money: **commercial work renders on
  RealVisXL ONLY -- Kontext/FLUX is non-commercial, film only.**
- Omnisend write access deliberately NOT granted: she drafts, approvals queue, Barry sends.
  `OMNISEND_API_KEY` is still absent from .env.

**CHARACTER LoRAs: THE "FRIED" ASSUMPTION WAS FALSE.** Measured effective delta norms
(up@down x alpha/rank) across all 20 files: every one is 0.5-2.2, INCLUDING keth v7 which
the docs call fried. Noise output has some OTHER cause -- do not blame the weights again
without re-measuring. `CHARACTER_LORAS` was flipped to "all latest" on Barry's instruction,
bia_v3 rendered PURE NOISE within minutes, and it is **REVERTED to the proven set**
(bdubb/bia/yannah/tazz base, keth v5, vorshara v4). The vN files were never eyeballed after
their overnight runs -- newest is not working.

**MY STUDIO -- Barry's own generation app, separate from the office.**
`Desktop/MyStudio.html` + `Desktop/Start My Studio.bat` (its own ComfyUI on **port 8189**;
the office keeps 8188). Clears the GPU on launch, frees it when the window closes. IMAGE
tab (fast SDXL, or reference-governed Kontext when a character is tapped), VIDEO tab (LTX
with audio; a tapped character's reference becomes the start frame), gallery with
START / REF / DELETE per result.
- **Character buttons load his CURRENT looks** from the `Bia Project` folders, staged as
  `tools/ComfyUI/input/char_<key>_{face,body,group}.png`. The office's `bia_face`,
  `bia_body` and `yannah_ref` were updated to the new looks too (old kept as
  `*_OLD_backup.png`).
- **Group shots are ONE pass, not a chain.** Measured: Kontext's "add X into the scene on
  the left" reports SUCCESS and silently returns the scene unchanged. All references are
  stitched into one strip and everyone placed in a single pass, named by position.
- **Close-up references cause giant heads** (Kontext matches scale across the stitch), so
  group work uses BODY refs cropped tight -- `char_*_group.png`, capped 1024 long edge;
  stitching four 3520x4704 images OOM'd the card.
- Fidelity falls off past ~3-4 characters; composition beats fighting it.
- Local file caching is brutal: after editing MyStudio.html, CLOSE THE TAB (or use
  incognito) -- a plain refresh serves the stale copy. The build tag top-right is the tell.

**TALIYAH: THE LLM SLANG-SCRUB IS RETIRED** (Barry: "get rid of the scrub slang. i ll see
how she talks after"). It was hardwired to the OLLAMA backend, so under the one-big-thing
VRAM rule EVERY reply of hers killed the shared Bonsai server and forced a cold restart
plus full re-prefill for the next seat -- ~45s replies for her and cold starts for everyone
after her. The free regex pass stays; a REGISTER rule now sits in her recency tail. Revert
path is in the code comment.

**ANTI-DEGRADATION INSTRUMENT: `scripts/office_health.py`** (read-only). Prints the
resolved model per seat, always-on load per agent (warn 140K / fail 190K -- Elliot produced
word salad at 220K), auto-summary creep on the always-on shelf, conversation depth, and the
exemplar corpus size. **Run it when replies feel off, before changing anything.** Every
real fix this session came from measuring first.

**Desktop:** organised into Apps / Archive / Games / Installers / Launchers with custom
icons; `MY STUDIO` and `THE OFFICE` shortcuts (`data/mystudio.ico`, `data/theoffice.ico`,
`data/foldericons/`). `Taliyah.ico` moved to `data/` and "Barry's AI Agents.lnk" points
there now. `hostinger-recovery-codes.txt` is still sitting in the open on the Desktop --
flagged to him, his call.

"""


def main() -> None:
    text = io.open(P, encoding="utf-8").read()
    if "SESSION 2026-08-22/23" in text:
        print("already documented -- nothing to do")
        return
    assert ANCHOR in text, "anchor heading not found"
    io.open(P, "w", encoding="utf-8").write(text.replace(ANCHOR, BLOCK + ANCHOR, 1))
    print(f"CLAUDE.md updated (+{len(BLOCK):,} chars)")


if __name__ == "__main__":
    main()
