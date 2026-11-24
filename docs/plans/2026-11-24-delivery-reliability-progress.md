# CloudMeet Delivery Reliability and Conversation Progress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the approved CloudMeet flow resumable across sessions and supported targets, with numbered steps, factual status and elapsed time visible in the originating conversation.

**Architecture:** Converge existing Actions, delivery routing and public installation helpers behind one persisted task runner; do not create another installer or revision counter. Hermes is an adapter for requests and progress delivery, not the owner of installation semantics. Private task state is execution evidence; the revision branch allocates versions and the knowledgebase remains the sole governance ledger.

**Tech Stack:** Existing Python stdlib helpers, GitHub Actions/API, Docker Compose and Hermes native message facilities, selected only after inspecting their actual interface. Linux/WSL auxiliary unittest; no product build or Docker invocation in this maintenance stage.

---

## Approval, boundary and current evidence

- 2026-11-24: user approved the stability analysis, requested numbered/status/timed output in the conversation, and separately answered “是” after the normal-flow-change warning. Includes implementation/auxiliary verification, not new dispatch, revision allocation, publication, production installation, 150 synchronization/restart or cron creation.
- Config baseline 137187acefe421f6c2bfba2bca896c7549bd6147; knowledgebase baseline a8cfa30d3b061d7df22fb0cc629d2a057849bda4. Product sources, published r16 bytes/digests, CA and signing stay unchanged.
- `actions.py` persists dispatch intent but requires caller-supplied Run ID and hardcodes amd64. `delivery-route.py` only plans. `online_update.py` has target lock/backup/rollback but no durable end-to-end stage reconciliation. `test_online_update.py` covers seven helper cases, not interrupted update execution.
- r16 final apply took about four minutes; earlier stalls included cron/sudo mismatch, stale H5 credential, downloads, temporary wrapper path assumptions and Docker identity semantics. Do not infer measured overall success rate or guarantee a fixed install duration from one run.
- Existing Hermes `linux/delivery_task.py` belongs to Hermes delivery, is not a general CloudMeet controller. Do not copy or alter its product contract to make a second CloudMeet task store.

## Public status contract and state ownership

Task records live outside repos under an explicitly selected restricted state root; no token/env/private key in public events. Record immutable task request/scope/endpoint/instance and tool/source/config identities, plan digest, stable step IDs and numbers, run/attempt/artifact/digest references, ordered events, attempts and notification receipts. No machine-specific runtime state in Git.

Persist intent before side effects; reconcile remote facts after uncertain outcome. A task record never by itself proves a remote operation completed. Fixed step IDs survive retries; total plan is fixed once side effects begin. Adding scope requires explicit new plan/authorization, not silently renumbering.

States: pending/running/succeeded/failed/blocked/waiting_approval/not_applicable/cancelled; expose recovery/rollback activity and final restoration separately. A successful rollback is not a successful upgrade. Build, publish, deployment basics and requested business acceptance have separate completion fields; none auto-substitute for another.

Timing: monotonic duration within process, persisted UTC boundaries and committed intervals. Keep attempt and step totals, execution versus waiting, wall-clock task total, and parallel overlap. Across crashes unknown intervals remain unknown; historical records are not assigned invented duration. No percentage/ETA unless backed by a real denominator/model.

Example original-conversation payload:
```text
[04/08][执行中] 拉取并验证七服务镜像
目标：118｜批次：r16｜task_id：<task>
本步已耗时：01分20秒｜任务累计：03分15秒
进度：4/7个服务镜像已验证
```
Failure adds safe cause, attempt, current-service impact, next action and resume position. Begin/end/state changes notify promptly; long-step heartbeat about 60s, coalesce noisy events. Only delivered receipts mean sent; terminal stdout and skill installation do not prove delivery. Store pending/outcome-unknown notifications, reconcile acknowledgement before retransmission where supported; if native transport lacks deduplication, document at-least-once/unknown limitations rather than promise exactly-once delivery.

## Task 1: Failing contracts for task events and timing

**Files:** `build-tools/delivery_state.py`, `build-tools/tests/test_delivery_state.py`.

1. Write failing stdlib unittests for immutable plan, stable step IDs, attempt retention, valid transitions, private permissions and concurrent-writer refusal. Add injected clock fixtures for waiting/execution, parallel intervals, backwards wall clock and restart unknown gaps.
2. Run `python3 -B -m unittest discover -s build-tools/tests -p test_delivery_state.py`; verify failure is missing implementation, not unavailable platform tooling.
3. Implement append/replay events plus derived snapshot in one state owner; use native advisory lock on Linux, atomic snapshot, flush/fsync and corruption checks. Reject ambiguous/incomplete records instead of initializing over them. Define event-first crash recovery and lock release on process death.
4. Repeat tests to green. Add actual subprocess interruption fixtures using only temporary local files, no Docker/SSH.
5. Register new maintained paths in AGENTS, update controlled inputs and commit task with diff/secret checks. Do not merge a claim of full runner readiness.

