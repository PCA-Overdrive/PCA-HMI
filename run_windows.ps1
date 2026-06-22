$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

$VenvDir = Join-Path $RootDir ".venv-windows"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python was not found. Install Python 3 first."
}

function Test-VenvPython {
    if (-not (Test-Path $VenvPython)) {
        return $false
    }

    try {
        & $VenvPython --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

Write-Host "======================================"
Write-Host "PCA-HMI Windows runner"
Write-Host "======================================"

if (-not (Test-VenvPython)) {
    Write-Host "Creating virtual environment: $VenvDir"
    if (Test-Path $VenvDir) {
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }

    $PythonCommand = @(Get-PythonCommand)
    $PythonExe = $PythonCommand[0]
    $PythonArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $PythonArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }

    & $PythonExe @PythonArgs -m venv $VenvDir
}

Write-Host "Installing requirements..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $RootDir "requirements.txt")

Write-Host ""
Write-Host "Starting Flask server..."
Write-Host "Local: http://localhost:5000"
Write-Host "Press Ctrl+C to stop."
Write-Host "======================================"
Write-Host ""

& $VenvPython (Join-Path $RootDir "app\main.py")
