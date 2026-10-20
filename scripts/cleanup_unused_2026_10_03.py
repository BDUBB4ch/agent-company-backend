"""Barry 2026-10-03: "get rid of all that we are not using. Keep Bonsai 1 as fall back."
MOVES (never deletes) every unused item into C:\\Users\\Owner\\Desktop\\DELETE-ME-2026-10-03, keeping the folder layout,
and writes MANIFEST.txt there. Same drive = instant rename. Barry deletes that folder himself (Shift+Delete)."""
import glob
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
DEST = os.path.join(HOME, "Desktop", "DELETE-ME-2026-10-03")
M = os.path.join(ROOT, "tools", "ComfyUI", "models")

ITEMS = {
    "1 LTX-2.3 set (replaced by LTX-2.5 on 09-04)": [
        f"{M}/checkpoints/ltx-2.3-22b-dev-fp8.safetensors",
        f"{M}/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
        f"{M}/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors",
        f"{M}/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        f"{M}/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"],
    "2 Z-Image _nvme duplicates (code loads the D: copies)": [
        f"{M}/unet/z_image_turbo_bf16_nvme.safetensors",
        f"{M}/unet/z_image_turbo_int8_convrot_nvme.safetensors",
        f"{M}/text_encoders/qwen_3_4b_nvme.safetensors"],
    "3 LatentSync (replaced by LTX talking)": [f"{ROOT}/tools/latentsync", f"{ROOT}/tools/latentsync-venv"],
    "4 character LoRA training leftovers": sorted(glob.glob(f"{M}/loras/*_sep04_seg*")) + [f"{M}/loras/_fried_vorshara_sep04"],
    "5 voice bake-off losers": [f"{ROOT}/tools/tts/models/Qwen__Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                                f"{ROOT}/tools/tts/models/Qwen__Qwen3-TTS-Tokenizer-12Hz",
                                f"{ROOT}/tools/tts/models/ResembleAI__chatterbox-turbo",
                                f"{ROOT}/tools/tts/qwen3tts", f"{ROOT}/tools/tts/chatterbox"],
    "6 pip download cache": [os.path.join(HOME, "AppData", "Local", "pip", "cache")],
    "8 Qwen3.8-27B candidate (never wired)": [f"{ROOT}/models/qwen38"],
    "9 Kev (Laya's teacher; weekly retrain doesn't use it)": [f"{ROOT}/tools/kev", f"{ROOT}/tools/kev-hf"],
    "10 unjudged _sep04 character LoRAs": sorted(glob.glob(f"{M}/loras/*_character_sep04.safetensors")),
}


def size(p: str) -> int:
    if os.path.isfile(p):
        return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs
               if os.path.isfile(os.path.join(r, f)))


def main() -> None:
    os.makedirs(DEST, exist_ok=True)
    lines, total = [], 0
    for label, paths in ITEMS.items():
        got = 0
        for p in paths:
            p = os.path.normpath(p)
            if not os.path.exists(p):
                lines.append(f"  (already gone) {p}")
                continue
            rel = os.path.relpath(p, os.path.splitdrive(p)[0] + os.sep)
            target = os.path.join(DEST, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            n = size(p)
            try:
                shutil.move(p, target)
                got += n
                lines.append(f"  moved {n / 1e9:6.2f} GB  {p}")
            except OSError as e:
                lines.append(f"  FAILED {p}: {e}")
        total += got
        lines.insert(len(lines) - len(paths), f"{label}: {got / 1e9:.1f} GB")
    lines.append(f"TOTAL moved: {total / 1e9:.1f} GB -> {DEST}")
    lines.append("To restore anything: move it back to the path shown. To free the space: Shift+Delete this folder.")
    with open(os.path.join(DEST, "MANIFEST.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
