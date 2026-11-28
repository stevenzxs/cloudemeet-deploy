# CloudMeet server release installation inputs

This package carries eight digest-pinned service images and the `jitsi-mgr` UI static archive. It does not install or modify a server automatically.

1. Verify the release files with `sha256sum -c SHA256SUMS`. Set every `IMAGE_*` in `.env` from this batch's `images.json`; keep the digest suffix unchanged. Set the site origin and TLS mode to the values approved for this batch; select the corresponding Caddyfile and set `PUBLIC_URL`, `MEDIA_PORT`, and `MEDIA_HOST`.
2. Generate unique secrets for the variables marked `REPLACE_WITH_RANDOM_SECRET` on the target host, including `JITSI_MGR_DB_PASSWORD` for the PostgreSQL database. Protect `.env` (mode `0600`); do not put secrets in the release or shell history. Generate an RSA key pair for jitsi-mgr in `data/jitsi-mgr/keys/` (`jwt-private.pem` as PKCS#8 PEM and `jwt-public.pem` as X.509 PEM), for example with `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out data/jitsi-mgr/keys/jwt-private.pem` and `openssl pkey -in data/jitsi-mgr/keys/jwt-private.pem -pubout -out data/jitsi-mgr/keys/jwt-public.pem`. Make the directory private and the private key mode `0600`. These files are required at startup and must be backed up securely.
3. Extract `jitsi-mgr-ui.tar.gz` to `artifacts/jitsi-mgr-ui/`. Create persistent `data/` directories and review ports/firewall before startup.
4. Start the application services; Compose starts the digest-pinned PostgreSQL service, persists its data in `jitsi-mgr-postgres-data`, and waits for its health check before starting jitsi-mgr. Caddy creates its internal CA in the persistent `caddy-data` volume:

   ```sh
   mkdir -p data/host-control
   docker compose -f compose.yaml up -d gateway app-web api jitsi-mgr web jicofo jvb
   gateway_id=$(docker compose -f compose.yaml ps -q gateway)
   docker cp "$gateway_id:/data/caddy/pki/authorities/local/root.crt" data/host-control/caddy-root.crt
   chmod 0644 data/host-control/caddy-root.crt
   ```

   Never copy or mount `root.key`, the Caddy storage volume, or any private key into Prosody. The Compose file mounts only `root.crt` read-only; Prosody uses `CLOUDMEET_HOST_CONTROL_CA` with `verify="peer"`, validating the `gateway` service name.
5. Start Prosody only after the file exists: `docker compose -f compose.yaml up -d prosody`. Validate with `docker compose -f compose.yaml config --quiet` before starting services. For public ACME, DNS and inbound TCP 80/443 must reach Caddy. For private CA, provision client trust separately. Keep UDP media port reachable.

Do not use floating image tags. Preserve all data and Caddy volumes; this package does not define upgrade or cleanup behavior.