## Task 2: Instance description and preflight contract

**Files:** planned `build-tools/instance_profile.py`, `build-tools/tests/test_instance_profile.py`; existing `build-tools/delivery-route.py`, `delivery-target.py`, `tests/test_standard_flow.py`, `tests/test_delivery_contract.py`.

1. Red tests for fresh versus existing instance, explicit architecture/origin/SSH identity/root/project/ordered Compose/target-env/public CA refs, missing privilege capability and unsupported image-store semantics. Persist only non-secret parameters or restricted refs.
2. Verify old behavior fails new cases before implementing normalization/capability reporting. No 118 alias/path defaults for another target; never auto-trust host keys or enable sudo.
3. Reuse target and route validators. Preflight gathers all safely discoverable blockers once; it does not allocate or mutate target. Existing batch deployment skips build-only secrets/version infrastructure that it does not consume.
4. Green tests using fake OS/SSH/Docker providers. State the actually supported matrix, unknown platforms fail explicitly. Commit with inputs and registration.

## Task 3: One download owner and deterministic Actions reconciliation

**Files:** `build-tools/actions.py`, `tests/test_actions.py`; planned `build-tools/delivery_fetch.py`, `tests/test_delivery_fetch.py`; `.github/workflows/build-joint.yml` only if a reviewed correlation input is necessary.

1. Red tests for one output-file writer, trusted digest, bounded Range resumption, bad TLS/hash refusal, proxy public-only/no credentials, disk-full and remote request accepted but client timed out.
2. Reuse current dispatch intent and approved accelerator/fallback rule. Persist selection before download; verify asset ID/size/range before resume and final hash before promotion. No rebuild/allocation for a download failure.
3. Bind task to a uniquely identifiable Run using actual API/workflow capabilities. If multiple matching Runs exist, block for reconciliation, never auto-redispatch. Architecture must come from immutable task rather than hardcoded amd64.
4. Mock network/API tests green; do not trigger GitHub Actions. Commit; workflow change, if needed, must retain reviewed permissions and fixed source contract.

## Task 4: Converged task CLI, not another installer

**Files:** planned `build-tools/delivery.py`, `tests/test_delivery_runner.py`; `actions.py`, `delivery-route.py`, `delivery_state.py`.

1. Red tests for create/plan/status/run/resume/cancel semantics, fixed task scope, two controller processes, dispatch uncertainty and skipped build on published-batch deployment.
2. Expose a single task-facing CLI invoking existing helpers. Adapters own IO; state owner owns events. Persist intent/outcome/evidence before advancing. Cancel must distinguish controller stop from stopping Actions or target apply; do not falsely claim downstream cancellation.
3. Resume reconciles actual GitHub and target state; unknown state blocks. Operator can query while work runs without starting a second operation.
4. Green fake-adapter tests and subprocess crash recovery. Commit with no production action.

## Task 5: Stage-aware existing target updater

**Files:** `build-tools/offline-runtime/online_update.py`, `image_transport.py`, `deploy.py`, `tests/test_online_update.py`, `tests/test_delivery_contract.py`; planned `tests/test_update_recovery.py`.

1. Red tests exercise the real orchestration with fake command/HTTP/filesystem adapters: partial pulls, post-backup crash, Compose failure, partial switch, H5 failure, rollback failure, process killed before result persistence and second apply after success.
2. Add state/event hooks to existing public core; never duplicate its install, backup, CA, idle or image identity logic. Recheck target/config facts under lock before mutation, not only before slow pull. Preserve old data/CA and backups.
3. Add current-deployment receipt atomically after verified success, separate from immutable original candidate and historical project name. If switched but receipt absent, reconcile actual seven images/H5 before resuming, do not assume success or rollback blindly.
4. Keep explicit offline authorization and no-network target contract. Cover containerd/config/manifest distinctions in the paths actually used; unsupported cases fail clearly.
5. Green integration-style auxiliary tests; no live Docker/install. Commit, then schedule supported-target validation only under separate environment authorization.

## Task 6: Conversation rendering and native Hermes adapter

**Files:** planned `build-tools/delivery_progress.py`, `tests/test_delivery_progress.py`, `build-tools/hermes_progress.py`, `tests/test_hermes_progress.py`; online Skill and checklist. Actual Hermes product/config changes require separate repository inspection and branch.

