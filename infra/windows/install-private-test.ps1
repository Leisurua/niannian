param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [string]$OfflineDependencies
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = 'C:\ProgramData\NiannianTest'
$taskName = 'NiannianEcsPrivateTest'
$Bundle = (Resolve-Path -LiteralPath $Bundle).Path
if ($OfflineDependencies) {
    $OfflineDependencies = (Resolve-Path -LiteralPath $OfflineDependencies).Path
}
if (!(Test-Path -LiteralPath "$env:windir\System32\msvcp140.dll")) {
    throw 'Install the Microsoft Visual C++ v14 Redistributable (x64) first.'
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'The Niannian test task already exists. Inspect its status before reinstalling.'
}
New-Item -ItemType Directory -Path $root -Force | Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)(F)' '*S-1-5-32-544:(OI)(CI)(F)' '*S-1-5-19:(OI)(CI)(M)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Unable to secure the private deployment directory' }
Expand-Archive -LiteralPath $Bundle -DestinationPath $root -Force
Expand-Archive -LiteralPath "$root\runtime\python.zip" -DestinationPath "$root\runtime\python" -Force
& tar.exe -xzf "$root\source.tar.gz" -C $root
if ($LASTEXITCODE -ne 0) { throw 'Unable to extract NianNian source' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'start-private-test.py') -Destination $root -Force
$python = "$root\runtime\python\tools\python.exe"
if ($OfflineDependencies) {
    & $python -m zipfile -e $OfflineDependencies "$root\runtime\site"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to extract offline backend dependencies' }
} else {
    & $python -m ensurepip
    if ($LASTEXITCODE -ne 0) { throw 'Unable to bootstrap pip' }
    & $python -m pip install --disable-pip-version-check --no-cache-dir --only-binary ':all:' --target "$root\runtime\site" -r "$root\niannian\backend\requirements.lock"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install backend dependencies' }
}
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}\start-private-test.py"' -f $root) -WorkingDirectory $root
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output 'The Niannian private test task has started'
