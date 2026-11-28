# Platform-Specific Version Allocators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Android, MSI, and server independent persistent revision allocators starting at high-water r63, and delete the entire `full-build-deploy` skill and its joint-delivery capability.

**Architecture:** Each standalone skill owns its version policy, allocator implementation, allocation workflow, and allocator tests. Each allocator atomically commits only its own policy update to `main`, with same-run/attempt idempotency and safe push-race retries. Remove the shared/joint workflow stack and all full-build-owned files once retained standalone paths no longer reference them.

**Tech Stack:** GitHub Actions reusable workflows, Python 3 standard library, Git CLI, Node.js tests for existing client tools, Python `unittest` repository suites.

**Spec:** `docs/superpowers/specs/2026-11-28-platform-version-allocators-design.md`

## Global Constraints

- Each platform policy starts with `current_revision: 63`; first new allocation for each platform is r64.
- A failed or cancelled allocation consumes its platform revision; no counter reuse or automatic bootstrap/reset.
- Same run/attempt reuses an assignment only when its request identity and material SHA match exactly.
- Missing/corrupt state is fatal; recovery requires explicit review of authoritative Git history.
- Do not change approved product baselines, version formulas, source pins, signing identities, TLS behavior, publishing permissions, or deployment authorization.
- Do not dispatch Actions, allocate real revisions, publish, or deploy during implementation verification.
- Delete all of `skills/full-build-deploy/`; preserve historical design/plan docs as historical records, but remove active operational instructions pointing to it.
- Do not modify `D:\knowledgebase`.

## Review Focus

- Two concurrent allocations for the same platform must not allocate the same revision: test using local bare Git remote races in each allocator's suite.
- Two platforms may independently allocate the same numerical revision without modifying each other's policy: test cross-platform policy isolation.
- Repeated identical run/attempt must return the exact same assignment, while changed material/request identity must fail: test idempotency and conflict rejection.
- Missing, malformed, or regressed policy state must not be silently recreated or reset: test fatal errors before any write.
- No active workflow, routing description, test, or operator README may retain a runtime path to the deleted full-build skill: final repository-wide active-reference scan.

---

## File Map

- `skills/android-build-deploy/config/version-policy.json`: Android baseline, namespace, `current_revision`, last allocation evidence.
- `skills/android-build-deploy/tools/versioning/`: Android-only derivation and repository-counter implementation.
- `skills/android-build-deploy/.github/workflows/revision-allocation.yml` (or skill-owned reusable workflow under repository `.github/workflows/` if GitHub discovery requires it): Android-only allocation entry.
- `skills/android-build-deploy/tests/test_version_allocator.py`, `tests/test_android_workflow.py`: Android allocation and dispatch contract.
- Equivalent `config/version-policy.json`, `tools/versioning/`, allocation workflow, and tests under `skills/msi-build-deploy/` and `skills/server-build-deploy/`.
- `.github/workflows/build-android.yml`, `build-msi.yml`, `build-server.yml`: call matching allocator and pass matching assignment into their build/publish jobs.
- `.github/workflows/build-clients.yml`: remove if only used by the deleted joint flow; standalone clients already have their own workflows.
- `.github/workflows/build-joint.yml`, `build-package.yml`, `publish-release.yml`, `revision-allocation.yml`: delete after confirming no retained caller.
- `skills/android-build-deploy/tests/test_tool_parity.py`, `skills/msi-build-deploy/tests/test_tool_parity.py`: remove maintenance-source comparison to full-build; replace with isolated inventory/ownership checks.
- `skills/*-build-deploy/SKILL.md`, client `tools/clients/README.md`: update full-build/shared-counter routing and paths.
- `tools/check-deployment-layout.py`, `README.md`, active agent/skill routing files: remove references to deleted full-build runtime or route to the corresponding standalone skill where applicable.
- `skills/full-build-deploy/`: delete entire tree after callers are removed and required standalone code/config already exists in standalone skills.
- `config/version-policy.json`: assess and remove only if it is solely stale shared-version state; do not delete unrelated config.

## Task 1: Establish Android allocator contract and tests

**Files:**
- Create: `skills/android-build-deploy/config/version-policy.json`
- Create: `skills/android-build-deploy/tools/versioning/revision_versions.py`
- Create: `skills/android-build-deploy/tools/versioning/repository_counter.py`
- Test: `skills/android-build-deploy/tests/test_version_allocator.py`

**Interfaces:**
- `revision_versions.derive(policy: dict, revision: int) -> dict` returns the existing assignment version fields for Android, retaining the approved Android version formula.
- `repository_counter.allocate(policy_path: Path, request: dict, *, attempt: int, remote: str | None = None, retries: int = 8) -> dict` returns an assignment with namespace, request, versions, and digest.

