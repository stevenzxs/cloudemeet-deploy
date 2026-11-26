# CloudMeet Build and Deployment Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close CloudMeet build/release/first-install reliability gaps so the current model can execute the user's exact standard-delivery prompt through deployment and acceptance without redundant questions, command edits, or unsupported success claims.

**Architecture:** Audit and preserve the existing Actions, revision ledger, release/package format, and shared install core. Add a versioned machine-validated release contract across producers and consumers, strengthen recovery around the existing durable task record, and provide one deterministic operator entry point with automated gates and current-model acceptance fixtures.

**Tech Stack:** Existing GitHub Actions YAML, Python deployment/build tools and tests, Node client tooling/tests, release JSON/SHA256 manifests, OpenCode current-model environment; use existing project toolchains and avoid adding another model integration.

**Spec:** `docs/superpowers/specs/2026-11-26-cloudmeet-reliability-design.md`

## Global Constraints

- `config/client.env` remains the sole product client-origin/TLS configuration source; expected values are assertions, not a second source.
- Preserve approved TLS modes, signing identities, rN allocation semantics, release scope, data/CA protections, and production approval boundaries.
- Reject contradictions before publication or target side effects; never ask the model to choose between conflicting evidence.
- Use fixed source/config SHAs, release/asset digests, and image digests; releases remain immutable.
- First install does not authorize deleting existing data; do not overwrite or reinitialize existing secrets/data, and preserve failed state.
- Reuse the existing revision ledger and shared install/update core where valid; do not create parallel product logic without audit evidence.
- Update `build-tools/inputs.sha256` for modifications to covered build materials.
- Safely sync knowledgebase and deploy config `origin/main` before reading task-specific materials; use task branches and complete the required main-merge/remote-verification/branch-cleanup closure.
- No production workflow dispatch, durable revision allocation, publication, CA action, SSH mutation, installation, or deployment without the corresponding existing task authorization.
- First model acceptance is only the current model using the exact prompt in the spec; other model evaluation is deferred.
- Report fixed numbered steps with status, per-step and cumulative elapsed time; update with evidence about every 60 seconds during long steps; preserve timing/step identity on resume and mark unknown gaps honestly.

## Review Focus

- Approved TLS/origin differs between joint evidence, server material, client evidence, and setup arguments — test r31-shaped mismatch rejection before publish.
- Missing/stale service or jitsi-mgr/H5 asset despite a successful workflow — test required inventory and exact digest coverage.
- Host identity, existing instance/data, unsupported resources, or inadequate engine/OS/architecture — test first-install stops before mutation and never guesses.
- Retry after partial setup or process loss — test no duplicate initialization, allocation, dispatch, overwrite, or cleanup.
- Public asset proxy/API distinction, TLS verification, and digest mismatch — test allowed fallback only and reject corrupted/untrusted material.
- Long phases and process interruption — test fixed step IDs, status, step/cumulative elapsed time, evidence-based ~60-second updates, and honest unknown intervals on resume.

---

## File map (confirm exact existing owners during Task 1 audit)

- `build-tools/` — release contract schema/validator and validation integration in existing orchestration; preserve current source of truth and tool boundaries.
- `build-tools/tests/` — producer/consumer, mutation, omission, and recovery regression coverage.
- `.github/workflows/` — earliest reliable validation gates and artifact/evidence handoffs; no push-triggered publication changes.
- `build-tools/offline-runtime/` — only if audit proves shared first-install preflight/recovery needs correction; no second installer.
- `skills/cloudmeet-deploy/SKILL.md` and/or `skills/cloudmeet-online-delivery/SKILL.md` — deterministic model-facing entry, aligned with actual approved contract.
- `docs/superpowers/specs/2026-11-26-cloudmeet-reliability-design.md` — accepted intent, constraints, and acceptance case.
- `docs/superpowers/plans/2026-11-26-cloudmeet-reliability.md` — execution checklist and verification record.
- `build-tools/inputs.sha256` — update whenever covered materials change.

### Task 1: Trace the real contract path and lock ownership

**Files:**
- Read: `AGENTS.md`, `build-tools/README.md`, relevant workflow YAML, `build-tools/joint-release.py`, `build-tools/online-material.py`, `build-tools/setup.py`, shared runtime install/start/initialize modules, existing task-state tooling, and relevant tests.
- Modify: this plan's audit findings section only (and create a focused audit note under `docs/superpowers/` if findings cannot fit here).
- Test: existing relevant test commands identified from package/workflow definitions; do not run product build or production workflow.

**Interfaces:**
- Consumes: approved release contract and r31 evidence from the design.
- Produces: an evidence-backed field ownership map (authoritative source, generated copies, consumers), actual recovery-state inventory, earliest gate placement, and precise test commands for later tasks.