1. Inspect native Hermes message routing/streaming/notification API and actual channel acknowledgement. Do not guess endpoints or infer that CLI stdout reaches the user.
2. Red tests for start/status/error/heartbeat rendering, duration/unknown display, secret-safe fields, original conversation ID routing, callback failure, duplicate/outcome-unknown acknowledgement, persisted delivery cursor and restart replay.
3. Renderer consumes persisted state only. Adapter sends native notifications, coalesces per-task heartbeat near 60s and records receipts. No new cron/service by default. If no safe asynchronous delivery capability exists, implement truthful query/active-session output and explicitly block the autonomous-push acceptance claim.
4. Green mock-channel tests; real conversation delivery/permission tests separately authorized. Commit without 150 installation/restart.

## Task 7: Hermes upgrade survival and capability report

**Files (hermes-config, inspect actual applicable instructions first):** `linux/upgrade-offline.sh`, `test_upgrade_offline.py`, `controller_preflight.py`, `test_controller_preflight.py`, `instances/150-approvals.md`; planned scoped `linux/cloudmeet_capabilities.py`, `linux/test_cloudmeet_capabilities.py` only if existing preflight cannot be safely reused.

1. Test ordered complete Compose provenance rather than arbitrary glob order, persistence refs and retained config, tool/SSH/GitHub/approval checks and notification capability. Do not extend Hermes-product repo allowlist to CloudMeet by accident.
2. Separate Hermes health from CloudMeet capability result. Do not run privileged deployment just to test readiness; report semantics not yet proved by safe read-only probe.
3. Green fake-container/config tests. Preserve existing approval scope; no broad approval auto-repair, dependency installs, CA/keystore changes or 150 mutation.
4. Commit only in its own latest-main task branch; register knowledgebase evidence after actual checks. Real upgrade survival remains unverified until authorized exercise.

## Task 8: Verification, governance and rollout

**Files:** `AGENTS.md`, `build-tools/inputs.sha256`, `build-tools/migration/STATUS.md`, online Skill/checklist, `D:/knowledgebase/audits/project-register.md`.

1. Run targeted red/green at every task. After convergence, Linux/WSL `python3 -B -m unittest discover -s build-tools/tests -p 'test_*.py'`; root layout check and migration governance test. No product build, no local Docker.
2. Verify all controlled inputs, mirrored workflows where changed, diff and finite secret checks. Scope tests to actual changes; do not run Linux fixtures natively on Windows or expand into dependency/CVE cleanup.
3. Latest-main branch workflow: push task, merge main, read remote full SHA, clean only this task branch and retain clean worktree detached if needed. Record code/config paired SHA and honest results in the sole ledger.
4. Distinct later gates: tool implementation, 150 fixed-SHA installation, real originating-conversation notifications, supported new-target install, same-target upgrade, interrupted task/Hermes restart recovery, client and non-P2P media. Do not claim any from auxiliary test count.

## Execution order and acceptance targets

Tasks 1–6 first, then targeted Hermes integration (7), closeout (8). Same session can execute serially, no automatic agent delegation required. Every task has a tested checkpoint; avoid long-lived unmerged changes. Existing r16 remains running and untouched.

Measure real task outcomes and per-stage execution/waiting durations before promising a success-rate/latency target. Required behaviors: no duplicate side effects after uncertain outcome, early consolidated blockers, stable step IDs and retained attempts after restart, visibly delivered factual progress, and no live-install code edits when switching among supported targets.

## Current implementation status

Task 1 implemented with 19 focused Linux/WSL tests (initial 10 missing-feature failures observed before implementation; added restart-between-steps, malformed-input, attempt-outcome, post-completion timing and task-ID-binding failures then fixed). Private numbered atomic event files, hash-chain/replay plus replaceable snapshot, advisory lock, fixed plan/identity/step IDs, evidence-required retry, attempt timing/outcome/UTC boundaries and unknown restart intervals are local foundations only. A real child exits via os._exit with committed active state; new owner acquires lock and blocks pending reconciliation. Read-only status uses committed events, not live inferred elapsed time. This foundational API does not yet persist Run/artifact/notification receipts or recovery/rollback activity; those belong to the subsequent runner and adapter tasks below, not a claim of full Task 1–8 completion.

No network, Actions, Docker, target mutation or native message channel invoked. New foundational modules named in later tasks do not exist merely because planned. Full task runner, automatic timed progress, real Hermes push and cross-environment recovery remain **待实现/待核验**. Baseline updater tests 7/7; final full auxiliary validation, doc checks and branch closure recorded in the knowledgebase. Journal digests detect inconsistent local data, are not signatures or independent rollback protection. Immutable event state is intentionally private and not a public log sink; public renderer/notification receipts remain Task 6.
