# Screenshot Graveyard: one-command setup and start (Windows PowerShell).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = $null
foreach ($c in @("py -3.12", "py -3.11", "python")) {
    $exe, $arg = $c.Split(" ", 2)
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        $ok = & $exe $arg -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($ok -eq "True") { $py = $c; break }
    }
}
if (-not $py) {
    Write-Host "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/"
    exit 1
}

if (-not (Test-Path .venv)) {
    Write-Host "Creating a virtual environment..."
    $exe, $arg = $py.Split(" ", 2)
    & $exe $arg -m venv .venv
}
$vpy = ".\.venv\Scripts\python.exe"
if (-not (Test-Path .venv\.deps-ok) -or ((Get-Item requirements.txt).LastWriteTime -gt (Get-Item .venv\.deps-ok -ErrorAction SilentlyContinue).LastWriteTime)) {
    Write-Host "Installing requirements (first run takes a few minutes)..."
    & $vpy -m pip install --upgrade pip | Out-Null
    & $vpy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "Installing requirements failed. Check your internet connection and try again."; exit 1 }
    New-Item .venv\.deps-ok -ItemType File -Force | Out-Null
}

if (-not (Get-Command tesseract -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
    Write-Host "Note: Tesseract OCR isn't installed, so text inside screenshots can't be read."
    Write-Host "      Install it with: winget install UB-Mannheim.TesseractOCR"
}

Write-Host "The image model (~600 MB) downloads once, the first time it's needed."
& $vpy -m app
