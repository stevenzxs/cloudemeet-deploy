# Host transfer: default product integration and historical maintenance

## Versioned sources and boundaries

- Prosody source: stevenzxs/jitsi-meet-prosody commit `72b2dc8`, `jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua`.
- Deployment copy SHA256: `91779945f43d4f7d7ad2cabe32f04503fb62d29ddaf410e74cfc87209b1b201c`.
- Sanitized business Web IQ errors: stevenzxs/jitsi-meet-web commit `784c1d0`.
- API baseline `632c247` already implements durable rotation/claim/ack/recovery. Inject `JITSI_ROLE_CHECK_SECRET`; do not claim Java changes are necessary without evidence.

As explicitly approved on 2026-11-12, all new normal deployments enable host transfer by default through the formal package and shared offline runtime, not a separate patch overlay. This policy is defined in deploy/AGENTS.md. Ordinary JWT owner mapping is not this feature; never replace rotation/revocation with an ordinary moderator grant. Creator reclaim and administrator recovery remain off. Existing packages and servers are not automatically updated.

The current local implementation is still being completed and verified; this document does not claim an Actions build or target runtime has passed. The normal chain is build-tools/package.sh → offline-runtime/initialize.py → offline-runtime/start.py: deliver public plugins, generate the internal service secret and private TLS material on target, inject the secret into API, expose HTTPS only on the container network, and configure Prosody module loading, strict trust and authenticated endpoints. Missing required materials/configuration must fail, not silently disable transfer. Packaging validates materials only; rotation, revocation, acknowledgement and recovery acceptance remain separate.

## Historical incremental procedure (not the normal new-deployment entry)

Preparation now discovers the container UID/GID and preserves existing XMPP_MUC_MODULES;
root service identities require explicit review. The API secret is generated server-side
in mode0600 host-control/api.env and shared with the Prosody candidate configuration.
The internal gateway listener has no published Compose port, validates the private
certificate chain, and allows only the named internal POST routes. Preparation keeps
transfer/reclaim disabled until backend verification. Staging preserves the existing
Caddyfile inode/public certificate configuration and checks both plugin destinations
before copying. Backup includes source-images.yaml/target configuration when present;
registry.yaml is optional for source-built packages. These are preparation tools,
not an automatically executed deployment or a complete fresh-package integration.

1. Check actual instance origin/project/Compose/digests and idle conferences. Run `python3 tools/backup-host-control.py --root <instance> --project <project>`. It preserves config/plugins/container identities and creates an integrity-checked SQLite backup. Backup is server-only mode0700 and contains secrets.
2. Run `python3 tools/prepare-host-control.py --root <instance> --prosody-container <container>`. Existing output refuses overwrite. It generates strict private TLS, an independent service secret and an initially disabled overlay in `host-control/`. Confirm API port9000 and context `/mapi` against runtime.
3. Install the hash-verified transfer plugin into the actual persistent custom plugin directory. Preserve the matching JWT owner plugin with online role-check support. Append `host-control/compose.json` after existing Compose files.
4. Append generated `gateway-internal.caddy` to existing Caddyfile, retaining public `/mapi/internal` denial and other routes. Listener9443 is Docker-only, never publish its port. Only seven named POST endpoints are allowed.
5. Validate merged Compose (`config --quiet`), Caddy config and Lua syntax. Recreate only API/gateway with `--no-deps`. Strict TLS, missing/wrong secret403, authenticated status and public internal404 must pass before continuing.
6. Recreate Prosody with transfer/reclaim false; verify loaded configuration, ordinary owner/participant roles and operational bridge. Then enable transfer/reclaim while admin recovery stays false. Restart only required services during idle; do not blindly restart healthy Jicofo/JVB.
7. After backend gates pass, append `config.cloudmeetHostTransferEnabled = true;` and `patches/web/host-control-custom-config.js` to persistent Jitsi `custom-config.js`, preserving existing actions. stable11248 filters External API configOverwrite; use supported persistent configuration, not bundle/Redux injection.
8. Publish tested business Web through a recorded persistent artifact override or derived image, preserving original digest and candidate SHA256. Do not silently rebuild seven services or change checked-in `.env`; verify actual page/iframe same-origin.

Tooling: `enable-host-control.py` requires idle conferences/participants and an
existing backup, preserves the bind-source inode and leaves administrator recovery
off. It does not restart services. `stage-host-control-web.py` verifies the input
archive digest, refuses existing candidates and creates `host-control/web-compose.json`;
append that overlay **after** `host-control/compose.json` and the instance's existing
Compose files. Recreate only app-web. Keep both overlays in future operations so
updates do not accidentally discard host-control TLS or the published Web artifact.
`inspect-host-control-state.py` reads only authority state/operation counts, never
credentials or session bindings. Actual Prosody Lua TLS can be checked with
`tests/prosody-host-control-tls.lua` inside the running image (strict CA/hostname).

2026-11-10 jks instance: installed Electron1.0.9/Android1.0.17 closed the
host-control abnormal-recovery acceptance in dedicated room789745736. Product
transfer and native return passed; a persisted pending receipt survived target
process death and recovered through verified recover/HMAC rebind/ack; an active
host re-entered after full process death; product creator reclaim passed. Each
completed operation returned API authority ACTIVE. Sessions dying before receipt
of the private credential correctly could not self-recover and required creator
recovery. Meeting ended with conferences0/participants0/operational bridge1.
This remains host-control evidence, not media or production-security clearance.
Sanitized batch evidence remains in
`history/deployments/20261110-jks-118/host-transfer/ACCEPTANCE.md` (local evidence).

## Tests

Deployment: `node --test tests/host-menu.test.cjs` and `python3 -B -m unittest discover -s tests -p 'test_host_control*.py'`.
Prosody source: `lua tests/host-transfer.lua jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua` and `luac -p jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua`.
Business Web: `npm test`, `npm run build`, `npm run check:webview-syntax`. API: `mvn test`; run Linux concurrency tests separately if platform-skipped.

Installed Electron/Android dedicated-meeting acceptance must verify actual menu and confirmation, recipient persistence before ack, exactly one business owner, new key accepted/old key and JWT rejected. Cover member forgery, duplicate request, target departure, lost credential/ack and pending rejoin. Creator reclaim requires independent creator capability; do not fabricate it for old meetings. End only test meetings, verify empty conferences, retain sanitized evidence.

## Rollback

Before first transfer, restore only affected config/plugins/overrides from backup, preserving current data/CA and old image identities; recheck health/roles/signaling. After any transfer or pending operation, **do not disable online revocation or restore old SQLite**: old credentials could regain authority. Keep the fence and secret, recover through supported receipt/reclaim, and take a new consistent snapshot. Never delete authority records or certificates to make tests pass.

Source commits and unit tests do not imply target installation or device acceptance. Record actual gates and skips in batch evidence.
