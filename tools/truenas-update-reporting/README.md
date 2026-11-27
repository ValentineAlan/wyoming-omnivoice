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

## GitHub-built service updates

An explicit `source_update` mapping opts a service into release discovery. The
nightly script checks the configured GitHub branch for a newer `app-release.json`
version and an exact changelog section, even without a TrueNAS image-update flag.
It pins the resolved commit, builds before restarting, and updates only the mapped
service with `--no-deps --no-build --pull never`. The original Compose configuration
remains authoritative. Runtime settings, ports and data mounts must remain equal.
The observed application version and HTTP health response must both match before
the report can claim success. Failed verification restores the previous image.

LaptopLander opts in only `hunter`; browser and helper updates are separate work.
This prevents registry pulls of the local `github-main` tags. A TrueNAS image flag
may remain for another service; the email continues to expose it. Unknown versions,
downgrades, missing release notes and source mismatches fail closed. Same-version
GitHub changes do not trigger a rebuild: runtime changes require a new release.

`deployments/` contains private local receipts with source commit, version, image
IDs and verified/rollback status. Keep receipts out of GitHub. Version and rollback
tags are retained on the NAS. The helper does not publish images to a registry.

For a single-app run using the normal lock, stopped-state handling and email flow:

```sh
bash update-truenas-apps4.sh --app ebay-hunter-stack
```

Run `python3 -m unittest discover -s . -p 'test_*.py'` and `bash -n
update-truenas-apps4.sh` before installing script changes. The source updater and
its mapping must be installed alongside the reporting helper.

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
