# Deploy Speedvibe API to Railway from this folder (no GitHub repo picker required).
# Run in PowerShell AFTER: railway login
#
# Usage:
#   cd ...\speedvibe-info-tech-ai_integration
#   .\scripts\railway-deploy.ps1
#
# First run only: creates/links project — follow prompts, or use:
#   railway init -n "speedvibe-api"

$ErrorActionPreference = "Stop"
# scripts/ -> project root (folder with app.py)
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (-not (Test-Path "app.py")) {
    Write-Host "Expected app.py in $root"
    exit 1
}
Write-Host "Working directory: $(Get-Location)"

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "Install CLI: npm install -g @railway/cli"
    exit 1
}

railway whoami 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run:  railway login"
    Write-Host "Then run this script again."
    exit 1
}

if (-not (Test-Path ".railway")) {
    Write-Host "No .railway link yet. Running: railway init"
    railway init
}

Write-Host "Deploying..."
railway up

Write-Host @"

Next: set secrets (Dashboard -> Variables, or CLI):
  railway variables --set OPENAI_API_KEY=sk-...
  railway variables --set GEMINI_API_KEY=...
  railway variables --set SPEEDVIBE_BASE_URL=https://speedvibeinfotech-hub.com.ng

Optional: CHROMA_PERSIST_DIR=/data/chroma (if you attach a volume).

"@
