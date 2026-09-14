# Releases, builds and updates

## Repository layout

The existing `wyoming_omnivoice.py`, `voice_files.py` and `acceleration.py` implement
the server. `tests/` exercises the protocol and voice handling without downloading
the model. `Dockerfile`, dependency locks and the two Compose files package it.
`.github/workflows/test.yaml` checks pushes and pull requests;
`publish.yaml` builds and pushes GHCR images on version tags or manual dispatch.
`truenas/` is optional catalog packaging. Retain the existing Apache-2.0 `LICENSE`,
`NOTICE` and voice provenance rather than substituting a license placeholder.

## Large CUDA image strategy

Keep the tested dependency stack in the existing Dockerfile. CUDA libraries arrive
through the pinned PyTorch CUDA wheels; starting with another full CUDA image would
duplicate much of that payload. Dependency installation precedes wrapper COPYs,
so wrapper changes can reuse the expensive layers. GitHub Actions imports and exports
the `buildcache` registry cache in GHCR, which avoids repeatedly rebuilding the
large stack on fresh runners. Model weights and personal voices stay in `/data`,
outside the distributed image. `.dockerignore` restricts build inputs.

The existing full build has previously succeeded on a GitHub-hosted runner. A cold
cache still needs substantial disk and download capacity. If a future dependency
update exceeds runner capacity, use an adequately sized isolated Linux runner;
do not run untrusted pull requests on the production TrueNAS host. Builds target
`linux/amd64`; building/import checks do not require a GPU. Actual synthesis testing
does. The current GPU runtime uses CUDA 13.0 and supports Turing-or-newer NVIDIA
hardware with a compatible R580-or-newer driver. Historical releases are not the
recommended installation target; use the current release and its hardware requirements.

## Publish

The workflow uses the short-lived `GITHUB_TOKEN` with `contents: read` and
`packages: write`. No personal token belongs in this repository. The OCI source
label links the package to its repository. If GHCR rejects a push, check the
package's Actions access for this repository. New packages default to private;
confirm intended visibility in GitHub package settings before advertising anonymous
pulls. See [GitHub's publishing guide](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).

For a new release, update `VERSION` in the wrapper, update the Compose and `.env.example`
version defaults, and record tested compatibility in `VALIDATION.md`. Run the tests
and test the candidate on the intended GPU, including complete and streamed Wyoming
requests and a Home Assistant speech request. Commit the release, then create and
push a matching tag such as `v1.1.1`. Do not move an existing release tag.

* A stable tag `v1.1.1` publishes `:1.1.1` and `:latest` from the same build.
* A prerelease tag such as `v1.2.0-rc.1` publishes only `:1.2.0-rc.1`.
* Manual workflow dispatch publishes `:edge`, without changing `:latest`.
* `:buildcache` is build infrastructure, not an installable release.

Only publish stable releases in increasing version order: publishing an older
stable version also moves `latest`. Serialized publishing prevents overlapping
builds from racing. The workflow rejects tags that differ from the wrapper version.
Check the completed Actions run and pull the resulting image before announcing a
release. GitHub release notes can then point to the exact image digest.

The historical `1.1.0` publication predates the `latest` policy. To initialize or
roll back that alias, manually run **Promote tested release** with an existing stable
GHCR version. This copies its registry manifest to `latest` without rebuilding CUDA
layers or changing the versioned tag. Only promote a release already tested on the
intended hardware. Check that workflow's result before using the alias.

## Upgrade and rollback

Pin a tested version or `ghcr.io/valentinealan/wyoming-omnivoice@sha256:...` in
`.env` as `OMNIVOICE_IMAGE`. `latest` is convenient but mutable; it does not update
a running container automatically. Save your current image digest and `.env`,
back up reference voices and configuration, and read release compatibility notes.

Change `OMNIVOICE_IMAGE` to the new version, then for NVIDIA installations run:

```sh
docker compose -f compose.yaml -f compose.nvidia.yaml pull
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
docker compose -f compose.yaml -f compose.nvidia.yaml ps
docker compose -f compose.yaml -f compose.nvidia.yaml logs --tail=100
```

Wait for health and test speech from Home Assistant. A health check confirms Wyoming
readiness, not end-to-end GPU audio quality. First startup may download weights.
For CPU installs omit the two `-f` arguments. For rollback restore the old image
reference and compatible environment settings, then repeat pull/up. Preserve `/data`;
do not delete the cache/voices as part of a routine update. Pin a local model directory
through `OMNIVOICE_MODEL` if exact model-weight reproducibility is required: the
default upstream model download is not revision-pinned.
