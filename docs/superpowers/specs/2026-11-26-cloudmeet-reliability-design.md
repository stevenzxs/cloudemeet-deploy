# CloudMeet Build and Deployment Reliability Design

Date: 2026-11-26  
Status: Draft for user approval  
Scope: CloudMeet configuration/deployment repository and its connected build, release, first-install, upgrade, and acceptance contracts.

## Intent

Adopt Superpowers as the software-development method for CloudMeet work and make the existing build-to-deployment path reliable enough that different models, including smaller models such as DeepSeek and Cloud Haiku, can execute it without inventing steps, rewriting commands, or silently weakening gates. The recent r31 release demonstrates the class of failure to prevent: a successful joint workflow and published package coexisted with server material whose origin/TLS facts did not match the approved release contract.

The goal is not merely more prose or a new orchestrator. It is to find and close the gaps between approved contracts, configuration, build outputs, immutable release assets, install tooling, target state, and evidence.

The first operational acceptance scenario is to use the current model (no other-model evaluation in this phase) with this exact user prompt and complete it end-to-end:

> 按 CloudMeet 标准交付流程，TLS 模式 caddy-public-acme，入口 https://cloudmeet.stevenzxs.cn，执行到构建与发布，在服务器118.193.36.35 首次安装部署。

The intended endpoint includes the requested build and release, first installation on the specified server, and the applicable deployment acceptance. The agent must not ask again for values already explicit in the prompt, pause for routine choices already settled by approved policy, or express uncertainty that can be resolved by deterministic checks and code. “No pauses” does not waive approval boundaries or permit proceeding through a verified contradiction: a real defect must be caught by automated gates before side effects, with an actionable failure if it escapes.

During execution, report progress and elapsed time on a fixed cadence: show the current numbered step, status, elapsed time for that step, and cumulative task elapsed time. For long steps, provide evidence-based progress approximately every 60 seconds. On resume, preserve step identity and prior elapsed intervals; mark unknown gaps as unknown and do not invent percentages or ETAs.

## Goals

- Use Superpowers practices for future CloudMeet software work: understand the problem, agree design before implementation, write an execution plan, make changes incrementally, test before claiming completion, and verify delivered behavior.
- Make critical release/install contracts machine-readable and validate the same values across configuration, workflow inputs, build evidence, package manifests, release assets, and installer arguments.
- Fail before publication or target-side effects when a contract is inconsistent; show the conflicting fields and evidence rather than asking a model to guess.
- Give small-model execution a narrow, deterministic, documented entry point with explicit allowed actions, inputs, checkpoints, stop conditions, and recovery behavior.
- Preserve release immutability, fixed source/config SHAs and image digests, version-ledger semantics, secrets/data/CA protections, and existing approval boundaries.
- Make first install and upgrade distinguishable, idempotence/retry behavior explicit, and partial failure recoverable without destructive cleanup or rerunning initialization over existing state.
- Establish end-to-end evidence for build, package, release, target installation, TLS/API/signaling, and media acceptance as separate claims.
- Validate the exact prompt above using the current model only; defer evaluating DeepSeek, Cloud Haiku, or other models.
- Provide fixed-step progress and elapsed-time reporting, including per-step and cumulative time, with evidence-based updates about every 60 seconds for long steps.

## Non-goals

- No change to approved production TLS modes, client trust, signing identities, version allocation, release scope, or data-retention policy as part of the design itself.
- No automatic rebuilding, release publication, target installation, CA issuance, destructive cleanup, or production deployment merely because reliability work is approved.
- No replacement of all existing tooling with a new orchestration platform unless audit evidence shows the current architecture cannot enforce the required contracts.
- No claim that a successful CI run, uploaded artifact, running container, or HTTP 200 alone proves full product or media acceptance.
- No changes to other projects.

## Approaches considered

