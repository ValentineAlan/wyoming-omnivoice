# TrueNAS custom-app release notes

The daily updater has two version domains: TrueNAS package versions and application
versions. Custom YAML apps report `1.0.0_custom`; generic iX Apps report the template
version. Neither is an application release number.

## Installed reporting flow

1. Capture the image IDs, OCI source/version/revision labels and configured runtime
   version constants from the containers in the exact `ix-<app-id>` Compose project.
   Reading source files does not execute them and works with stopped containers.
2. Compare against the last successfully emailed state, or the pre-update state for
   a newly encountered app. Run the original TrueNAS update and stopped-state logic.
3. Read the mapped repository's `CHANGELOG.md`; select versions strictly after the
   previously installed version through the actually installed version. If the
   image is unchanged, show the installed release notes as context, not new changes.
4. Report each service separately. A Chromium image update is not a Hunter release.
   Exact OCI commit ranges can provide fallback commit notes. If identity or notes
   cannot be established, say so and link the source without substituting latest notes.
5. Send plain text and sanitized HTML. Advance the reporting baseline only after a
   successful mail API job. Failed app updates retain their previous baseline.

Tracked custom apps deployed manually between nightly runs are included in the
next report without another restart. A first baseline does not invent prior history.
GitHub branch changes alone are not evidence of a deployment.

## Files and operation

On this installation, helpers and non-secret repository mappings are in
`/mnt/Decathlon/appdata/truenas-update-reporting/`. The existing cron command remains
`update-truenas-apps4.sh` at its existing path. Its schedule is unchanged.
`last-reported-custom-apps.json` is local state and `last-report.md` is the latest
successfully submitted report. Keep both out of GitHub.

Add owned apps to `custom-app-changelogs.json` by TrueNAS app ID and Compose service,
specifying the repository and Python source path containing `APP_VERSION` or
`VERSION`. OCI labels provide automatic source lookup for other custom services.
Legacy image mappings must use the full verified image ID, never a mutable tag.
Unversioned helpers are reported as unversioned rather than inheriting a base OS
version. This does not retrofit labels or rebuild existing production images.

```sh
python3 -m unittest -v test_custom_app_changelog
bash -n update-truenas-apps4.sh
python3 custom_app_changelog.py capture APP_ID before.json
python3 custom_app_changelog.py capture APP_ID after.json
python3 custom_app_changelog.py report before.json after.json
```

These commands do not update apps or send mail. The reporter fetches public GitHub
notes without credentials. Offline/private/unmatched sources are identified as
unverified; GitHub permissions must be configured separately for private sources.
Do not reset the baseline to hide unreported deployments.

## Release discipline

Every runtime change needs a new application version and matching changelog section.
Use that section for GitHub Release notes. Publish immutable versioned images with
`org.opencontainers.image.source`, `.version`, and `.revision` labels; verify the
deployed image digest and runtime version. The `Changelog contract` workflow checks
versioned entries and version bumps for runtime changes. Make it a required branch
check in repository settings if merges must be blocked on failure.

An unchanged mutable image may still be flagged by TrueNAS. The report now exposes
that remaining update flag instead of equating a successful command with new code.
