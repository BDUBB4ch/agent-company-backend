# Manually start Bonsai's llama-server (PrismML fork, Vulkan build).
#
# You normally do NOT need this -- the backend starts/stops this server on
# its own (see backend/bonsai_llm.py) whenever an agent on the Bonsai
# backend gets a message, and stops it when an Ollama model or AmuseBridge
# needs the GPU. This script exists for testing Bonsai directly (e.g. with
# curl against the OpenAI-compatible API) without going through the app.
#
# Endpoint once running:  http://127.0.0.1:8811/v1/chat/completions
# Health check:           http://127.0.0.1:8811/health

$root = Split-Path $PSScriptRoot -Parent
$exe = Join-Path $root "tools\llama-prism\vulkan\llama-server.exe"
$model = Join-Path $root "models\bonsai\Ternary-Bonsai-27B-Q2_0.gguf"
$mmproj = Join-Path $root "models\bonsai\Ternary-Bonsai-27B-mmproj-BF16.gguf"

if (-not (Test-Path $exe)) { Write-Error "llama-server.exe not found at $exe"; exit 1 }
if (-not (Test-Path $model)) { Write-Error "Model not found at $model"; exit 1 }

$args = @(
    "-m", $model,
    "--host", "127.0.0.1",
    "--port", "8811",
    "--jinja",           # native OpenAI-style tool_calls via the model's chat template
    "-ngl", "99",        # every layer on the GPU
    "-c", "32768",       # deliberate -- NOT the full 262K; context VRAM is the budget
    "--reasoning-budget", "1024"  # unbounded thinking ate whole replies on big prompts -- see bonsai_llm.py
)
if (Test-Path $mmproj) { $args += @("--mmproj", $mmproj) }  # image input, optional

Write-Host "Starting Bonsai llama-server on http://127.0.0.1:8811 ..."
& $exe @args
