# Agent Office — File Map

Map of the Claude Code build on `bdubbs-desktop`, generated 2026-08-29.

**Two folders on the Desktop make up the build:**

| Folder | What it is |
|---|---|
| `C:\Users\Owner\Desktop\AgentCompanyBackend` | Python/FastAPI backend, agent brains, knowledge skills, models, ComfyUI |
| `C:\Users\Owner\Desktop\AgentDashboard` | The browser UI (vanilla HTML/CSS/JS) that talks to the backend |

Entry points: `Start My Studio.bat`, `THE OFFICE.lnk`, `MY STUDIO.lnk`, `TEACH DROP.lnk`, `Barry's AI Agents.lnk` (all on the Desktop), plus `AgentDashboard\Start Dashboard.bat` and `Studio.bat`.

## Orientation

- **`backend/`** — 36 Python modules. The big ones: `main.py` (240K, the API surface), `agents.py` (112K), `llm_router.py` (87K, per-agent model routing), `memory.py` (46K), `comfy_image.py` (44K, local image gen).
- **`knowledge/`** — 102 markdown skill files, the agents' baked-in offline domain knowledge (business ops, commerce, design, engineering, horticulture, legal, marketing, operations, plus the product catalog and directing/prompting skills).
- **`drop/`** — the per-agent file-drop folders, one per agent (Amara, Derek, Elliot, Marcus, Priya, Sophie, Taliyah, Victor, Vivian), each with `knowledge/ persona/ personality/ skills/ _done/ _failed/`. All currently empty.
- **`personalities/` + `personas/`** — the per-agent character/voice files. Note `personas/BusinessOps.md` and `personas/MovieDirector.md` are 0 bytes.
- **`models/`** — Bonsai 27B GGUFs (~15GB). `kokoro/` and `piper_voices/` — local TTS voices (~900MB).
- **`scripts/`** — 210 one-off maintenance/seed/training scripts, mostly dated filenames.
- **`data/`** — runtime output: `brain.db` (7M), logs, JSON backups, generated images, character canon docs. Not source.
- **`tools/`** — vendored third-party: ComfyUI (66,240 files), llama-prism, modular-skills.
- **`workflows/`** — ComfyUI API workflow JSONs (LTX video, SDXL, Qwen edit, Kontext, LoRA training).

## Things worth a look

