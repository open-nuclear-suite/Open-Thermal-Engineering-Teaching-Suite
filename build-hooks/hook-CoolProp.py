"""PyInstaller hook for CoolProp's compiled extensions and delvewheel DLLs."""

from PyInstaller.utils.hooks import collect_all, collect_delvewheel_libs_directory


datas, binaries, hiddenimports = collect_all("CoolProp")
datas, binaries = collect_delvewheel_libs_directory(
    "CoolProp",
    libdir_name="coolprop.libs",
    datas=datas,
    binaries=binaries,
)
