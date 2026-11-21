#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
base_compose="${script_dir}/docker-compose.yml"
tls_compose="${script_dir}/docker-compose.tls.yml"
env_file="${script_dir}/.env"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

host=""; certificate=""; private_key=""; ca_certificate=""; https_port=443; storage_port=9443
certbot_name=""; renew_certificate=false
while (( $# )); do
  case "$1" in
    --host) [[ $# -ge 2 ]] || die "--host requires a DNS name or IP address."; host="$2"; shift 2 ;;
    --certificate) [[ $# -ge 2 ]] || die "--certificate requires a PEM file."; certificate="$2"; shift 2 ;;
    --private-key) [[ $# -ge 2 ]] || die "--private-key requires a PEM file."; private_key="$2"; shift 2 ;;
    --ca-certificate) [[ $# -ge 2 && -n "$2" ]] || die "--ca-certificate requires a PEM file."; ca_certificate="$2"; shift 2 ;;
    --certbot-name) [[ $# -ge 2 ]] || die "--certbot-name requires a certificate name."; certbot_name="$2"; shift 2 ;;
    --renew-certificate) renew_certificate=true; shift ;;
    --https-port) [[ $# -ge 2 ]] || die "--https-port requires a port."; https_port="$2"; shift 2 ;;
    --storage-port) [[ $# -ge 2 ]] || die "--storage-port requires a port."; storage_port="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

for command in docker curl openssl; do command -v "${command}" >/dev/null || die "${command} is required."; done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
[[ "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || die "Set --host to the certificate DNS name or IP address."
[[ "${https_port}" =~ ^[0-9]{1,5}$ && "${storage_port}" =~ ^[0-9]{1,5}$ ]] || die "TLS ports must have one to five decimal digits."
https_port=$((10#${https_port})); storage_port=$((10#${storage_port}))
(( https_port >= 1 && https_port <= 65535 && storage_port >= 1 && storage_port <= 65535 && https_port != storage_port )) \
  || die "TLS ports must be distinct and between 1 and 65535."
if [[ -n "${certbot_name}" ]]; then
  [[ "${certbot_name}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && -z "${certificate}" && -z "${private_key}" ]] \
    || die "Use --certbot-name on its own to select a Certbot certificate and key."
  live="/etc/letsencrypt/live/${certbot_name}"
  archive="/etc/letsencrypt/archive/${certbot_name}"
  certificate="$(realpath -e "${live}/fullchain.pem")" || die "Certbot fullchain is unavailable."
  private_key="$(realpath -e "${live}/privkey.pem")" || die "Certbot private key is unavailable."
  [[ "${certificate}" == "${archive}"/fullchain*.pem && "${private_key}" == "${archive}"/privkey*.pem ]] \
    || die "Certbot certificate and key must resolve to the selected archive."
fi
for source in "${certificate}" "${private_key}"; do
  [[ "${source}" = /* && -f "${source}" && ! -L "${source}" ]] || die "Certificate and key must be absolute regular files."
done
certificate="$(realpath "${certificate}")"; private_key="$(realpath "${private_key}")"
host_check=-verify_hostname
[[ "${host}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && host_check=-verify_ip
verify_server() {
  openssl verify -purpose sslserver "${host_check}" "${host}" -untrusted "${certificate}" "$@" "${certificate}" >/dev/null
}
if [[ -n "${ca_certificate}" ]]; then
  [[ "${ca_certificate}" = /* && -r "${ca_certificate}" && -f "${ca_certificate}" ]] \
    || die "CA certificate must be a readable absolute PEM file."
  verify_server -CAfile "${ca_certificate}" \
    || die "Certificate must be valid for ${host} and chain to the supplied CA."
elif ! verify_server 2>/dev/null; then
  verify_server -CAfile "${certificate}" -check_ss_sig \
    || die "Certificate must be valid for ${host} and trusted; supply --ca-certificate for a private CA."
  ca_certificate="${certificate}"
fi
cert_public="$(openssl x509 -in "${certificate}" -pubkey -noout | openssl pkey -pubin -outform DER | openssl sha256)"
key_public="$(openssl pkey -in "${private_key}" -pubout -outform DER | openssl sha256)"
[[ "${cert_public}" == "${key_public}" ]] || die "Certificate and private key do not match."

if [[ ! -f "${env_file}" ]]; then
  [[ "${renew_certificate}" == false ]] || die "Run the initial TLS deployment before renewing the gateway certificate."
  bash "${script_dir}/deploy.sh" --host "${host}" --init-only
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
if [[ "${renew_certificate}" == true ]]; then
  "${compose[@]}" up -d --no-deps --force-recreate gateway
else
  "${compose[@]}" up -d --build
fi
probe_trust=()
if [[ -n "${ca_certificate}" ]]; then probe_trust=(--ca-certificate "${ca_certificate}"); fi
bash "${script_dir}/smoke-tls.sh" --host "${host}" \
  --https-port "${https_port}" --storage-port "${storage_port}" "${probe_trust[@]}"
