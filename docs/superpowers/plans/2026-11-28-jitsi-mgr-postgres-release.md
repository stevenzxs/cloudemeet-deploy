# jitsi-mgr PostgreSQL Release Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the published CloudMeet server bundle start the pinned production `jitsi-mgr` against persistent PostgreSQL.

**Architecture:** Add a digest-pinned PostgreSQL infrastructure service to the release Compose template, provide its data volume and readiness health check, and make `jitsi-mgr` use explicit PostgreSQL settings and a required secret. Keep the eight application images and build matrix unchanged.

**Tech Stack:** Docker Compose, Python workflow tests, GitHub Actions server build/publish workflow.

**Spec:** `docs/superpowers/specs/2026-11-28-jitsi-mgr-postgres-release-design.md`

## Global Constraints

- Application image inventory remains the eight services in `images.json`.
- PostgreSQL is an infrastructure service, not an application build-matrix entry.
- Use `caddy-public-acme` and `https://cloudmeet.stevenzxs.cn` when publishing.
- Do not deploy to the server in this task.
- Do not expose database credentials in source, workflow output, or logs.
- Follow branch governance: feature branch, merge and push `main`, then remove the feature branch.

## Review Focus

- A config validation that assumes Compose service count equals image count must allow exactly one non-image database service; cover with a regression test.
- Missing database password must fail Compose rendering instead of using a default; cover with a regression test.
- `jitsi-mgr` must wait for database health, not merely container start; assert health condition.
- PostgreSQL volume must persist independently of container recreation; assert named volume mapping.
- Infrastructure image must be digest-pinned; assert the exact image reference has `@sha256:` and no floating tag.

---

### Task 1: Release Compose and regression tests

**Progress:** Implementation and verification complete; awaiting commit.

**Verification evidence:** Regression test failed before Compose/PostgreSQL changes because the runtime definition had only eight services; targeted server workflow test now passes (15/15), full suite passes (28/28), Compose YAML parses, and `git diff --check` is clean. Docker Registry API verified `postgres:16.13` index digest `sha256:5d143123fdf80462d1778cd4f24b9f7ca13c87174bca19141fb194c5a1ebca59` and its linux/amd64 manifest.

**Files:**
- Modify: `skills/server-build-deploy/templates/compose.yaml`
- Modify: `skills/server-build-deploy/tests/test_server_workflow.py`
- Modify if required by the discovered validator: release Compose validation code/tests in `skills/server-build-deploy/tools/`

**Interfaces:**
- Consumes: current eight `IMAGE_*` variables and release `images.json` contract.
- Produces: nine Compose runtime services, with exactly eight application image placeholders and one digest-pinned PostgreSQL infrastructure image.

- [ ] **Step 1: Add failing regression assertions**
  Assert that PostgreSQL is a service with an immutable digest reference, a named data volume, and a health check; `jitsi-mgr` uses PostgreSQL URL/driver/dialect, requires a password, and depends on PostgreSQL with `condition: service_healthy`; all eight application image placeholders remain unchanged and there is no ninth application image.
- [ ] **Step 2: Run the targeted test and verify expected failure**
  Run `python -m unittest skills.server-build-deploy.tests.test_server_workflow` or the repository's documented equivalent. Expected: failure because PostgreSQL service/configuration is absent.
- [ ] **Step 3: Implement the minimal Compose and validator changes**
  Select an official supported PostgreSQL major and verify its immutable image digest; add the infrastructure service and named volume. Use `${JITSI_MGR_DB_PASSWORD:?generate a unique secret}` with no default. Configure URL `jdbc:postgresql://postgres:5432/jitsi_mgr`, PostgreSQL driver, PostgreSQL dialect, and health-gated dependency. If a repository validator enforces equality of Compose services to image inventory, change it to distinguish the eight app services from the infrastructure service.
- [ ] **Step 4: Run targeted and full server workflow tests**
  Run targeted Compose assertions, then the full server-build-deploy test suite. Expected: all pass.
- [ ] **Step 5: Commit the implementation**
  Commit the spec, plan, Compose change, validator change (if any), and tests together with message `fix: configure PostgreSQL for jitsi manager`.

### Task 2: Merge and publish

**Files:**
- No further source files unless tests/review identify a concrete defect.

**Interfaces:**
- Consumes: tested feature-branch commit.
- Produces: pushed `main` commit and one published amd64 server release.

- [ ] **Step 1: Verify the branch diff and test evidence**
  Confirm only the approved release configuration, tests/validator, spec, and plan are changed; rerun the full suite and confirm a clean worktree after commit.
- [ ] **Step 2: Merge to `main` and push**
  Use the repository's required PR/merge process; verify remote `main` contains the feature commit.
- [ ] **Step 3: Clean up the feature branch**
  Delete the local and remote feature branch only after confirming it is merged and pushed.
- [ ] **Step 4: Run server-build-deploy publication workflow**
  Sync clean `main`, set `material_commit` to the exact pushed SHA, `architecture=amd64`, `publish_images=true`, TLS `caddy-public-acme`, and origin `https://cloudmeet.stevenzxs.cn`.
- [ ] **Step 5: Verify release assets and report**
  Wait for successful version/build/publish jobs. Download the new Release assets, verify every `SHA256SUMS` entry and GitHub asset digest, and confirm the published Compose contains the PostgreSQL infrastructure configuration and unchanged eight-image inventory. Explicitly report `NOT_DEPLOYED`.
