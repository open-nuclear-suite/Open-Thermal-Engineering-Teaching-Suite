$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Open Thermal Engineering Teaching Suite"
Write-Host "1. P-v-T Demonstrator"
Write-Host "2. Boiler Furnace Simulator"
Write-Host ""

$selection = Read-Host "Select an application (1 or 2)"

switch ($selection) {
    "1" {
        & (Join-Path $PSScriptRoot "PVT-demonstrator\run_azel.ps1")
    }
    "2" {
        $appDirectory = Join-Path $PSScriptRoot "boiler_furnace_simulator"
        py -m pip install -r (Join-Path $appDirectory "requirements.txt")
        py (Join-Path $appDirectory "boiler_furnace_simulator.py")
    }
    default {
        throw "Invalid selection. Enter 1 or 2."
    }
}
