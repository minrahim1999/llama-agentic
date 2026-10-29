<# Start llama-server with settings from .env
   Usage: .\scripts\start_server.ps1 [model_path]
#>
$ErrorActionPreference = "Stop"

# Load .env if present
$envFile = Join-Path $PSScriptRoot "..\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } | ForEach-Object {
        $key, $value = $_ -split '=', 2
        if ($key -and $value) {
            [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
        }
    }
}

$MODEL_PATH = $args[0] -or $env:LLAMA_MODEL_PATH
$PORT       = $env:LLAMA_PORT        -or "11435"
$CTX        = $env:LLAMA_CTX_SIZE    -or "8192"
$GPU_LAYERS = $env:LLAMA_N_GPU_LAYERS -or "-1"

if (-not $MODEL_PATH) {
    Write-Host "Error: no model path specified."
    Write-Host "Usage: .\scripts\start_server.ps1 C:\path\to\model.gguf"
    Write-Host "Or set LLAMA_MODEL_PATH in .env"
    exit 1
}

if (-not (Test-Path $MODEL_PATH)) {
    Write-Host "Error: model file not found: $MODEL_PATH"
    exit 1
}

Write-Host "Starting llama-server..."
Write-Host "  Model : $MODEL_PATH"
Write-Host "  Port  : $PORT"
Write-Host "  Ctx   : $CTX"
Write-Host "  GPU   : $GPU_LAYERS layers"
Write-Host ""

& llama-server `
    --model $MODEL_PATH `
    --port $PORT `
    --ctx-size $CTX `
    --n-gpu-layers $GPU_LAYERS `
    --parallel 1 `
    --jinja `
    --log-disable