1. **Prompt/document-only hardening.** Consolidate instructions and simplify model-facing steps. This is cheap, but it leaves correctness dependent on the model noticing cross-file inconsistencies; it does not prevent another r31-class mismatch. Not sufficient as the main approach.
2. **Executable contracts and staged gates (recommended).** Audit the current workflow and tools, define one authoritative contract representation for each release, validate it at configuration freeze, build/package, joint publication, download, and pre-install boundaries, then strengthen recoverability and the model-facing entry point. This builds on the existing Actions, package, and shared install core and offers the best risk/effort balance.
3. **Replace the delivery path with a new end-to-end orchestrator/state machine.** This could provide strong control but has a large migration surface and risks introducing a second installation path before the existing gaps are understood. Keep as a possible later response only if the audit proves staged gates cannot close the gaps.

Recommended approach: 2, with evidence-based scope expansion only when needed.

## Design proposal

### 1. Evidence-first audit and failure taxonomy

Map the actual path from approved config and source SHAs through workflow dispatch, revision allocation, image/JAR/H5/client build, package assembly, joint publication, artifact download, setup, shared initialization/start, runtime checks, and acceptance records. Trace recent failures (including r31 contract mismatch, r29 missing jitsi-mgr material, and earlier first-install interruptions) to identify where a defect escaped and what verification would have caught it earlier. Classify findings by prevention layer and impact; do not assume an old ledger status describes the current target without fresh evidence.

### 2. Single release contract and consistency validation

Define a versioned, schema-validated release contract bound to the fixed configuration SHA, source identities, allocated revision/Run attempt, architecture, TLS mode, expected origin, services, image references/digests, jitsi-mgr/H5 materials, package identity, and client identities. Reuse existing authoritative config and revision sources; do not create competing editable sources. Generate evidence/manifests from the fixed contract rather than manually copying fields.

Add validations that compare the contract with actual outputs and reject missing, contradictory, or stale values at multiple boundaries:

- before expensive builds or durable allocation where possible;
- after each build and package assembly;
- before GHCR/Release publication, including server material versus approved TLS/origin and client-origin/CA contract;
- after download, against independent API asset digests and internal manifests;
- immediately before setup/first-install side effects, against explicit target parameters and observed target state.

Diagnostics must name the field, expected value/source, actual value/source, and stop point without leaking secrets. Tests must include mutation cases proving the r31-shaped mismatch is rejected.

### 3. Deterministic delivery interface for small models

Provide one concise, versioned operator entry point backed by the actual scripts. It should specify task type (preflight, first install, upgrade, acceptance), required arguments, exact command/tool, expected output, state transitions, side effects, explicit approvals, timeout/reporting behavior, and recovery command/position. The interface delegates to the shared install/update core; it does not introduce parallel product logic. Separate read-only preflight from apply. The model should select and pass declared values, not infer origin, architecture, release identity, or cleanup scope.

### 4. Target-state and recovery safety

Before install/update, record a durable task intent and establish actual target identity and state: host key, OS/architecture, engine/Compose compatibility, resources, ports, services/volumes, exact install root/project, current release identity, and existing secrets/data/certificates. A retry must resume from verified state or stop for reconciliation; it must not repeat initialization, allocate a new revision, dispatch another workflow, overwrite an existing root, or clean failed state automatically. Failures preserve logs and state, and report the last successful phase, failed action, target impact, and safe resume point.

### 5. Review and test strategy

Require code review to inspect contract producers and consumers together, not only changed files locally. Tests should be layered: schema/unit checks, package and workflow contract tests, mutation/property cases for missing/mismatched values, mocked target-state and recovery tests, then controlled real-run evidence only under separately approved operational scope. Review checklists should focus on trust boundaries, stale copies, omission paths, mismatched source/config/asset identity, retries, and negative cases. Small-model prompts are not a substitute for these gates.

### 6. Superpowers development method

For each implementation task: use brainstorming when intent/scope is ambiguous; document and approve designs before implementation; write a plan; execute in small steps with tests; review the diff; run verification before completion claims; and keep deployment/release approval separate from code-change authorization. Repository instructions must describe this workflow without conflicting with existing governance or silently changing the approved CloudMeet delivery contract.

### 7. Acceptance using the current model

