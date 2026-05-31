$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $repoRoot ".build-venv"
$venvScripts = Join-Path $venvRoot "Scripts"
$activateScript = Join-Path $venvScripts "Activate.ps1"

if (-not (Test-Path $activateScript)) {
    throw "Missing virtual environment activation script at $activateScript"
}

Set-Location $repoRoot
. $activateScript
$env:PYTHONPATH = $repoRoot
python -m src.pdf_spec_app
