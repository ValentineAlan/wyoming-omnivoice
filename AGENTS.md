# Change and release requirements

The owner requires GitHub changelog entries to flow into the TrueNAS update emails.
Apply these requirements to every future change in this repository.

- Record meaningful user-visible changes, fixes, configuration/compatibility changes,
  and validation in `CHANGELOG.md` in the same change as the implementation.
- Runtime code/dependency changes must increment the application's `APP_VERSION`
  or `VERSION` constant and have an exact `## <version>` changelog heading. Keep
  released version sections immutable; do not reuse a version for different code.
- Keep `app-release.json` at the same version. Docker images embed it so all
  services, including helpers, can be associated with their release notes.
- Put documentation-only and operational changes under `## Unreleased` until they
  belong to a release. Separate TrueNAS package updates from application releases.
- Use clear prose about observed behavior. Do not claim a deployment or test passed
  unless it was verified. Do not reconstruct unknown historical release details.
- Publish versioned container tags and retain the exact image digest. Supply OCI
  source, version, and revision labels when building/publishing an image. Keep the
  runtime version discoverable in the application source file.
- When creating a GitHub Release, use the matching changelog section as its body.
  Commit comments alone are not sufficient release notes.
- Before and after deploying to TrueNAS, verify the app ID, Compose project/service,
  image ID, application version, ports and data mounts. Preserve the existing app's
  settings and persistent data. Do not confuse TrueNAS `1.0.0_custom` or an iX App
  package version with the application version.
- The NAS reporter compares deployed versions and image IDs, and checks for manual
  deployments since the last successful email. Keep its app/service-to-repository
  mapping current if names or source paths change. Report exact changelog ranges,
  not the latest release regardless of what was installed.
- Run `python tools/check_changelog.py <base-commit>` and relevant tests. Report any
  remaining provenance gaps instead of asserting that an update installed new code.

Never commit secrets, live app configuration, logs, databases, browser profiles,
tokens, or private keys. See existing security and deployment documentation.
