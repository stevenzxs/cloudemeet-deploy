# First Install Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained minimal skill for first-time Docker deployment of CloudMeet's eight services.

**Architecture:** Keep the skill self-contained as a procedural guide in `skills/first-install/SKILL.md`; consume the verified server delivery bundle as task input, not another skill directory. Add a repository test guarding its scope and references.

**Tech Stack:** Markdown and Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-28-first-install-design.md`

## Global Constraints
- The skill may not depend on any other directory.
- Scope is first-time Docker deployment of `web`, `app-web`, `api`, `jitsi-mgr`, `gateway`, `prosody`, `jicofo`, and `jvb`.
- Exclude build/release, version allocation, clients, upgrades, offline bundles, and live server operations.

## Review Focus
- Transitive imports/resources reaching outside the skill directory: test recursively scans local references/imports.
- First-install path accidentally invoking upgrade behavior: test/inspect command entrypoint is install-only.
- Missing required files or secrets inadvertently copied: test dependency closure and inspect copied configuration for credential values.
- Skill claims server actions are authorized implicitly: inspect explicit authorization/stop boundaries.
- The eight-service inventory drifts: assert exact service identifiers in skill docs/config.

---

### Task 1: Define and validate self-contained skill boundary

**Files:**
- Create: `skills/first-install/SKILL.md`
- Create: `skills/first-install/tests/test_skill_boundary.py`
- Test: `skills/first-install/tests/test_skill_boundary.py`

**Interfaces:**
- Produces: a discoverable skill with frontmatter `name: cloudmeet-first-install`; boundary test guarding external skill-directory references and exact eight-service scope.

- [x] **Step 1: Write failing tests** for skill presence/frontmatter, exact service identifiers, explicit first-install-only scope and no references to `skills/<other-skill>`.
- [x] **Step 2: Run** `python -m unittest discover -s skills/first-install/tests -p 'test_*.py' -v`; observed expected failure because `SKILL.md` did not exist.
- [x] **Step 3: Write** `SKILL.md` using the MSI skill structure, documenting authorization, prerequisites, workflow, verification and stop/report conditions; keep instructions self-contained and do not invoke any server.
- [x] **Step 4: Run** focused unittest command and verify it passes.
- [ ] **Step 5: Commit** only this task's files with a conventional commit.

### Task 2: Lock the minimal self-contained operating contract

**Files:**
- Modify: `skills/first-install/SKILL.md`
- Modify: `skills/first-install/tests/test_skill_boundary.py`

**Interfaces:**
- Consumes: first-install contract from Task 1.
- Produces: explicit handling of the verified server delivery bundle as input, with no execution dependency on another skills directory.

- [x] **Step 1: Extend tests** to assert the skill has no hard reference to another skill's executable files, and excludes build/release/client/upgrade/offline workflows.
- [x] **Step 2: Run** `python -m unittest discover -s skills/first-install/tests -p 'test_*.py' -v`; all checks passed after the contract was documented.
- [x] **Step 3: Document** the verified server delivery bundle as a user-supplied install input, never an implicit path into another skills directory. Scope all operations to the identified target and installation directory.
- [x] **Step 4: Run** focused tests; no server connection, image pull, or host mutation occurred.
- [ ] **Step 5: Commit** task files with a conventional commit.

### Task 3: Full verification and review

**Files:**
- Test: `skills/first-install/tests/test_skill_boundary.py`
- Test: no runtime is copied; delivery bundle is a verified user-supplied input.

- [x] **Step 1:** Run focused boundary tests; no runtime test suite applies.
- [x] **Step 2:** Run repository deployment-layout validation; it reports four missing registered entries: `deploy/config/docker-compose.yml`, `deploy/config/init.py`, `deploy/config/jitsi-base.yaml`, and `deploy/config/start.sh`. Leave unrelated files unchanged.
- [x] **Step 3:** Review scope, secrets, and cross-directory references; no deployment ran, and pre-existing user changes were left untouched.
