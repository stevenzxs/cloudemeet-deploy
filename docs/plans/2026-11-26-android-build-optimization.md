# Android Build Cache and Timing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce repeat Android build work with Gradle caching and expose actionable phase timings without weakening package verification.

**Architecture:** Configure the existing pinned `actions/setup-java` step to cache Gradle dependencies using checked-out Android Wrapper, dependency-lock, and build configuration files. Enable Gradle's task-output build cache while retaining forced packaging tasks, then record elapsed durations for Gradle execution, each final APK verification, and delivery in build evidence and step logs. Task-output cache is local to each hosted runner unless a separately verified persistence mechanism is added; dependency-cache hits must not be reported as task-output-cache hits.

**Tech Stack:** GitHub Actions, pinned setup-java action, Gradle, Node.js, node:test.

---

### Task 1: Regression coverage

**Files:**
- Modify: `build-tools/clients/tests/workflow.test.cjs`
- Modify: `build-tools/clients/tests/cli.test.cjs`

Assert Android-only Gradle cache setup is keyed from checked-out Gradle inputs and the build uses `--build-cache`. Assert explicit timing records exist for Gradle, per-package verification, and delivery, including failure-safe persistence. Preserve the existing `--rerun`, signing, and package-gate expectations.

### Task 2: Workflow cache configuration

**Files:**
- Modify: `.github/workflows/build-clients.yml`

Move the already SHA-pinned Java setup step after the pinned `jm` checkout, configure `cache: gradle` and a dependency path covering Wrapper properties, dependency lock files, settings/build scripts, and version catalogs. Report whether setup-java restored a cache. Do not add new permissions, dependencies, or build triggers.

### Task 3: Build and package phase timing

**Files:**
- Modify: `build-tools/clients/build-clients.cjs`

Use a monotonic clock to measure Gradle execution, each artifact's final verification, and delivery. Log elapsed milliseconds, retain timings in the candidate build manifest on both success and failure, and pass `--build-cache` while keeping `--rerun` packaging behavior.

### Task 4: Verification and integrity

Run focused Node tests, relevant client regression tests, workflow syntax/structure checks, `git diff --check`, and regenerate/verify `build-tools/inputs.sha256`. Do not start Actions, allocate a revision, build product artifacts, publish, or deploy.
