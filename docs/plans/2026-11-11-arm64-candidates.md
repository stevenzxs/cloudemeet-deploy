# Seven-service ARM64 Candidate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and retain seven source-built ARM64 candidate images, with smoke tests and traceable identities, without registry publication or server access.

**Architecture:** Keep the proven three-service control-plane job; export its images only after successful integration. Build the remaining four services in independent native ARM64 jobs. Upload image archives separately from explicitly selected evidence; preserve source env/lockfiles, fixed source commits and actual resolved ARM64 base identities. Candidates remain incomplete for seven-service integration, offline installation and media acceptance.

**Tech Stack:** GitHub Actions ubuntu-24.04-arm, Docker, Python standard library, Node/npm, Maven/Java 17, Go.

---

## Approved design and constraints

- Use Actions artifacts, no GHCR writes, merge or target access. User approved branch commits/push and Actions execution.
- Build current clean source identities: web f765042bf280cbd7dcd4a9bbdb63b09e9e4d3259; app-web 784c1d004cfcea32f5316314f5979cb74aba88b0; api 632c247064b14fe5cd9b8806ed42cb8fb45adcba; gateway 0d98caea58f794f88e709b1bef2880996a471bca. Retain existing three pinned control-plane commits.
- Do not alter source repositories, env or lockfiles. Business Web uses its checked-in config, not an unapproved origin override. This candidate is not yet qualified for a different server origin.
- Builders may acquire published dependencies online. Record resolved base digest/platform, dependency manifests and output hashes; do not imply package-version reproducibility or security clearance.
- Export images before running API persistence smoke to avoid test data entering images. Only new ephemeral container/volume cleanup is allowed.
- Download completed artifacts into deploy/history, not packages. No READY_FOR_INSTALL claim.

### Task 1: Candidate evidence contract (test first)

Files: tests/test_arm64_candidates.py; tools/arm64-candidate-evidence.py.

1. Add negative tests for wrong architecture, absent/duplicate service, absent source revision and altered archive hashes; add passing seven-service and partial-job evidence tests.
2. Run `python -B -m unittest discover -s tests -p test_arm64_candidates.py` and observe missing implementation failure.
3. Implement strict image platform/source/size/hash validation and bounded image export with provenance JSON. Archive actual Docker image IDs (not registry digests); preserve base and dependency evidence.
4. Re-run tests, then commit this step together with approved plan.

### Task 2: Four native source builds and smoke

Files: tools/arm64-candidate-build.py; tools/arm64-candidate-smoke.py; tools/arm64-candidate-sources.json; tools/arm64-candidate-*.Dockerfile.

1. Add config/recipe regression tests for four services, locked revisions, native runner, no test skip, unchanged env/lockfiles and no published application-image substitution.
2. Observe failures; implement checkout-at-commit and base-resolution evidence, native source builds and runtime packaging.
3. web: npm ci/make all, explicit public payload allowlist, upstream pinned lifecycle, nginx config/static smoke.
4. app-web: npm ci/npm run verify, preserve checked-in origin, maintained nginx routes and SPA/asset/internal route smoke.
5. api: full Maven verify; ARM64 JRE, health/SQLite persistence across two fresh containers on an ephemeral volume.
6. gateway: native Go module verify/race-short tests/build; Caddy modules/version and HTTP startup smoke, no CA export.
7. Validate Python/tests, shell syntax and diff; commit once focused tests pass.

### Task 3: Workflow and control-plane retention

Files: .github/workflows/arm64-smoke.yml; tools/arm64-control-build.sh; tools/ARM64-CI.md.

1. Add tests requiring four-job matrix, three control-plane archives, explicit upload paths, no private compose upload, bounded retention and no packages write.
2. Extend control job to collect source/base/dependency provenance and save three images after existing gate success.
3. Add four-service native matrix with fail-fast false, independent evidence/image artifact upload and timeouts. Do not re-run the redundant original source-smoke matrix for candidate-only changes if avoidable.
4. Run focused suite, existing host-control tests, syntax and diff checks. Commit and push approved branch; retain push/run identity.

### Task 4: Verification and handoff

1. Read fresh Actions run jobs; do not claim build success before terminal result.
2. Retain logs and artifacts for completed jobs; verify archive hashes and image/source/platform evidence. Failed/partial artifacts cannot qualify all seven.
3. Update build-tools/migration/STATUS.md with actual run, artifacts, completed gates, blockers and next action.
4. If runtime failures occur, preserve evidence and fix the demonstrated cause only; at most three attempts per cause. Do not expand to dependency remediation or server work.

Execution is in the existing isolated worktree in this session; no delegation is needed. Final acceptance requires actual native CI results, not local syntax tests.
