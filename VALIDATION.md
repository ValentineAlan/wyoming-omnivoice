# Release validation

Validation performed on 12 September 2026 during preparation of version 1.0.0.

| Check | Result |
| --- | --- |
| Protocol unit tests | 11 passed; no model download required |
| Docker build from the published Dockerfile | Passed on Linux amd64 |
| Locked dependency consistency (`pip check`) | Passed |
| P40 normal synthesis | Passed; 24 kHz mono PCM, non-silent audio |
| P40 streamed synthesis | Passed, including completion events |
| P40 CUDA matrix multiplication and attention | Passed in float16 and float32 |
| CPU normal synthesis | Passed with float32 model |
| CPU streamed synthesis | Passed |
| Non-root UID/GID 568 and dropped capabilities | Passed for both inference modes |
| Wyoming readiness health check | Passed for both modes |
| TrueNAS official metadata/schema validator | Passed using `apps_validation:latest` |
| ixVolume and host-path catalog rendering | Both passed with library 2.3.11 |

The real inference tests used an existing, locally cached model and reference
voice, with eight generation steps. They ran in isolated containers on TrueNAS
26.0.0-BETA.3, without replacing the live voice service. The P40 used driver
580.178.04 and reported compute capability 6.1. The Python dependency versions
are recorded in `requirements.lock`.

For the same short test phrase, GPU synthesis took approximately 3.4–3.9 seconds
and CPU synthesis approximately 8.1–8.8 seconds on the test host. These are smoke
test timings, not performance guarantees or a quality benchmark. Other voices,
languages, CPUs, GPUs, and generation settings need their own evaluation.

GitHub Actions test and image-publishing results are available in the repository's
Actions tab. TrueNAS catalog CI and review remain separate from these local
checks. Passing validation does not imply catalog approval.

## Published image and catalog installation checks

The public `ghcr.io/valentinealan/wyoming-omnivoice:1.0.0` image was built
successfully by GitHub Actions and pulled anonymously on TrueNAS. Its digest is
`sha256:b8dd1d041cfe2890eed9f72099876b2a121f1fe17e5ea03c8c3de7fcd98e3b83`.
The published image passed the P40 float16/float32 matrix and attention checks.

Both officially rendered catalog storage variants were started with Docker
Compose using the public image, isolated test paths and a loopback test port.
The permissions helper, non-root service, readiness check, normal synthesis and
streamed synthesis passed for ixVolume and host-path configurations. These CPU
tests reused cached model weights and used eight steps; they do not establish
cold-download performance. They used generated voices without personal audio.

With four CPU threads matching the configured four-CPU limit, the ixVolume case
completed normal/streamed synthesis in 4.269/4.150 seconds. The host-path case,
including supported voice tags and non-default tuning, took 4.485/4.806 seconds.
All outputs were non-silent 24 kHz mono audio. Timings are smoke-test observations.

All 15 OmniVoice settings have native configuration fields with descriptions.
Additional checks covered decimal range validation, missing NVIDIA assignment,
and reference-audio/transcript pairing. Voice design instructions accept the
upstream's supported tags rather than freeform prose. Official schema validation
passed after these changes. Catalog-wide port validation covered 443 app schemas.

TrueNAS review, upstream CI and the maintainer's CDN icon upload remain external
submission steps. The catalog submission is PR #5793 in `truenas/apps`.
