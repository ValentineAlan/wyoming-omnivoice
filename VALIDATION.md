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
