# junction_comfyui25_to_office_models.ps1 -- make D:\ComfyUI25 see the office's
# models and input folders IN PLACE, so repointing COMFY_DIR at it breaks nothing.
#
# Why junctions and not extra_model_paths.yaml: comfy_image.py and main.py do
# DIRECT filesystem checks against COMFY_DIR/input (125 staged character refs),
# COMFY_DIR/models/loras (the @handle LoRA gating) and COMFY_DIR/models/<path>.
# extra_model_paths only tells ComfyUI where to look; it does not help Python
# code that calls os.path.isfile on those paths. A junction makes the paths
# genuinely resolve. (Measured 2026-09-04: D:\ComfyUI25\models held 36
# placeholder files and input held 1, so replacing them loses nothing.)
#
# Reversible: the placeholders are moved to *.orig, not deleted. Refuses to run
# while a render is live. Does not need admin (junctions do not).

$ErrorActionPreference = "Stop"
$D = "D:\ComfyUI25"
$C = "C:\Users\Owner\Desktop\AgentCompanyBackend\tools\ComfyUI"
$flag = "C:\Users\Owner\Desktop\AgentCompanyBackend\data\video_rendering.flag"
if (Test-Path $flag) { Write-Host "render live -- refusing" -ForegroundColor Red; exit 3 }
if (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*ComfyUI25*main.py*' }) {
    Write-Host "D:\ComfyUI25 is running -- stop it first" -ForegroundColor Red; exit 4 }

foreach ($name in @("models", "input")) {
    $dst = Join-Path $D $name; $src = Join-Path $C $name
    if (-not (Test-Path $src)) { throw "source missing: $src" }
    $item = Get-Item $dst -EA SilentlyContinue
    if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Write-Host "${name}: already a junction -> $((Get-Item $dst).Target)"; continue }
    if ($item) {
        $n = (Get-ChildItem $dst -Recurse -File -EA SilentlyContinue | Measure-Object).Count
        if ($n -gt 60) { throw "$dst has $n files -- not the placeholder set, refusing to move it aside" }
        Move-Item $dst "$dst.orig" -Force
        Write-Host "${name}: moved $n placeholder files to $name.orig"
    }
    cmd /c mklink /J "$dst" "$src" | Out-Null
    Write-Host "${name}: junction -> $src"
}
Write-Host "verify:"
"  loras seen : " + (Test-Path (Join-Path $D "models\loras\bia_character.safetensors"))
"  refs seen  : " + (Test-Path (Join-Path $D "input\keth_ref_canon.png"))
"  checkpoints: " + ((Get-ChildItem (Join-Path $D "models\checkpoints") -File -EA SilentlyContinue | Measure-Object).Count) + " files"
