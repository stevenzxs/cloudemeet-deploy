# Online Material Origin Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate online client deployment metadata from the validated origin/TLS contract for the current build run rather than requiring dynamic fields in `config/client.env`.

**Architecture:** `build-package.yml` already writes `needs.version.outputs.origin_contract` to the package job environment, and `package.sh` embeds the same contract at `provenance/origin-contract.json`. Pass that provenance file explicitly to `online-material.py`; the generator validates it and builds the client origin/TLS fields from it, retaining only static client settings such as CA filename and client version from `client.env`.

**Tech Stack:** Python 3 standard library, Bash, GitHub Actions YAML, unittest.

**Spec:** `docs/superpowers/specs/2026-11-27-online-material-origin-contract-design.md`

## Global Constraints

- Do not use implicit defaults for missing, invalid, or conflicting origin/TLS inputs.
- Keep dynamic deployment parameters out of static `config/client.env`.
- Do not trigger a new build/release Run or deploy; version `11248.0.1+r54` is consumed and must not be reused.
- Follow repository branch workflow: create a modification branch, commit there, merge into `main`, then delete the modification branch.
- Knowledgebase references `standards/project-delivery.md` and `audits/project-register.md` were not present in `D:\knowledgebase`; do not modify knowledgebase files.

## Review Focus

- Missing origin contract must fail clearly rather than falling back to `client.env`; pin this in the missing-contract regression test.
- Contract origin/TLS mismatch or malformed origin must fail before archive creation; pin using certificate policy validation tests.
- Public ACME must not inherit a private CA filename from static config; pin this in the public-mode assembly test.
- Private-CA mode must continue to require and hash exactly the configured public CA; preserve and run existing private-CA assembly coverage.
- Port normalization must preserve explicit non-default HTTPS ports while omitting `:443`; pin both cases in origin derivation tests.

---

### Task 1: Pass the packaged, approved origin contract into online assembly

**Files:**
- Modify: `skills/full-build-deploy/scripts/package.sh:579`
- Test: `skills/full-build-deploy/tests/test_delivery_contract.py`
- Test: `skills/full-build-deploy/tests/test_workflow_isolation.py`

**Interfaces:**
- Consumes: generated package provenance file `output/provenance/origin-contract.json`.
- Produces: `online-material.py --origin-contract <path>` invocation, with no contract read from ambient process configuration.

- [ ] **Step 1: Write a failing workflow/command contract test** asserting the assembly invocation passes `output/provenance/origin-contract.json` to `online-material.py`.
- [ ] **Step 2: Run the focused test and verify it fails** because the current invocation has only `--source` and `--destination`.
- [ ] **Step 3: Add the explicit `--origin-contract` argument** to `package.sh` using the provenance file written earlier in the same assembly.
- [ ] **Step 4: Run the focused test and verify it passes.**

### Task 2: Build online client metadata from the supplied contract

**Files:**
- Modify: `skills/full-build-deploy/tools/online-material.py:58-90`
- Test: `skills/full-build-deploy/tests/test_delivery_contract.py:167-198`

**Interfaces:**
- Consumes: `assemble(source: Path, destination: Path, origin_contract_path: Path)` and `--origin-contract` CLI argument.
- Produces: `candidate.json` with `client_origin` and `tls_mode` bound to validated `origin_contract`; static `client.env` contributes only `CLIENT_CA_FILE` and other non-target client settings.

- [ ] **Step 1: Update the assembly fixture test first** to use a `client.env` without `SITE_PORT`, `SITE_SCHEME`, `SITE_DOMAIN`, or `TLS_MODE`, supply a contract, and assert origin/TLS metadata in the generated candidate.
- [ ] **Step 2: Run that test and verify the expected failure** is missing contract argument/unsupported assembly interface, not fixture setup.
- [ ] **Step 3: Implement strict contract loading and validation**: require `origin` and supported `tls_mode`; derive the CA filename only for private-CA mode; reject a configured private CA in public-ACME mode; retain `certificate.require_mode` checks and the existing SHA-256 CA calculation.
- [ ] **Step 4: Add focused validation cases** for missing contract, invalid TLS mode/origin, public ACME with no private CA, and HTTPS port normalization (`443` omitted; non-default port retained).
- [ ] **Step 5: Run focused tests and verify all pass**, including existing archive integrity and private-CA tests.

### Task 3: Verify regression suite and commit the fix

**Files:**
- Verify: `skills/full-build-deploy/tests/`
- Include: design, plan, workflow/package/test changes from Tasks 1–2.

- [ ] **Step 1: Run the full full-build-deploy Python test suite** with the repository's existing test command; record all pass/fail counts.
- [ ] **Step 2: Review the diff** for unrelated edits, generated files, accidental changes to `client.env`, or invocation paths that bypass contract validation.
- [ ] **Step 3: Commit on the modification branch** with a message describing the origin-contract binding fix.
- [ ] **Step 4: Merge the modification branch into `main`, push `main`, and delete the modification branch** only after tests pass and the diff is verified.

## Self-review against spec

- Contract sourcing and strict failure behavior: Tasks 1–2.
- Dynamic fields removed from the static-config dependency: Task 2 regression fixture and implementation.
- Regression coverage for successful assembly, invalid/missing contract, CA modes, and port normalization: Task 2.
- Test suite and repository branch delivery: Task 3.
- No build/release/deployment authorization: Global Constraints.
