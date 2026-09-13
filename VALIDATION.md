# Version 1.1.0 validation

Tested on 13 September 2026. Results for earlier releases are not used to claim
compatibility of this runtime.

## Runtime and voice tests

- Twenty protocol and voice-file tests passed on Linux.
- The runtime image built on an Ubuntu x86-64 VM. `pip check` and imports of
  PyTorch, TorchAudio, TorchCodec and OmniVoice passed.
- PyTorch 2.14.0+cu130 reports sm_86 among its compiled architectures.
- Public wrapper source was tested in that dependency image as UID/GID 568 with
  all capabilities dropped and no-new-privileges enabled.
- A fresh writable data directory received the synthetic example WAV/TXT pair.
  Existing files survived a restart. Wyoming readiness checks passed.
- Nine CPU and nine RTX 3090 requests produced non-silent 24 kHz PCM, covering
  normal requests and streamed text. The GPU test enabled FlashInfer and CUDA
  graphs. Speech recognition matched the checked sentences.
- The example was generated without reference audio; no personal recordings are
  included. Its recognized words matched the bundled transcript.

## RTX 3090 benchmark

The same three sentences were repeated three times with a reference
voice on RTX 3090 and stock NVIDIA driver 580.173.02. The benchmark configuration
used 12 generation steps and short text chunks. Warm first audio improved from
about 0.50–0.69 seconds to 0.21–0.25 seconds with FlashInfer and CUDA graphs. The
first request after restart remained slower (about 2.9 seconds).

These measurements cover TTS server latency, not an entire Home Assistant request.
They are a small functional benchmark, not a claim for every voice or GPU.
Fourteen additional varied requests completed with a four-shape graph cache.

## TrueNAS catalog

The current official apps_validation container passed metadata/schema validation.
Basic storage, host-path storage and custom voice/preset configurations rendered.
The template also rejects incompatible CPU/FlashInfer and graph settings, an empty
custom voice, an odd PCM packet size and empty voice-design tags.

The proposed form supplies fixed controls, help text, preset values and validated
custom overrides. Cache locations are fixed in the image. A generic Custom App
installation cannot display this tailored form before catalog inclusion.

The release container is built and published by the repository's container workflow.
Its workflow result is the record of the final Dockerfile build. Catalog approval
and the maintainer CDN icon upload remain pending independently of local tests.

Submission: https://github.com/truenas/apps/pull/5793
