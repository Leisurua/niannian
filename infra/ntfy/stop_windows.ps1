$ErrorActionPreference = 'Stop'
$service = Get-Service -Name 'NianNianNtfy' -ErrorAction SilentlyContinue
if ($service) { Stop-Service -Name $service.Name; return }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $projectRoot 'artifacts/ntfy-runtime'
$binary = (Resolve-Path (Join-Path $runtime 'ntfy_2.34.0_windows_amd64/ntfy.exe')).Path
$pidFile = Join-Path $runtime 'private/pid'
if (-not (Test-Path -LiteralPath $pidFile)) { return }
$serverPid = [int](Get-Content -LiteralPath $pidFile)
$server = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if (-not $server) { return }
if ($server.Path -ne $binary) { throw 'Process identity mismatch; refusing to stop another program.' }
Stop-Process -Id $serverPid
