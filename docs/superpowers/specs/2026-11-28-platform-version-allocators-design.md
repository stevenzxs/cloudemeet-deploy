# Platform-specific version allocators design

## Intent

Replace the shared Android/MSI/server revision counter with three independently maintained allocators and policy files under their respective skill directories. Each platform starts at high-water mark `63`; its next allocation is `r64`. Delete the entire `full-build-deploy` skill and its joint delivery capability, not merely its version allocator. Android, MSI, and server standalone build/release workflows remain supported through their own skills.

## Goals

- Android, MSI, and server each own their allocator implementation and durable counter state.
- Concurrent allocations for the same platform remain atomic, retry safely, and reuse an assignment only for the same run/attempt.
- Separate platform revisions are carried into package versions, release tags, evidence, and validation.
- All retained build entry points use the platform-specific contract; no active workflow silently continues allocating from the former shared counter.
- Remove the full-build skill, its joint build/package/publish/deploy/acceptance workflow and tools, and active routing/docs/tests that imply this capability remains available.
- Preserve the existing approved product baselines and version formula unless a platform-specific existing contract requires otherwise.

## Non-goals

- Reconstructing or deleting external GitHub Releases or prior allocation history.
- Preserving the full-build skill's joint eight-service + H5 + dual-client delivery, deployment, or acceptance capability. These capabilities are intentionally removed by this request.
- Changing product baselines, signing identities, source pins, TLS behavior, deployment authorization, or publishing permissions.
- Modifying the knowledgebase.

## Current state and constraints

- `skills/full-build-deploy/config/version-policy.json` currently contains `current_revision: 63` and the latest allocation record. Root `config/version-policy.json` contains baseline fields but no counter.
- `.github/workflows/revision-allocation.yml` invokes `skills/full-build-deploy/tools/allocate-workflow.py`; Android/MSI/server and joint/package/client workflows reference that shared allocator.
- `build-joint.yml` currently passes one assignment to server, both clients, and joint publishing. Under this design, joint delivery is removed rather than migrated; standalone platform workflows remain.
- `single-build-deploy` is absent from the current tree, but historical design/plan documents still describe its former dependence on shared version policy. Those documents are historical records and should not be rewritten as though the deleted skill still exists; active code references must be identified separately.
- The current last recorded shared revision is 63. Per user's decision, initialize each platform's independent counter to 63; do not restart numbering or infer higher per-platform values without evidence.

## Approaches considered

1. **Three independent allocators and state files; delete full-build skill (selected).** Each retained platform skill owns its policy and allocator; standalone workflows use these. Full-build joint workflows and capability are removed. This matches the explicit deletion request but removes joint delivery and deployment support.
2. Three allocators while preserving joint builds by composing platform assignments. This retains a cross-platform delivery capability and the full-build skill's purpose, contrary to the explicit request to delete the entire skill. Rejected.
3. Delete only the old shared allocator. Rejected because the user explicitly clarified that the whole full-build skill should be deleted.

## Proposed design

- Add `skills/android-build-deploy/config/version-policy.json` and allocator code under that skill; likewise for MSI and server. Each policy owns its schema/namespace, approved baseline data required by its version derivation, `current_revision: 63`, and idempotency evidence for the last allocated run/attempt. Never copy live state between platform files after initialization.
- Add platform-specific reusable allocation workflows or equivalent skill-local workflow-call entry points. Each validates material SHA, workflow/repository identity, source pins and TLS/origin contract before allocation; atomically fetches latest `main`, checks same-run/attempt idempotency, increments only that platform's counter, commits to `main`, and retries safe push races. Missing/invalid state is fatal; no automatic bootstrap or counter reset.
- Standalone Android/MSI/server workflows call their own allocator. Remove `.github/workflows/build-joint.yml`, `build-package.yml`, `build-clients.yml`, `publish-release.yml`, the shared `revision-allocation.yml`, and other active joint-only workflow/tool/config/test files after tracing and removing callers. Do not remove generic deployment assets merely because they once shared a folder; enumerate skill-owned files and references before deletion.
- Delete `skills/full-build-deploy/` entirely after migrating any still-required platform-specific material to the corresponding standalone skill and verifying no active workflow references it. Remove active skill routing and claims of joint delivery/deployment; historical specs/plans may remain clearly historical.
- Update active docs/tests and parity checks to assert allocator isolation, correct policy ownership, cross-platform non-interference, same-run idempotency, concurrent push retry, malformed/missing state failure, and absence of full-build skill/workflow references in active paths.
- Once all consumers are gone, delete the old shared policy state rather than retaining it as an active counter. Preserve its last known value/record only in version-control history; do not use it as a live fallback.

## Recovery and compatibility

- Existing published revisions through r63 remain unchanged. Each new platform sequence begins at r64; equal revision numbers across platforms are expected and are disambiguated by platform-specific tags and assignment namespace.
- A failed/cancelled allocation consumes its platform revision. A corrected material change uses a new run/revision. A same-run/same-attempt retry returns the existing assignment only if request identity and material SHA match exactly.
- No automatic recovery from missing/corrupt policy state. Stop, preserve evidence, and require explicit reviewed recovery from authoritative Git history. Never reset a counter based only on release listing.
- Rollback is roll-forward: do not restore the deleted shared allocator or full-build workflows as a fallback. Disable allocation if a platform policy becomes invalid; recover only from that platform's authoritative Git history with explicit review. Do not reuse allocated revisions.

## Validation and release gates

- Unit tests for each allocator: initial r64, isolation, idempotency, invalid state, digest/identity validation, and concurrent updates against local bare Git remotes.
- Workflow contract tests: each standalone entry calls its matching allocator; no active workflow invokes the old shared allocator or refers to the deleted full-build skill.
- Run platform tool/workflow test suites and repository-wide relevant tests. Inspect all active references to `revision-allocation.yml`, shared `current_revision`, and `skills/full-build-deploy` before completion.
- Do not dispatch Actions, allocate a real revision, publish, or deploy as part of implementation verification.

## Open to implementation

Exact assignment JSON shape and reusable workflow topology may be chosen during planning, provided they preserve the invariants above and do not introduce a shared revision fallback. The user has explicitly selected deletion of the entire full-build skill; the intentional loss of joint deployment/acceptance is part of scope.
