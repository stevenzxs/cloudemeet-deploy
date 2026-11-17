#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$#" -ne 4 ] || [ "$4" != '--apply' ]; then
  echo 'Usage: bash rollback-cert.sh CONTAINER HOST_CADDYFILE BACKUP --apply' >&2; exit 2
fi
container=$1; config=$(realpath -- "$2"); backup=$(realpath -- "$3")
[ -f "$config" ] && [ -f "$backup" ] && [ ! -L "$2" ] && [ ! -L "$3" ]
docker inspect "$container" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]
assert c["Config"]["Cmd"] == ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], "Not a legacy Caddyfile instance; do not restore old certificate tags"
assert any(m["Destination"]=="/etc/caddy/Caddyfile" and m["Source"]==sys.argv[1] for m in c["Mounts"])
' "$config"
stage="/config/cloudmeet-rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
docker cp "$backup" "$container:$stage"
docker exec "$container" caddy validate --config "$stage" --adapter caddyfile
saved="${config}.before-rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
cp -p -- "$config" "$saved"
cat "$backup" > "$config"
if ! docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  cat "$saved" > "$config"
  docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true
  echo "Rollback reload failed; prior file restored. Inspect manually: $saved" >&2; exit 1
fi
echo "Rollback configuration reloaded; pre-rollback backup: $saved"
