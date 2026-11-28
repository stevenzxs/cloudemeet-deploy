---
name: cloudmeet-first-install
description: Use when performing a first-time Docker installation of all eight CloudMeet server services on a Linux server. Triggers on "first-time CloudMeet installation", "deploy eight services", "Docker first install". Does not cover builds, releases, clients, upgrades, or offline installation.
---

# CloudMeet First-Time Docker Installation (Eight Services)

This skill covers only the first-time Docker installation of these eight CloudMeet services on one Linux server: `web`, `app-web`, `api`, `jitsi-mgr`, `gateway`, `prosody`, `jicofo`, and `jvb`. The skill and its bundled files do not reference other repository directories. A verified, published server delivery bundle is an installation input, not a dependency on another skill directory. Stop if a complete, trusted bundle is unavailable; do not build or guess images.

## Task Boundary and Authorization

- Preflight/planning requests: inspect the host and materials read-only; do not install.
- First installation: run host-mutating commands only after the user explicitly authorizes the target host and first install.
- This skill does not authorize builds, releases, cleanup of existing deployments, deletion of data or volumes, or changes to certificate trust roots. Editing this skill is not server-operation authorization.
- Stop if CloudMeet containers, a Compose project, data directories, or uncertain data state already exist. Do not clean up and continue, and do not convert a first install into an upgrade.

## Fixed Preconditions

- The target is a user-identified Linux host with Docker Engine installed and running, and architecture matching the delivered images. This skill does not install Docker Engine or change system packages.
- The user supplies verified server delivery materials from one batch: the eight-service inventory, image digests/identities, Compose configuration, `jitsi-mgr` JAR and management frontend, and SHA256 manifest. Verification evidence must be independent of the files being checked.
- The installation origin is the user-approved HTTPS origin (full scheme, host, and port). TLS mode comes from the batch's controlled delivery contract; never infer it from a default or switch it ad hoc.
- Installation directory and secret configuration remain on the target host. Never put private keys, tokens, or passwords in this skill, the repository, chat, or delivery logs.

## First-Install Procedure

1. **Identify target and state:** Verify host identity, Linux distribution/architecture, Docker/Compose versions, disk space, firewall, and user-specified installation path. Read-only inspect containers, Compose projects, ports, and data paths. Stop on any uncertainty or existing instance.
2. **Verify delivery bundle:** Obtain the user-selected server Release assets in an isolated working directory. Verify Release batch, provenance, and independently supplied SHA256. Confirm all eight services and required `jitsi-mgr` artifacts exist, architecture matches, and images use immutable digests. Reject floating tags, digest mismatches, and mixed-batch materials.
3. **Verify configuration:** Confirm rendered Compose contains exactly the eight services, has no `build:`, and image references exactly match the verified batch. Confirm HTTPS origin, ports, domain/DNS, and approved TLS mode. Do not print credentials in terminal logs or reports.
4. **Prepare fresh instance:** Place verified materials in a confirmed-empty, user-specified directory. Following the delivery bundle instructions, create per-instance secrets and target parameters on the host; restrict secret-file permissions to the administrator. Keep newly generated CA/private keys only in the target instance's persistent directory; never overwrite existing files.
5. **Review before installation:** Show target identity, installation path, service inventory, batch, image digests, origin, TLS mode, expected ports, and planned Compose operation. Confirm backup/recovery strategy, persistent-volume locations, and rollback boundary. Obtain user approval for any high-impact change not already covered.
6. **Start services:** From the verified instance directory, use the delivery bundle's Compose files to start all eight services. Use only pinned images; do not build, pull floating tags, delete volumes, run prune, or stop/replace existing services. Preserve exit codes and non-secret logs.
7. **Verify and report:** Check Compose service state, health checks, HTTPS certificate chain/hostname/validity, Web/API and management reachability, Prosody/Jicofo signaling, and JVB media path. If no real client call and non-P2P media test was performed, mark it "not accepted"; running containers alone is not end-to-end acceptance.

## Stop and Report

- Host identity, authorization, empty first-install state, architecture, path, or backup/recovery conditions are unclear.
- Bundle provenance, batch, digest, service inventory, rendered Compose, or TLS/origin contract does not match.
- The operation would overwrite existing data/services/volumes, install Docker, change trust roots/keys, or exceed user authorization.
- Any installation, health-check, certificate, signaling, or media step fails.

On stop, report the last completed stage, exact failure, preserved evidence location, and unexecuted steps. Do not automatically clean up, retry destructive operations, or claim unverified checks passed.
