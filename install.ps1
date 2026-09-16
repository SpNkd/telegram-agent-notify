$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
py -3 "$ProjectRoot\scripts\install.py" @args

