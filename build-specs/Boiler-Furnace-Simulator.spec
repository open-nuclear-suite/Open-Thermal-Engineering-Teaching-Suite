# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Mohsin/Documents/Thermal Engineering/boiler_furnace_simulator/boiler_furnace_simulator.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Mohsin/Documents/Thermal Engineering/hiref.logo.png', '.')],
    hiddenimports=[],
    hookspath=['C:/Users/Mohsin/Documents/Thermal Engineering/build-hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Boiler-Furnace-Simulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
