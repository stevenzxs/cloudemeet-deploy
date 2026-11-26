# CloudMeet Full Build/Publish Isolated Toolchain Implementation Plan

> **For agentic workers:** Execute this plan task by task on `feat/full-build-deploy-isolated-toolchain`. Preserve the user's requested endpoint: build and publish only; do not deploy.

**Goal:** Make the full CloudMeet build-and-publish skill self-contained under its own directory, collect and normalize the user-provided HTTP(S) origin, resolve its hostname to IP evidence, and leave GitHub-required workflow files as thin repository entry points.

**Architecture:** Copy the complete build/publish dependency closure into `skills/full-build-deploy/` under dedicated `scripts/`, `tools/`, `config/`, `patches/`, `docker/`, `runtime/`, and `tests/` subdirectories. Keep GitHub-discovered YAML files under `.github/workflows/`, but make them invoke only skill-owned implementation files. The skill-owned source of truth is separate from existing `build-tools/`; do not mutate or route through the latter. Track skill-owned inputs with a skill-local SHA256 manifest and include all new workflow and skill-owned inputs in the repository's existing build integrity manifest.

**Tech Stack:** GitHub Actions YAML, Python 3, Bash, Node.js, existing CloudMeet build scripts and tests.

**Spec:** User-approved scheme 2 in conversation: each skill has its own scripts and tools directory; this skill builds and publishes only; user supplies HTTP(S) entry address; default ports are 80/443; resolve hostname to IP; do not ask for first-install/upgrade/media IP; no actual Actions run or publication during this implementation.

**Dynamic-origin design:** `docs/superpowers/specs/2026-11-26-cloudmeet-dynamic-origin-design.md`. The user's per-batch origin is authoritative and must not be matched against or written into the committed `config/client.env`.

## Global Constraints

- Keep the task on the feature branch and preserve existing main history and unrelated worktrees.
- Do not overwrite or delete files outside this task's declared scope.
- `build-joint.yml` must build eight services, H5, Electron, and Android as one assigned batch.
- `publish_images` remains false by default; implementation verification must not dispatch a real workflow.
- Build/publish skill ends at publication evidence and always reports `NOT_DEPLOYED`.
- The workflow-dispatch `expected_origin` must be normalized from the user URL and validated against fixed `config/client.env`; resolved IP evidence must not replace the domain origin.
- The workflow-dispatch `expected_origin` is the authoritative per-batch origin; generate temporary client configuration from it and immutable non-origin settings. Never require it to equal the committed `config/client.env` origin or mutate that file.
- DNS name, IPv4, and IPv6 origins are supported subject to existing TLS policy. `caddy-public-acme` requires DNS HTTPS/443; IP origins require private CA trust with a matching SAN.
- Skill-owned implementation must not import, invoke, or read `build-tools/`, root `config/`, or root `patches/` at runtime.
- Any changed build input must have its digest updated in the relevant integrity manifests.

## Review Focus

1. URL without a scheme, malformed URL, credentials, path/query/fragment, invalid port, IPv6 literal, IDN, and DNS failure: reject or normalize deterministically, never silently change host.
2. DNS returning multiple IPv4/IPv6 addresses: retain sorted unique address evidence while preserving the hostname in the canonical origin.
3. Workflow provenance: reject a build whose normalized origin or DNS evidence differs from the approved dispatch contract.
4. Source/tool closure: prove no active package/client/release workflow command references root `build-tools/`, root `config/`, or root `patches/`.
5. Integrity manifest: verify all skill-owned tracked build inputs and ensure user-provided address evidence is not written to secret-bearing logs.

---

### Task 1: Add user-origin normalization and DNS resolution

**Files:**
- Create: `skills/full-build-deploy/tools/origin_contract.py`
- Create: `skills/full-build-deploy/tests/test_origin_contract.py`
- Test: `skills/full-build-deploy/tests/test_origin_contract.py`

**Interfaces:**
- Produces `normalize_origin(value: str) -> dict` with canonical `origin`, `scheme`, `host`, `port`, and sorted unique `addresses` fields.
- DNS lookup is injectable for deterministic tests; production default uses the platform resolver.

- [ ] Write tests for HTTPS/HTTP default ports, explicit port preservation, malformed/non-origin inputs, and multi-address DNS results.
- [ ] Add tests for IPv4 and IPv6 literals, IPv6 bracketed authority, and deterministic literal-IP evidence.
- [ ] Run the tests and confirm expected failures because the module is absent.
- [ ] Implement the smallest parser/resolver that accepts only absolute HTTP(S) origins with hostname or IP literal, no credentials/path/query/fragment, valid port, and deterministic address ordering.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Create the skill-owned dependency closure

**Files:**
- Create: `skills/full-build-deploy/scripts/package.sh` and required build scripts
- Create: `skills/full-build-deploy/tools/` copies of required Python/Node build, version, client, H5, audit, and publication modules
- Create: `skills/full-build-deploy/config/`, `patches/`, `docker/`, `runtime/`, `templates/`, `tests/`, `sources.json`, and skill-local `inputs.sha256`
- Test: skill-owned copies of current relevant Python and Node tests