- [ ] **Step 1: Add failing Android policy and derivation tests** asserting baseline fields, `current_revision == 63`, revision 64 output equals the established Android formula, and malformed revision/policy is rejected.
- [ ] **Step 2: Run the focused tests and confirm failure** with `python -B -m unittest skills.android-build-deploy.tests.test_version_allocator -v` (adjust invocation to repository's import layout if required; expected failures are missing module/behavior).
- [ ] **Step 3: Implement Android-only derivation and policy** using the approved baseline fields and a distinct namespace such as `cloudmeet-android-v1`; do not include MSI/server counters.
- [ ] **Step 4: Add allocator tests** for r64, same-run idempotency, request mismatch rejection, missing/corrupt state failure, and local bare-remote concurrent push retry.
- [ ] **Step 5: Implement `repository_counter.allocate`** by following the current safe Git fetch/commit/push retry pattern, scoped exclusively to the Android policy path.
- [ ] **Step 6: Run Android allocator tests and confirm pass.**
- [ ] **Step 7: Commit** `feat(android): add isolated revision allocator`.

## Task 2: Add MSI and server allocators

**Files:**
- Create: `skills/msi-build-deploy/config/version-policy.json`
- Create: `skills/msi-build-deploy/tools/versioning/revision_versions.py`
- Create: `skills/msi-build-deploy/tools/versioning/repository_counter.py`
- Create: `skills/msi-build-deploy/tests/test_version_allocator.py`
- Create: `skills/server-build-deploy/config/version-policy.json`
- Create: `skills/server-build-deploy/tools/versioning/revision_versions.py`
- Create: `skills/server-build-deploy/tools/versioning/repository_counter.py`
- Create: `skills/server-build-deploy/tests/test_version_allocator.py`

**Interfaces:** Same public signatures as Task 1; implementations and policy paths are skill-local, not imports from Android or each other.

- [ ] **Step 1: Add failing MSI/server derivation tests** asserting each platform's baseline and revision-64 version outputs match existing formulas and namespaces differ.
- [ ] **Step 2: Run focused tests and confirm failure.**
- [ ] **Step 3: Implement MSI and server policies and derivation modules** with `current_revision: 63`, their approved platform-specific fields, and no shared counter fields.
- [ ] **Step 4: Add allocator isolation/idempotency/corrupt-state/concurrency tests** for both skills using local bare Git remotes.
- [ ] **Step 5: Implement each skill-local allocator**; ensure it can modify only its own policy file in a generated commit.
- [ ] **Step 6: Run all three platform allocator suites and confirm independent test histories permit equal numeric r64.**
- [ ] **Step 7: Commit** `feat: add isolated MSI and server revision allocators`.

## Task 3: Wire standalone workflows to platform allocators

**Files:**
- Create: platform-specific allocation reusable workflow files under each skill or `.github/workflows/` (choose GitHub-valid location; do not recreate a shared allocator).
- Modify: `.github/workflows/build-android.yml`
- Modify: `.github/workflows/build-msi.yml`
- Modify: `.github/workflows/build-server.yml`
- Test: `skills/android-build-deploy/tests/test_android_workflow.py`
- Test: `skills/msi-build-deploy/tests/test_msi_workflow.py`
- Test: `skills/server-build-deploy/tests/test_server_workflow.py`
- Create/modify: per-platform allocation workflow contract tests.

**Interfaces:** Each allocator workflow accepts the existing material SHA, TLS mode, origin, and (server) architecture context; outputs its platform assignment and validated origin contract. Assignment JSON remains consumable by the existing corresponding package builder.

- [ ] **Step 1: Update workflow tests to require the corresponding skill-local allocator and policy path; assert each standalone build/publish uses only that workflow's assignment.**
- [ ] **Step 2: Run the three workflow tests and confirm failure against shared `revision-allocation.yml`.**
- [ ] **Step 3: Add three platform-specific allocation workflow entry points** that validate material identity and origin/TLS contract before allocation, then call only the matching allocator.
- [ ] **Step 4: Update each standalone workflow's `version` job** to use its platform-specific allocation workflow; retain current dispatch inputs, artifact contracts, publish authorization, and output evidence.
- [ ] **Step 5: Add tests proving Android/MSI/server allocation workflow paths and scopes cannot cross-call another platform's policy.**
- [ ] **Step 6: Run all three workflow suites and relevant client tool tests.**
- [ ] **Step 7: Commit** `refactor(workflows): allocate standalone platform revisions independently`.

## Task 4: Remove joint/full-build workflow callers and refresh active routing

**Files:**
- Delete: `.github/workflows/build-joint.yml`
- Delete: `.github/workflows/build-package.yml`
- Delete: `.github/workflows/build-clients.yml`
- Delete: `.github/workflows/publish-release.yml`
- Delete: `.github/workflows/revision-allocation.yml`
- Modify: `.github/workflows/build-single.yml` only if it remains active and points to removed capability; otherwise remove only after tracing its purpose and callers.
- Modify: `README.md`
- Modify: `tools/check-deployment-layout.py`
- Modify: standalone `SKILL.md` and client `tools/clients/README.md` files.
- Modify/delete: tests outside `skills/full-build-deploy/` that assert full-build maintenance-source parity or joint entry points.

- [ ] **Step 1: Add/adjust active routing tests** to assert standalone Android/MSI/server routes and absence of joint/full-build capability claims in maintained operator docs.
- [ ] **Step 2: Run routing tests and confirm existing full-build references fail the new contract.**
- [ ] **Step 3: Remove joint-only workflows after confirming no remaining retained `uses:` or dispatch caller.**
- [ ] **Step 4: Update Android/MSI/server skill descriptions and workflow documentation** to state independent revision policy ownership; remove obsolete references to shared counter, `full-build-deploy`, and missing `single-build-deploy` paths.
- [ ] **Step 5: Update client tool READMEs** to use their own skill directories; replace parity tests that compare to full-build source with checks that client tools/config are self-contained and inventory-consistent.
- [ ] **Step 6: Update `README.md` and layout checker** so no active instructions or required runtime paths point to full-build; remove unsupported joint/deploy claims without disturbing unrelated repository docs.
- [ ] **Step 7: Run standalone workflow/routing tests and `python -B tools/check-deployment-layout.py`.**
- [ ] **Step 8: Commit** `refactor: retire joint full-build workflow entry points`.

## Task 5: Delete full-build skill and obsolete shared state

**Files:**
- Delete: entire `skills/full-build-deploy/` tree.
- Delete: root `config/version-policy.json` only if inspection proves it is exclusively an obsolete shared version policy; otherwise retain unrelated fields and remove only obsolete version fields.
- Modify: repository-level active manifests/checks that enumerate skill files, if present.
- Test: repository-wide active-reference guard.

- [ ] **Step 1: Add a repository-level guard test** scanning active workflows, skills, README/operator instructions, and layout-check inputs for runtime references to `skills/full-build-deploy` or shared `revision-allocation.yml`; exempt clearly historical documents under `docs/superpowers/{specs,plans}` with no current operational instruction.
- [ ] **Step 2: Run the guard and record all remaining active references; classify each as required migration or historical-only.**
- [ ] **Step 3: Delete `skills/full-build-deploy/` in its entirety** only after confirming all required standalone tools/configs and workflows exist and no active reader remains.
- [ ] **Step 4: Remove obsolete root shared counter/policy state** only after checking all its fields and readers; preserve unrelated approved configuration if the file is not version-only.
- [ ] **Step 5: Keep historical specs/plans intact** but add a short historical/superseded notice only where a document could reasonably be mistaken for current operating instructions; do not bulk-rewrite history.
- [ ] **Step 6: Run active-reference guard; require zero active full-build runtime/workflow references.**
- [ ] **Step 7: Commit** `refactor: remove full-build-deploy skill and shared revision state`.

## Task 6: Full verification and final review

**Files:** No intended source changes; fix only failures within approved scope.

- [ ] **Step 1: Run Android allocator, Android workflow, and Android client-tool tests.**
- [ ] **Step 2: Run MSI allocator, MSI workflow, and MSI client-tool tests.**
- [ ] **Step 3: Run server allocator and server workflow tests.**
- [ ] **Step 4: Run repository-wide Python tests that remain after full-build deletion** and YAML/workflow syntax validation available in the repository.
- [ ] **Step 5: Run `python -B tools/check-deployment-layout.py` and the active-reference guard.**
- [ ] **Step 6: Inspect `git diff --check`, full diff, deleted-file list, and all three policy JSON documents; verify each starts at 63, allocator namespaces differ, and no real Actions/publish/deploy was run.**
- [ ] **Step 7: Commit any verification-only fixes separately and report exact commands/results, removed full-build capabilities, and remaining historical references.**

## Plan Self-Review

- Spec goals covered: platform-owned state and code (Tasks 1–2); safe concurrent/idempotent allocation (Tasks 1–2); workflow wiring (Task 3); intentional removal of joint/full-build capability (Tasks 4–5); compatibility and recovery constraints (Global Constraints and tests); verification/no live dispatch (Task 6).
- Main risk: many full-build files serve deployment/package flows and may have non-workflow references. Task 4 and Task 5 require reference tracing before deletion; do not use broad recursive removal until exact tracked scope is reviewed.
- Historical docs are preserved because they document past decisions; active instructions and machine-consumed references are removed or retargeted.
