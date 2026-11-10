# Host transfer delivery contract — 2026-11-10

## Scope and gates

- Route: plan_first. Repair host transfer for existing GHCR amd64 instance at https://jks.whclaw.top, /opt/cloudmeet-jks on 118; no ARM migration, no full stack rebuild, no unrelated cleanup.
- User authorized continuing implementation, commits, documentation and regression delivery without intermediate confirmations. Preserve databases, secrets, certificates and unrelated services; do not reset any deployment.
- Sources: recover historical Prosody plugin read-only from 202, inspect before importing into jitsi-meet-prosody; deployment copies record source commit and SHA256. 202 must not be changed.
- Assets/boundaries: host/creator keys, JWTs, service secret; untrusted members → authenticated XMPP session → Prosody → authenticated private API. Never authorize from menu visibility, nicknames or client messages alone.
- Required controls: unique business owner excluding core automatic owners; durable pending fence; confirmed credential claim/ack; old credential revocation; strict private TLS; public internal routes remain blocked; administrator recovery remains disabled.
- Done only with source/patch commits, synchronized deployment instructions, automated regression results, backed-up incremental target installation and installed Electron/Android transfer/claim/revocation evidence. Build/unit pass does not imply device acceptance.

## Steps

1. Verify source/runtime state and recover actual historical plugin plus provenance. Review protocol/API compatibility and tests; do not invent a replacement based only on historical claims.
2. Add executable regression tests, improve sanitized client IQ errors, restore supported persistent menu configuration. Run red/green focused tests and full frontend checks.
3. Version Prosody source and deployment copies, private authenticated service channel configuration, preflight/rollback documentation and deployment tests. Test actual Lua version and API suite.
4. Backup target, confirm no active meetings, apply only needed incremental changes with feature disabled first; validate private auth/TLS/public denial and ordinary roles before enabling.
5. Execute installed-client positive/negative/recovery tests on dedicated meetings; retain sanitized evidence, clean only dedicated sessions, commit/push applicable repositories and summarize actual gates.

## Verification / stop conditions

Commands: frontend npm test / npm run build / npm run check:webview-syntax; API Maven tests; Lua executable protocol harness; deployment node/Python tests; actual installed clients and matching target logs.
Stop unsafe rollout if missing source, incompatible runtime, failed authorization/fencing, active meetings or unavailable required credentials. Record blocker, continue independent code/docs/tests. Never bypass verification or clear pending authority to make tests pass.

## Current checkpoint

- deploy baseline 83463eb; frontend/API/Prosody clean at 516a7cb/632c247/937053c.
- Historical 202 root read-only SSH works; plugin found at /root/.jitsi-meet-cfg/prosody/prosody-plugins-custom/mod_muc_host_transfer.lua (705 lines). No 202 changes.
- 118 diagnosis: no transfer module, cancel/service-unavailable, missing custom menu. Implementation and acceptance still pending.
- Source commits pushed: Prosody72b2dc8 (recovered plugin+8 Lua protocol tests), business Web784c1d0 (sanitized IQ errors+7 red/green tests). Web231/231, build and WebView83 emitted syntax pass. API Windows122 tests/0 failures/0 errors/1 skip; Linux targeted Maven attempt first hit PowerShell comma parsing, corrected run timed out while resolving/building; do not count Linux API pass.
- 118 verified backup: /opt/cloudmeet-jks/backups/host-control-20261110T075725Z, SQLite integrity passed, conferences0/participants0 before changes. Prepared independent secret/CA; recreated only api/gateway/prosody. Strict internal TLS missing/wrong secret403, correct secret409 for nonexistent room (authenticated business conflict). Public health remains available.
- First candidate mounted config into /run, Docker-created parent ownership caused startup permission errors. Corrected persistent /config/conf.d mount and uid1000 parent, recreated Prosody; current config check passes, focus and JVB reconnected, operational bridge1. Generator and migration fix retained for regression. No data/cert deletion or DB restore.
- Transfer/reclaim remain FALSE, online role check configured, admin recovery FALSE. Fresh installed Electron test meeting550711616 reached verified moderator. Old dedicated482129364 Android reconnected after restart; force-stop/relaunch only Android test app, no data clear. Need end550711616 before next idle rollout gate.
- NEW critical gap: Android1.0.9 native lib-jitsi-meet path has no host-control credential/ack receiver (not the historical WebView). Need durable encrypted planner integration, authenticated room-only listener, ack after write+readback, completion/token verification, demotion revocation and native transfer action before enabling live transfers. jm has no scoped AGENTS; existing middleware.native.ts and cloudmeet/scheduleStorage.native.ts are integration points. Never enable server and call Android acceptance complete without this.
- Resume: target seven containers running; transfer/reclaim remain false. Android candidate now contains source/namespace/session-bound receipt listener, encrypted readback-before-ack, API completion fence, origin-scoped receipts, duplicate protection, exact-operation revocation, retry/claim and HMAC challenge recovery using native Mac, plus native confirmation dialog transfer (no reliance on middleware order for grantOwner interception). Nine Node tests pass. Need negative challenge tests, outgoing transfer tests, source-origin legacy key review and actual candidate APK/device checks before enablement.
- Native `tsc -p tsconfig.native.json` reports10 global Window typing errors in untouched config/i18n/helpers/gifs; no changed-file diagnostics, but whole-project check FAILS. ESLint cannot load missing tsconfig.web.json. Do not claim these pass. Initial root tsc invocation only printed help (no root config).
- New Android builder launched with explicit https://jks.whclaw.top:443 env in history/client-builds/host-transfer-jks.env; batch2026-11-10T08-15-44-696Z-38504 still building. Source build temporarily changes tracked deployment.json; never commit that temporary build override. Source edits made after build launch (native confirmation dialog) require fresh final build before acceptance.
- Dedicated Electron550711616 all-end requested through product UI on resume; verify server conferences0, do not assume UI request proves cleanup. No new server rollout on resume.
