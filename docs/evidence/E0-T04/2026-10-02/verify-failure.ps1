$ErrorActionPreference = 'Stop'
function Invoke-WebRequest {
    param($Uri, [switch]$SkipHttpErrorCheck, $TimeoutSec)
    if ($Uri -like '*?list-type=2') {
        return [pscustomobject]@{ StatusCode = 403 }
    }
    # Inject an unexpected object GET response without changing the real bucket policy.
    return [pscustomobject]@{ StatusCode = 200 }
}
try {
    & 'D:\class_project\infra\smoke.ps1'
    throw 'Smoke incorrectly succeeded after an injected HTTP 200.'
}
catch {
    if ($_.Exception.Message -ne 'Anonymous object GET returned 200, expected 403.') { throw }
    Write-Output 'PASS: Unexpected object GET fails smoke before the final PASS.'
}
$check = @'
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc ls --recursive local/nianian-private/e0-t04-smoke/
'@
$objects = docker compose -f 'D:\class_project\infra\docker-compose.yml' run --rm --no-deps -T --entrypoint /bin/sh bucket-init -c $check
if ($LASTEXITCODE -ne 0 -or ($objects | Out-String).Trim()) { throw 'Smoke probes remain after failure.' }
Write-Output 'PASS: The failure path cleaned its synthetic probe; no smoke objects remain.'
