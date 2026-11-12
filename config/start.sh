#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo 'Initialize first: python3 config/init.py' >&2; exit 1; }
# Export only validated public target values; .env must contain secrets only.
target_exports=$(python3 -B config/target.py config/target.env)
eval "$target_exports"
python3 -B - <<'PY'
from config.target import read_env
values = read_env('.env')
if set(values) != {'JWT_APP_SECRET', 'JICOFO_AUTH_PASSWORD', 'JVB_AUTH_PASSWORD'} or not all(values.values()):
    raise ValueError('.env must contain three non-empty secrets only; existing file was not changed')
PY
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
compose=(docker compose --project-directory "$PWD" --env-file config/jitsi.env --env-file .env -f config/jitsi-base.yaml -f config/docker-compose.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-build --pull never
"${compose[@]}" ps
