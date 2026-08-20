<#
.SYNOPSIS
Sets up or starts the Grocery Home app with its project virtual environment.

.EXAMPLE
.\start_grocery_home.ps1 -Setup

.EXAMPLE
.\start_grocery_home.ps1
#>

[CmdletBinding()]
param(
    [switch]$Setup,
    [string]$DataDir,
    [string]$BindAddress = "0.0.0.0",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    Write-Error @"
The Grocery Home virtual environment was not found at:
  $PythonExe

Create it first:
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
"@
}

$CliArgs = @("-m", "grocery_home.cli")
if ($Setup) {
    $CliArgs += "setup"
}
else {
    $CliArgs += @("serve", "--host", $BindAddress, "--port", "$Port")
}

if ($DataDir) {
    $CliArgs += @("--data-dir", $DataDir)
}

Push-Location $ProjectRoot
try {
    & $PythonExe @CliArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
