#!/usr/bin/env bash
# Installs only into an existing, fully configured host-transfer deployment.
set -euo pipefail
umask 077
if [ "$#" -ne 2 ] || [ "$2" != '--apply' ]; then
  echo 'Usage: bash install-host-transfer-prosody.sh PROSODY_CONTAINER --apply' >&2
  exit 2
fi
container=$1
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle"
sha256sum -c SHA256SUMS
# Do not enable a transport without its revocation/authentication dependencies.
docker exec "$container" sh -c '
set -eu
config=/run/prosody/config
test -d "$config"
for name in host_transfer_url host_transfer_complete_url host_transfer_status_url host_transfer_rebind_url host_transfer_claim_url host_role_check_secret host_transfer_participant_domain host_role_check_url; do
  if ! grep -RqE "^[[:space:]]*$name[[:space:]]*=" "$config"; then
    echo "Missing prerequisite configuration: $name; no changes made" >&2
    exit 1
  fi
done
grep -RqE "^[[:space:]]*host_transfer_enabled[[:space:]]*=[[:space:]]*true" "$config" || { echo "Host transfer is not enabled; no changes made" >&2; exit 1; }
grep -Rq "\"muc_host_transfer\"" "$config" || { echo "Module loading is not configured; no changes made" >&2; exit 1; }
'
target=$(docker inspect "$container" --format '{{range .Mounts}}{{if eq .Destination "/prosody-plugins-custom"}}{{.Source}}{{end}}{{end}}')
[ -n "$target" ] && [ -d "$target" ] || { echo 'Persistent custom plugin mount required' >&2; exit 1; }
if [ "${CONFIRM_IDLE:-}" != yes ]; then
  echo 'Confirm conferences are idle, then rerun with CONFIRM_IDLE=yes. No changes made.' >&2
  exit 1
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
backup="$target/host-transfer-backup-$stamp"
mkdir -m 700 -- "$backup"
plugin="$target/mod_muc_host_transfer.lua"
if [ -e "$plugin" ]; then cp -p -- "$plugin" "$backup/mod_muc_host_transfer.lua"; fi
cp -- mod_muc_host_transfer.lua "$plugin"
chmod 644 "$plugin"
echo "Plugin installed. Backup directory: $backup"
docker restart "$container"
echo 'Prosody restart command completed. Check logs and actual transfer/revocation; this is not functional acceptance.'
