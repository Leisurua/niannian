param([ValidateSet("family", "elder")][string]$Client = "family")
$ErrorActionPreference = "Stop"
$Package = if ($Client -eq "family") { "NianNian-Family" } else { "NianNian-Elder" }
python -m PyInstaller --noconfirm --onefile --windowed `
    --name $Package --paths (Join-Path $PSScriptRoot "src") `
    --specpath (Join-Path $PSScriptRoot "build") `
    --workpath (Join-Path $PSScriptRoot "build/$Client") `
    --distpath (Join-Path $PSScriptRoot "dist") `
    (Join-Path $PSScriptRoot "launcher_$Client.py")
if ($LASTEXITCODE -ne 0) { throw "客户端打包失败" }
