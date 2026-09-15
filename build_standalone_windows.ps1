param(
    [string]$Version = "2.0.0",
    [string]$BasePython = "py",
    [string]$BasePythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".build-venv\Scripts\python.exe"
$packageName = "Open-Thermal-Engineering-Teaching-Suite-$Version-Windows-x64"
$releaseDir = Join-Path (Join-Path $projectRoot "release") $packageName
$zipPath = Join-Path (Join-Path $projectRoot "release") "$packageName.zip"
$workDir = Join-Path $projectRoot "build"
$specDir = Join-Path $projectRoot "build-specs"

if (-not (Test-Path -LiteralPath $python)) {
    if ($BasePython -eq "py") {
        & py "-$BasePythonVersion" -m venv (Join-Path $projectRoot ".build-venv")
    } else {
        & $BasePython -m venv (Join-Path $projectRoot ".build-venv")
    }
}

$buildPythonVersion = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($buildPythonVersion -ne "3.12") {
    throw "Standalone releases require Python 3.12; found $buildPythonVersion in .build-venv."
}

& $python -m pip install --upgrade pyinstaller
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")

New-Item -ItemType Directory -Force -Path $releaseDir, $workDir, $specDir | Out-Null

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--distpath", $releaseDir,
    "--workpath", $workDir,
    "--specpath", $specDir,
    "--additional-hooks-dir", (Join-Path $projectRoot "build-hooks"),
    "--add-data", "$projectRoot\hiref.logo.png;."
)

& $python -m PyInstaller @commonArgs `
    --name "PVT-Demonstrator" `
    "$projectRoot\PVT-demonstrator\pvt_native_azel.py"

& $python -m PyInstaller @commonArgs `
    --name "Boiler-Furnace-Simulator" `
    "$projectRoot\boiler_furnace_simulator\main.py"

& $python -m PyInstaller @commonArgs `
    --name "Boiler-Furnace-Simulator-Suite-Style" `
    "$projectRoot\boiler_furnace_simulator\suite_main.py"

$boilerExe = Join-Path $releaseDir "Boiler-Furnace-Simulator.exe"
$archiveViewer = Join-Path `
    (Split-Path -Parent $python) "pyi-archive_viewer.exe"
$archiveEntries = & $archiveViewer -l $boilerExe
if (-not ($archiveEntries -match "coolprop\.libs.*\.dll")) {
    throw "CoolProp runtime DLLs are missing from the standalone package."
}

Copy-Item -LiteralPath "$projectRoot\WINDOWS-README.TXT" `
    -Destination (Join-Path $releaseDir "README.TXT") -Force
Copy-Item -LiteralPath "$projectRoot\LICENSE" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\ATTRIBUTIONS.md" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\CITATION.cff" -Destination $releaseDir -Force

Get-FileHash -Algorithm SHA256 `
    (Join-Path $releaseDir "PVT-Demonstrator.exe"), `
    (Join-Path $releaseDir "Boiler-Furnace-Simulator.exe"), `
    (Join-Path $releaseDir "Boiler-Furnace-Simulator-Suite-Style.exe") |
    ForEach-Object { "$($_.Hash)  $(Split-Path -Leaf $_.Path)" } |
    Set-Content -Encoding ascii (Join-Path $releaseDir "SHA256SUMS.txt")

Compress-Archive -LiteralPath $releaseDir -DestinationPath $zipPath `
    -CompressionLevel Optimal -Force

Write-Host "Standalone release created at:"
Write-Host $zipPath
