OPEN THERMAL ENGINEERING TEACHING SUITE
Version 2.0.0 - Source Release
Released: 9 September 2026

======================================================================
OVERVIEW
======================================================================

The Open Thermal Engineering Teaching Suite is a pair of interactive
Windows desktop applications for teaching:

1. Pressure-volume-temperature (P-v-T) properties, saturation
   boundaries, isotherms, and working-fluid comparison.
2. Boiler-furnace combustion, furnace response, heat transfer, and
   flue-gas behaviour.

This download contains the Python source code, Windows setup helper, and
Windows launchers for both applications.

======================================================================
IMPORTANT SAFETY NOTICE
======================================================================

This software is intended only for conceptual exploration and classroom
demonstration. It is not suitable for equipment design, safety analysis,
certification, operator training, or plant operation.

The boiler-furnace simulator uses CoolProp's IAPWS-IF97 steam properties
inside simplified educational boiler, combustion, and control models.

======================================================================
SYSTEM REQUIREMENTS
======================================================================

- Windows 10 or Windows 11
- Python 3.10 or newer from:
  https://www.python.org/downloads/windows/
- A local Windows desktop session

When installing Python, select "Add python.exe to PATH" and keep the
optional Tcl/Tk component enabled.

======================================================================
INSTALLATION
======================================================================

1. Extract the ZIP archive to a folder where you have write permission.
2. Open the extracted folder.
3. Double-click:

       setup_windows.bat

The setup helper creates a local Python virtual environment named .venv
and installs the required packages.

An internet connection is required during the initial setup so that the
Python dependencies can be downloaded.

======================================================================
RUNNING THE APPLICATIONS
======================================================================

To open the P-v-T Demonstrator, double-click:

    run_pvt_demonstrator.bat

To open the Boiler Furnace Simulator, double-click:

    run_boiler_furnace_simulator.bat

If a launcher closes immediately, open Command Prompt in the extracted
folder and run the corresponding .bat file there so the error message
remains visible.

======================================================================
TROUBLESHOOTING
======================================================================

"'py' is not recognized"
    Install Python from python.org, enable "Add python.exe to PATH", and
    then reopen Command Prompt.

"ModuleNotFoundError"
    Run setup_windows.bat again.

"No module named tkinter"
    Modify or reinstall Python and enable the "tcl/tk and IDLE" optional
    feature.

No application window appears
    Run the software in a local Windows desktop session rather than a
    headless service or notebook.

======================================================================
SOURCE CODE, SUPPORT, AND FEEDBACK
======================================================================

Source repository:
https://github.com/open-nuclear-suite/Open-Thermal-Engineering-Teaching-Suite

Author and maintainer:
maxisnote20

Email: maxisnote20@gmail.com

Please use the GitHub repository for source-code access and issue
reporting. Academic collaboration and teaching feedback are welcome.

======================================================================
CITATION AND ATTRIBUTION
======================================================================

If you use this software in teaching, research, or published work, please
cite it using the metadata in CITATION.cff.

The P-v-T Demonstrator uses CoolProp for thermophysical property
calculations. The boiler-furnace simulator's water-and-steam property
approximations are informed by the IAPWS Industrial Formulation 1997.
See ATTRIBUTIONS.md in the distribution for complete attribution details.

======================================================================
LICENSE
======================================================================

Copyright (c) 2026 maxisnote20

This software is distributed under the MIT License. See the included
LICENSE file for the full license text.
