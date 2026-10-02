$ErrorActionPreference = 'Stop'
$root = 'D:\class_project'
$project = 'niannian-e0-t04-fresh-20261002'
$composeArgs = @('compose', '-p', $project, '-f', "$root\infra\docker-compose.yml", '-f', "$PSScriptRoot\fresh.override.yml")
function Invoke-Compose {
    & docker @composeArgs @args
    if ($LASTEXITCODE -ne 0) { throw 'Disposable infrastructure verification command failed.' }
}
try {
    Invoke-Compose up -d --pull never --wait --wait-timeout 120 postgres minio
    Invoke-Compose run --rm --no-deps --pull never bucket-init
    $version = Invoke-Compose exec -T postgres psql -U nianian -d nianian -Atqc "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    if (-not $version) { throw 'pgvector missing on a fresh volume.' }
    Write-Output "PASS: Fresh PostgreSQL volume enabled pgvector $version."
    $policy = @'
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc stat local/nianian-private >/dev/null
mc anonymous get local/nianian-private
'@
    $result = Invoke-Compose run --rm --no-deps -T --pull never --entrypoint /bin/sh bucket-init -c $policy
    if (($result | Out-String) -notmatch 'private') { throw 'Fresh bucket is not private.' }
    $code = Invoke-Compose exec -T minio curl --silent --output /dev/null --write-out '%{http_code}' 'http://localhost:9000/nianian-private?list-type=2'
    if (($code | Out-String).Trim() -ne '403') { throw 'Fresh anonymous listing was not denied.' }
    Invoke-Compose run --rm --no-deps --pull never bucket-init
    Write-Output 'PASS: Fresh private bucket exists; anonymous listing HTTP 403; repeated initialization exit 0.'
}
finally {
    Invoke-Compose down --volumes --remove-orphans
    Write-Output 'PASS: Only the disposable verification project and volumes were removed.'
}
