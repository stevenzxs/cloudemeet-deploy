# CloudMeet per-batch dynamic origin design

## Intent

The full build/publish skill must build client artifacts for the HTTP(S) entry URL explicitly supplied for that batch. A stale hard-coded `SITE_DOMAIN` in repository configuration must not silently override the user's input or cause a false mismatch. This makes repeat runs predictable for different DNS names or IP-based endpoints without mutating committed configuration.

## Goals

- Accept an absolute HTTP(S) origin whose host is a DNS name, IPv4 literal, or IPv6 literal.
- Default omitted ports to 80 for HTTP and 443 for HTTPS; preserve explicit ports.
- Resolve DNS names and retain sorted unique address evidence. Keep the supplied host in the client URL; never substitute a resolved IP for a DNS name.
- Generate a per-batch client configuration from the user's origin and the fixed non-origin client settings (version, TLS mode, CA policy).
- Make TLS validation, Electron/Android configuration, Android trust generation, network audit, package verification, and publication evidence consume that same per-batch contract.
- Never rewrite the repository's canonical `config/client.env` or leak generated batch configuration into later runs.

## Non-goals

- This skill does not deploy, install, upgrade, SSH to, or perform live acceptance against a server.
- The origin URL does not authorize release publication; publication remains a separate explicit input.
- Do not relax existing certificate policy. `caddy-public-acme` remains DNS hostname + HTTPS/443 + system trust. IP origins require `private-ca` with a CA certificate whose SAN covers the IP.
- Do not alter upstream source locks, signing identity, TLS policy, or unrelated build infrastructure.

## Approaches considered

1. **Per-batch generated configuration (selected):** pass the normalized origin contract through workflow inputs/environment and create temporary client configuration in the run workspace. It avoids shared-state races and leaves committed configuration immutable.
2. Rewrite the skill's fixed config before each run: rejected because retries/concurrency can observe stale or cross-batch values, and a run can dirty its source checkout.
3. Only change the prompt and keep comparing against fixed config: rejected because it preserves the defect and downstream client artifacts still use the hard-coded origin.

## Contract and flow

1. The skill receives the user's URL and calls the skill-owned origin normalizer.
2. Normalization validates HTTP(S), host, and port; returns canonical origin, scheme, host, port, and resolved address list. DNS lookup failure stops before revision allocation.
3. The canonical origin and address evidence are passed as explicit workflow inputs. The workflow validates the TLS mode against the canonical origin before allocating a revision.
4. Each build job checks out immutable source/configuration, creates a batch-local client config from the canonical origin plus fixed version/TLS/CA fields, and builds both clients using that file. Android trust material is generated for the batch host.
5. Build audits and final package verification compare observed client settings against the same origin contract, and provenance records canonical origin plus DNS evidence.
6. The publish job verifies the same-run assignment and evidence. Completion is reported as built/published or built-only; always `NOT_DEPLOYED`.

## Constraints and implementation calls

- IPv6 URL authorities must be bracketed in the canonical origin; the host field passed to DNS/IP parsing omits brackets.
- Resolver addresses are sorted deterministically (IPv4 then IPv6, numeric order) and deduplicated.
- A literal IP is its own address evidence; no DNS lookup is needed.
- Canonical origin omits only a scheme's default port; explicit ports remain present.
- Generated config lives under a unique job/run temp path and is passed by explicit path, not exported as a mutable repository default.
- Existing workflow dispatch still requires explicit TLS mode, material commit, architecture, and publication approval boolean.

## Acceptance

- Unit tests prove domain, IPv4, IPv6, default/explicit ports, DNS evidence, and rejected malformed URLs.
- TLS tests prove the user's input is authoritative and does not have to match the repository's fixed `SITE_DOMAIN`; ACME/IP policy remains enforced.
- Client contract tests prove generated config drives Electron and Android values, Android trust host, network audit, and package verification.
- Workflow static tests prove origin validation occurs before persistent revision allocation and all build/publish jobs pass the same contract.
- Isolation tests prove skill-owned runtime code does not route through shared root build tools/config/patches.
- No real Actions run, external publication, or deployment is performed for implementation verification.
