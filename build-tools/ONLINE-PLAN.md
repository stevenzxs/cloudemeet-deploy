# CloudMeet online delivery implementation — 2026-11-17

## Approved scope

Client CI checkpoint: added build-clients.yml candidate and static regression.
Manual dispatch only, configuration/source SHA pinned, read-only contents,
Android missing signing secrets fails before dependency install; no debug fallback
permitted by prerequisite, no Release publishing yet. Static test passes 1/1.
DO NOT DISPATCH: public CA acquisition from fixed certificate repository, explicit
Node/JDK/SDK/NDK/WiX toolchain, artifact provenance and release promotion remain
unfinished. No secrets uploaded and no cloud client build claimed.

2026-11-17 user expanded delivery to seven services plus two clients. Reuse the
verified server batch; build/release Electron Windows x64 from
stevenzxs/jitsi-meet-electron and Android from stevenzxs/jm (local jm, same source).
Synchronize client.env to https://118.193.36.35:8443 and dedicated public CA.
No client-trust waiver: prepare and verify endpoint-scoped trust before activation.
Client builds use controlled configuration-repository Actions with fixed source SHA.
Do not increment versions implicitly or overwrite historical artifacts.

User approved commits/pushes, merging the confirmed knowledgebase policy, installing
150 tooling and initializing a dedicated CA, seven-service Actions builds/publication,
and data-preserving updates/certificate replacement on 118.193.36.35.
Target: existing amd64 instance, https://118.193.36.35:8443, UDP 10000;
150 orchestrates and signs; Actions never receives CA or target SSH private keys.
No client rebuild, data deletion, global Docker changes, or unrelated host changes.

## Ordered gates and evidence

1. GOV-02/05: merge only confirmed policy onto knowledgebase main, preserve concurrent
   changes; synchronize clean cloud checkout; record actual loaded SHA.
2. GOV-03: extend existing build-package workflow with explicit publication input.
   Publish exact same-run verified archives only after package success; least-privilege
   packages:write in publication job only. Record config/source SHA, image config ID,
   registry digest and platform. Keep offline path intact. Unit/static tests before push.
3. GOV-04: add fixed-SHA Actions API orchestration, bounded status queries, artifact
   verification and persistent task records in the existing config repository/Skill.
   Verify dedicated GitHub authorization; do not repurpose knowledgebase-only token.
4. GOV-02/05: certificate repo supports noninteractive encrypted CA keys with external
   password file, stable public metadata and no-overwrite signing. Test then install
   fixed commit on 150. Initialize CA outside repos; independent recovery backup must
   be arranged/verified before activation. Commit public CA only, never private keys.
5. GOV-05: extend common runtime for existing-instance digest updates. Validate exact
   instance/project/mounts, idle meetings, backup SQLite consistently and retain secrets,
   data and CA volumes. Pull all images before changing anything; rollback config/images
   without overwriting newer user data. Test refusal and rollback paths without Docker.
6. Dispatch approved amd64 seven-service run from Hermes, retain run/attempt and all
   artifact/digest checks. Failed or partial run never qualifies as full publication.
7. Deploy fixed digests on 118, verify TLS/API/signaling and patch identities separately.
   Activate new external certificate only after scoped client trust transition and
   backup verification. Internal TLS remains unchanged; no TLS bypass acceptance.
8. Record actual evidence in knowledgebase ledger; provide Android resumable prompts.
   Model-driven/Android and media acceptance remain separate from direct shell execution.

Stop affected gate for missing credentials, conflicting remote changes, backup failure,
active meetings, unprepared client trust or unavailable resources. Never substitute
local server build or silently weaken approval/security to finish the chain.

## Checkpoint

### Continuation

- User authorized independent local encrypted CA recovery backup. Backup and
  separate DPAPI-current-user protected password stored outside repos under
  C:/Users/ZL/AppData/Local/CloudMeetRecovery/{backups,credentials}/ca-v1-20261117.
  ACLs checked: current user and SYSTEM only. Re-read backup, unprotect password,
  decrypt private key in memory and compare public key to registered CA: PASS.
  Windows profile dependency remains; no independent offline password escrow claim.
  Client trust gate remains, external CA not activated.
- Same-run server artifact 14299373897 ZIP verified SHA256
  361a6c8bdb33cc10154c6b04998f3d20ec9024a7f3b1c508256568d7b5e35316;
  internal server archive SHA256
  6a9f18ba1a274233d37f757c0682d7750409ffbf4787c44c0d0992310dd8eba4.
  Non-image materials extracted in Temp for online configuration review only.

- Current 118 is an authorized clean-install target: ledger separately records user
  approved deletion without backup. Ubuntu24.04 amd64, existing Docker/containerd
  store, no Compose plugin. All seven fixed GHCR images pulled and checked against
  RepoDigests, platform and config content SHA256 from streaming docker image save.
  All passed. Engine Id here is manifest digest, not config ID. No containers started.
- 150 leaf chain/IP SAN/key pair and dedicated public root DER fingerprint verified.
  Independent CA recovery backup remains unverified; no CA private key exported.
  Concurrent client.env now points at 10.1.2.28:8443; preserve it, do not silently
  change it to 118 or rebuild clients. Same-run server artifact acquisition pending.

