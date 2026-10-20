import sys, json, time, urllib.request, uuid
sys.path.insert(0,"scripts")
import compare_keth_loras as C
# no-LoRA control, same prompt/seed as every other test
C.run("morning_ctrl_nolora", None)
# and the known-good v5 for comparison
C.run("morning_v5_recheck", "keth_character_v5.safetensors")
