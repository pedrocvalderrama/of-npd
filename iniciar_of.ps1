$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonOf = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonOf)) {
    throw 'Ambiente Python ausente. Siga a instalacao em README_INTERFACE.md.'
}

& $pythonOf -u (Join-Path $PSScriptRoot 'iniciar_of.py')
if ($LASTEXITCODE -ne 0) { throw 'O servidor OF foi encerrado com erro.' }
