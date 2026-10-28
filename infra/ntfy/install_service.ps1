$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $projectRoot 'artifacts/ntfy-runtime'
$binary = (Resolve-Path (Join-Path $runtime 'ntfy_2.34.0_windows_amd64/ntfy.exe')).Path
$private = Join-Path $runtime 'private'
$config = (Resolve-Path (Join-Path $private 'server.yml')).Path
$serviceName = 'NianNianNtfy'
$command = '"' + $binary + '" serve --config "' + $config + '"'
$existing = Get-CimInstance Win32_Service -Filter "Name='NianNianNtfy'"
if ($existing) {
    if ($existing.PathName -ne $command) { throw 'The existing service belongs to another configuration.' }
} else {
    $account = New-Object System.Management.Automation.PSCredential('NT AUTHORITY\LocalService', (New-Object System.Security.SecureString))
    New-Service -Name $serviceName -DisplayName 'NianNian private ntfy' -BinaryPathName $command `
        -StartupType Automatic -Credential $account -Description 'Private HTTPS family notifications; local subnet only.' | Out-Null
}
& sc.exe sidtype $serviceName unrestricted | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not enable the dedicated service SID.' }
$serviceAccount = New-Object System.Security.Principal.NTAccount('NT SERVICE', $serviceName)
$serviceSid = $serviceAccount.Translate([System.Security.Principal.SecurityIdentifier]).Value
& icacls $runtime /grant ('*' + $serviceSid + ':(OI)(CI)RX') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant access to the ntfy binary.' }
& icacls $private /grant ('*' + $serviceSid + ':(OI)(CI)M') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant access to the private ntfy data.' }
Start-Service -Name $serviceName
(Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
