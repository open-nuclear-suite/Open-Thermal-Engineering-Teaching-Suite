OPEN THERMAL ENGINEERING TEACHING SUITE
Version 2.0.0 - Folder-Based Windows Release
Released: 9 September 2026

CONTENTS

- PVT-Demonstrator\PVT-Demonstrator.exe
- Boiler-Furnace-Simulator\Boiler-Furnace-Simulator.exe
- LICENSE
- ATTRIBUTIONS.md
- CITATION.cff
- SHA256SUMS.txt

SYSTEM REQUIREMENTS

- 64-bit Windows 10 or Windows 11
- A local Windows desktop session

Python does not need to be installed. The two application folders contain
the required Python runtime and software libraries.

INSTALLATION AND USE

1. Extract the complete ZIP file. Do not run an executable from inside
   the ZIP archive.
2. Keep every application's folder and its _internal subfolder together.
   Do not move an EXE out of its application folder.
3. To run the thermodynamic-property demonstrator, open the
   PVT-Demonstrator folder and double-click PVT-Demonstrator.exe.
4. To run the boiler-furnace simulator, open the
   Boiler-Furnace-Simulator folder and double-click
   Boiler-Furnace-Simulator.exe.

This folder-based edition usually starts faster than the single-file
edition because its bundled runtime does not need to be unpacked on every
launch.

Windows may display a Microsoft Defender SmartScreen warning because the
executables are not digitally signed. Verify the SHA-256 checksums in
SHA256SUMS.txt before running the applications.

IMPORTANT SAFETY NOTICE

This software is intended only for conceptual exploration and classroom
demonstration. It is not suitable for equipment design, safety analysis,
certification, operator training, or plant operation.

The boiler-furnace simulator uses simplified educational approximations.
It is not a complete, validated, or standards-conforming implementation
of IAPWS-IF97.

SOURCE CODE AND SUPPORT

https://github.com/open-nuclear-suite/Open-Thermal-Engineering-Teaching-Suite

Author and maintainer:
maxisnote20

Email: maxisnote20@gmail.com

CITATION AND LICENSE

If you use this software in teaching, research, or published work, please
cite it using the included CITATION.cff metadata.

The software is distributed under the MIT License. See LICENSE for the
full license text and ATTRIBUTIONS.md for scientific-software and
formulation attribution.
