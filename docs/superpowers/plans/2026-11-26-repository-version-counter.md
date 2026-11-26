# Repository-Managed Version Counter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify `skills/full-build-deploy` version allocation to a repository-managed counter and remove the old ledger machinery.

**Architecture:** The parent joint workflow increments `current_revision` in `skills/full-build-deploy/config/version-policy.json` on `main` before builds start. Server and client jobs inherit the single assignment and build in parallel from the reviewed `material_commit`.

**Tech Stack:** GitHub Actions reusable workflows, Python 3, Git normal fast-forward pushes, existing unittest suite.

**Spec:** `docs/superpowers/specs/2026-11-26-repository-version-counter-design.md`

## Global Constraints

- Every new parent full-build-deploy run/attempt consumes one revision.
- Failed or canceled builds never roll back the counter.
- Concurrent parent runs must receive distinct revisions.
- Server and clients inherit one assignment and build in parallel.
- Publication remains opt-in; no deployment behavior changes.
- Keep tests minimal and focused on the workflow contracts that matter.

## Review Focus

- Concurrent allocation push conflicts: loser must refetch and retry instead of reusing the same revision.
- Ambiguous push failure: same run/attempt must be idempotent if the commit actually landed.
- Counter initialization: start from the recovered revision 33, not from version baseline math.
- Workflow inheritance: reusable server/client workflows must not allocate independently.
- Digest manifest: governed file hashes must match the final simplified files.

---

## File Structure

- Modify `skills/full-build-deploy/config/version-policy.json`: add `current_revision`.
- Modify `skills/full-build-deploy/tools/allocate-workflow.py`: allocate from repository counter only.
- Add `skills/full-build-deploy/tools/repository_counter.py`: fetch latest `main`, increment counter, commit, push, retry on conflict, reuse same run/attempt if found.
- Modify `.github/workflows/revision-allocation.yml`: remove ledger inputs/env and call the simplified allocator.
- Modify `.github/workflows/build-joint.yml`: keep a single parent allocation and parallel server/client jobs.
- Modify `skills/full-build-deploy/SKILL.md`: document the simplified allocation model.
- Modify `skills/full-build-deploy/inputs.sha256`: refresh governed file hashes.
- Add focused tests for counter allocation and workflow contract; remove ledger-era tests.

## Task 1: Replace allocation implementation

**Files:**
- `skills/full-build-deploy/tools/repository_counter.py`
- `skills/full-build-deploy/tools/allocate-workflow.py`
- `skills/full-build-deploy/config/version-policy.json`

- [ ] Write focused failing tests for sequential allocation, same run/attempt idempotency, and concurrent push retry.
- [ ] Implement `repository_counter.py` with fetch/increment/commit/push/retry.
- [ ] Update `allocate-workflow.py` to emit the same assignment JSON shape while using the repository counter.
- [ ] Run focused tests and fix only failures caused by this task.

## Task 2: Simplify workflow contract and skill docs

**Files:**
- `.github/workflows/revision-allocation.yml`
- `.github/workflows/build-joint.yml`
- `skills/full-build-deploy/SKILL.md`
- workflow contract tests

- [ ] Remove ledger branch/anchor references from workflow and tests.
- [ ] Assert parent workflow allocates once and server/client jobs inherit one assignment.
- [ ] Update `SKILL.md` version-allocation wording to match the simplified model.
- [ ] Run workflow contract tests.

## Task 3: Remove ledger machinery and refresh governed digests

**Files:**
- `skills/full-build-deploy/tools/revision_git_ledger.py`
- `skills/full-build-deploy/tools/revision_ledger.py`
- related tests
- `skills/full-build-deploy/inputs.sha256`

- [ ] Remove ledger implementation and obsolete tests.
- [ ] Refresh `inputs.sha256` for changed governed files.
- [ ] Run the reduced Python and workflow test set.

## Task 4: Final verification

- [ ] Run the reduced relevant Python tests.
- [ ] Run client Node tests used by this skill.
- [ ] Inspect diff for remaining ledger references in the active full-build-deploy path.
- [ ] Commit the simplified branch, merge into `main`, and delete the feature branch after review.
