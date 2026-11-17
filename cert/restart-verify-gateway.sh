#!/usr/bin/env bash
# Explicit maintenance action: briefly interrupts gateway traffic.
# Usage: bash restart-verify-gateway.sh CONTAINER HTTPS_URL --apply
set -Eeuo pipefail
umask 077
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ $# -ne 3 || ${3:-} != --apply ]]; then
    printf 'Usage: bash %s CONTAINER HTTPS_URL --apply\n' "$0" >&2
    exit 2
fi
container=$1
url=$2
[[ -n "$container" && "$container" != -* ]] || die 'Invalid container name'
for tool in docker curl python3; do
    command -v "$tool" >/dev/null || die "Missing prerequisite: $tool"
done
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
[[ -f "$bundle/ca.crt" ]] || die 'Missing ca.crt beside script'
python3 - "$url" <<'PY'
import sys
from urllib.parse import urlsplit
u = urlsplit(sys.argv[1])
if (u.scheme != 'https' or not u.hostname or u.username is not None
        or u.password is not None or u.fragment
        or any(c.isspace() or ord(c) < 32 for c in sys.argv[1])):
    raise SystemExit('A valid HTTPS URL without credentials or fragment is required')
try:
    u.port
except ValueError:
    raise SystemExit('Invalid port')
PY
# Limit this helper to the confirmed legacy Caddyfile startup layout.
docker inspect "$container" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]
if c["Config"]["Cmd"] != ["run","--config","/etc/caddy/Caddyfile","--adapter","caddyfile"]:
    raise SystemExit("Unsupported startup configuration; no restart performed")
if not c["State"]["Running"]:
    raise SystemExit("Gateway is not running; no restart performed")
'
printf 'Validating Caddy configuration...\n'
docker exec "$container" caddy validate \
    --config /etc/caddy/Caddyfile --adapter caddyfile
printf 'Restarting only %s; gateway traffic will briefly be interrupted.\n' "$container"
docker restart "$container"

# Retry readiness with full certificate/hostname verification on every request.
# No redirects, proxies or insecure TLS fallback are allowed.
headers=$(mktemp)
errors=$(mktemp)
trap 'rm -f -- "$headers" "$errors"' EXIT
for attempt in {1..10}; do
    printf 'Strict HTTPS verification %s/10: %s\n' "$attempt" "$url"
    if code=$(curl --disable --noproxy '*' --proto '=https' \
        --cacert "$bundle/ca.crt" --head --silent --show-error \
        --connect-timeout 5 --max-time 15 \
        --dump-header "$headers" --output /dev/null \
        --write-out '%{http_code}' "$url" 2>"$errors"); then
        if [[ "$code" == 2?? ]]; then
            cat "$headers"
            printf 'PASS: CA/hostname verification and HTTP %s passed.\n' "$code"
            printf 'This does not verify other IPs, clients or meeting/media functionality.\n'
            exit 0
        fi
        printf 'HTTPS connected, but unexpected HTTP status: %s\n' "$code" >&2
    else
        cat "$errors" >&2
    fi
    if [[ "$attempt" -lt 10 ]]; then sleep 3; fi
done
die 'Verification failed after gateway restart. Preserve data/CA volumes; do not repeat first installation.'
