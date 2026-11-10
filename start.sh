#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
test -f .env || { echo 'Initialize first: python3 init.py <approved-ip>' >&2; exit 1; }
test -f artifacts/app.jar
test -f artifacts/dist/index.html
mkdir -p data/jitsi/web/nginx-custom data/jitsi/prosody/prosody-plugins-custom data/jitsi/storage/prosody
cp patches/web/custom-interface_config.js patches/web/custom-head.html patches/web/custom.css data/jitsi/web/
cp patches/web/nginx-custom/custom-css.conf data/jitsi/web/nginx-custom/
cp patches/prosody/mod_muc_jwt_owner.lua data/jitsi/prosody/prosody-plugins-custom/
find artifacts/dist data/jitsi/web data/jitsi/prosody/prosody-plugins-custom -type d -exec chmod 755 {} +
find artifacts/dist data/jitsi/web data/jitsi/prosody/prosody-plugins-custom -type f -exec chmod 644 {} +
# Verify against the selected Prosody image when changing the baseline.
chown 1000:1000 data/jitsi/storage/prosody
compose=(docker compose --env-file jitsi.env --env-file .env -f jitsi-base.yaml -f docker-compose.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-build --pull never
"${compose[@]}" ps
