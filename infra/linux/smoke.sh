#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_file="${script_dir}/docker-compose.yml"
env_file="${script_dir}/.env"

[[ -f "${env_file}" ]] || { printf 'ERROR: run deploy.sh first.\n' >&2; exit 1; }
compose=(docker compose --env-file "${env_file}" -f "${compose_file}")

value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${env_file}" | tail -n 1
}

api_port="$(value API_PORT)"
minio_port="$(value MINIO_PORT)"
public_host="$(value NIANNIAN_HOST)"
[[ "${api_port}" =~ ^[0-9]+$ && "${minio_port}" =~ ^[0-9]+$ ]] || {
  printf 'ERROR: API_PORT and MINIO_PORT must be numeric.\n' >&2
  exit 1
}

deadline=$((SECONDS + 300))
until response="$(curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:${api_port}/health" 2>/dev/null)"; do
  if (( SECONDS >= deadline )); then
    printf 'ERROR: API did not become healthy within 300 seconds.\n' >&2
    "${compose[@]}" ps >&2
    "${compose[@]}" logs --tail 80 migrate api worker >&2
    exit 1
  fi
  sleep 2
done

grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' <<<"${response}" || {
  printf 'ERROR: unexpected /health response.\n' >&2
  exit 1
}

migrate_id="$("${compose[@]}" ps -a -q migrate)"
[[ -n "${migrate_id}" ]] || { printf 'ERROR: migration container is missing.\n' >&2; exit 1; }
[[ "$(docker inspect --format '{{.State.ExitCode}}' "${migrate_id}")" == "0" ]] || {
  printf 'ERROR: database migration failed.\n' >&2
  "${compose[@]}" logs migrate >&2
  exit 1
}

for service in api worker postgres minio; do
  [[ -n "$("${compose[@]}" ps --status running -q "${service}")" ]] || {
    printf 'ERROR: %s is not running.\n' "${service}" >&2
    exit 1
  }
done

"${compose[@]}" exec -T api python -m alembic current | grep -q '(head)' || {
  printf 'ERROR: database is not at the Alembic head revision.\n' >&2
  exit 1
}

bucket_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
  "http://127.0.0.1:${minio_port}/nianian-private?list-type=2")"
[[ "${bucket_status}" == "403" ]] || {
  printf 'ERROR: private bucket probe returned HTTP %s, expected 403.\n' "${bucket_status}" >&2
  exit 1
}

printf 'PASS: API health, migration head, worker, PostgreSQL, MinIO and private bucket.\n'
printf 'Android API URL: http://%s:%s\n' "${public_host}" "${api_port}"
printf 'Android WebSocket base: ws://%s:%s\n' "${public_host}" "${api_port}"
printf 'MinIO upload endpoint: http://%s:%s\n' "${public_host}" "${minio_port}"
