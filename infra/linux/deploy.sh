#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_file="${script_dir}/docker-compose.yml"
env_file="${script_dir}/.env"
template_file="${script_dir}/.env.example"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
  fi
}

detect_host() {
  local candidate
  candidate="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "${candidate}" ]] || die "Cannot detect a LAN address; rerun with --host <Kali-LAN-IP>."
  printf '%s' "${candidate}"
}

public_host=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || die "--host requires an IPv4 address or DNS name."
      public_host="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: bash infra/linux/deploy.sh [--host <Kali-LAN-IP-or-DNS>]\n'
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "Docker is not installed. See infra/linux/README.md."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

if [[ ! -f "${env_file}" ]]; then
  [[ -n "${public_host}" ]] || public_host="$(detect_host)"
  [[ "${public_host}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || die "Host must be an IPv4 address or DNS name."
  umask 077
  cp "${template_file}" "${env_file}"
  sed -i \
    -e "s/REPLACE_WITH_KALI_LAN_IP/${public_host}/" \
    -e "s/POSTGRES_PASSWORD=GENERATED_BY_DEPLOY_SCRIPT/POSTGRES_PASSWORD=$(random_hex 24)/" \
    -e "s/MINIO_ROOT_USER=GENERATED_BY_DEPLOY_SCRIPT/MINIO_ROOT_USER=niannian$(random_hex 8)/" \
    -e "s/MINIO_ROOT_PASSWORD=GENERATED_BY_DEPLOY_SCRIPT/MINIO_ROOT_PASSWORD=$(random_hex 24)/" \
    -e "s/AUTH_SIGNING_KEY=GENERATED_BY_DEPLOY_SCRIPT/AUTH_SIGNING_KEY=$(random_hex 32)/" \
    "${env_file}"
  chmod 600 "${env_file}"
  printf 'Created private configuration: %s\n' "${env_file}"
elif [[ -n "${public_host}" ]]; then
  die "${env_file} already exists; edit NIANNIAN_HOST there instead of overwriting secrets."
fi

compose=(docker compose --env-file "${env_file}" -f "${compose_file}")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
bash "${script_dir}/smoke.sh"
