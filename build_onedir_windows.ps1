param([string]$Version = "2.0.0")

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".build-venv\Scripts\python.exe"
$packageName = "Open-Thermal-Engineering-Teaching-Suite-$Version-Windows-x64-onedir"
$releaseRoot = Join-Path $projectRoot "release"
$releaseDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"
$workDir = Join-Path $projectRoot "build-onedir"
$specDir = Join-Path $projectRoot "build-specs-onedir"

if (-not (Test-Path -LiteralPath $python)) {
    py -m venv (Join-Path $projectRoot ".build-venv")
}

& $python -m pip install --upgrade pyinstaller
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")

New-Item -ItemType Directory -Force -Path `
    $releaseDir, $workDir, $specDir | Out-Null

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
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

$coolPropLibDir = Join-Path $releaseDir `
    "Boiler-Furnace-Simulator\_internal\coolprop.libs"
$coolPropRuntime = Get-ChildItem -LiteralPath $coolPropLibDir `
    -Filter "*.dll" -File -ErrorAction SilentlyContinue
if (-not $coolPropRuntime) {
    throw "CoolProp runtime DLLs are missing from the onedir package."
}

Copy-Item -LiteralPath "$projectRoot\ONEDIR-README.TXT" `
    -Destination (Join-Path $releaseDir "README.TXT") -Force
Copy-Item -LiteralPath "$projectRoot\LICENSE" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\ATTRIBUTIONS.md" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\CITATION.cff" -Destination $releaseDir -Force

$executables = @(
    (Join-Path $releaseDir "PVT-Demonstrator\PVT-Demonstrator.exe"),
    (Join-Path $releaseDir "Boiler-Furnace-Simulator\Boiler-Furnace-Simulator.exe"),
    (Join-Path $releaseDir "Boiler-Furnace-Simulator-Suite-Style\Boiler-Furnace-Simulator-Suite-Style.exe")
)

Get-FileHash -Algorithm SHA256 $executables |
    ForEach-Object {
        $relativePath = $_.Path.Substring($releaseDir.Length + 1)
        "$($_.Hash)  $relativePath"
    } |
    Set-Content -Encoding ascii (Join-Path $releaseDir "SHA256SUMS.txt")

Compress-Archive -LiteralPath $releaseDir -DestinationPath $zipPath `
    -CompressionLevel Optimal -Force

Write-Host "Folder-based release created at:"
Write-Host $zipPath
