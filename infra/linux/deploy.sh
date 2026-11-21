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

random_fernet() {
  command -v openssl >/dev/null 2>&1 || die "openssl is required to generate CONTACT_ENCRYPTION_KEY."
  openssl rand 32 | openssl base64 -A | tr '+/' '-_'
}

detect_host() {
  local candidate
  candidate="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "${candidate}" ]] || die "Cannot detect a LAN address; rerun with --host <Kali-LAN-IP>."
  printf '%s' "${candidate}"
}

public_host=""; init_only=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || die "--host requires an IPv4 address or DNS name."
      public_host="$2"
      shift 2
      ;;
    --init-only) init_only=true; shift ;;
    -h|--help)
      printf 'Usage: bash infra/linux/deploy.sh [--host <Kali-LAN-IP-or-DNS>] [--init-only]\n'
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [[ "${init_only}" == false ]]; then
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. See docs/deployment.md."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
fi

if [[ ! -f "${env_file}" ]]; then
  [[ -n "${public_host}" ]] || public_host="$(detect_host)"
  [[ "${public_host}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || die "Host must be an IPv4 address or DNS name."
  umask 077
  [[ -f "${template_file}" ]] || die "Missing .env.example"
  postgres_password="$(random_hex 24)"
  minio_suffix="$(random_hex 8)"
  minio_password="$(random_hex 24)"
  signing_key="$(random_hex 32)"
  contact_key="$(random_fernet)"
  staged_env="$(mktemp "${env_file}.XXXXXX")"
  trap 'rm -f "${staged_env}"' EXIT
  sed \
    -e "s/REPLACE_WITH_KALI_LAN_IP/${public_host}/" \
    -e "s/POSTGRES_PASSWORD=GENERATED_BY_DEPLOY_SCRIPT/POSTGRES_PASSWORD=${postgres_password}/" \
    -e "s/MINIO_ROOT_USER=GENERATED_BY_DEPLOY_SCRIPT/MINIO_ROOT_USER=niannian${minio_suffix}/" \
    -e "s/MINIO_ROOT_PASSWORD=GENERATED_BY_DEPLOY_SCRIPT/MINIO_ROOT_PASSWORD=${minio_password}/" \
    -e "s/AUTH_SIGNING_KEY=GENERATED_BY_DEPLOY_SCRIPT/AUTH_SIGNING_KEY=${signing_key}/" \
    -e "s|CONTACT_ENCRYPTION_KEY=GENERATED_BY_DEPLOY_SCRIPT|CONTACT_ENCRYPTION_KEY=${contact_key}|" \
    "${template_file}" > "${staged_env}"
  chmod 600 "${staged_env}"
  ln -T "${staged_env}" "${env_file}" || die "Could not publish ${env_file} without overwriting an existing file."
  printf 'Created private configuration: %s\n' "${env_file}"
elif [[ -n "${public_host}" ]]; then
  die "${env_file} already exists; edit NIANNIAN_HOST there instead of overwriting secrets."
fi
[[ "${init_only}" == true ]] && exit 0

compose=(docker compose --env-file "${env_file}" -f "${compose_file}")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
bash "${script_dir}/smoke.sh"
