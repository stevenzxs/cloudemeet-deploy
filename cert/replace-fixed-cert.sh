#!/usr/bin/env bash
# Explicit maintenance of instances already started with fixed-tag native JSON.
set -euo pipefail
umask 077
if [ "$#" -ne 4 ] || [ "$4" != '--apply' ]; then
  echo 'Usage: bash replace-fixed-cert.sh CONTAINER /config/ACTIVE.json ACCESS_IP --apply' >&2; exit 2
fi
container=$1; active=$2; ip=$3
[[ "$active" =~ ^/config/cloudmeet-fixed-tags-[A-Za-z0-9-]+\.json$ ]] || exit 2
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle"
sha256sum -c SHA256SUMS
openssl verify -CAfile ca.crt -purpose sslserver -verify_ip "$ip" server.crt
openssl x509 -in server.crt -checkend 86400 -noout
cert_pub=$(openssl x509 -in server.crt -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
key_pub=$(openssl pkey -in server.key -pubout -outform DER | sha256sum)
[ "$cert_pub" = "$key_pub" ] || { echo 'Certificate/key mismatch' >&2; exit 1; }
docker inspect "$container" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]
assert c["Config"]["Cmd"] == ["run", "--config", sys.argv[1]], "Recreate gateway with fixed JSON command first; no changes made"
assert any(m["Destination"]=="/config" and m.get("RW") for m in c["Mounts"])
' "$active"
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
stage=$(mktemp -d)
trap 'rm -f -- "$stage/current.json" "$stage/candidate.json"; rmdir -- "$stage"' EXIT
docker cp "$container:$active" "$stage/current.json"
directory="/config/cloudmeet-cert/$stamp"
python3 cert-tool.py fixed-json --input "$stage/current.json" --output "$stage/candidate.json" --certificate-directory "$directory"
docker exec "$container" mkdir -p "$directory"
docker cp server.crt "$container:$directory/server.crt"
docker cp server.key "$container:$directory/server.key"
docker exec "$container" chmod 600 "$directory/server.key"
docker cp "$stage/candidate.json" "$container:$directory/candidate.json"
docker exec "$container" caddy validate --config "$directory/candidate.json"
backup="$active.backup-$stamp"
docker exec "$container" cp -p "$active" "$backup"
docker exec "$container" cp "$directory/candidate.json" "$active"
if ! docker exec "$container" caddy reload --config "$active"; then
  docker exec "$container" cp "$backup" "$active"
  docker exec "$container" caddy reload --config "$active" || true
  echo "Reload failed; restored $backup. Inspect manually." >&2; exit 1
fi
echo "External certificate updated; internal paths unchanged. Backup: $backup"
echo 'Verify repeated no-SNI TLS fingerprints, internal TLS and actual client loading; this is not acceptance.'