**Interfaces:**
- Build and publication scripts resolve all paths relative to the skill root (or an explicit repository root), not the root shared `build-tools/`, `config/`, or `patches/` paths.
- Original main-tree shared files remain untouched.

- [ ] Determine the transitive runtime/test closure from actual imports and path references; copy only files needed for full service/H5/client build, provenance, package assembly, and joint publish (including runtime materials embedded in released packages).
- [ ] Add a closure test that scans active skill-owned scripts and rejects references to shared root build/config/patch paths.
- [ ] Run closure test before adapting paths and record expected failure.
- [ ] Adapt copied code to skill-root paths and ensure produced package contents and provenance retain the expected relative names.
- [ ] Run copied build/client/release unit tests without invoking Docker or external deployment.
- [ ] Add a skill-local manifest and verify its listed files against SHA256.

### Task 3: Make TLS and client builds consume the per-batch origin

**Files:**
- Modify: `skills/full-build-deploy/tools/tls_contract.py`
- Modify: `skills/full-build-deploy/tools/clients/core.cjs`
- Modify: `skills/full-build-deploy/tools/clients/build-clients.cjs`
- Modify: `skills/full-build-deploy/tools/clients/ca-config.cjs`
- Modify: `skills/full-build-deploy/tools/clients/network-audit.cjs`
- Modify: `skills/full-build-deploy/tools/clients/verify-package.cjs`
- Test: skill-owned TLS and client contract tests

**Interfaces:**
- TLS validation accepts `EXPECTED_ORIGIN` as the source of SITE_DOMAIN/SITE_SCHEME/SITE_PORT for the current batch; fixed config remains source only for TLS mode, client version, CA policy, and other non-origin values.
- Client builder accepts an explicit generated `--env-file` path and uses that file for every client and audit operation.

- [ ] Add failing tests for origin differing from fixed config, IP origins by TLS mode, explicit port, and hostname preservation.
- [ ] Run those tests and confirm the current fixed-config equality check fails the dynamic-origin case.
- [ ] Implement origin-derived effective config and preserve ACME DNS/HTTPS/443 and private-CA requirements.
- [ ] Add failing client tests proving effective env values propagate to Android trust and network audit.
- [ ] Implement the per-batch env-file interface and verify focused tests pass.

### Task 4: Convert GitHub workflow files into skill-specific entry points

**Files:**
- Modify: `.github/workflows/build-joint.yml`
- Modify: `.github/workflows/build-package.yml`
- Modify: `.github/workflows/build-clients.yml`
- Modify: `.github/workflows/publish-release.yml`
- Modify: `.github/workflows/revision-allocation.yml`
- Test: `skills/full-build-deploy/tests/test_workflow_isolation.py`

**Interfaces:**
- Dispatch continues to accept approved TLS mode, user origin, material commit, architecture, and explicit publication boolean.
- All invoked scripts/tests run under `skills/full-build-deploy/`; no workflow step executes root `build-tools/*`.

- [ ] Write workflow isolation tests asserting default no-publication, correct skill-owned command paths, origin contract gate before revision allocation, and no deploy step.
- [ ] Run and confirm failures against current workflows.
- [ ] Update workflows to checkout/build/test/release from the skill-owned closure; preserve concurrency, permissions, provenance, and same-run/attempt guarantees.
- [ ] Run workflow static tests and YAML parsing/lint available in repository.

### Task 5: Wire skill prompt, evidence, and integrity manifests

**Files:**
- Modify: `skills/full-build-deploy/SKILL.md`
- Modify: `skills/full-build-deploy/inputs.sha256`
- Modify: `build-tools/inputs.sha256`
- Modify: installed copy `C:/Users/ZL/.config/opencode/skills/cloudmeet-full-build-deploy/SKILL.md` only after source is final
- Test: skill metadata and input-contract checks

**Interfaces:**
- Skill asks for only an HTTP(S) entry URL when not supplied; normalizes omitted ports to 80/443, resolves DNS, displays canonical origin and address set, and passes that exact contract to workflow inputs.
- Skill has no first-install, upgrade, media IP, SSH, deployment, or server acceptance stage.

- [ ] Add prompt/contract tests for missing URL, URL port defaults, resolved-IP reporting, and build/publish-only endpoint.
- [ ] Update skill prose and local tool usage to match the implemented interface.
- [ ] Regenerate/check both local and repository integrity manifests without changing unrelated manifest entries.
- [ ] Copy finalized skill to the OpenCode user installation and verify byte hash equality.

### Task 6: Verify and close out

**Files:** all task files above.

- [ ] Run skill-local unit tests, closure tests, workflow static checks, local manifest verification, repository manifest verification for changed entries, `git diff --check`, and secret scan for the task diff.
- [ ] Confirm there was no GitHub workflow dispatch, GHCR/Release publication, SSH, or server operation.
- [ ] Review diff and report any unsupported/unverified runtime boundary rather than claiming end-to-end build success.
- [ ] Commit the completed change on this task branch; merge to main and delete the task branch only after the user-facing review/approval and project merge requirements are satisfied.
