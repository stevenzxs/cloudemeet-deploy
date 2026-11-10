# Optional host transfer deployment

## Versioned sources and boundaries

- Prosody source: stevenzxs/jitsi-meet-prosody commit `72b2dc8`, `jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua`.
- Deployment copy SHA256: `91779945f43d4f7d7ad2cabe32f04503fb62d29ddaf410e74cfc87209b1b201c`.
- Sanitized business Web IQ errors: stevenzxs/jitsi-meet-web commit `784c1d0`.
- API baseline `632c247` already implements durable rotation/claim/ack/recovery. Inject `JITSI_ROLE_CHECK_SECRET`; do not claim Java changes are necessary without evidence.

Default templates do not enable transfer. Ordinary JWT owner mapping is not this feature. Never replace rotation/revocation with an ordinary moderator grant. Administrator recovery remains off.

## Incremental procedure

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

2026-11-10 jks instance: installed Electron1.0.9/Android1.0.11 completed three
product-confirmed transfers and creator reclaim in dedicated room330416681;
each operation returned API authority ACTIVE. Old Electron host key rejected with
business40304/no token; creator Electron refresh retained host. Meeting ended,
idle0/0/operational bridge1 verified. This is not pending-disconnect fault or media
acceptance. Android claim-probe warning fix is a newer candidate, not covered by
that installed1.0.11 result. Sanitized batch evidence remains in
`history/deployments/20261110-jks-118/host-transfer/ACCEPTANCE.md` (local evidence).

## Tests

Deployment: `node --test tests/host-menu.test.cjs` and `python3 -B -m unittest discover -s tests -p 'test_host_control*.py'`.
Prosody source: `lua tests/host-transfer.lua jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua` and `luac -p jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua`.
Business Web: `npm test`, `npm run build`, `npm run check:webview-syntax`. API: `mvn test`; run Linux concurrency tests separately if platform-skipped.

Installed Electron/Android dedicated-meeting acceptance must verify actual menu and confirmation, recipient persistence before ack, exactly one business owner, new key accepted/old key and JWT rejected. Cover member forgery, duplicate request, target departure, lost credential/ack and pending rejoin. Creator reclaim requires independent creator capability; do not fabricate it for old meetings. End only test meetings, verify empty conferences, retain sanitized evidence.

## Rollback

Before first transfer, restore only affected config/plugins/overrides from backup, preserving current data/CA and old image identities; recheck health/roles/signaling. After any transfer or pending operation, **do not disable online revocation or restore old SQLite**: old credentials could regain authority. Keep the fence and secret, recover through supported receipt/reclaim, and take a new consistent snapshot. Never delete authority records or certificates to make tests pass.

Source commits and unit tests do not imply target installation or device acceptance. Record actual gates and skips in batch evidence.
