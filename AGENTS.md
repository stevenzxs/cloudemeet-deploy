# Packaging and deployment contract

## Route and ownership
- Start with `README.md`; it points to the actual installable version. `packages/` is the handoff, `history/` is retained evidence, `skills/` is skill maintenance source, `clients/` is accepted MSI/APK delivery. Do not create another root delivery tree.
- Build tools remain in `../build-tools/`; Linux compilation/image export stays in approved WSL work/cache/staging. Windows handles client packaging. Do not move source projects into this tree.
- Root Compose/config/patch files are transitional templates, not the offline release. Do not apply their online pull flow to an offline bundle. Keep templates in place until a separately scoped migration updates all callers.
- Do not edit immutable `packages/**` or historical batch payloads to fix a reference. Generate a new version when content changes. Keep historical path strings, manifests, logs, checksums and signatures unchanged.

## Scope and release gates
1. Record confirmed architecture/OS/origin, source-build versus published images, seven-service/patch/client scope, and requested end milestone. Do not ask the same choices again.
2. Source-build uses current workspace application sources plus published dependencies/base images; record actual source commit, dirty state, base/dependency identities and artifact hashes. Never substitute an application image silently. Preserve original env and lockfiles.
3. Assemble explicitly incomplete candidates in WSL; check all files, image identities/platform, dependency closure and content. No secrets, CA private keys, production databases or real server `.env` in delivery.
4. `READY_FOR_INSTALL` requires actual isolated full-OS offline Docker installation where requested, empty-store import, original initializer/startup and strict TLS/API/signaling/operational-bridge checks. Userspace-only containers, existing caches and unit tests are insufficient. A QA-only status override must stay outside delivery and must not become release evidence by itself.
5. Publish to `packages/<version>/`, verify every checksum after final copy, and update README with actual path, trusted SHA256SUMS digest, supported baseline, commands and unverified items. A retained history copy alone is not delivery.
6. Target installed and full acceptance are separate: preserve target-generated CA, build endpoint-scoped clients with only public trust material, then verify real multi-endpoint ICE/UDP/bidirectional media. Never label unresolved CVEs as accepted or imply installability grants production security approval.

## Stop conditions and progress
- Stay on the requested milestone; no broad vulnerability remediation, dependency upgrades, cache deletion, extra host Docker daemon or unrelated cleanup. Capture out-of-scope findings as risks, continue independent work, and stop only at a concrete blocker or authorization boundary.
- Local consolidation never authorizes SSH, restart, switch, uninstall or deletion on a server. Before destructive target changes: verified recovery backup, exact target/resources to delete and preserve, risk statement and explicit second confirmation. Preserve 202/118 and historical `old_deploy/`, `openeuler-arm-deploy/`.
- Report completed gates, pending gates, actual artifacts and blockers, not invented overall percentages. Keep one current checkpoint in `../build-tools/migration/STATUS.md`; historical evidence is not current runtime truth.

## Skill maintenance and validation
- Canonical skills: `skills/cloudmeet-deploy-offline/` and `skills/cloudmeet-deploy/`. Update relevant references and evals, then back up and synchronize only these named installed copies. Do not edit unrelated skills/settings.
- Validate Linux installer tests in WSL: `wsl -d Ubuntu-24.04 -- python3 -B -m unittest discover -s /mnt/d/code/jitsi/build-tools -p "test_offline*.py"`; they assume POSIX paths/root APIs and are not a Windows-native suite. From workspace root also run `node --test build-tools/migration/client-layout.test.cjs`. Use the package's `install.py --verify-only` after any package copy/move. Do not run engine/deploy merely to validate documentation.
