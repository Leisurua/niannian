#!/usr/bin/env bash
set -Eeuo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
host=""; certificate=""; https_port=443; storage_port=9443
while (( $# )); do
  case "$1" in
    --host) host="$2"; shift 2 ;;
    --certificate) certificate="$2"; shift 2 ;;
    --https-port) https_port="$2"; shift 2 ;;
    --storage-port) storage_port="$2"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done
[[ -n "${host}" && -f "${certificate}" ]] || die "Host and certificate are required."
curl_args=(--fail --silent --show-error --max-time 10 --cacert "${certificate}")
response="$(curl "${curl_args[@]}" --resolve "${host}:${https_port}:127.0.0.1" \
  "https://${host}:${https_port}/health")"
grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' <<<"${response}" || die "Unexpected HTTPS health response."
websocket_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
  --cacert "${certificate}" --http1.1 --header 'Connection: Upgrade' --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  --resolve "${host}:${https_port}:127.0.0.1" \
  "https://${host}:${https_port}/v1/ws/conversations/00000000-0000-0000-0000-000000000000" || true)"
[[ "${websocket_status}" == "401" || "${websocket_status}" == "403" ]] \
  || die "WSS upgrade path returned ${websocket_status}, expected an authentication rejection."
bucket_status="$(curl --silent --show-error --max-time 10 --cacert "${certificate}" \
  --output /dev/null --write-out '%{http_code}' \
  --resolve "${host}:${storage_port}:127.0.0.1" "https://${host}:${storage_port}/nianian-private?list-type=2" || true)"
[[ "${bucket_status}" == "403" ]] || die "Private HTTPS bucket probe returned ${bucket_status}, expected 403."
printf 'PASS: HTTPS API, WSS reverse-proxy path, TLS MinIO endpoint and private bucket are reachable.\n'
printf 'Android/Windows API: https://%s:%s\n' "${host}" "${https_port}"
printf 'Android WebSocket: wss://%s:%s\n' "${host}" "${https_port}"
printf 'Photo endpoint: https://%s:%s\n' "${host}" "${storage_port}"
