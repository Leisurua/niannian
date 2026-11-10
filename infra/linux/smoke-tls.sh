#!/usr/bin/env bash
set -Eeuo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
host=""; ca_certificate=""; https_port=443; storage_port=9443
while (( $# )); do
  case "$1" in
    --host) [[ $# -ge 2 ]] || die "--host requires a value."; host="$2"; shift 2 ;;
    --ca-certificate|--certificate) [[ $# -ge 2 ]] || die "$1 requires a PEM file."; ca_certificate="$2"; shift 2 ;;
    --https-port) [[ $# -ge 2 ]] || die "--https-port requires a value."; https_port="$2"; shift 2 ;;
    --storage-port) [[ $# -ge 2 ]] || die "--storage-port requires a value."; storage_port="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done
[[ -n "${host}" ]] || die "Host is required."
curl_args=(--silent --show-error --max-time 10 --noproxy '*')
if [[ -n "${ca_certificate}" ]]; then
  [[ -f "${ca_certificate}" ]] || die "CA certificate file does not exist."
  curl_args+=(--cacert "${ca_certificate}")
fi
response="$(curl "${curl_args[@]}" --fail --retry 4 --retry-connrefused --retry-delay 1 --retry-max-time 12 \
  --resolve "${host}:${https_port}:127.0.0.1" \
  "https://${host}:${https_port}/health/ready")"
grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"' <<<"${response}" || die "Unexpected HTTPS readiness response."
websocket_status="$(curl "${curl_args[@]}" --output /dev/null --write-out '%{http_code}' \
  --http1.1 --header 'Connection: Upgrade' --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  --resolve "${host}:${https_port}:127.0.0.1" \
  "https://${host}:${https_port}/v1/ws/conversations/00000000-0000-0000-0000-000000000000" || true)"
[[ "${websocket_status}" == "401" || "${websocket_status}" == "403" ]] \
  || die "WSS upgrade path returned ${websocket_status}, expected an authentication rejection."
bucket_status="$(curl "${curl_args[@]}" \
  --output /dev/null --write-out '%{http_code}' \
  --resolve "${host}:${storage_port}:127.0.0.1" "https://${host}:${storage_port}/nianian-private?list-type=2" || true)"
[[ "${bucket_status}" == "403" ]] || die "Private HTTPS bucket probe returned ${bucket_status}, expected 403."
printf 'PASS: HTTPS API, WSS reverse-proxy path, TLS MinIO endpoint and private bucket are reachable.\n'
printf 'Android/Windows API: https://%s:%s\n' "${host}" "${https_port}"
printf 'Android WebSocket: wss://%s:%s\n' "${host}" "${https_port}"
printf 'Photo endpoint: https://%s:%s\n' "${host}" "${storage_port}"
