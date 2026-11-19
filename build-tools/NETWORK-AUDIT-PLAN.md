# Network parameter audit implementation — 2026-11-19

Approved scope: seven services plus Electron and Android. No build dispatch,
registry publication, signing or server operation in this implementation task.

## 2026-11-19 approved audit convergence

### Second review follow-up (bounded implementation)

- Shared start.runtime_environment allowlists transport/tool environment, then loads
  maintained jitsi.env, effective target and exact secrets; preflight uses placeholders.
  Parent Compose/interpolation overrides are not accepted. Pin effective target hash
  across initialize/start and recheck before certificate activation.
- Direct-entry origin port must match HTTPS_PORT; gateway/JVB wildcard bindings only.
  Proxy/NAT port translation is not inferred by this direct-entry installer.
- Resolve Android compiled references using resource table and actual resource members;
  hash only the referenced CA resource, never an arbitrary APK member.
- Pending: trusted signing identity input from certificate authority repository,
  phased failure recovery, final bundle validation and complete Hermes handoff.
  Do not implement unreviewed recovery by deleting existing data or reinitializing.

Goal: preserve existing entry points while separating immutable delivery inputs
from explicit instance configuration and retaining complete audit evidence.
Architecture: setup/deploy accept an external target file; target.py provides one
validated resolver for initialization, rendering and startup. Validate before
imports or secret creation. Never edit package checksums to configure an instance.
Tech stack: Python standard library, Bash, Node.js and existing Actions workflows.

1. Add regression failures for missing/incorrect published ports and external target
   resolution. Implement exact required mapping checks and shared target resolver.
2. Forward explicit --target-env through setup/deploy; preflight before mutations,
   propagate the resolved path to child processes and retain public instance evidence.
3. Keep client preflight/source/generated/final reports in one batch directory;
   delivery copies all phases and verifies hashes.
4. Strengthen Android final-resource references without byte-string fallback as
   proof of effective trust; require tooling or fail closed.
5. Review Hermes task association/artifact verification and certificate-repository
   signing handoff separately; do not invent signing commands or authorize Secrets.
6. Run failing tests before implementation, then auxiliary suites, input hashes,
   workflow parity and diff checks. Preserve historical layout failure. Update ledger
   with actual implemented scope and remaining blockers; no cloud acceptance claim.

1. Add failing no-Docker tests for generic/target media requirements, invalid ports,
   rendered Compose consistency, secret exclusion and retained failure reports.
2. Implement a shared standard-library audit: discover network parameters and fixed
   endpoints from maintained inputs, retain file/line evidence and input hashes;
   validate derived target settings and rendered seven-service Compose.
3. Wire server build/assembly and first startup, retaining JSON/Markdown reports
   on failure and embedding package-stage reports before checksum generation.
4. Wire client preflight and temporary generated settings before native compilation;
   record final package checks and hashes in a separate audit before delivery.
5. Run auxiliary Python/Node regressions, checksum and workflow parity checks;
   document limitations and update the unique governance ledger.

Generic packages defer media identity to installation explicitly. Target startup
requires an explicit usable MEDIA_HOST. Static results never prove firewall/NAT,
STUN/TURN, TLS connectivity or actual meeting acceptance. Optional unconfigured
endpoints are reported, not invented. Only network values are logged; credentials,
URL userinfo/query and arbitrary rendered environments are never dumped.
