param([ValidateSet('smoke','full','serve','test','report')][string]$Task = 'smoke')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'README 설치 절차로 .venv를 먼저 만드세요.' }
switch ($Task) {
    'smoke' { & $python -m medspeech.cli smoke }
    'full' { & $python -m medspeech.cli full }
    'test' { & $python -m pytest -q }
    'report' { & $python -m medspeech.cli report }
    'serve' { & $python -m uvicorn medspeech.api:app --host 127.0.0.1 --port 8000 --no-access-log }
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
