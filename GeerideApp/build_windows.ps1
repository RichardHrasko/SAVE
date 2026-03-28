$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = "C:\Users\risko\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$deployScript = Join-Path $projectRoot ".venv\Lib\site-packages\PySide6\scripts\deploy.py"
$specFile = Join-Path $projectRoot "pysidedeploy.spec"
$sitePackages = Join-Path $projectRoot ".venv\Lib\site-packages"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $deployScript)) {
    throw "Deploy script not found: $deployScript"
}

if (-not (Test-Path $specFile)) {
    throw "Deploy spec not found: $specFile"
}

$env:PYTHONPATH = $sitePackages

& $pythonExe $deployScript -c $specFile -f -v
