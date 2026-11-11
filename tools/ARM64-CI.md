# ARM64 CI checkpoint

Branch `ci/arm64-smoke`, native runner `ubuntu-24.04-arm`, manual dispatch or branch push. No registry write permissions, SSH or target changes.

1. Initial source smoke: Prosody core/native Lua/transfer plugin tests and JVB Maven verify/Java runtime. User reported first run successful.
2. Control-plane gate: build full Prosody/Jicofo/JVB from pinned sources and the pinned ARM64 lifecycle base, then start a disposable internal network without published ports. Require exactly three running containers, no OOM/restart, and two observations of at least one operational JVB in Jicofo stats. Always retain sanitized logs/result and remove only the ephemeral Compose project.

Local checks: `python3 -B -m unittest discover -s tests -p test_arm64_integration.py`, existing `test_host_control*.py`, `bash -n tools/arm64-control-build.sh`. Actual ARM64 execution happens only in Actions; local static checks do not qualify a release.

Output artifact: `arm64-control-plane-<run_id>`. `.compose.private.json` contains throwaway credentials and is deliberately excluded from artifacts and deleted during cleanup. No image publication, seven-service acceptance, host-transfer runtime acceptance, Kylin runtime installation or media acceptance is claimed by this workflow.

Next gate after a successful control-plane run: construct the other four ARM64 service images and lock the seven-service candidate, then registry publication and separately authorized Kylin acceptance. Do not substitute AMD64 application images.
