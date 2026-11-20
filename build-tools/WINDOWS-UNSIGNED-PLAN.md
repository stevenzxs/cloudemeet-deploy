# Windows unsigned client delivery implementation plan

Approved 2026-11-20 after explicit normal-workflow warning and separate confirmation. Android keeps its release signing identity; HTTPS CA trust stays unchanged.

## Contract

Route: plan_first. Remove Windows signing hooks, credentials, tool prerequisites and signature gates; label deliveries unsigned, not signature-passed. Preserve source SHAs, versions/rN, ABI, origin, CA, integrity and outer 35-minute timeout. No key rotation, Secrets deletion, certificate-tool changes, deployment or cancellation.

## Steps and verification

1. Add failing existing revision/workflow/delivery regressions: no Windows signing hooks/module/Secrets; unsigned metadata explicit; Android remains signature-gated.
2. Change adapter, preflight, checker, delivery and workflow. Preserve native packageAfterCopy and version mappings; remove signing postPackage, bypass retired OpenVPN postMake with identity return. Keep Android keystore injection and DER check.
3. Update project policy, CloudMeet knowledgebase contract and online Skill/checklist; register plan and refresh input hashes. Historical batch evidence stays immutable.
4. Run node --test build-tools/clients/tests/*.test.cjs, Python revision workflow regressions, input hashes and git diff --check. These do not replace product/Actions acceptance.
5. Commit/push/merge short branches; verify remote main, clean only this task's branches. Back up 150 outside repositories, synchronize fixed configuration/knowledgebase SHAs and affected installed Skill with hashes.
6. Dispatch exactly one joint amd64 Actions via 150 fixed actions.py with persistent unique intent and publish=true, origin https://118.193.36.35:8443. Record actual Run/SHA/revision. No deployment.

Stop on unexpected dirty work/conflicts, missing credentials/Runner capability or failed gates. No local product-build fallback. Current evidence/checkpoints belong in migration/STATUS.md and the unique knowledgebase register.
