#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$#" -ne 4 ]; then
  echo 'Usage: bash replace-cert.sh CONTAINER HOST_CADDYFILE ACCESS_IP --apply' >&2; exit 2
fi
container=$1; config=$2; ip=$3
[ "$4" = '--apply' ] || exit 2
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
config=$(realpath -- "$config")
[ -f "$config" ] && [ ! -L "$2" ] || { echo 'Regular Caddyfile required'; exit 1; }
cd "$bundle"
sha256sum -c SHA256SUMS
python3 -c 'import ipaddress,sys; assert ipaddress.ip_address(sys.argv[1]).version == 4' "$ip"
openssl verify -CAfile ca.crt -purpose sslserver -verify_ip "$ip" server.crt
openssl x509 -in server.crt -checkend 86400 -noout
cert_pub=$(openssl x509 -in server.crt -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
key_pub=$(openssl pkey -in server.key -pubout -outform DER | sha256sum)
[ "$cert_pub" = "$key_pub" ] || { echo 'Certificate/key mismatch'; exit 1; }
# Reject unknown mounting layouts rather than editing an unrelated instance file.
docker inspect "$container" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]; mounts=c["Mounts"]
assert c["Config"]["Cmd"] == ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], "Not a legacy Caddyfile instance; use reviewed fixed-JSON maintenance"
assert any(m["Destination"]=="/etc/caddy/Caddyfile" and m["Source"]==sys.argv[1] for m in mounts), "Caddyfile mount mismatch"
assert any(m["Destination"]=="/config" and m.get("RW") for m in mounts), "Persistent writable /config mount required"
' "$config"
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
backup="${config}.cert-backup-${stamp}"
directory="/config/cloudmeet-cert/$stamp"
candidate=$(mktemp)
trap 'rm -f -- "$candidate"' EXIT
python3 - "$bundle" "$config" "$directory" "$candidate" <<'PY'
import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('cert_tool',Path(sys.argv[1])/'cert-tool.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
Path(sys.argv[4]).write_text(m.external_tls(Path(sys.argv[2]).read_text(),sys.argv[3]))
PY
docker exec "$container" mkdir -p "$directory"
docker cp server.crt "$container:$directory/server.crt"
docker cp server.key "$container:$directory/server.key"
docker exec "$container" chmod 600 "$directory/server.key"
docker cp "$candidate" "$container:$directory/Caddyfile"
docker exec "$container" caddy validate --config "$directory/Caddyfile" --adapter caddyfile
cp -p -- "$config" "$backup"
# Preserve the bind-mounted inode. Atomic rename would leave the running container
# reading its previous inode until recreation. Restore the same inode on failure.
cat "$candidate" > "$config"
if ! docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  cat "$backup" > "$config"
  docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true
  echo "Reload failed; old file restored. Inspect service manually. Backup: $backup" >&2; exit 1
fi
echo "Certificate configuration reloaded. Backup: $backup"
echo 'This is NOT client/TLS/media acceptance. Distribute ca.crt to clients through a trusted channel.'
