$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".build-venv\Scripts\python.exe"
$releaseDir = Join-Path $projectRoot "release\Open-Thermal-Engineering-Teaching-Suite-1.0.0-Windows"
$workDir = Join-Path $projectRoot "build"
$specDir = Join-Path $projectRoot "build-specs"

if (-not (Test-Path -LiteralPath $python)) {
    py -m venv --system-site-packages (Join-Path $projectRoot ".build-venv")
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
    "--add-data", "$projectRoot\utm.fkm.logo.png;.",
    "--add-data", "$projectRoot\hiref.logo.png;."
)

& $python -m PyInstaller @commonArgs `
    --name "PVT-Demonstrator" `
    --collect-all CoolProp `
    "$projectRoot\PVT-demonstrator\pvt_native_azel.py"

& $python -m PyInstaller @commonArgs `
    --name "Boiler-Furnace-Simulator" `
    "$projectRoot\boiler_furnace_simulator\boiler_furnace_simulator.py"

Copy-Item -LiteralPath "$projectRoot\WINDOWS-README.TXT" `
    -Destination (Join-Path $releaseDir "README.TXT") -Force
Copy-Item -LiteralPath "$projectRoot\LICENSE" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\ATTRIBUTIONS.md" -Destination $releaseDir -Force
Copy-Item -LiteralPath "$projectRoot\CITATION.cff" -Destination $releaseDir -Force

Get-FileHash -Algorithm SHA256 `
    (Join-Path $releaseDir "PVT-Demonstrator.exe"), `
    (Join-Path $releaseDir "Boiler-Furnace-Simulator.exe") |
    ForEach-Object { "$($_.Hash)  $(Split-Path -Leaf $_.Path)" } |
    Set-Content -Encoding ascii (Join-Path $releaseDir "SHA256SUMS.txt")

Write-Host "Standalone release created at:"
Write-Host $releaseDir
