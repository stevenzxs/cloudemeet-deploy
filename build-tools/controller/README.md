# Restricted CloudMeet version controller

Operational replacement of the offline runner; same approved allocation policy,
namespace and append-only history. Not a new revision counter or product builder.

Install the reviewed unit on 150 only after preparing a fresh
`/opt/cloudmeet-version-controller` owned by an unprivileged `cloudmeet-runner`
account with no sudo/docker group membership. Runner registration is repository
scoped to stevenzxs/cloudemeet-deploy. Preserve the old registration files and
ledger; remove only the explicitly approved old GitHub runner ID 21 after the new
registration is verified. Do not resume the old listener.

Download the GitHub-reported runner archive with TLS and verify its independently
queried SHA256 before extraction. Registration tokens are short lived; send via
standard input over verified SSH, never commit or print them. Keep registration
credentials mode 0600. Install unit root-owned; enable after sandbox verification.

Under no concurrent allocation, SQLite backup API copies the old database to the
new `ledger/ledger.sqlite` and a root-only independent `/var/backups/cloudmeet-version`
snapshot. Verify SQLite integrity, identity, all allocation digests, contiguous
revisions and highest Run against GitHub. Compare an isolated restored copy, not
the live file. Save snapshot SHA256, source policy identity and Run/revision list.
The unit cannot access the root-only backups, Hermes data or Docker socket.

Only then change CLOUDMEET_VERSION_LEDGER to
`/opt/cloudmeet-version-controller/ledger/ledger.sqlite`. Never initialize an empty
database or reuse consumed revisions. Existing workflow main/manual checks remain;
the sandbox is an additional OS boundary, not a claim that labels enforce trust.

Rollback before new allocation: stop the new service, restore the previous GitHub
variable and retain both copies for review. After new allocation, never switch to
the stale copy; preserve the authoritative newer history and reconcile explicitly.
Backup restoration after a loss must check independent high-water/Run evidence;
a snapshot's existence does not prove freshness. This replacement does not claim
future per-allocation backup automation or product delivery acceptance.