- [ ] **Step 1: Trace origin/TLS from `config/client.env` through dispatch assertions, build evidence, server package candidate, joint release evidence, registry record, and setup arguments.** Record exact files/functions and current r31 divergence path.
- [ ] **Step 2: Trace all required release members (seven image digests, jitsi-mgr JAR/UI, H5, client evidence, package manifests) from production through consumption.** Record omissions that can survive a green job.
- [ ] **Step 3: Trace task persistence, first-install phases, retries, and current target preflight boundaries.** Distinguish durable external state, target state, and transient logs.
- [ ] **Step 4: Identify the earliest reliable pre-publication/pre-side-effect gate without moving durable revision allocation semantics.** Record evidence from workflow dependencies and tests.
- [ ] **Step 5: Run only relevant existing tests and static checks; capture actual pass/failure results, including baseline failures.** No global construction, Actions dispatch, or server changes. Report the step number/status and elapsed timing at the task's progress cadence.
- [ ] **Step 6: Review findings against the design, update this plan's exact file ownership and test commands, and commit the audit milestone.**

### Task 2: Add schema-validated immutable release contract

**Files:**
- Create/modify: exact contract schema/model location selected from Task 1 (prefer existing Python/Node format and ownership).
- Modify: `config/client.env` consumers only if needed to parse once and derive the contract; do not add a competing editable config.
- Test: focused contract schema/normalization tests.

**Interfaces:**
- Consumes: Task 1 field ownership map.
- Produces: one immutable contract object bound to config SHA, sources, run/attempt and revision allocation, architecture, TLS/origin, service inventory, all image references/digests, jitsi-mgr/H5/client identities, and package identity.

- [ ] **Step 1: Write tests for valid contract generation from a fixed fixture, including `caddy-public-acme` and `https://cloudmeet.stevenzxs.cn`.** Assert fixed config SHA/run/attempt and explicit service inventory.
- [ ] **Step 2: Run tests and confirm missing TLS mode, malformed origin, absent service, unbound source/config SHA, and duplicate fields fail.**
- [ ] **Step 3: Implement schema validation and canonical serialization in the exact module chosen by Task 1.** Derive fields from approved config and signed/verified workflow inputs; do not infer values from hostnames or prior Release.
- [ ] **Step 4: Test stable canonical digest and rejection of unsupported schema versions/unknown required fields.**
- [ ] **Step 5: Run focused tests and `git diff --check`; update `inputs.sha256` if covered files changed; commit.**

### Task 3: Enforce contract across build, package, and joint publication

**Files:**
- Modify: existing producer/consumer modules and workflow gate identified in Task 1; likely `build-tools/joint-release.py`, `build-tools/online-material.py`, `.github/workflows/build-joint.yml`, and adjacent tests.
- Test: existing joint-release/material/workflow tests plus new contract mismatch tests.

**Interfaces:**
- Consumes: Task 2 immutable contract.
- Produces: generated evidence/manifests carrying the contract digest and validators rejecting output drift before publish preparation/publication.

- [ ] **Step 1: Add failing test reproducing r31: joint evidence says public ACME/domain origin while server package says `https://cloudmeet.internal` and local-certificate mode.** Assert explicit mismatch diagnostic and no publishable result.
- [ ] **Step 2: Add failing omission tests for missing any of the seven images, jitsi-mgr backend/UI, H5, and required client evidence.**
- [ ] **Step 3: Run tests to confirm current code accepts at least one bad fixture or fails at the expected new assertion.**
- [ ] **Step 4: Implement shared validation at the earliest reliable boundary discovered in Task 1, and revalidate final generated output immediately before publication.** Preserve revision allocation semantics and draft/atomic publication policy.
- [ ] **Step 5: Add tests proving valid fixture publication proceeds while any field/asset mutation is rejected before external publication calls.**
- [ ] **Step 6: Run focused tests, workflow syntax checks, input digest checks, and `git diff --check`; commit.**

### Task 4: Verify downloaded release and setup contract before target effects

**Files:**
- Modify only shared package-verification/setup/preflight files selected by Task 1.
- Test: setup/package verification and target-preflight tests.

**Interfaces:**
- Consumes: published contract plus independent GitHub asset digests and package manifests.
- Produces: verified install plan bound to package SHA, registry record, expected origin/TLS, target parameters, and target identity; no secrets in diagnostics.

- [ ] **Step 1: Add failing tests for altered package bytes, mismatched external asset digest, conflicting setup origin/TLS, wrong architecture, missing certificate mode requirements, and missing jitsi-mgr/H5 materials.** Assert no target mutation functions are called.
- [ ] **Step 2: Add tests for existing root/data/secrets or unrecognized containers/volumes; assert first-install rejects without cleanup or reinitialization.**
- [ ] **Step 3: Implement verification using trusted API asset digest and internal checksums as separate evidence; retain strict TLS and host verification.**
- [ ] **Step 4: Verify explicit r31-valid contract succeeds in an isolated fixture, then run focused tests and commit.**

### Task 5: Make resume/idempotence reliable around actual first-install phases

**Files:**
- Modify only the existing durable task-state/controller and shared install core files proven incomplete by Task 1.
- Test: task-state, setup, initialize/start, and recovery tests.

**Interfaces:**
- Consumes: verified install plan from Task 4 and existing task/event identity mechanisms.
- Produces: phase-by-phase durable execution record; safe resume or explicit reconciliation state; preserved failure scene.

