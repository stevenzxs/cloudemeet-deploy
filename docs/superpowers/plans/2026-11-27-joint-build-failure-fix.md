# Joint Build Failure Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed package configuration source mismatch and retry Maven HTTP 616 failures without changing dependency origin policy.

**Architecture:** The package assembler reads `jitsi-mgr.env` from repository-level `config/`, leaving the skill-config allowlist unchanged. The Maven router treats HTTP 616 as a transient same-origin response, using existing bounded retries and fallback rules. The un-reproduced Gradle DSL error remains untouched.

**Tech Stack:** Bash-embedded Python packaging, Python `urllib` Maven proxy, Python `unittest`, Gradle 8.14 for an isolated local repro only.

**Spec:** `docs/superpowers/specs/2026-11-27-joint-build-failure-fix-design.md`

## Global Constraints

- Work on branch `fix/r49-joint-build-failures` in `D:\code\jitsi\deploy`.
- Do not add `jitsi-mgr.env` to `skills/full-build-deploy/config/` or weaken its allowlist.
- Only a Tencent HTTP 404 may fall back to Maven Central; HTTP 616 must retry Tencent only.
- Do not modify `jm/android/build.gradle` based on the currently un-reproduced error.
- Do not commit, push, dispatch, publish, deploy, or reuse Run 45936635245 artifacts.
- Report Windows-only/unrelated suite failures; no full-suite green claim unless all tests pass in a compatible environment.

## Review Focus

- HTTP 616 succeeds on bounded retry without changing origin — test same-origin retry and success.
- HTTP 616 exhaustion fails closed without Central fallback — test all attempts stay on Tencent.
- Repository config exists while skill config excludes private deployment material — test assembler path and preserve allowlist.
- Fixture path resolution differs from production checkout layout — exercise synthetic packaging fixture if Windows UTF-8 constraints allow.
- Gradle sources-JAR task configuration differs by plugin/context — keep DSL unchanged and record local repro result; remote verification remains pending.

---

### Task 1: Fix repository-level manager configuration source

**Files:**
- Modify: `skills/full-build-deploy/scripts/package.sh` at the embedded package assembler config reads/copy.
- Modify: `skills/full-build-deploy/tests/test_config_allowlist.py`.
- Modify: `skills/full-build-deploy/tests/test_package.py` synthetic fixture.

**Interfaces:**
- Consumes repository root `config/jitsi-mgr.env` and existing `SKILL_ROOT`.
- Produces package-root `jitsi-mgr.env` and derives manager runtime settings from the same source.

- [x] **Step 1: Write/check regression assertion** that the assembler resolves manager configuration from repository-level `config/` and does not refer to `skill_root/config/jitsi-mgr.env`.
- [x] **Step 2: Run the focused allowlist test** and confirm it fails against the pre-fix path. Evidence: earlier focused run failed with expected `AssertionError` because the package script referenced the skill config path.
- [x] **Step 3: Change the embedded assembler** to resolve repository root from the known `SKILL_ROOT` layout, read/copy `config/jitsi-mgr.env`, and keep all allowlist contents unchanged. Adapt the synthetic fixture to model both repository and skill configuration roots.
- [x] **Step 4: Run the allowlist test and focused synthetic package test**; `PYTHONUTF8=1 python -m unittest test_config_allowlist test_maven_route test_package.PackageTests.test_assembly_python_contract_with_synthetic_materials test_package.PackageTests.test_amd64_assembly_python_contract` passed (24 tests).

### Task 2: Retry Maven HTTP 616 on the same origin

**Files:**
- Modify: `skills/full-build-deploy/tools/maven-route.py`.
- Modify: `skills/full-build-deploy/tests/test_maven_route.py`.

**Interfaces:**
- Preserve `fetch_artifact(relative, opener, audit)` interface and existing three-attempt/backoff behavior.
- Add 616 to transient HTTP status handling only; do not change fallback predicate.

- [x] **Step 1: Add tests** for a 616 then success (all requests to Tencent, expected bounded backoff/audit actions) and for exhausted 616 (three Tencent requests, final failure, no Central request).
- [x] **Step 2: Run Maven route tests** and confirm the new 616 cases fail before implementation. Evidence: earlier run showed HTTP 616 raised immediately and only one request was made.
- [x] **Step 3: Add 616 to the existing transient HTTP status allowlist** without altering the Tencent-404-only fallback rule.
- [x] **Step 4: Run the complete Maven route test module** and verify it passes: 19/19 passed in the route module; combined route/allowlist command passed 22 tests.

### Task 3: Local integrated verification and status

**Files:**
- Review changes in the files above; no additional production files planned.

**Interfaces:**
- No new interfaces.

- [x] **Step 1: Run focused package-config, Maven-route, and synthetic assembly tests** from `skills/full-build-deploy/tests`: 24/24 passed.
- [x] **Step 2: Run repository suite where practical**; initial Windows run: 246 tests, 2 failures, 26 errors, 2 skipped. Root causes fixed/handled: Python bytecode polluted verified package fixtures; POSIX-only state-lock tests ran on Windows; two stale assertions referenced a skill absent from this repository; Windows cannot provide POSIX file-mode bits; deployment tests assumed `/etc/os-release` and `geteuid`; certificate generation required native OpenSSL. Final Windows run: 244 tests, 0 failures/errors, 24 skipped. POSIX-only delivery-state semantics and unavailable external/platform prerequisites remain skipped rather than deleted.
- [x] **Step 3: Run `git diff --check` and inspect branch/status/diff**; confirm no `jm` DSL edit and no workflow dispatch occurred.
- [x] **Step 4: Report remaining uncertainty**: remote Maven 616 source and `jitsiAndroidSourcesJar` failure are not confirmed fixed without an authorized new Android run and full diagnostic artifact.
