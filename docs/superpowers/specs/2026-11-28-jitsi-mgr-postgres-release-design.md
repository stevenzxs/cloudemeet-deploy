# jitsi-mgr PostgreSQL Release Configuration

## Intent

Make a fresh server release start `jitsi-mgr` with the PostgreSQL database its pinned `prod` profile requires. The r67 Compose file currently selects `prod` while setting an H2 URL; the app's prod profile supplies the PostgreSQL driver and dialect, so startup fails.

## Goals

- Add PostgreSQL as a persistent infrastructure service to the release Compose bundle.
- Configure `jitsi-mgr` to use PostgreSQL with a unique required password, explicit PostgreSQL URL/driver/dialect, and database readiness dependency.
- Keep the eight CloudMeet application image inventory/build matrix unchanged.
- Pin PostgreSQL to an immutable image digest and validate that property in tests.
- Commit and merge the fix to `main`, push, clean up the feature branch, then build and publish a new amd64 server Release.

## Non-goals

- Do not update/restart the current server deployment in this task.
- Do not alter the `jitsi-mgr` upstream source or image matrix.
- Do not clean up existing server files, containers, or volumes.
- Do not change TLS/origin: use `caddy-public-acme` and `https://cloudmeet.stevenzxs.cn` for the release.

## Approaches

1. **Add PostgreSQL as release infrastructure (approved).** Add a digest-pinned PostgreSQL service with persistent storage and health check; wire `jitsi-mgr` to it using a required random password. This matches the pinned production profile and migrations.
2. Change the application production profile and migrations to support H2. Rejected because it expands application-source scope and changes the existing production database contract.
3. Force H2 driver/dialect at deployment. Rejected because PostgreSQL-only migration syntax remains incompatible and masks the source mismatch.

## Constraints and calls

- The eight named application services and digest identities in `images.json` remain unchanged; PostgreSQL is an infrastructure service, not a ninth application image.
- PostgreSQL image identity must use an immutable digest; select an official supported version and record the exact digest in the release Compose template.
- Database credentials must have no insecure default and must not be printed; generate/store them in the target `.env` with mode `0600`.
- Use a named persistent volume for PostgreSQL data, a health check, and `depends_on` health gating for `jitsi-mgr`.
- Add regression assertions for both the nine-service runtime Compose shape and the unchanged eight-image release inventory.
- Preserve branch governance: feature branch, tested commit, merge to `main`, push, and branch cleanup.
- Build and publish only after `main` contains the fix. This authorization does not include server deployment.

## Open implementation detail

Verify a stable official PostgreSQL image digest and existing release workflow validation points before coding. Keep the chosen PostgreSQL major version explicit and compatible with the migrations.
