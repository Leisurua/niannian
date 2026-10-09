param(
    [ValidateRange(1, 600)]
    [int]$WaitTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$compose = Join-Path $PSScriptRoot 'docker-compose.yml'

docker compose -f $compose build minio bucket-init
if ($LASTEXITCODE -ne 0) { throw 'Pinned MinIO source build failed.' }

docker compose -f $compose up -d --wait --wait-timeout $WaitTimeoutSeconds postgres minio
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL or MinIO did not become healthy.' }

docker compose -f $compose run --rm bucket-init
if ($LASTEXITCODE -ne 0) { throw 'Private bucket initialization failed.' }

$extension = docker compose -f $compose exec -T postgres psql -U nianian -d nianian -Atqc "SELECT extname FROM pg_extension WHERE extname = 'vector'"
if ($LASTEXITCODE -ne 0 -or ($extension | Out-String).Trim() -ne 'vector') {
    throw 'pgvector extension is unavailable.'
}

$response = Invoke-WebRequest -Uri 'http://127.0.0.1:9000/nianian-private?list-type=2' -SkipHttpErrorCheck -TimeoutSec 10
if ($response.StatusCode -ne 403) { throw "Anonymous bucket listing returned $($response.StatusCode), expected 403." }

# Use a unique synthetic object so a 403 proves that an existing object is private.
# Remove only this run's probe, including when the HTTP check fails.
$probeKey = 'e0-t04-smoke/' + [guid]::NewGuid().ToString('N') + '.txt'
try {
    $upload = @'
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
printf 'E0-T04 synthetic infrastructure probe\n' | mc pipe "local/nianian-private/$1" >/dev/null
mc stat "local/nianian-private/$1" >/dev/null
'@
    docker compose -f $compose run --rm --no-deps -T --entrypoint /bin/sh bucket-init -c $upload smoke $probeKey
    if ($LASTEXITCODE -ne 0) { throw 'Private probe upload or authenticated stat failed.' }
    Write-Output 'PASS: Authenticated stat confirms the synthetic probe exists.'

    $objectResponse = Invoke-WebRequest -Uri "http://127.0.0.1:9000/nianian-private/$probeKey" -SkipHttpErrorCheck -TimeoutSec 10
    if ($objectResponse.StatusCode -ne 403) {
        throw "Anonymous object GET returned $($objectResponse.StatusCode), expected 403."
    }
    Write-Output 'PASS: Anonymous bucket listing and existing-object GET both returned HTTP 403.'
}
finally {
    $cleanup = @'
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc rm "local/nianian-private/$1" >/dev/null
'@
    docker compose -f $compose run --rm --no-deps -T --entrypoint /bin/sh bucket-init -c $cleanup smoke $probeKey
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic probe cleanup failed; infrastructure smoke is not PASS.' }
    Write-Output 'PASS: Synthetic probe cleanup completed.'
}

Write-Output 'PASS: PostgreSQL, pgvector, MinIO, private bucket, and anonymous access denial.'
