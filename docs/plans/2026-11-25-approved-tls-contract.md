# Approved TLS contract implementation plan

Goal: reject a batch whose fixed configuration or final materials differ from the user's approved TLS mode/origin, before allocation and before publication.

Architecture: config/client.env remains the only product configuration source. Required expected_tls_mode/expected_origin workflow inputs express approval, never override configuration. A shared Python validator checks configuration and final evidence. Legacy published material remains immutable. Existing-instance mode changes remain explicitly blocked until separately reviewed migration tooling exists; this task does not deploy or provide an unsafe migration bypass.

1. Add failing unit tests for missing approval, wrong mode/origin, duplicate configuration, public/private CA boundaries and mismatched final evidence.
2. Implement build-tools/tls_contract.py; wire all top-level and reusable allocation paths before persistent allocation; propagate approval to joint publication and check both clients/server before publishing.
3. Include approved/actual TLS identity and NOT_DEPLOYED warning in release evidence, notes and Actions summary.
4. Update project rules/Skill and knowledgebase approval/evidence. Regenerate inputs.sha256, run auxiliary tests and workflow structure validation; no product builds, allocation, dispatch, publication or target access.
5. Commit/push/merge and verify both repositories' remote main; remove only this task's merged branches.

Acceptance: public approval against private config fails before allocator; internally consistent private artifacts cannot satisfy public approval; absent approval fails closed; matching public/private batches pass policy checks. Live ACME issuance/renewal and migration are not established by these tests.
