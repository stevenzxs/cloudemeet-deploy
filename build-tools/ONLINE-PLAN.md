# CloudMeet online delivery implementation — 2026-11-17

## Approved scope

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
