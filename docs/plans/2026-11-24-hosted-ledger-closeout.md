# Hosted ledger closeout implementation plan

Scope: finish the previously approved hosted Runner/Git ledger migration. Preserve
all pending work, original SQLite, r1–r14 records, current ledger history and secrets.
No new production revision, Actions dispatch, build, publication or 118 change.

1. Preserve existing implementation/KB bundles and uncommitted patches on 150 and
   an independent machine; start from current origin/main and reuse reviewed code.
2. Reproduce push-timeout and migration-format regressions. Reconcile ambiguous
   commits by bounded fetch; preserve the initial four migration files byte-for-byte
   and add canonical ledger.json in a normal descendant commit. Pin that anchor.
3. Verify SQLite consistent snapshot against all allocation/attempt objects and
   independent GitHub Run identities; confirm no old writer is active. Read back
   remote tree/state and variable. Restore a bundle on an independent machine.
4. Run revision/full auxiliary tests, workflow permission/trigger and hash checks.
   Merge/push config and KB to main, verify remote SHAs and clean task branches.
5. Back up then fast-forward the clean 150 delivery checkout; preserve dirty old
   worktrees. Sync installed Skill/checklist and verify file hashes/discovery.
   Report cloud execution and active-conversation loading separately as unverified.

Governance: GOV-02/03/04/05 configuration boundaries and evidence only; existing
release/target acceptance gaps remain. Retain seven-day independent snapshots and
high-water evidence; no new scheduler or unrelated backup cleanup.
