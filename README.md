# Open Thermal Engineering Teaching Suite

A pair of interactive Windows desktop applications for teaching thermodynamic
properties and boiler-furnace operation.

> **Teaching software only.** These applications are intended for conceptual
> exploration and classroom demonstration. They are not suitable for equipment
> design, safety analysis, certification, operator training, or plant operation.

## Included applications

| Application | Topics | Entry point |
| --- | --- | --- |
| P-v-T Demonstrator | Pressure-volume-temperature surfaces, saturation boundaries, isotherms, and working-fluid comparison | `PVT-demonstrator\pvt_native_azel.py` |
| Boiler Furnace Simulator | Combustion, furnace response, heat transfer, and flue-gas behaviour | `boiler_furnace_simulator\boiler_furnace_simulator.py` |

## Windows requirements

- Windows 10 or Windows 11
- Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/)
- A local Windows desktop session capable of opening GUI windows

During Python installation, select **Add python.exe to PATH** and keep the
optional Tcl/Tk component enabled.

## Installation

Open **Command Prompt** (`cmd.exe`), then clone the repository:

```cmd
git clone https://github.com/open-nuclear-suite/Open-Thermal-Engineering-Teaching-Suite.git
cd Open-Thermal-Engineering-Teaching-Suite
```

Run the Windows setup helper:

```cmd
setup_windows.bat
```

This creates a local `.venv` environment and installs all required packages.

## Running the applications

From Command Prompt, or by double-clicking the corresponding file:

```cmd
run_pvt_demonstrator.bat
```

```cmd
run_boiler_furnace_simulator.bat
```

## Repository layout

```text
.
|-- PVT-demonstrator/
|-- boiler_furnace_simulator/
|-- AUTHORS.md
|-- CITATION.cff
|-- LICENSE
|-- README.md
|-- requirements.txt
|-- run_boiler_furnace_simulator.bat
|-- run_pvt_demonstrator.bat
`-- setup_windows.bat
```

## Troubleshooting

- **`'py' is not recognized`**: install Python from python.org and select
  **Add python.exe to PATH**, then reopen Command Prompt.
- **`ModuleNotFoundError`**: rerun `setup_windows.bat`.
- **`No module named tkinter`**: modify or reinstall Python and enable the
  **tcl/tk and IDLE** optional feature.
- **No window appears**: use a local desktop session rather than a headless
  service or notebook.
- **A launcher closes immediately**: run it from Command Prompt so the error
  remains visible.

## Author and contact

**Mohsin Mohd Sies**

- Nuclear Engineering Program
- Faculty of Chemical and Energy Engineering
- Universiti Teknologi Malaysia
- Email: [mohsin.sies@gmail.com](mailto:mohsin.sies@gmail.com)
- GitHub: [open-nuclear-suite](https://github.com/open-nuclear-suite)

For academic collaboration, teaching feedback, or questions about the
applications, please contact the author.

## Citation

If you use this software in teaching, research, or published work, please cite
it using the metadata in [CITATION.cff](CITATION.cff).

## Scientific software and formulation attribution

The P-v-T Demonstrator uses
[CoolProp](https://coolprop.org/) for thermophysical property calculations:

> Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and
> pseudo-pure fluid thermophysical property evaluation and the open-source
> thermophysical property library CoolProp. *Industrial & Engineering Chemistry
> Research, 53*(6), 2498–2508.
> [https://doi.org/10.1021/ie4033999](https://doi.org/10.1021/ie4033999)

The boiler-furnace simulator's water-and-steam property approximations are
informed by the
[IAPWS Industrial Formulation 1997](https://www.iapws.org/relguide/IF97-Rev.pdf)
(IAPWS-IF97), published by the International Association for the Properties of
Water and Steam. The simulator uses simplified educational approximations; it
is not a complete, validated, or standards-conforming implementation of
IAPWS-IF97.

See [scientific attributions](ATTRIBUTIONS.md) for further details.

## License

Copyright (c) 2026 Mohsin Mohd Sies. This project is distributed under the
[MIT License](LICENSE).
