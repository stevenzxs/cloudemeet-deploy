# Repository-Managed Build Version Counter

## Intent

Simplify `skills/full-build-deploy` so the joint build workflow allocates each build revision directly from the deployment repository configuration, without a dedicated ledger branch, SQL ledger, or migration compatibility code.

## Goals

- Keep version state in `skills/full-build-deploy/config/version-policy.json`.
- Allocate one monotonically increasing revision for every new parent full-build-deploy run/attempt.
- Consume the revision even if the build later fails or is canceled.
- Keep server, H5, Electron, Android, and optional publication jobs on one shared assignment.
- Keep build jobs parallel after allocation.
- Handle concurrent parent runs safely without returning the same revision.
- Reduce tests to the smallest set that proves this workflow's contracts.

## Non-goals

- No GitHub Release lookup as the source of build revisions.
- No dedicated ledger branch, SQL ledger, migration tooling, or compatibility shims.
- No publication or deployment authorization changes.
- No retry of failed child jobs with mixed old attempt material.

## Current state

The skill currently depends on a separate `cloudmeet-revision-ledger` branch and a complex allocator/test matrix. That design is harder to operate than this skill needs and makes routine branch cleanup dangerous.

## Selected approach

Store `current_revision` in `version-policy.json`. During the parent allocation job, read the current value from `main`, increment it, and commit that single configuration update back to `main` before builds start. A normal non-fast-forward push conflict means another run won the race; fetch the latest `main` and retry. The workflow then emits one assignment JSON consumed by server, clients, H5, and optional publish jobs.

The allocation job checks out the immutable `material_commit` for reviewed inputs, but writes only the counter update to the latest `main`. Build jobs continue to check out the exact `material_commit`.

## Simplification rules

- The skill only needs a small amount of workflow evidence:
  - allocation happens once in the parent workflow;
  - server/client jobs inherit the same assignment;
  - publish remains opt-in;
  - the ledger branch and anchor are gone;
  - the version policy is the counter source.
- Old ledger tests and migration tests are removed rather than repaired.
- `SKILL.md` text is updated to describe this simpler allocation model.
