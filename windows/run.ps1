param([ValidateSet("family", "elder")][string]$Client = "family")
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$Package = if ($Client -eq "family") { "niannian_family_client" } else { "niannian_elder_demo" }
python -m $Package
exit $LASTEXITCODE
