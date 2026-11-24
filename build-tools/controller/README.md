# Hosted CloudMeet revision ledger — migration and recovery

Approved replacement: GitHub-hosted `ubuntu-24.04` allocator and dedicated
`cloudmeet-revision-ledger` branch in `stevenzxs/cloudemeet-deploy`.
The old systemd unit is historical only: **do not install it, register a replacement
self-hosted runner, or resume offline runner id21**.

## Contract and implementation

`revision_git_ledger.py` retains the existing policy hash/namespace and assignment
object unchanged. `ledger.json` contains ordered allocation objects and append-only
`[run_id, attempt]` evidence. The branch contains this regular file, no workflow.
The initial four migration evidence files may remain, but their blob identities
must stay exactly as pinned at the approved anchor; other files are rejected.
Every commit since the approved migration anchor is checked for linear ancestry,
contiguous revisions, unique Run IDs, record digests, policy binding and unchanged
history prefixes. Missing branch, unknown anchor or corrupt history blocks; allocation
never initializes an empty ledger. Ordinary fast-forward pushes from the fetched tip
are compare-and-swap, never force/lease pushes. A rejected or ambiguous push re-fetches,
revalidates and recomputes; bounded retries fail closed. Output follows remote readback.
Concurrent same Run reuses its committed object; child jobs require an existing record.
Failed/cancelled runs consume once committed, including cancellation before output.

Only reusable allocator jobs get `contents: write`; caller jobs must permit nested
workflow permissions. Product checkout/build jobs retain their existing permissions.
The GitHub token is injected only into the allocation step, via an environment Git
HTTP header (masked, not URL/argv/config-file). No signing/CA Secrets are needed.
No Actions concurrency queue is used: Git CAS handles concurrency without pending-run
replacement/cancellation. Failed admission before persistence does not claim an allocation.

## Migration — authorized execution with evidence

1. Freeze **all** allocator writers, confirm no active old Run can write SQLite,
   retain old runner id21 offline. Record existing namespace/policy and independent
   Run/high-water evidence. Current supplied live history is r1–r14 at
   `/opt/data/delivery-controller/cloudmeet-version/ledger.sqlite`; never initialize,
   reset, update, delete, or allocate against it during migration.
2. Preserve a consistent SQLite backup with the SQLite backup API in a restricted
   location outside Git. `export_sqlite(path, policy)` uses a read-only transaction,
   integrity checks and validates all rows, attempts and assignments. Run it on the
   consistent backup, not a copied live WAL file. It returns data only; it does not
   create a branch, commit, push or allocate. Independently compare all 14 original
   assignment objects, Run IDs, attempts, contiguous r1–r14 and highest Run against
   authoritative evidence; never reconstruct from successful Releases/retained Runs.
3. For a missing branch, use a separately authorized orphan migration. For the
   existing 2026-11-24 branch, preserve its four files/history and append exported
   `ledger.json` in an ordinary descendant commit. Review contents/digests and
   record its full SHA. Publish only after explicit authorization and verify remote
   exact commit/tree/data. Set `CLOUDMEET_LEDGER_ANCHOR` to this independently approved
   SHA; missing variable deliberately blocks all new allocation. Record execution
   evidence separately; this document alone does not prove activation.
4. Keep independent immutable ledger branch bundles/snapshots and high-water
   evidence **for the last 7 days** (not zero backups; do not cancel existing backup
   jobs). Before activation/dispatch, record the restricted backup destination,
   verify a restore in isolation and retention behavior. Do not introduce a new
   scheduled job without a separate request. Retain migration evidence
   and original SQLite history; do not prune them merely as rolling daily backups.
   This change does not install/alter any live backup scheduler or delete backups.
5. Review/merge the allocator implementation and coordinate KB/installed instructions
   so the retired Runner setup is not executed. Pin the final material SHA. Test a
   separately authorized real Actions run only after migration and backup gates.
   With unchanged r1–r14 history the next **new** Run gets r15; reruns/children of old
   Runs remain subject to their original immutable config/source/scope identity.
   Historic fixed workflows are not rewritten; block them from old writer access.

## Recovery and residual boundaries

Do not switch back to stale SQLite after the first Git allocation. Reconcile the
newer authoritative history explicitly. Git remote loss, deleted branch, divergence,
force rewrite or old snapshot recovery requires independent recent high-water/Run
checks and approved recovery, not bootstrap/reset. The fixed migration anchor detects
rollback before migration, but cannot by itself detect a rollback to a later valid
ancestor; 7-day independent backups/high-water evidence remain required.

GitHub `contents: write` is repository-wide, not a branch-scoped capability. Client
append-only validation cannot stop an administrator or another authorized workflow
from force rewriting/deleting the remote branch. Branch rules/access policy are an
owner decision, not claimed here as installed. Fork PRs must not receive write tokens.
Real GitHub token permissions, rules, network failure/readback and end-to-end delivery
remain unverified; local bare-remote tests are not cloud acceptance.

## 2026-11-24 execution checkpoint

Canonical migration anchor: `484f7cb59010816daef2beda54d94db69e5f3764`,
ordinary child of `13f75580e4b65f87407c2285f186c44c8882326d`.
The initial four files and 14 original assignments/attempts are unchanged; the
canonical state matches a SQLite backup-API snapshot with SHA256
`40eae683f18c2f98a91ca9374276f36b4766b068b5a187a7ec21609801cf059e`.
All 14 independent GitHub Run IDs/config SHAs were checked; high-water Run is
44888921798. Anchor variable was written and read back. Old runner remains offline.
Preservation/snapshot/Run evidence is under
`/opt/data/delivery-controller/backups/closeout-20261124/`; an independent bundle
restore and state-to-SQLite comparison passed on the operator machine under
`C:/Users/ZL/AppData/Local/Temp/opencode/cloudmeet-closeout/`.
No production allocation or Actions dispatch was performed. Real hosted token
execution and subsequent delivery remain unverified. Before the next dispatch,
refresh the independent snapshot/Run high-water checks; this checkpoint must not
be treated as permanently fresh recovery evidence. Keep rolling snapshots seven
days, preserve original migration evidence, and do not add a scheduler implicitly.
