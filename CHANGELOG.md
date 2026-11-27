# Changelog

Release notes are matched to the deployed application version, not the TrueNAS iX App package version.

## Unreleased

- Fix the nightly updater's opt-in GitHub source path: discover versioned releases independently of TrueNAS image flags, build a pinned commit, and verify the running version and HTTP health before reporting success.
- Update only the mapped Hunter service, preserving Chromium, the SID helper, runtime settings and data mounts; retain rollback images and deployment receipts, and restore the old image if verification fails.
- Add `--app APP_ID` for scoped cron-script runs. Keep source-update operational changes separate from the OmniVoice application release version.
- Validation: 21 updater/reporting tests pass, including source discovery without a TrueNAS flag, failure rollback and unchanged runtime settings; add these checks and shell syntax validation to CI.
- Fix custom deployment reports on large NAS inventories by filtering app IDs and merging JSON files instead of passing the full inventory as a command argument.
- Reject invalid report inventories rather than sending an empty success summary; fix custom target-version formatting.
- Make full-report tests use synthetic deployment metadata and notes, including an inventory over 200 KB; all 12 reporting tests pass.

- Add custom-app release-note reporting for the TrueNAS daily update email, using observed application versions and image IDs.
- Detect deployments made between nightly runs and report service changes separately.
- Add formatted HTML reports and explicit warnings for unchanged images still flagged as outdated.
- Require changelog entries and version bumps for future runtime changes through repository instructions and CI.

## 1.1.0

- Existing repository source version when this changelog was introduced. Historical changes have not been reconstructed or attributed to this release.
- Refer to `README.md` and `VALIDATION.md` for the documented feature set, compatibility and validation of this source line.

## 0.1.7

### Verified legacy deployment record — 10 November 2026

- Preserved the existing RTX 3090/CUDA 13 build and published it as `ghcr.io/valentinealan/wyoming-omnivoice:3090-cu130-torch214-20260913` so TrueNAS can pull it during updates.
- The registry manifest digest is `sha256:b668eac92667770a0734d7e1b48f60d7c2bda8fa05893825b57f00f493a132f0`; its image ID is `sha256:a357191be32510a1acc7f95994f949556084c410e6f163be8481f02d0532f5d3`.
- Verified Wyoming discovery advertised application version `0.1.7` and speech generation succeeded after updating the generic iX App package to `1.4.8`.
- Application code, voice settings, GPU selection and persistent data were unchanged. This is a deployment record, not reconstructed original release notes or a claim that the legacy image contains the current `1.1.0` source.
