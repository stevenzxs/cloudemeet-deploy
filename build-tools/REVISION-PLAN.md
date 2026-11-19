# CloudMeet joint revision versions — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give seven services and two clients a shared revision, distinct display/platform versions and persistent run allocation.

**Architecture:** A pure Python version contract owns derivation. A repository-external SQLite ledger serializes allocation on a dedicated 150 runner; reusable Actions consumes one parent assignment. Existing package/build/verification entrypoints consume a bound JSON record, never infer a revision from successful releases.

**Tech Stack:** Python standard library/SQLite, Node.js, GitHub Actions, existing Gradle/Forge/WiX entrypoints.

## Approved design and boundaries

- Client baseline 1.0.21: display 1.0.21+rN, Android int('1021'+N), MSI 1.0.(21+N), PE 1.0.(21+N).0. Universal APK; no new ABI split builds.
- Server baseline requires explicit registration; 11248.0.2 was an audit example, not approved input. Component source versions/SHAs remain independent.
- Before enabling allocation, register reviewed baselines and historical Android/MSI high-water marks. Unknown history blocks release allocation; never silently substitute zero.
- Persistent ledger is outside Git and initialized explicitly, not auto-recreated after loss. SQLite BEGIN IMMEDIATE, unique run/revision identities and immutable allocation records. Same run reuses; failed/cancelled allocated runs consume N; query does not allocate.
- One allocation job precedes builds; joint server/client jobs inherit parent Run ID. Standalone builds also allocate through it. Persistent runner is a deployment prerequisite, not installed by this change.
- No product build, credential upload, publication, formal allocation or server operation is authorized here.

## Task 1: Pure version contract and allocation
1. Add `build-tools/tests/test_revision_versions.py`: r1/r2/r10/r100, overflow, identity mismatch, retry reuse, concurrent allocation, missing ledger refusal.
2. Run `python -B -m unittest discover -s build-tools/tests -p test_revision_versions.py`; observe red.
3. Add `build-tools/revision_versions.py`, `build-tools/revision_ledger.py`, explicit policy `config/version-policy.json`.
4. Run tests green. Test only temporary ledgers.

## Task 2: Consumers
1. Add client contract tests for display/MSI/PE/Android separation and required bound record.
2. Wire `core.cjs`, `build-clients.cjs`, `verify-package.cjs` to validated assignment; packaged app keeps full display identity and mapped package numeric version. Use existing Forge config via scoped wrapper, not copied product compilation logic.
3. Wire `package.sh` to record validation; OCI display version differs from safe batch/tag. Embed exact assignment in provenance and final manifest.
4. Run Node tests and Python package tests without Docker or product compilation.

## Task 3: Workflow convergence
1. Add static contract tests for manual-only entrypoints, single allocation, parent inheritance, no handwritten version fallback.
2. Add reusable allocation workflow; wire existing server/client jobs and joint top-level workflow.
3. Keep Actions references pinned and permissions bounded. Preserve same-run/attempt artifact isolation and explicit publish approval.
4. Regenerate maintained workflow template and inputs.sha256; run YAML/embedded-script syntax and hash checks.

## Task 4: Governance and handoff
1. Update `AGENTS.md` file inventory/version clauses and READMEs; document missing activation prerequisites without declaring runtime acceptance.
2. Run full auxiliary tests; preserve protected historical layout failure separately.
3. Commit scoped changes, sync remote per user request, update unique knowledgebase ledger with evidence and unverified gates.

Stop at code/tooling delivery. Runner installation, historical high-water verification, server baseline approval and real Actions execution remain separately controlled gates.

## Verification checkpoint — 2026-11-19

- Python auxiliary suite: 93/94; sole remaining failure is the pre-existing protected `output/assemble-11248.0.1.sh` inventory issue. No history deleted or test suppressed. Revision-specific suite includes controller inheritance/retry fixtures and SQLite concurrency/corruption/range guards.
- Node client tools: 30/30, including temporary asset-parent recovery and numeric/display mapping. No product build or real final-package execution performed.
- Four changed Actions workflows: actionlint 1.7.12 syntax/expression/reuse checks pass with declared custom Runner label; shellcheck/pyflakes disabled, Bash and embedded Python checked separately.
- Remaining activation gates: approved server baseline; verified historical Android/MSI upgrade floors; protected controller Runner and explicit persistent ledger initialization/backup recovery; real Actions/package/signature/upgrade verification. Policy remains disabled.
- SQLite rejects missing/corrupt local history but cannot prove an entire restored database is the newest copy. Restore requires independent Run/high-water evidence; no claim of automatic anti-rollback enforcement.