- **Git is a month behind.** Last commit `7542791` is dated 2026-07-25; there are **76 uncommitted changes** in the working tree. Everything since late July — the dashboard work, agent homes, voice work, Bonsai routing — is unversioned. Worth committing.
- **`memory.db` is 0 bytes** in `data/` while `brain.db` is 7M — likely dead/abandoned, worth confirming before it confuses something.
- **`data/` is mixing runtime output with archives.** ~200 loose files at the top level, including `backend.log` (4M), `backend.log.old` (5M), `bonsai_server.log` (3M), `comfyui.log` (2M), and ~50 `backup_disk_canon_before_*.md` snapshots. A `data/archive/` sweep would make it navigable again.
- **`AgentDashboard\AgentCompanyBackend\venv\`** is a stray empty nested folder — leftover, safe to remove.
- **Six `neo*.html` dashboard variants** (56K–165K each) sit beside `index.html`. Only one is presumably live; the rest are old iterations.
- `.env` is present and correctly gitignored — its contents are deliberately not reproduced here.

## Exclusions

Not expanded below: `venv/`, `.git/`, `__pycache__/`, and the vendored contents of `tools/`. `data/` is listed one level deep only.

---

```
AgentCompanyBackend/
  .claude/
    settings.local.json  (1K)
  .env  (928B)
  .env.example  (2K)
  .gitignore  (834B)
  BUILD_HISTORY.md  (119K)
  CLAUDE.md  (42K)
  HANDOFF-2026-08-13.md  (6K)
  PLAN-brain-graph.md  (9K)
  README.md  (4K)
  _seed_knowledge.py  (7K)
  _seed_ops_design_prod.py  (2K)
  backend/
    agents.py  (112K)
    applog.py  (3K)
    bizwatch.py  (10K)
    bonsai_llm.py  (26K)
    braingraph.py  (9K)
    breakroom.py  (19K)
    codefix.py  (7K)
    comfy_image.py  (44K)
    competitor_watch.py  (8K)
    config.py  (8K)
    db_backup.py  (2K)
    dispatch.py  (7K)
    document_extract.py  (10K)
    health.py  (3K)
    ideation.py  (14K)
    ingest.py  (11K)
    jobs.py  (8K)
    kokoro_tts.py  (5K)
    llm_router.py  (87K)
    main.py  (240K)
    media_understanding.py  (17K)
    memory.py  (46K)
    omnisend_client.py  (5K)
    piper_tts.py  (3K)
    read_project_file.py  (6K)
    recall.py  (17K)
    reflect.py  (22K)
    script_index.py  (16K)
    script_wip.py  (10K)
    searxng_search.py  (3K)
    standing_rules.py  (5K)
    store.py  (15K)
    tone_guard.py  (7K)
    tracing.py  (8K)
    update_checker.py  (6K)
    web_search.py  (2K)
  data/   [runtime data, logs, backups - top level only]
    _bdubb_new_2026-08-10/   [17 files, not expanded]
    _bdubb_src_2026-08-09/   [22 files, not expanded]
    _bia_new_2026-08-11/   [24 files, not expanded]
    _bia_old_refs/   [2 files, not expanded]
    _bia_video_frames/   [4 files, not expanded]
    _dead_v8_checkpoints_2026-08-09/   [18 files, not expanded]
    _rejected_2026-08-09/   [1 files, not expanded]
    _retired_pose_skeletons_2026-08-07/   [15 files, not expanded]
    _sheets/   [18 files, not expanded]
    _tazz_new/   [20 files, not expanded]
    _voice_tmp/   [6 files, not expanded]
    backup_bdubb_build_2026-08-20/   [11 files, not expanded]
    backup_retired_scripts_2026-08-21/   [4 files, not expanded]
    backups/   [15 files, not expanded]
    bia_aug6_crops/   [11 files, not expanded]
    bia_iris_preview/   [3 files, not expanded]
    bionova-evidence/   [8 files, not expanded]
    codefix_backups/   [1 files, not expanded]
    eye_crops/   [2 files, not expanded]
    foldericons/   [5 files, not expanded]
    hero/   [7 files, not expanded]
    ipadapter_test/   [1 files, not expanded]
    keth_v4_preview/   [27 files, not expanded]
    keth_v5_preview/   [43 files, not expanded]
    mockups/   [1 files, not expanded]
    plate_preview/   [11 files, not expanded]
    product-images/   [119 files, not expanded]
    props/   [15 files, not expanded]
    restore/   [16 files, not expanded]
    script_wip_backups/   [12 files, not expanded]
    tazz_233826_preview/   [8 files, not expanded]
    tazz_v4_preview/   [21 files, not expanded]
    v8_progress/   [0 files, not expanded]
    video_frames/   [188 files, not expanded]
    HANDOFF_2026-08-08.md  (13K)
    HANDOFF_2026-08-09.md  (7K)
    HANDOFF_2026-08-11.md  (8K)
    HANDOFF_2026-08-12.md  (7K)
    HANDOFF_2026-08-13.md  (8K)
    HANDOFF_2026-08-14.md  (11K)
    Taliyah.ico  (175K)
    _check_pass2.png  (1008K)
    _kontext_dl_done.txt  (5B)
    _pasted_persona_check.txt  (0B)
    _sophie2.json  (3K)
    _vorshara_masters_sheet.png  (3M)
    _vorshara_v2_preview.png  (4M)
    ab_test_patch.log  (462B)
    abliterated_bonsai_vocab_2026-08-20.json  (6K)
    agent_appearance_captions_2026_08_29.json  (15K)
    agent_homes_2026_08_29.json  (35K)
    agent_homes_v1_offices_2026_08_29.json  (6K)
    amanda_transcripts.json  (9K)
    backend.log  (4M)
    backend.log.old  (5M)
    backend_run.log  (184K)
    backup_all_facts_2026-08-07.json  (795K)
    backup_approval_169_video_test_2026-08-26.json  (891B)
    backup_barry-character-canon_2026-08-07.md  (12K)
    backup_breakroom_before_homes_2026-08-29.py  (14K)
    backup_breakroom_log_test_2026-08-25.jsonl  (2K)
    backup_canon_before_revert_2026-08-08.md  (30K)
    backup_conversations_2026-08-15.json  (61K)
    backup_disk_canon_2026-08-15.md  (75K)
    backup_disk_canon_before_anchors_2026-08-08.md  (12K)
    backup_disk_canon_before_asset_names_2026-08-14.md  (46K)
    backup_disk_canon_before_banger_2026-08-25.md  (103K)
    backup_disk_canon_before_bdubb_build_2026-08-20.md  (81K)
    backup_disk_canon_before_bdubb_voice_2026-08-20.md  (94K)
    backup_disk_canon_before_bdubb_voice_correction_2026-08-20.md  (101K)
    backup_disk_canon_before_bdubb_voice_direction_2026-08-26.md  (107K)
    backup_disk_canon_before_bdubb_voice_ruling_2026-08-20.md  (99K)
    backup_disk_canon_before_build_refinement_2026-08-21.md  (101K)
    backup_disk_canon_before_feminine_rule_2026-08-26.md  (111K)
    backup_disk_canon_before_five_voices_2026-08-26.md  (108K)
    backup_disk_canon_before_forearm_story_2026-08-21.md  (102K)
    backup_disk_canon_before_full_weapon_prompts_2026-08-14.md  (56K)
    backup_disk_canon_before_history_purge_2026-08-26.md  (112K)
    backup_disk_canon_before_keth_synth_2026-08-20.md  (88K)
    backup_disk_canon_before_keth_undouble_2026-08-20.md  (89K)
    backup_disk_canon_before_pitch_ladder_2026-08-20.md  (96K)
    backup_disk_canon_before_sync_2026-08-08.md  (35K)
    backup_disk_canon_before_tazz_selector_2026-08-21.md  (102K)
    backup_disk_canon_before_voice_bible_2026-08-20.md  (84K)
    backup_disk_canon_before_voice_directions_b_2026-08-20.md  (91K)
    backup_disk_canon_before_vorshara_stern_2026-08-26.md  (111K)
    backup_disk_canon_before_vorshara_voice_2026-08-20.md  (89K)
    backup_disk_canon_before_weapon_rulings_2026-08-14.md  (51K)
    backup_disk_canon_before_yannah_canon_2026-08-16.md  (75K)
    backup_disk_canon_before_yannah_forearm_2026-08-16.md  (81K)
    backup_elliot_diet_2026-08-27.json  (137K)
    backup_ep1_v9_before_cinematic_rewrite_2026-08-20.md  (38K)
    backup_fact466_ep1_canon_v7_before_bdubb_build_2026-08-20.md  (110K)
    backup_fact592_before_bdubb_voice_direction_2026-08-26.md  (107K)
    backup_fact592_before_five_voices_2026-08-26.md  (108K)
    backup_fact592_canon_before_anchors_2026-08-08.md  (26K)
    backup_fact592_canon_before_asset_names_2026-08-14.md  (46K)
    backup_fact592_canon_before_banger_2026-08-25.md  (103K)
    backup_fact592_canon_before_yannah_canon_2026-08-16.md  (75K)
    backup_fact638_scifi-action-drama-directing.md_before_replace_2026-08-20.md  (11K)
    backup_fact673_director_persona_v1_2026-08-20.md  (5K)
    backup_fact691_v9_before_cinematic_rewrite_2026-08-20.md  (38K)
    backup_fact878_coding_craft_2026-08-28.md  (4K)
    backup_homes_checkpoint_workpersona_2026-08-28.json  (3K)
    backup_homes_v2_answers_2026-08-28.json  (11K)
    backup_mind_test_content_2026-08-25.json  (15K)
    backup_movie_history_rows_1452_1453_2026-08-20.json  (10K)
    backup_movie_thread_2026-08-23.json  (44K)
    backup_movie_thread_2026-08-25.json  (28K)
    backup_nodes_train_before_clip_2026-08-09.py  (54K)
    backup_personalities_verbatim_2026-08-28.md  (6K)
    backup_priya_mirror_facts_2026-08-26.json  (15K)
    backup_reflections_log_test_2026-08-25.log  (488B)
    backup_seedance_before_vo_rule_2026-08-23.md  (15K)
    backup_seedance_prompting_before_25_2026-08-13.md  (9K)
    backup_start_everything_bat_2026-08-28.bat  (7K)
    backup_talia_crew_facts_2026-08-08.json  (67K)
    backup_taliyah_orphan_1724_2026-08-27.json  (1K)
    backup_taliyah_probe_turns_2026-08-27.json  (1K)
    backup_taliyah_selfimage_purge_2026-08-27.json  (27K)
    backup_thread_business_20260827_005103.json  (12K)
    backup_thread_cio_20260825_014523.json  (4K)
    backup_thread_cio_20260826_232119.json  (6K)
    backup_thread_cio_20260827_010243.json  (12K)
    backup_thread_cio_20260828_014559.json  (33K)
    backup_thread_movie_20260827_002240.json  (28K)
    backup_thread_operations_20260827_004705.json  (15K)
    backup_use_when_routing_2026-08-25.json  (239K)
    backup_victor_probe_test_2026-08-26.json  (2K)
    barry-character-canon.md  (108K)
    bat_parity_test.txt  (87B)
    bdubb-products-2026-08-23.csv  (147K)
    bdubb_products.json  (6K)
    bench_abliterated_bonsai_2026-08-20.json  (5K)
    bench_three_models.json  (16K)
    bench_tools_fixed.json  (2K)
    bia_dataset_audit_2026-08-05.txt  (812B)
    bia_dataset_plan_2026-08-07.md  (8K)
    bia_project_audit_2026-08-07.md  (8K)
    bonsai_content_and_reasoning.json  (12K)
    bonsai_explicit_vocab.json  (8K)
    bonsai_probe_results.json  (5K)
    bonsai_server.log  (3M)
    bonsai_vs_specialists.json  (9K)
    brain.db  (7M)
    brain_mask_b64.txt  (16K)
    breakroom_log.jsonl  (18K)
    canon_caption_tokens_2026-08-07.md  (3K)
    character-bible-DRAFT.md  (18K)
    character-consistency.md  (6K)
    comfyui-tooling-amd.md  (7K)
    comfyui.err.log  (11K)
    comfyui.log  (2M)
    comfyui_kontext.log  (44K)
    comfyui_train.log  (25K)
    competitor_prices_last.json  (6K)
    cpu_encoder_test.txt  (74B)
    dataset_audit_2026-08-04.md  (10K)
    dm_log.jsonl  (8K)
    ep1_production_v9_verbatim.md  (83K)
    ep1_treatment_v8_verbatim.md  (31K)
    ep1_treatment_v9_DRAFT.md  (38K)
    ep1_treatment_v9_verbatim.md  (60K)
    foldericons_preview.png  (14K)
    google-feed-2026-08-23.csv  (1M)
    google-feed-2026-08-23.txt  (1M)
    groupchat_log.jsonl  (6K)
    hero_options.json  (946B)
    hero_upscale_compare.png  (601K)
    homes_amara_faceonly.log  (2K)
    homes_elliot_reroll.log  (2K)
    homes_handtest.log  (2K)
    homes_v10_barryframing.log  (2K)
    homes_v2_build.log  (3K)
    homes_v2_rerun_priya.log  (3K)
    homes_v3_fullbody.log  (3K)
    homes_v3_rerolls.log  (2K)
    homes_v4_amara_body.log  (2K)
    homes_v4_amara_fresh.log  (2K)
    homes_v4_amara_full.log  (2K)
    homes_v4_amara_reroll.log  (2K)
    homes_v4_wideshots.log  (2K)
    homes_v5_fullscene.log  (2K)
    homes_v6_faces.log  (2K)
    homes_v7_panel.log  (2K)
    homes_v8_faces_hands.log  (2K)
    homes_v8_fresh.log  (2K)
    homes_v9_framing.log  (2K)
    jobs.log  (24K)
    keth_canon_check.json  (19K)
    keth_dataset_plan_2026-08-07.md  (9K)
    kontext_all.log  (2K)
    kontext_keth_redo.log  (265B)
    ltx_test_result.txt  (21B)
    marcus_transcripts.json  (10K)
    memory.db  (0B)
    mystudio.ico  (34K)
    mystudio_comfy.log  (5K)
    mystudio_ltx_workflow.json  (7K)
    mystudio_preview.png  (12K)
    paired_rest.log  (1K)
    paired_test.log  (523B)
    phase5_before_probes.txt  (903B)
    qwen_amara.log  (333B)
    qwen_download.log  (758B)
    qwen_download2.log  (335B)
    qwen_gguf_download.log  (317B)
    qwen_test2.log  (301B)
    reflections.log  (5K)
    relight.log  (518B)
    seedance-prompting.md  (8K)
    tazz_dataset_plan_2026-08-07.md  (5K)
    theoffice.ico  (23K)
    theoffice_preview.png  (6K)
    traces.jsonl  (913K)
    train_5_overnight.log  (3K)
    train_batch1_v4.log  (138B)
    train_bia_keth_night.log  (947B)
    train_keth_v4.log  (903B)
    train_keth_v5.log  (831B)
    train_keth_v6.log  (1K)
    train_keth_v7.log  (862B)
    train_keth_v8.log  (1K)
    train_queue_all.log  (10K)
    train_tazz_v3.log  (1K)
    train_vorshara_v5.log  (1007B)
    tunableop_comfy0.csv  (0B)
    venv_video_test.txt  (28B)
    video-directing.md  (5K)
    video_rendering.flag  (16B)
    vorshara_v5_sort.txt  (2K)
    watchdog.log  (14K)
  drop/
    Amara/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Derek/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Elliot/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Marcus/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Priya/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Sophie/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Taliyah/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Victor/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
    Vivian/
      _done/
      _failed/
      knowledge/
      persona/
      personality/
      skills/
  knowledge/
    bdubb-products/
      SKILL.md  (4K)
      bionova-coco-feeding-chart.md  (4K)
      bionova-cost-basis.md  (5K)
      bionova-innexo-lab-results.md  (5K)
      bionova-suggested-retail-2025.md  (4K)
      bionova-wholesale-pricelist.md  (6K)
      competitor-hydrobuilder.md  (4K)
      global-garden-wholesale-pricelist.md  (48K)
    business_ops/
      competitive-strategy/
        SKILL.md  (9K)
      tax-fundamentals/
        SKILL.md  (12K)
      analyze.md  (3K)
      close-management.md  (3K)
      data-visualization.md  (5K)
      explore-data.md  (4K)
      financial-statements.md  (5K)
      journal-entry-prep.md  (3K)
      reconciliation.md  (4K)
      statistical-analysis.md  (5K)
      variance-analysis.md  (6K)
    commerce/
      ads-performance-analysis.md  (5K)
      business-finance-and-taxes.md  (5K)
      product-sourcing-and-dropshipping.md  (5K)
      supplier-scam-red-flags.md  (4K)
    design/
      accessibility-review.md  (2K)
      design-critique.md  (2K)
      design-handoff.md  (2K)
      design-system.md  (2K)
      research-synthesis.md  (1K)
      user-research.md  (2K)
      ux-copy.md  (2K)
    engineering/
      prompt-engineering/
        SKILL.md  (11K)
      architecture.md  (3K)
      code-review.md  (3K)
      codex-and-coding-agents.md  (3K)
      coding-craft.md  (6K)
      debug.md  (3K)
      debugging-discipline.md  (3K)
      defensive-security.md  (4K)
      deploy-checklist.md  (3K)
      documentation.md  (3K)
      incident-response.md  (2K)
      mojo-language.md  (4K)
      system-design.md  (2K)
      tech-debt.md  (2K)
      testing-strategy.md  (3K)
      web-development.md  (4K)
      writing-agent-skills.md  (6K)
    horticulture/
      bionova-and-recommendations.md  (4K)
      growing-media-soil-hydro-coco.md  (3K)
      indoor-crops-and-equipment.md  (4K)
      plant-nutrition-fundamentals.md  (4K)
    legal/
      canned-responses.md  (5K)
      compliance-check.md  (6K)
      contract-review.md  (8K)
      legal-risk-assessment.md  (5K)
      meeting-briefing.md  (3K)
      nda-triage.md  (5K)
    marketing/
      bdubb-product-shots.md  (3K)
      brand-promo-style.md  (5K)
      brand-review.md  (5K)
      campaign-plan.md  (6K)
      competitive-brief.md  (5K)
      content-creation.md  (4K)
      draft-content.md  (2K)
      email-sequence.md  (5K)
      performance-report.md  (6K)
      seo-audit.md  (4K)
      viral-hooks.md  (13K)
    operations/
      capacity-plan.md  (2K)
      change-request.md  (2K)
      compliance-tracking.md  (3K)
      process-doc.md  (1K)
      process-optimization.md  (2K)
      risk-assessment.md  (2K)
      runbook.md  (1K)
      status-report.md  (1K)
      vendor-review.md  (2K)
    product-catalog-full/
      SKILL.md  (56K)
    product-research/
      SKILL.md  (8K)
    productivity/
      task-triage.md  (3K)
      workplace-memory.md  (3K)
    starter-brain/
      content-engine.md  (2K)
      context-interview-method.md  (3K)
      daily-briefing-method.md  (2K)
      five-tool-stack-audit.md  (2K)
      lead-triage.md  (2K)
      voice-dna-capture.md  (3K)
    3d-previz-blockout.md  (4K)
    character-image-pipeline.md  (5K)
    character-visual-canon.md  (6K)
    director-influences.md  (6K)
    director-persona.md  (8K)
    fixing-renders-with-the-editor.md  (4K)
    flagging-judgment-calls.md  (3K)
    how-to-think.md  (4K)
    local-generation-toolkit.md  (5K)
    oneiric-production-method.md  (15K)
    prop-shot-structure.md  (4K)
    scifi-action-drama-directing.md  (11K)
    seedance-production-tasks.md  (7K)
    seedance-prompting.md  (21K)
    seedream-image-generation.md  (6K)
  kokoro/
    dl.log  (26K)
    kokoro-v1.0.onnx  (310M)
    voices-v1.0.bin  (27M)
  models/
    bonsai/
      Ternary-Bonsai-27B-Abliterated-LowDeg-Q2_0.gguf  (7G)
      Ternary-Bonsai-27B-Q2_0.gguf  (7G)
      Ternary-Bonsai-27B-mmproj-BF16.gguf  (888M)
      curl2.log  (109K)
      curl_abliterated.log  (133K)
  personalities/
    BusinessOps.md  (1K)
    CIO.md  (262B)
    Creative.md  (201B)
    Engineer.md  (1K)
    Legal.md  (207B)
    Marketing.md  (235B)
    MovieDirector.md  (266B)
    Operations.md  (378B)
    Taliyah.md  (2K)
  personas/
    BusinessOps.md  (0B)
    Engineer.md  (1K)
    MovieDirector.md  (0B)
  piper_voices/
    en_GB-alan-medium.onnx  (60M)
    en_GB-alan-medium.onnx.json  (5K)
    en_GB-alba-medium.onnx  (60M)
    en_GB-alba-medium.onnx.json  (5K)
    en_GB-cori-high.onnx  (109M)
    en_GB-cori-high.onnx.json  (5K)
    en_GB-jenny_dioco-medium.onnx  (60M)
    en_GB-jenny_dioco-medium.onnx.json  (5K)
    en_GB-northern_english_male-medium.onnx  (60M)
    en_GB-northern_english_male-medium.onnx.json  (5K)
    en_US-amy-medium.onnx  (60M)
    en_US-amy-medium.onnx.json  (5K)
    en_US-hfc_female-medium.onnx  (60M)
    en_US-hfc_female-medium.onnx.json  (5K)
    en_US-joe-medium.onnx  (60M)
    en_US-joe-medium.onnx.json  (5K)
    en_US-ryan-high.onnx  (115M)
    en_US-ryan-high.onnx.json  (4K)
  requirements.txt  (688B)
  scripts/
    _ab_test_patch.py  (2K)
    _bia_test.py  (1012B)
    _control_check.py  (296B)
    _find_rear_shot.py  (982B)
    _inspect_lora.py  (2K)
    _keth_diag.py  (1K)
    _paired_rest.py  (2K)
    _paired_test.py  (927B)
    _relight.py  (1K)
    _tazz_lit2.py  (609B)
    _tazz_redo.py  (496B)
    _trace_renders.py  (1K)
    _validate_clip_patch.py  (1K)
    _yannah_redo.py  (499B)
    abliterated_vocab_test_2026_08_20.py  (8K)
    abliterated_vocab_vulgar_rerun_2026_08_20.py  (4K)
    add_bionova_approval_status_2026_08_16.py  (2K)
    add_broll_rule_2026_08_16.py  (2K)
    add_new_yannah_frames.py  (4K)
    add_render_chat_lock_2026_08_29.py  (4K)
    add_routing_filing_rule_2026_08_16.py  (3K)
    add_routing_lines_2026_08_16.py  (8K)
    add_season2_creative_input_2026_08_23.py  (3K)
    add_use_when_grammar_skills_2026_08_16.py  (4K)
    add_use_when_routing_2026_08_25.py  (6K)
    add_video_reference_workflow_2026_08_16.py  (3K)
    add_vo_vs_dialogue_rule_2026_08_23.py  (5K)
    analyze_voice_samples_2026_08_20.py  (6K)
    apply_anchor_bible_2026_08_08.py  (13K)
    apply_asset_names_2026_08_14.py  (6K)
    apply_bdubb_build_everywhere_2026_08_20.py  (5K)
    apply_bdubb_build_refinement_2026_08_21.py  (3K)
    apply_bdubb_build_ruling_2026_08_20.py  (5K)
    apply_bdubb_build_to_script_2026_08_20.py  (3K)
    apply_bdubb_voice_2026_08_20.py  (5K)
    apply_bdubb_voice_direction_2026_08_26.py  (4K)
    apply_bdubb_voice_is_barry_2026_08_20.py  (5K)
    apply_bia_canon_captions.py  (2K)
    apply_bia_figure_2026_08_10.py  (2K)
    apply_bia_spec_2026_08_10.py  (4K)
    apply_canon_anchors.py  (5K)
    apply_every_mention_rule_2026_08_14.py  (2K)
    apply_feminine_voice_rule_2026_08_26.py  (3K)
    apply_five_voice_directions_2026_08_26.py  (10K)
    apply_handle_destination_rule_2026_08_14.py  (4K)
    apply_handle_substitution_rule_2026_08_14.py  (3K)
    apply_keth_voice_synth_2026_08_20.py  (5K)
    apply_keth_voice_undouble_2026_08_20.py  (4K)
    apply_names_roster_2026_08_14.py  (5K)
    apply_pitch_ladder_2026_08_20.py  (6K)
    apply_talia_ruling_2026_08_14.py  (3K)
    apply_tazz_bruises_2026_08_21.py  (3K)
    apply_tazz_weapon_selector_2026_08_21.py  (2K)
    apply_voice_bible_2026_08_20.py  (7K)
    apply_voice_directions_2026_08_20b.py  (6K)
    apply_vorshara_stern_2026_08_26.py  (4K)
    apply_vorshara_voice_2026_08_20.py  (5K)
    apply_weapon_pairing_fix_2026_08_14.py  (3K)
    apply_weapon_pairing_rule_2026_08_14.py  (4K)
    apply_weapon_prompts_2026_08_14b.py  (22K)
    apply_weapon_props_2026_08_11.py  (7K)
    apply_weapon_rulings_2026_08_14.py  (10K)
    apply_yannah_canon_2026_08_16.py  (10K)
    apply_yannah_forearm_ruling_2026_08_16.py  (4K)
    apply_yannah_forearm_story_2026_08_21.py  (3K)
    assign_product_brands_2026_08_23.py  (5K)
    audit_store_vs_gg.py  (3K)
    augment_dataset.py  (3K)
    bench_abliterated_bonsai_2026_08_20.py  (3K)
    bench_three_models.py  (11K)
    bench_tools_fixed.py  (4K)
    bionova_sale_15pct_2026_08_23.py  (5K)
    bonsai_content_and_reasoning.py  (10K)
    bonsai_explicit_vocab.py  (6K)
    bonsai_vs_specialists.py  (7K)
    build_agent_homes_2026_08_29.py  (20K)
    build_anchors_card_2026_08_21.py  (4K)
    build_bia_v4_dataset.py  (4K)
    build_dataset_downscale_only.py  (5K)
    build_gg_pricelist_skill.py  (3K)
    build_gguf_workflows.py  (3K)
    build_tazz_v3_dataset.py  (5K)
    build_yannah_v3_dataset.py  (5K)
    chunk_ep1_treatment_v8_2026_08_20.py  (7K)
    chunk_ep1_treatment_v9_cinematic_2026_08_20.py  (8K)
    cleanup_elliot_2026_08_15.py  (3K)
    compare_keth_loras.py  (5K)
    compare_vorshara_loras.py  (4K)
    condense_seedance_skill_2026_08_15.py  (2K)
    depad_training_images.py  (4K)
    download_qwen_gguf_2026_08_28.py  (3K)
    download_qwen_image_edit_2026_08_28.py  (3K)
    export_google_feed.py  (9K)
    export_products_csv.py  (5K)
    fix_bdubb_voice_ruling_2026_08_20.py  (7K)
    fix_bionova_seo_2026_08_23.py  (8K)
    fix_canon_after_build_sweep_2026_08_20.py  (5K)
    fix_handle_destination_rule_2026_08_14.py  (3K)
    fix_history_routing_dates_2026_08_25.py  (2K)
    fix_pillarbox.py  (4K)
    fix_reply_routing_sweep_2026_08_29.py  (4K)
    fix_start_everything_bat_2026_08_28.py  (1K)
    generate_hero_options.py  (6K)
    install_agent_portraits_2026_08_27.py  (3K)
    install_seedance_skills_2026_08_15.py  (2K)
    kontext_all_characters.py  (4K)
    kontext_generate.py  (5K)
    margin_audit_2026_08_23.py  (5K)
    minimize_captions.py  (5K)
    normalize_training_images.py  (3K)
    office_health.py  (6K)
    organize_brains.py  (12K)
    pose_skeleton.py  (9K)
    preflight_dataset.py  (3K)
    prep_bia_v4.py  (6K)
    prep_keth_v4.py  (9K)
    prep_keth_v5.py  (6K)
    prep_tazz_v4.py  (8K)
    prepare_bia_v3.py  (3K)
    prepare_keth_v3_captions.py  (1K)
    prepare_tazz_v3_captions.py  (1K)
    prepare_vorshara_v5.py  (2K)
    probe_bonsai_elliot_64k.py  (4K)
    probe_bonsai_office_prompt.py  (5K)
    probe_bonsai_tools_and_refusal.py  (6K)
    probe_gguf_video.py  (4K)
    probe_system_status_2026_08_29.py  (974B)
    probe_v2_solo_renders.py  (4K)
    probe_voice_samples_2026_08_20.py  (2K)
    qwen_edit.py  (5K)
    qwen_t2i.py  (4K)
    qwen_vs_sdxl_test.py  (3K)
    rebuild_vorshara_dataset.py  (10K)
    record_repricing_2026_08_13.py  (2K)
    refresh_product_catalog.py  (3K)
    relax_bia_guardrail_2026_08_10.py  (2K)
    remove_bia_framing_line_2026_08_10.py  (2K)
    render_posed.py  (5K)
    replace_design_skills_2026_08_12.py  (3K)
    replace_director_skill_2026_08_20.py  (4K)
    reprice_ghf_to_market_2026_08_23.py  (6K)
    resume_download.py  (2K)
    retire_v7_install_v8_2026_08_21.py  (5K)
    rollout_channel_colors_2026_08_29.py  (4K)
    run_bia_v4.bat  (221B)
    run_keth_v4.bat  (224B)
    run_keth_v5.bat  (190B)
    run_keth_v6.bat  (190B)
    run_keth_v7.bat  (840B)
    run_keth_v8.bat  (2K)
    run_tazz_v4.bat  (224B)
    run_train_queue_all.bat  (3K)
    run_train_queue_v8.bat  (2K)
    seed_ads_analysis_skill_2026_08_29.py  (2K)
    seed_amara_selfimage_2026_08_28.py  (4K)
    seed_bionova_lab_results_2026_08_13.py  (3K)
    seed_commerce_skills_2026_08_13.py  (2K)
    seed_director_influences_2026_08_23.py  (3K)
    seed_ep1_treatment_v8_2026_08_20.py  (4K)
    seed_filing_rules.py  (4K)
    seed_hearing_skill_2026_08_29.py  (3K)
    seed_how_to_think_2026_08_29.py  (2K)
    seed_image_pipeline_skill.py  (1K)
    seed_new_skills_2026_08_11.py  (2K)
    seed_organization_skill_2026_08_25.py  (4K)
    seed_sophie_craft_2026_08_29.py  (2K)
    seed_starter_brain_skills_2026_08_29.py  (3K)
    seed_story_writing_skill_2026_08_16.py  (3K)
    seed_v9_format_exemplar_2026_08_20.py  (14K)
    seed_vivian_store_skill_2026_08_21.py  (6K)
    set_keth_eyes_dark_green.py  (3K)
    split_character_sheets.py  (9K)
    stack_watchdog.ps1  (3K)
    stage_banger_ref_2026_08_25.py  (1K)
    start_bonsai.ps1  (2K)
    studio_cli.py  (5K)
    sulphur_smoke_test.py  (3K)
    sync_canon_banger_2026_08_25.py  (2K)
    teach_mojo_skills_2026_08_28.py  (3K)
    test_banger_handle_2026_08_25.py  (4K)
    test_job_routing.py  (5K)
    test_keth_v4.py  (4K)
    test_shot_lookup.py  (3K)
    tighten_face_refs_2026_08_28.py  (2K)
    time_ltx.py  (3K)
    train_5_characters_overnight.bat  (4K)
    train_5_scheduled_wrapper.bat  (184B)
    train_batch1_v4.bat  (3K)
    train_batch1_v4_wrapper.bat  (173B)
    train_bia_keth_night.bat  (2K)
    train_bia_keth_night_wrapper.bat  (175B)
    train_bia_v4.bat  (2K)
    train_bia_v4_wrapper.bat  (159B)
    train_character_checkpointed.py  (9K)
    train_character_loras.py  (10K)
    train_keth_v8_checkpointed.py  (7K)
    train_one_v4.bat  (4K)
    train_tazz_v3.bat  (2K)
    train_tazz_v3_wrapper.bat  (161B)
    train_vorshara_overnight.bat  (1K)
    train_vorshara_v4.bat  (2K)
    train_vorshara_v5_curriculum.bat  (2K)
    train_vorshara_v5_wrapper.bat  (180B)
    train_yannah_v3.bat  (2K)
    train_yannah_v3_wrapper.bat  (165B)
    update_claudemd_2026_08_23.py  (9K)
    update_seedance_skill_2026_08_13.py  (3K)
    upgrade_sophie_coder_2026_08_28.py  (5K)
    upscale_hero_image.py  (4K)
    verify_bonsai_router_path.py  (3K)
  searxng/
    docker-compose.yml  (272B)
    settings.yml  (818B)
  tools/   [vendored third-party tools - summary only]
    ComfyUI/   [66240 files, not expanded]
    llama-prism/   [104 files, not expanded]
    modular-skills/   [111 files, not expanded]
  workflows/
    sulphur/
      LICENSE.txt  (21K)
      ltx23_i2v_base.json  (71K)
      ltx23_i2v_distilled.json  (12K)
      ltx23_t2v_base.json  (72K)
      ltx23_t2v_distilled.json  (73K)
    comfy_i2v_ltx_api.json  (7K)
    comfy_ipadapter_ref_api.json  (1K)
    comfy_kontext_api.json  (3K)
    comfy_qwen_edit_api.json  (1K)
    comfy_qwen_edit_gguf_api.json  (2K)
    comfy_qwen_t2i_gguf_api.json  (1K)
    comfy_t2i_sdxl_api.json  (1K)
    comfy_t2v_ltx_api.json  (7K)
    comfy_t2v_sulphur_api.json  (9K)
    comfy_train_lora_api.json  (1K)

AgentDashboard/
  Start Dashboard.bat  (2K)
  Studio.bat  (2K)
  Taliyah.ico  (175K)
  app.js  (88K)
  assets/
    cyber/   [31 files]
    homes/   [36 files]
    office_bg.png  (2M)
    offices/   [9 files]
    plates/   [2 files]
    portraits/   [9 files]
  brainmap.js  (16K)
  index.html  (16K)
  neo-chamber-v1.html  (106K)
  neo-chamber.html  (165K)
  neo-holo.html  (64K)
  neo-roll6.html  (65K)
  neo-v4.html  (56K)
  neo.html  (65K)
  r1-addons.js  (9K)
  style.css  (29K)
  theme-cyber.css  (9K)
  theme-cyber.js  (5K)
```
