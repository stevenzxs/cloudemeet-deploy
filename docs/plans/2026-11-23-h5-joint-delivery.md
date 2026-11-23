# H5 increment to existing CloudMeet delivery

Goal: Add H5 to existing seven-service/two-client joint delivery, not replace existing workflows.
Architecture: static H5 served by gateway; exact source lock, shared parent assignment, public files only. Online/offline first/update share H5 verification and activation. No eighth service or client redistribution changes.

## Steps / acceptance

1. Pin H5 source; implement public-file identity/hash verification in build-tools/offline-runtime/h5.py and unit tests. Reject missing, extra, symlink, mismatched assignment/identity. No product builds locally.
2. Extend existing package workflow and package.sh to obtain fixed H5 source, run native tests and stage H5 before package checksums. Include evidence in joint-release.py gate; offline export preserves and verifies H5.
3. First-install start.py: install H5 runtime config/current pointer and exact gateway route/read-only parent mount. Update online_update.py with reviewed bounded migration, backup and rollback; maintain existing secret/data/idle/TLS protections.
4. Run targeted auxiliary tests and Caddy validation if existing reviewed tooling is available. Update inputs.sha256 and AGENTS inventory; commit/push/main closure. Knowledgebase approval records incremental extension for online/offline first/update.
5. Check 150 controlled entry and available GHCR/Release identities, dedicated credentials, allocator recovery. Dispatch only after preflight gates; existing public-origin/CA retained. Approved H5 baseline 0.1.0 inherits the existing parent rN without changing the allocator policy identity.
6. Only verified joint delivery may update 118. No local full build, no data reset, no TLS bypass. Record actual run/result, download hashes, backup/apply/restore, clients/media separately.

Current checkpoint: steps 1–3 implemented but not committed; integration/recovery verification and input hashes remain open. Fresh regression: 152 auxiliary tests and 11 native H5 tests passed; added source-mutation rejection regression passed in the focused H5 suite (10 tests). No Actions, allocation, publication or target mutations. Plan file is not completion evidence.

## Resumed preflight, 2026-11-23

- H5_SOURCE_READ_TOKEN exists in the deployment repository; actual Actions cross-repository read remains unverified. Never use the credential disclosed in conversation.
- GitHub runner 21 is offline. Registration belongs to this repository, Default pool, installed inside the Hermes container and owned by hermes UID 1000. No listener process observed; latest log ends with cancellation on 2026-11-21. Do not restart it merely to bypass the isolation gate.
- Container `/opt/data` maps to host `/opt/stevenzxs-hermes/data`, not host `/opt/data`. Real version ledger remains intact at the configured container path. Read-only SQLite integrity check passed; policy identity matches, all allocation digests match, r1–r14 are contiguous, highest Run 44888921798.
- Version-ledger backup ledger.sqlite.bak-20261120 is valid but EMPTY (zero allocations); it cannot recover r14. The separate revision-ledger-backups series belongs to a different schema and is not automatically a valid version-ledger backup. Independent authoritative high-water recovery remains unverified.
- Runner registration, version ledger and controller auth are owned by the same Hermes UID in the same container. Dedicated label alone does not prove runtime isolation. Formal dispatch remains blocked pending a reviewed restricted runner execution boundary and tested independent recovery; no ledger initialization/reset or revision allocation performed.

## User steering and existing-artifact decision

- User requested no further diagnosis or recovery of the old offline runner. Stop that lane; replacing the runner is an option, not an operation already performed or a waiver of new-runner registration/permission gates. No persistent standard workflow changes are inferred.
- Fresh GitHub query: Run44888921798 succeeded at configuration5fffae8f8d0a30be1dd8167564ae7d85e7f46ca5, including seven service builds, Electron, Android, and server publish. Artifact inventory includes registry and server/client artifacts, not H5. Repository Release list is empty. Therefore r14 is retained but does not meet this task's complete joint H5 delivery contract. No new allocation/dispatch is made by this query.
- Added stage entry integration regression exercising public inventory, native-test invocation, parent r15 derivation, origin, Caddy routing and readonly Compose mount (Git/npm external calls mocked); focused H5 suite 11/11 passes. This is not an actual Actions credential or target installation test.
