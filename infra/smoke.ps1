$ErrorActionPreference = 'Stop'
$compose = Join-Path $PSScriptRoot 'docker-compose.yml'

docker compose -f $compose build minio bucket-init
if ($LASTEXITCODE -ne 0) { throw 'Pinned MinIO source build failed.' }

docker compose -f $compose up -d --wait postgres minio
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL or MinIO did not become healthy.' }

docker compose -f $compose run --rm bucket-init
if ($LASTEXITCODE -ne 0) { throw 'Private bucket initialization failed.' }

$extension = docker compose -f $compose exec -T postgres psql -U nianian -d nianian -Atqc "SELECT extname FROM pg_extension WHERE extname = 'vector'"
if ($LASTEXITCODE -ne 0 -or ($extension | Out-String).Trim() -ne 'vector') {
    throw 'pgvector extension is unavailable.'
}

$response = Invoke-WebRequest -Uri 'http://127.0.0.1:9000/nianian-private?list-type=2' -SkipHttpErrorCheck
if ($response.StatusCode -ne 403) { throw "Anonymous bucket listing returned $($response.StatusCode), expected 403." }

Write-Output 'PASS: PostgreSQL, pgvector, MinIO, bucket initialization, and anonymous access denial.'
