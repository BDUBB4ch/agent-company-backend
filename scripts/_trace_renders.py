"""Zero-training evidence: render several LoRAs that were trained BEFORE my patch
existed, plus the 30-step one trained WITH it. Same prompt/seed/harness as every
other test. ~12s each, no training.

Question being answered: do LoRAs from this pipeline normally render coherently,
and is 'renders pure noise' unique to the runs my patch was present for?
"""
import sys
sys.path.insert(0, "scripts")
import compare_keth_loras as C
import shutil, pathlib

ROOT = pathlib.Path(".").resolve()
LORAS = ROOT / "tools/ComfyUI/models/loras"
DEAD = ROOT / "data/_dead_v8_checkpoints_2026-08-09"

# bring the quarantined patched ones back just long enough to render them
for n in ["_cliptest_30_steps_00001_.safetensors",
          "keth_character_v8_seg1_150_steps_00001_.safetensors"]:
    if (DEAD / n).exists() and not (LORAS / n).exists():
        shutil.copyfile(DEAD / n, LORAS / n)

RUNS = [
    ("trace_pre_400steps", "keth_character_400_steps_v1.safetensors"),   # pre-patch
    ("trace_pre_v2",       "keth_character_v2.safetensors"),             # pre-patch
    ("trace_pre_v4",       "keth_character_v4.safetensors"),             # pre-patch
    ("trace_patched_30",   "_cliptest_30_steps_00001_.safetensors"),     # WITH patch
    ("trace_patched_150",  "keth_character_v8_seg1_150_steps_00001_.safetensors"),  # WITH patch
]
for prefix, lora in RUNS:
    C.run(prefix, lora)