- Run 44017306066 attempt 1 SUCCESS for seven builds/package/publish, fixed config
  1868880d8fca9a6cb078ef5b2ae21e7e985c036d. Batch 11248.0.2-44017306066-1.
  Downloaded registry artifact 14299364333, verified API ZIP SHA256
  2614775315c2a9b8985f7f3a10acb012873b7bc061d01ecd99f14e3153694d3e,
  internal registry JSON SHA256
  82aa5feb8c9a5ce02e569763abd5535437ff9b61f49f218499b72defd40baf0d.
  Independently fetched all seven GHCR manifests anonymously by fixed digest,
  recalculated manifest byte digests and checked config=image_id: all pass including
  JVB. Exact state PUBLISHED_NOT_DEPLOYED. Server package local delivery, Hermes
  orchestration, 118 update/TLS and client/media acceptance remain separate gates.

- Attempt 4: first four services published; Prosody upload failed unknown blob,
  remaining services not attempted. Partial registry artifact 14299231743 verified
  ZIP SHA256 08a295e8a268adbbae99953645f9cd1d270742f0a30d23d32b4777f325fb8c0a.
  No remote manifest for Prosody/Jicofo/JVB attempt 4; underlying blob-loss cause unknown.
- Pushed fix 1868880d8fca9a6cb078ef5b2ae21e7e985c036d: bounded same-image unknown-blob
  retry with tag-absence guard, no auth retry, preserve initial partial evidence.
  Clean export named deploy passes inputs SHA and 63 tests (one skipped); original
  workspace historical output layout failure preserved. New run 44017306066 active
  with this exact commit, version 11248.0.2 amd64, explicit publication enabled.

- Attempt 3: six images published/remote-config verified (gateway/app-web/api/web/
  prosody/jicofo); JVB push denied write_package. Retrieved partial registry artifact
  14298800702, verified ZIP SHA256
  3cc5839c58db48a25a4c502281c1bca0c1d3b5e64e4509fe526e36d61bb0d771.
  Status remains PUBLISHING_NOT_COMPLETE; preserve published tags, do not deploy or
  retry publication over existing batch. JVB-specific Actions Write access needs fixing.

- Attempt 2 of run 44008112446: all seven builds/package SUCCESS; gateway absence
  probe now passes but actual push fails `denied: permission_denied: write_package`.
  Public visibility is effective, workflow token package write access is not. Verify
  Manage Actions access grants cloudemeet-deploy (workflow host), not caddy (source).
  No further unchanged rerun or 118 mutation. Job log 133801934014 retrieved via fresh
  signed redirect; watcher log-download HTTP401 is separate from registry denial.

- Run 44008112446 attempt 1 finished: seven builds and package SUCCESS, publish FAILED
  before first push at gateway tag-absence probe. Docker login succeeded; original
  script suppressed probe stderr, so exact Actions denial still needs diagnostic rerun.
- Confirmed gateway source stevenzxs/caddy at full SHA
  0d98caea58f794f88e709b1bef2880996a471bca in sources.json, local source HEAD,
  and actual 118 running image revision label. No source substitution needed.
- Authenticated GitHub Packages API: cloudmeet-gateway PRIVATE, other six PUBLIC;
  all seven have no linked repository. Existing authorized registry credential sees
  MANIFEST_UNKNOWN for failed batch gateway tag. Actions package access needs review;
  broad local credentials were not injected into Actions or copied to 150.
- Publication probe now retains bounded diagnostics and still fails closed on auth,
  transport and ambiguous errors; initial partial registry evidence is written before
  probing. Focused publication regressions 3/3 pass; not yet committed/cloud-verified.

- Local existing Git credential verified repo/workflow access (not copied to 150).
  Approved amd64 11248.0.2 run dispatched: 44008112446, config 502adc2.
  This is local dispatch, not Hermes acceptance; bounded background monitoring active.
- Added token-file Actions API entry and existing-instance image-only updater, 8 focused
  tests pass. Updater is limited to unchanged reviewed external patches/configuration;
  requires strict TLS and empty JVB /stats conferences map, checks pulled IDs, keeps
  SQLite backup/config/old image IDs and verifies TLS/API or restores old image IDs.
- Read-only inspection found current 118 Caddy certificate is NOT valid for the public
  IP: strict IP verification fails. Historical HTTP acceptance is not strict IP TLS.
  Do not bypass this preflight; new-CA client trust remains required before activation.
- 150 issued and verified an IP SAN leaf for 118 using encrypted CA v1. Sensitive output
  remains on 150 under cloudmeet-issuer/118-leaf-v1; not transferred or activated.

- Knowledgebase approved policy pushed to main at 2afe241; cloud retained its existing
  branch records and merged main at 90b2bb2 (clean). It is not the exact main commit.
- Explicit same-run publication implemented; targeted tests pass. Linux suite 60/61:
  existing ignored output/assemble-11248.0.1.sh fails layout inventory. Not deleted.
- Certificate tooling c5af437 pushed and installed at /opt/cloudmeet-cert-tools/c5af437;
  nine unit tests pass locally and on 150. A source archive upload is bootstrap evidence,
  not proof Hermes can fetch the private repo unaided.
- Dedicated encrypted CA v1 created on 150 at data/cloudmeet-issuer (outside workspace).
  Public identity committed separately to certificate repo 959de73; not activated.
  Independent backup and scoped client trust transition remain pending.
- No independent CloudMeet GitHub credential found on 150; knowledgebase-only token
  not reused. Actual Hermes dispatch/publication and private repository fetch blocked.
- Online existing-instance updater/rollback and model-driven task integration remain
  unimplemented. No new Actions run, 118 update or certificate replacement performed.
