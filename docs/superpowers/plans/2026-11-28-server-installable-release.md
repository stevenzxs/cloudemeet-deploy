# Server Installable Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing server Release with the minimum reviewed installation files and eight immutable service images needed to install its exact batch.

**Architecture:** Keep the existing `build-server.yml` version/build/publish flow. Build `jitsi-mgr` backend as the eighth GHCR image while keeping its frontend static archive as a same-batch asset served by Caddy. Rewrite the deployment template for the eight custom images and stage minimal Compose/environment/Caddy/install files in the same Release, covered by existing SHA256SUMS.

**Tech Stack:** GitHub Actions YAML, Docker Compose YAML, Markdown, Python `unittest`/PyYAML.

**Spec:** User-approved minimal scope in conversation: same-batch Release includes required Compose, non-secret configuration template, installation instructions, and integrity coverage; no extra skills/workflows, no first-install changes, and no historical Release rewrite.

## Global Constraints
- Preserve existing dispatch inputs, revision allocation, build matrix, publication gate, GHCR digest pinning, and draft-upload-publish sequence.
- Release Compose declares exactly `web`, `app-web`, `api`, `jitsi-mgr`, `gateway`, `prosody`, `jicofo`, and `jvb`; all eight services use their same-batch digest references, while the jitsi-mgr frontend remains a Caddy-served static asset.
- Do not package secrets, target-host runtime values, or generated private keys.
- `jitsi-mgr` backend is the eighth custom image; its separately built frontend remains a static archive mounted read-only into Caddy.
- Do not change `skills/first-install/`, deploy a server, or modify historical Releases.
- Do not read, invoke, copy from, import, or otherwise depend on anything under `skills/full-build-deploy/`; that directory's tools may delete files.
- Keep changes limited to `skills/server-build-deploy/`, `.github/workflows/build-server.yml`, its tests, and this plan.

## Review Focus
- Missing/extra service in Compose: test exact service set.
- Floating, cross-batch, or tag-only image reference: test every image against generated `images.json` digest references.
- Compose/config/install instructions omitted from publication or SHA256SUMS: test workflow staging and checksum creation order.
- Secret-bearing configuration accidentally checked in: test templates for secret-like values and keep only placeholders/non-secret defaults.
- Build-only (`publish_images=false`) unexpectedly publishes assets: test existing publication gate remains intact.

---

### Task 1: Add minimal install files and contract tests

**Files:**
- Create: `skills/server-build-deploy/templates/compose.yaml`
- Create: `skills/server-build-deploy/templates/.env.example` (or an equivalently named non-secret template if repository convention requires it)
- Create: `skills/server-build-deploy/INSTALL.md`
- Modify: `skills/server-build-deploy/tests/test_server_workflow.py`

**Interfaces:**
- Produces: static installation assets copied unchanged into each published batch; Compose uses environment substitutions for per-instance values and digest-pinned image values supplied from the batch manifest.

- [x] **Step 1: Write failing tests** asserting Compose and required Caddy/environment/install templates exist, Compose has exactly eight digest-variable services, no build declarations or literal secrets exist, internal Caddy TLS uses `tls internal`, Prosody trusts only the exported root certificate read-only, and INSTALL documents origin/TLS and secret setup.
- [x] **Step 2: Run** focused tests and observe missing asset failures before implementation.
- [x] **Step 3: Add** Compose, non-secret environment, public-ACME/private-CA Caddyfiles and concise INSTALL instructions. Caddy provisions its internal CA; operator exports only `root.crt` to Prosody, which retains peer verification. No private CA key is shared.
- [x] **Step 4: Run** focused tests and Compose config validation.

### Task 2: Build and publish jitsi-mgr as the eighth image

**Files:**
- Modify: `skills/server-build-deploy/tools/build-service.sh`
- Modify: `.github/workflows/build-server.yml`
- Modify: `skills/server-build-deploy/tests/test_server_workflow.py`

**Interfaces:**
- Produces: `jitsi-mgr.tar.gz` and `build-evidence.json` for the backend image; keeps `artifacts/jitsi-mgr-ui.tar.gz` as the frontend static asset.
- Release `images.json` contains all eight service image digests.

- [x] **Step 1: Write failing tests** asserting jitsi-mgr backend image build, separate UI archive and eight-image publish loop.
- [x] **Step 2: Run** focused tests and observe missing Dockerfile/build behavior.
- [x] **Step 3: Implement** the jitsi-mgr image using the existing digest-pinned lifecycle base and Java 21 runtime, with immutable build labels and same-batch archive evidence; publish all eight image digests while retaining the UI archive.
- [x] **Step 4: Run** focused tests and assert manifest generation rejects any image count other than eight.

### Task 3: Include install assets in the existing Release and document its contents

**Files:**
- Modify: `.github/workflows/build-server.yml`
- Modify: `skills/server-build-deploy/SKILL.md`
- Test: `skills/server-build-deploy/tests/test_server_workflow.py`

**Interfaces:**
- Consumes: static asset paths from Task 1 and the `images.json` created by the existing publish step.
- Produces: the existing Release asset set plus Compose, non-secret config template, and INSTALL documentation; all are covered by the existing `SHA256SUMS`.

- [x] **Step 1: Extend tests** for all static assets, eight-image manifest, staging-before-checksum and publish gating.
- [x] **Step 2: Run** focused tests and observe missing install assets and workflow staging.
- [x] **Step 3: Modify** the publish script to copy reviewed assets from `material_commit`; update the server skill scope/asset list. Release creation remains gated by `publish_images`.
- [x] **Step 4: Run** focused tests and verify staging order and publish gate.

### Task 4: Verify focused regression suite and review scope

**Files:**
- Test: `skills/server-build-deploy/tests/test_server_workflow.py`
- Test: `skills/server-build-deploy/tests/test_version_allocator.py`
- Test: `skills/server-build-deploy/tests/test_allocator_workflow.py`

- [x] **Step 1:** Run `python -m unittest discover -s skills/server-build-deploy/tests -p 'test_*.py' -v`; all 24 server-build-deploy tests pass.
- [x] **Step 2:** Parse workflow and Compose YAML and inspect scoped diff; `docker compose config --quiet` succeeds with example env.
- [x] **Step 3:** No server operation, image pull, Release publication, historical Release edit, `first-install` modification, or `skills/full-build-deploy/` access occurred.