- [ ] **Step 1: Add failing interrupted-task tests at download, extraction, initialization, image pull, start, and certificate activation boundaries.** Assert resumption does not repeat irreversible prior phases.
- [ ] **Step 2: Add tests for duplicate task invocation and unknown state; assert no repeated initialization, revision allocation, workflow dispatch, or implicit apply.**
- [ ] **Step 3: Implement only missing persistence/recovery transitions, binding task ID, fixed release contract digest, attempt, target identity, and phase without storing secrets.**
- [ ] **Step 4: Verify all failure paths preserve diagnostics and data and return a deterministic resume/blocked reason.** Run relevant suite and commit.
- [ ] **Step 5: Verify persisted progress events retain stable step IDs, per-step/cumulative elapsed time, attempt intervals, and unknown gaps across interruption without fabricated ETA/percentage.**

### Task 6: Publish one deterministic model-facing execution entry

**Files:**
- Modify: the single canonical online delivery skill/entry identified in Task 1; update other copies only where governance requires them.
- Test: skill/entry contract tests and existing layout/input hash checks.

**Interfaces:**
- Consumes: verified delivery/install-plan interfaces from Tasks 3–5.
- Produces: fixed task classification, exact arguments/commands, expected outputs, side-effect boundaries, stop conditions, status format, and recovery references.

- [ ] **Step 1: Add contract tests that the entry includes the exact acceptance prompt’s explicit values, treats it as first install, and does not ask for those values again.**
- [ ] **Step 2: Add tests that the entry forbids guessed origins, mutable latest tags, command rewriting, silent TLS weakening, cleanup, and success claims without evidence.**
- [ ] **Step 3: Update canonical entry to call the actual checked tools in order and state routine progress reporting without repeated confirmation.** Respect safety/approval limits.
- [ ] **Step 3a: Specify progress events with fixed numbered steps, status, step and cumulative elapsed time, and evidence-based updates about every 60 seconds during long-running steps; resumed work keeps IDs and reports unknown timing gaps honestly.**
- [ ] **Step 4: Validate references resolve, copies (if required) match, and `inputs.sha256` passes; commit.**

### Task 7: Current-model end-to-end acceptance harness and exact-prompt trial

**Files:**
- Create/modify: isolated acceptance fixtures/harness within existing test infrastructure; no credentials or production side effects.
- Test: deterministic scenario suite for exact prompt, mismatch, partial failure/recovery, existing target, and valid release.

**Interfaces:**
- Consumes: canonical execution entry and verified contract/install interfaces.
- Produces: replayable trace and machine-checked outcome for the current model only.

- [ ] **Step 1: Build a sandbox/mock harness that exposes only the tools/actions needed for a dry-run and records every call.** It must not hold production credentials or target SSH access.
- [ ] **Step 2: Run exact prompt against valid fixture.** Assert no redundant question, no command edits, correct build/release/install sequence simulation, correct evidence gathering, and no false claims.
- [ ] **Step 3: Run mismatch and recoverable failure fixtures.** Assert the model does not guess or bypass the gate; it reports the machine-generated defect and safe resume point.
- [ ] **Step 4: Record current-model name/provider, harness revision, fixtures, trace digest, and outcomes; do not evaluate additional models.**
- [ ] **Step 4a: Assert progress trace includes fixed step IDs, status transitions, step/cumulative timing, and approximately 60-second evidence updates for simulated long steps; recovery preserves prior elapsed segments and does not invent ETA.**
- [ ] **Step 5: If isolated acceptance passes, report production end-to-end execution as a separate authorized operational task; this plan alone does not authorize it.**

### Task 8: Whole-branch review and evidence closure

**Files:**
- Review all implementation diff, tests, workflow permissions and `inputs.sha256`.
- Update: project audit ledger only with verified implementation/test evidence and outstanding production acceptance state.

**Interfaces:**
- Consumes: all task commits and current-model acceptance trace.
- Produces: reviewed branch, verified remote-main closure and honest status separating code correctness from cloud/target/media acceptance.

- [ ] **Step 1: Review the full diff against the design and each global/review constraint; fix and retest findings.**
- [ ] **Step 2: Run all relevant test groups and static checks; report existing unrelated failures separately, without claiming the full suite passed.**
- [ ] **Step 3: Inspect secrets, permissions, workflow triggers, generated package fields, and input hashes.**
- [ ] **Step 4: Follow the required task-branch commit/push/main-merge/remote-SHA/branch-cleanup closure.** Do not dispatch production workflows unless separately authorized.
- [ ] **Step 5: Record implementation evidence, sandbox acceptance result, and any unverified real build/release/install/TLS/media items in the unique knowledgebase ledger under its own required closure.**

## Completion gate

Do not claim the project is reliable or production-ready solely because unit tests pass. Report separately: contract regression prevention, package verification, recovery behavior, current-model isolated acceptance, cloud build/release evidence, actual target installation, strict TLS/API/signaling, and non-P2P media evidence. Real production deployment remains outside this implementation plan's authorization unless explicitly included by a later task request.
