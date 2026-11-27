# Joint Build Failure Fix Design

## Intent

Make the failed CloudMeet joint build's required service-package and Android client stages more resilient without weakening dependency-origin controls or changing unverified Gradle behavior.

## Goals

- Read `jitsi-mgr.env` from the repository-level deployment configuration and include it in the assembled package, without adding it to the skill configuration allowlist.
- Retry Maven HTTP 616 responses up to three attempts against the same Tencent mirror, with the existing bounded backoff; only a Tencent 404 may fall back to Maven Central.
- Do not modify `jitsiAndroidSourcesJar`: the task succeeds locally, so its remote failure is not yet root-caused.
- Keep actions read-only outside local code/test changes: do not run, publish, or deploy a GitHub workflow.

## Non-goals

- Do not broaden repository fallback for 616 or add a new dependency origin.
- Do not claim the complete Android workflow is fixed until a new authorized build verifies it and captures the Gradle problem report/stacktrace if needed.
- Do not reuse failed Run 45936635245 artifacts or its consumed revision.

## Approaches

- **A (selected):** Fix the confirmed package config path and add bounded same-origin 616 retry; leave the un-reproduced Gradle DSL untouched. This addresses proven defects while preserving repository policy.
- **B:** Also qualify the `android` DSL access in the sources Jar task. Rejected because the exact task succeeds in the current checkout under Gradle 8.14 and the failed run provides no stacktrace proving a DSL bug.
- **C:** Route 616 to Maven Central. Rejected because it weakens the established origin/fallback contract without knowing who generated 616.

## Constraints

- Work on branch `fix/r49-joint-build-failures` in `D:\code\jitsi\deploy`.
- Run local tests only; do not commit, push, dispatch workflow, publish or deploy.
- Report unrelated Windows-only failures honestly; do not call the full suite green.

## Verification

Run targeted Maven route and package configuration tests. Run synthetic package assembly tests if the Windows fixture can be made to use explicit UTF-8 without changing production behavior. Preserve the separate status that the complete Android remote build remains unverified.
