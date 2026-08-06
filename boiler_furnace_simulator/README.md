# Boiler Furnace Simulator

Interactive PyQt5 teaching application for exploring boiler-furnace operation,
combustion, heat transfer, and flue-gas behaviour.

Water-and-steam properties are evaluated with CoolProp's IAPWS-IF97 backend.
The surrounding boiler, combustion, heat-transfer, emissions, and control
models remain deliberately simplified for teaching and are not design tools.

The default Student view exposes the essential operating, drum-level, and
alarm inputs. Select Advanced engineering view at the top of the left input
pane to reveal all model assumptions, controller tuning, and instrumentation
controls. Both modes include Diagnostics, combined O2/CO2/excess-air and
CO/NOx/UHC trends, and a live energy-balance Sankey tab.

## Run

From the repository root in Command Prompt:

```cmd
setup_windows.bat
run_boiler_furnace_simulator.bat
```
