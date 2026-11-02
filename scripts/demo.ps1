#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'

$demoScript = Join-Path $PSScriptRoot 'demo.py'
if (-not (Test-Path -LiteralPath $demoScript -PathType Leaf)) {
    [Console]::Error.WriteLine("DT-RAM demo launcher: expected demo script at $demoScript")
    exit 1
}

$pythonCommand = $null
$pythonArgs = @()
if (-not [string]::IsNullOrWhiteSpace($env:PYTHON)) {
    $pythonCommand = $env:PYTHON
    if (-not (Test-Path -LiteralPath $pythonCommand -PathType Leaf) -and
        -not (Get-Command -Name $pythonCommand -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine("DT-RAM demo launcher: PYTHON points to an unavailable executable: $pythonCommand")
        exit 1
    }
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
    $pythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
} else {
    [Console]::Error.WriteLine('DT-RAM demo requires Python. Install Python 3 and ensure py or python is on PATH, or set PYTHON to its executable path.')
    exit 127
}

& $pythonCommand @pythonArgs $demoScript @args
exit $LASTEXITCODE
