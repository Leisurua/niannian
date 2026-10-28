param(
    [Parameter(Mandatory = $true)][string]$ServerIp,
    [ValidateRange(1024, 65535)][int]$Port = 8443
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$binary = (Resolve-Path (Join-Path $projectRoot 'artifacts/ntfy-runtime/ntfy_2.34.0_windows_amd64/ntfy.exe')).Path
if ((Get-NetIPAddress -AddressFamily IPv4).IPAddress -notcontains $ServerIp) {
    throw 'ServerIp must be an IPv4 address assigned to this computer.'
}
$ruleName = 'NianNian-ntfy-private-lan'
$rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($rule) {
    $application = $rule | Get-NetFirewallApplicationFilter
    if ($application.Program -ne $binary) { throw 'The existing rule belongs to another program.' }
    $rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -LocalAddress $ServerIp -RemoteAddress LocalSubnet
    $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $Port
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'NianNian private ntfy LAN HTTPS' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -LocalAddress $ServerIp `
        -RemoteAddress LocalSubnet -Program $binary -Profile Any | Out-Null
}