Use the user's exact prompt above as a repeatable acceptance case in the existing current-model environment. No integration for other models is in scope. Capture the model's tool/action trace and compare it with the expected task contract: it should derive all already-specified values, follow the approved release/build/install route, not edit the prescribed commands, not ask redundant questions, not report success without evidence, and not silently relax any safety gate. Progress output must retain fixed step numbering and report step status, per-step elapsed time, and task cumulative elapsed time; long steps receive evidence-based updates about every 60 seconds. Exercise representative clean-start, recoverable failure, and contract-mismatch fixtures in an isolated environment before any separately authorized real production run. The failure fixtures ensure “no pauses” means no avoidable interaction, not “ignore a real defect.”

## Constraints and safety boundaries

- Knowledgebase and deploy configuration `origin/main` must be safely synchronized before reading their task-specific execution materials; preserve work and stop on unsafe sync.
- Use the configured public read-only GitHub acceleration route first for supported public assets, then official HTTPS with certificate verification if unavailable; never weaken TLS or use public proxy for APIs, private repositories, Actions, push, or GHCR.
- Keep product source, deployment configuration, and runtime data/secrets separate.
- Preserve the mandatory task-branch/main closure for repository changes; update `build-tools/inputs.sha256` for covered build material changes.
- Treat the current target as unknown until read-only verification. Prior installation/cleanup history is context, not current state.
- A first-install request does not authorize deleting preexisting data. Existing data, unrecognized resources, incompatible package contracts, or unverifiable host identity stop the affected operation.
- No production Actions, version allocation, release, CA operation, SSH mutation, install, or deployment is authorized by this design approval alone.
- The first-model acceptance scenario is restricted to the current model and the exact prompt above; evaluation of additional models is deferred.

## Confirmed interpretation

- Cross-layer contradictions are defects to prevent through stronger implementation and code review, not routine judgment calls delegated to a model. If one escapes prevention and is detected before or during an operation, the affected side effect must still be blocked and the defect reported; do not guess or proceed on one conflicting source.
- `config/client.env` remains the sole product client-origin/TLS configuration source. Explicit `expected_origin`/`expected_tls_mode` values are approval assertions, not alternative configuration sources; all server and client release evidence must be derived from and match the fixed approved contract.
- Existing task-state/recovery mechanisms are audit inputs, not presumed complete. The audit should establish what is durably persisted outside the target and extend/reuse it where sound rather than assume a new state store is required.
- Gate placement is an implementation decision based on the workflow audit, preserving current revision-allocation semantics and rejecting invalid outputs as early as reliably possible.
- The user's exact end-to-end prompt defines the first current-model acceptance case; explicit prompt values are not to be re-asked, while production approvals and actual contradictions remain enforced.
- Progress is reported at fixed numbered steps with status, per-step elapsed time, cumulative elapsed time, and evidence-based approximately 60-second updates for long-running steps; resumed runs preserve prior timing and mark unknown gaps honestly.

## Success measures

- A regression test reproducing the r31 TLS/origin mismatch fails before a release can be marked publishable.
- Release metadata, server package, client evidence, and setup inputs are automatically checked against one fixed contract; valid and invalid fixtures demonstrate both acceptance and rejection.
- A small-model operator can execute preflight and an authorized non-production exercise using the written entry point without inventing or editing commands; every phase produces machine-checkable evidence.
- Repeating or resuming a failed first-install task cannot overwrite initialized secrets/data or duplicate external side effects.
- A controlled end-to-end test shows each phase separately: source/config identity, build, package integrity, release identity, target install, strict TLS/API/signaling, and non-P2P media where the environment permits.
- Progress traces show stable step IDs, elapsed timing, approximately 60-second evidence-based updates for long steps, and honest handling of recovery/unknown intervals.
- Remaining unverified operational capabilities are explicitly listed rather than inferred from code or documentation.

## Builder decisions

The implementation owner may choose the contract encoding/validator technology consistent with the existing Python/Node toolchain, CI structure, and package format. The audit will determine exact file ownership and whether any component needs restructuring. Production operation remains separately authorized.

## Evaluation environment

The first acceptance run uses the current model in the existing OpenCode environment. No other model API or integration is to be added. Before tests that can cause side effects, build an isolated/mock evaluation harness or use an already available non-production sandbox; the implementation audit determines the least invasive option. A real production end-to-end attempt remains governed by the existing authorization contract and is not implied by this design approval.
