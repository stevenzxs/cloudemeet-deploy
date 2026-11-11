# ARM64 CI checkpoint

Branch `ci/arm64-smoke`, native runner `ubuntu-24.04-arm`, manual dispatch or branch push. No registry write permissions, SSH or target changes.

1. Initial source smoke: Prosody core/native Lua/transfer plugin tests and JVB Maven verify/Java runtime. User reported first run successful.
2. Control-plane gate: build full Prosody/Jicofo/JVB from pinned sources and the pinned ARM64 lifecycle base, then start a disposable internal network without published ports. Require exactly three running containers, no OOM/restart, and two observations of at least one operational JVB in Jicofo stats. Always retain sanitized logs/result and remove only the ephemeral Compose project.

Local checks: `python3 -B -m unittest discover -s tests -p test_arm64_integration.py`, existing `test_host_control*.py`, `bash -n tools/arm64-control-build.sh`. Actual ARM64 execution happens only in Actions; local static checks do not qualify a release.

Output artifact: `arm64-control-plane-<run_id>`. `.compose.private.json` contains throwaway credentials and is deliberately excluded from artifacts and deleted during cleanup. No image publication, seven-service acceptance, host-transfer runtime acceptance, Kylin runtime installation or media acceptance is claimed by this workflow.

Next gate after a successful control-plane run: construct the other four ARM64 service images and lock the seven-service candidate, then registry publication and separately authorized Kylin acceptance. Do not substitute AMD64 application images.

## Seven-service candidate retention (2026-11-11)

Web build resource diagnostics: `web-builder.json` retains before/after host memory, VM OOM counters, CPU count, filtered kernel OOM records (or explicit probe-unavailable status), and an allowlisted Docker exit/OOM state. `web-cgroup-before.txt` and `web-cgroup-after.txt` retain available cgroup v2 memory events/peak/limits. The build command, source env/locks and compression settings are unchanged. The named ephemeral builder is inspected before removal; a killed child can set cgroup OOM counters even when Docker's parent-process OOM flag is false. Missing counters do not establish absence of OOM.

The workflow now builds four additional services in native ARM64 matrix jobs and retains three control-plane images after the existing bridge gate. The older standalone source smoke script remains available but is no longer duplicated in the candidate workflow.

Source identities are in `arm64-candidate-sources.json`; see the approved [implementation plan](../docs/plans/2026-11-11-arm64-candidates.md). Business Web keeps checked-in `.env` and lockfile unchanged (actual pinned configuration is `same-origin`, not an overridden address). Go/Maven/npm builders execute tests. Runtime images use source-built application payloads and published dependency/base images, not prebuilt application images.

Image artifacts `arm64-image-<service>-<run_id>` and `arm64-images-control-plane-<run_id>` contain gzip Docker save archives, per-service source/image/platform/hash JSON and checksum files, retained for **7 days**. Evidence artifacts are retained for 14 days. Download into a new `deploy/history/arm64-ci/` batch before expiry, validate every size/hash and require all seven service records before claiming seven candidates retained. Docker image IDs are not registry manifest digests. No registry write permissions are granted.

Per-service smoke covers static/SPA/default lifecycle, native SQLite write/read across fresh containers on a throwaway volume, and source Caddy HTTP/modules. It does not qualify seven-service TLS/API/BOSH/WS/roles/host-transfer integration, Kylin, offline installation, media or production security. API smoke data lives only in a new disposable volume, never in image bytes or uploaded evidence; runtime logs are not uploaded by four-service jobs. Only explicit evidence extensions are uploaded; the private control-plane Compose file remains excluded.
