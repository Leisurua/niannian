$ErrorActionPreference = 'Stop'
$service = Get-Service -Name 'NianNianNtfy' -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne 'Running') { Start-Service -Name $service.Name }
    return
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $projectRoot 'artifacts/ntfy-runtime'
$binary = Join-Path $runtime 'ntfy_2.34.0_windows_amd64/ntfy.exe'
$private = Join-Path $runtime 'private'
$config = Join-Path $private 'server.yml'
if (-not (Test-Path -LiteralPath $binary) -or -not (Test-Path -LiteralPath $config)) {
    throw 'Run infra/ntfy/setup_windows.py first.'
}
$existing = Get-CimInstance Win32_Process -Filter "Name='ntfy.exe'" |
    Where-Object { $_.ExecutablePath -eq $binary -and $_.CommandLine.Contains($config) }
if ($existing) { return }
$process = Start-Process -FilePath $binary -ArgumentList @('serve', '--config', ('"' + $config + '"')) `
    -WorkingDirectory $runtime -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $private 'stdout.log') -RedirectStandardError (Join-Path $private 'stderr.log')
Set-Content -LiteralPath (Join-Path $private 'pid') -Value $process.Id
