# Open Thermal Engineering Teaching Suite

An open collection of interactive desktop applications for teaching thermal
engineering concepts.

## Applications

### P-v-T Demonstrator

An interactive Tkinter and Matplotlib application for exploring pressure,
specific-volume, and temperature relationships for five working fluids.

```powershell
.\PVT-demonstrator\run_azel.ps1
```

### Boiler Furnace Simulator

An interactive PyQt5 furnace simulator with combustion, heat-transfer, and
flue-gas visualizations.

```powershell
py -m pip install -r .\boiler_furnace_simulator\requirements.txt
py .\boiler_furnace_simulator\boiler_furnace_simulator.py
```

## Requirements

- Windows, Linux, or macOS
- Python 3.10 or newer
- Tk support for the P-v-T Demonstrator

Each application keeps its own dependencies and launch instructions in its
subdirectory.

## Quick start

On Windows, run the suite launcher:

```powershell
.\launch_suite.ps1
```

Choose the application from the menu. The launcher installs that application's
Python dependencies before starting it.

