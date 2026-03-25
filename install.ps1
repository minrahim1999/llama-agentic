# install.ps1 — Windows PowerShell bootstrap for llama-agentic
# Run in PowerShell as: .\install.ps1
# Or with auto mode:    .\install.ps1 --auto
# Or: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
param([switch]$Auto, [string]$Model = "qwen2.5-coder-3b")

Write-Host ""
Write-Host "============================================================"
Write-Host "  llama-agentic — Windows installer"
Write-Host "============================================================"
Write-Host ""

# ── Check Python ─────────────────────────────────────────────────────────────
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 11) {
                $pythonCmd = $cmd
                Write-Host "  [OK]  Found $ver"
                break
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "  [!!]  Python 3.11+ not found. Attempting install via winget..."
    try {
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        $pythonCmd = "python"
        Write-Host "  [OK]  Python installed. You may need to restart your terminal."
    } catch {
        Write-Host "  [XX]  Could not auto-install Python."
        Write-Host "        Download from: https://www.python.org/downloads/"
        exit 1
    }
}

# ── Check Git ─────────────────────────────────────────────────────────────────
try {
    git --version | Out-Null
    Write-Host "  [OK]  Git found"
} catch {
    Write-Host "  [!!]  Git not found. Installing via winget..."
    try {
        winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
        Write-Host "  [OK]  Git installed. Restart your terminal and re-run this script."
        exit 0
    } catch {
        Write-Host "  [XX]  Could not auto-install Git."
        Write-Host "        Download from: https://git-scm.com/download/win"
        exit 1
    }
}

# ── Check llama-server ────────────────────────────────────────────────────────
$llamaFound = $false
$searchPaths = @(
    "C:\Program Files\llama.cpp\llama-server.exe",
    "C:\llama.cpp\llama-server.exe",
    "$env:LOCALAPPDATA\Programs\llama.cpp\llama-server.exe"
)

$llamaBin = Get-Command llama-server -ErrorAction SilentlyContinue
if ($llamaBin) {
    Write-Host "  [OK]  llama-server found: $($llamaBin.Source)"
    $llamaFound = $true
} else {
    foreach ($p in $searchPaths) {
        if (Test-Path $p) {
            Write-Host "  [OK]  llama-server found: $p"
            $llamaFound = $true
            break
        }
    }
}

if (-not $llamaFound) {
    Write-Host "  [!!]  llama-server not found. Attempting install via winget..."
    try {
        winget install -e --id ggerganov.llama.cpp --accept-source-agreements --accept-package-agreements
        Write-Host "  [OK]  llama.cpp installed."
        $llamaFound = $true
    } catch {
        Write-Host "  [!!]  Could not auto-install llama.cpp."
        Write-Host "        Download prebuilt binary from:"
        Write-Host "        https://github.com/ggerganov/llama.cpp/releases"
        Write-Host "        Then add the folder containing llama-server.exe to your PATH."
    }
}

# ── Disk space check ──────────────────────────────────────────────────────────
$disk = Get-PSDrive C | Select-Object -ExpandProperty Free
$freeGB = [math]::Round($disk / 1GB, 1)
if ($freeGB -lt 5) {
    Write-Host "  [!!]  Low disk space: $freeGB GB free. Models need 3-8 GB."
    $ans = Read-Host "  Continue anyway? [y/N]"
    if ($ans -notmatch "^[yY]") { exit 1 }
} else {
    Write-Host "  [OK]  Free disk space: $freeGB GB"
}

# ── Install Python package ────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Installing llama-agentic Python package..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Try uv first
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "  Using: uv tool install"
    uv tool install --editable $scriptDir
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "  Using: pipx install"
    pipx install --editable $scriptDir
} else {
    Write-Host "  Using: pip install (user)"
    & $pythonCmd -m pip install --user --editable $scriptDir
    Write-Host ""
    Write-Host "  NOTE: Ensure %APPDATA%\Python\Scripts is in your PATH."
    Write-Host "  Add it in: System Properties > Environment Variables"
}

# ── --Auto: write global config + download model ──────────────────────────────
if ($Auto) {
    Write-Host ""
    $autoArgs = @("install.py", "--auto", "--model", $Model)
    & $pythonCmd @autoArgs
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host "  NEXT STEPS"
Write-Host "------------------------------------------------------------"
if (-not $llamaFound) {
    Write-Host "  * Install llama.cpp from https://github.com/ggerganov/llama.cpp/releases"
    Write-Host ""
}
Write-Host "  1. Run the agent (first run starts setup wizard):"
Write-Host "       llama-agent"
Write-Host ""
Write-Host "  2. Download a model:"
Write-Host "       llama-agent download qwen2.5-coder-7b"
Write-Host ""
Write-Host "  3. Enable auto-start on boot:"
Write-Host "       llama-agent autostart enable"
Write-Host ""
Write-Host "  4. Check environment:"
Write-Host "       llama-agent doctor"
Write-Host ""
Write-Host "============================================================"
Write-Host "  Install complete!"
Write-Host "============================================================"
Write-Host ""
