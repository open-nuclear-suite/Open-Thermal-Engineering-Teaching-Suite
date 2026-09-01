# Boiler Furnace Simulator

Interactive PySide6/PyQtGraph teaching application for exploring
boiler-furnace operation, combustion, heat transfer, and flue-gas behaviour.
The model, launcher, and reusable plotting adapter are separated in the same
style as the Open Nuclear Suite simulators. Live plots are refreshed separately
from the physics step to keep the interface responsive.

Water-and-steam properties are evaluated with CoolProp's IAPWS-IF97 backend.
The surrounding boiler, combustion, heat-transfer, emissions, and control
models remain deliberately simplified for teaching and are not design tools.

The default Student view exposes the essential operating, drum-level, and
alarm inputs. Select Advanced engineering view at the top of the left input
pane to reveal all model assumptions, controller tuning, and instrumentation
controls. Both modes include Diagnostics, combined O2/CO2/excess-air and
CO/NOx/UHC trends, and a live energy-balance tab. The demonstration selector
offers a full guided tour plus focused load-response, combustion/emissions,
and fouling demonstrations. Demonstrations never change the selected tab.

The steam-side inputs include an explicit **Feedwater mass-flow rate (kg/s)**,
which remains visible in Student view. Actual and density-compensated feedwater mass flow remain visible in
the Measurements panel.

The Energy Balance tab contains both a live Sankey flow diagram and the
PyQtGraph comparison chart.

Two interface launchers are supplied:

- `run_boiler_furnace_simulator.bat` — the original light boiler interface.
- `run_boiler_furnace_simulator_suite_style.bat` — the Open Nuclear Suite-style
  dark interface with visible slider controls and direct numeric entry.

## Run

From the repository root in Command Prompt:

```cmd
setup_windows.bat
run_boiler_furnace_simulator.bat
```
