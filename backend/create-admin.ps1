param(
  [Parameter(Mandatory = $true)]
  [string]$JsonPath
)

$ErrorActionPreference = 'Stop'
$resolvedJson = (Resolve-Path -LiteralPath $JsonPath).Path
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  $python = 'python'
}

& $python -m app.cli create-admin --json-file $resolvedJson
if ($LASTEXITCODE -ne 0) {
  throw "Admin creation failed with exit code $LASTEXITCODE."
}
