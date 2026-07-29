$ErrorActionPreference = "Stop"
py -m pip install -r (Join-Path $PSScriptRoot "requirements_azel.txt")
py (Join-Path $PSScriptRoot "pvt_native_azel.py")
