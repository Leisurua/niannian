#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
base_compose="${script_dir}/docker-compose.yml"
tls_compose="${script_dir}/docker-compose.tls.yml"
env_file="${script_dir}/.env"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

host=""; certificate=""; private_key=""; ca_certificate=""; https_port=443; storage_port=9443
while (( $# )); do
  case "$1" in
    --host) [[ $# -ge 2 ]] || die "--host requires a DNS name or IP address."; host="$2"; shift 2 ;;
    --certificate) [[ $# -ge 2 ]] || die "--certificate requires a PEM file."; certificate="$2"; shift 2 ;;
    --private-key) [[ $# -ge 2 ]] || die "--private-key requires a PEM file."; private_key="$2"; shift 2 ;;
    --ca-certificate) [[ $# -ge 2 ]] || die "--ca-certificate requires a PEM file."; ca_certificate="$2"; shift 2 ;;
    --https-port) [[ $# -ge 2 ]] || die "--https-port requires a port."; https_port="$2"; shift 2 ;;
    --storage-port) [[ $# -ge 2 ]] || die "--storage-port requires a port."; storage_port="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

for command in docker curl openssl; do command -v "${command}" >/dev/null || die "${command} is required."; done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
[[ "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || die "Set --host to the certificate DNS name or IP address."
[[ "${https_port}" =~ ^[0-9]{1,5}$ && "${storage_port}" =~ ^[0-9]{1,5}$ ]] || die "TLS ports must be numeric."
https_port=$((10#${https_port})); storage_port=$((10#${storage_port}))
(( https_port >= 1 && https_port <= 65535 && storage_port >= 1 && storage_port <= 65535 && https_port != storage_port )) \
  || die "TLS ports must be distinct and between 1 and 65535."
for source in "${certificate}" "${private_key}"; do
  [[ "${source}" = /* && -f "${source}" && ! -L "${source}" ]] || die "Certificate and key must be absolute regular files."
done
certificate="$(realpath -- "${certificate}")"; private_key="$(realpath -- "${private_key}")"
host_check=-verify_hostname
[[ "${host}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && host_check=-verify_ip
verify_args=(-purpose sslserver "${host_check}" "${host}" -untrusted "${certificate}")
smoke_args=()
if [[ -n "${ca_certificate}" ]]; then
  [[ "${ca_certificate}" = /* && -f "${ca_certificate}" ]] || die "CA certificate must be an absolute file path."
  ca_certificate="$(realpath -- "${ca_certificate}")"
  verify_args+=(-CAfile "${ca_certificate}")
  smoke_args+=(--ca-certificate "${ca_certificate}")
fi
openssl verify "${verify_args[@]}" "${certificate}" >/dev/null \
  || die "Certificate trust, validity, or name check failed for ${host}."
cert_public="$(openssl x509 -in "${certificate}" -pubkey -noout | openssl pkey -pubin -outform DER | openssl sha256)"
key_public="$(openssl pkey -in "${private_key}" -passin pass: -pubout -outform DER | openssl sha256)"
[[ "${cert_public}" == "${key_public}" ]] || die "Certificate and private key do not match."

if [[ ! -f "${env_file}" ]]; then
  bash "${script_dir}/deploy.sh" --init-only --host "${host}"
fi

export NIANNIAN_HOST="${host}"
export HTTPS_PORT="${https_port}"
export S3_HTTPS_PORT="${storage_port}"
export TLS_CERT_FILE="${certificate}"
export TLS_KEY_FILE="${private_key}"
export API_BIND_ADDRESS=127.0.0.1
export MINIO_BIND_ADDRESS=127.0.0.1
export PUBLIC_BASE_URL="https://${host}:${https_port}"
export S3_PUBLIC_ENDPOINT="https://${host}:${storage_port}"
compose=(docker compose --env-file "${env_file}" -f "${base_compose}" -f "${tls_compose}")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
bash "${script_dir}/smoke-tls.sh" --host "${host}" \
  --https-port "${https_port}" --storage-port "${storage_port}" "${smoke_args[@]}"
