# Wyoming OmniVoice

![Wyoming OmniVoice](assets/icon.svg)

Run [k2-fsa OmniVoice](https://github.com/k2-fsa/OmniVoice) as a local
[Wyoming](https://github.com/OHF-Voice/wyoming) text-to-speech service for Home
Assistant. Includes a standalone Docker image and a proposed TrueNAS Community
app definition. **Catalog inclusion is pending review; this is an independent
community project.**

- Normal synthesis and Wyoming streamed text input.
- One configured voice, with optional reference audio and transcript.
- CPU or NVIDIA GPU inference; CUDA 12.6 dependencies retained for Tesla P40.
- Non-root container, persistent model cache, and a readiness health check.

Streaming generates successive pieces of text and sends PCM as each piece is
ready. It does not stream audio tokens directly from the model. Output is mono
16-bit PCM at the model's sampling rate (24 kHz for the tested model).

## Requirements

Use an x86-64 Linux Docker host. The TrueNAS catalog definition targets the
Docker-based Apps platform, with minimum version 24.10.2.2. Plan for at least
8 GB available system memory and 20 GB free app storage initially; actual usage
depends on model caches, image retention, and workload. CPU inference is slower
than GPU inference. Only one inference job runs at a time.

NVIDIA mode requires a compatible host NVIDIA driver and container GPU support.
On TrueNAS, enable the NVIDIA driver and select the GPU under app resources.
Pascal GPUs such as Tesla P40 require the pinned PyTorch CUDA **12.6** wheel;
switching to a CUDA 12.8 wheel is not a compatible upgrade for this image.

| Component | Release dependency |
| --- | --- |
| OmniVoice | 0.2.1, commit `08be0b4ccbac3e13e374e86fbfead4b4cac343e2` |
| PyTorch / TorchAudio | 2.8.0+cu126 |
| CUDA runtime base | 12.6.3 / Ubuntu 22.04 |
| Wyoming | 1.10.0 |
| Transformers | 5.17.0 |

Python packages are pinned in `requirements.lock`; the model is downloaded at
runtime from `k2-fsa/OmniVoice`. Model repository contents and operating-system
security updates are not frozen by the Python lock file.

## TrueNAS

Until catalog approval, use **Apps → Discover Apps → Custom App → Install via
YAML**. Choose an unused app name and paste a Compose configuration based on
`compose.yaml`. Replace `./data` with an absolute dataset path, for example
`/mnt/POOL/appdata/wyoming-omnivoice`. Create that dataset first and grant UID/GID
568 read/write access using TrueNAS dataset permissions. Keep your existing app
on its current port until the new installation is tested.

For NVIDIA, merge the service's `environment` and `deploy` settings from
`compose.nvidia.yaml` into the same service. Select the intended GPU; on hosts
with multiple GPUs, replace `count: 1` with `device_ids: ["GPU-YOUR-UUID"]`.
The endpoint has no web interface.

The proposed catalog app exposes CPU/NVIDIA selection, language, generation
steps, reference voice, TCP port, storage, UID/GID, and resource limits. Its
default storage is an automatically provisioned ixVolume. Host-path storage is
also supported; automatic permissions for host paths are opt-in.

On the first launch, model weights download to `/data/cache`. Startup can take
several minutes and requires internet access. The container becomes healthy
only after the model has loaded and answers Wyoming discovery requests.

In Home Assistant, open **Settings → Devices & services → Add integration →
Wyoming Protocol**, then enter the TrueNAS host address and the published TCP
port (default `10200`). Select OmniVoice as the text-to-speech provider in your
voice assistant configuration. Language selection in the app determines the
single advertised voice; per-request voice/language switching is not implemented.

## Docker Compose

Create a writable `data` directory for UID/GID 568, then:

```sh
docker compose up -d
# Or NVIDIA:
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
docker compose logs --tail=50 wyoming-omnivoice
```

The Compose files reference the versioned GHCR image. During release preparation,
build it locally if that tag has not been published yet:

```sh
docker build -t ghcr.io/valentinealan/wyoming-omnivoice:1.0.0 .
```

## Configuration

Add environment variables to the container, or run the script with `--help` for
equivalent command-line options. Defaults favor predictable quality rather than
minimum latency.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OMNIVOICE_DEVICE` | `cpu` | `cpu` or `cuda` |
| `OMNIVOICE_MODEL` | `k2-fsa/OmniVoice` | Hugging Face model ID or local model directory |
| `OMNIVOICE_LANGUAGE` | `English` | Language passed to OmniVoice |
| `OMNIVOICE_LANGUAGE_CODE` | `en` | Matching BCP 47 code advertised to Wyoming |
| `OMNIVOICE_REF_AUDIO` | empty | Reference WAV path inside the container |
| `OMNIVOICE_REF_TEXT` | empty | Accurate transcript of the reference WAV |
| `OMNIVOICE_INSTRUCT` | empty | Optional voice-design instruction |
| `OMNIVOICE_NUM_STEP` | `32` | Generation steps, 1–100 |
| `OMNIVOICE_GUIDANCE_SCALE` | `2.0` | Guidance, 0–10 |
| `OMNIVOICE_SPEED` | `1.0` | Speech speed, 0.25–4 |
| `OMNIVOICE_T_SHIFT` | `0.1` | Diffusion time shift, 0–1 |
| `OMNIVOICE_FULL_TEXT_CHARS` | `100` | Complete-request piece limit, 20–500 |
| `OMNIVOICE_FIRST_STREAM_CHARS` | `100` | First streamed piece limit, 20–500 |
| `OMNIVOICE_STREAM_CHARS` | `100` | Subsequent streamed piece limit, 20–500 |
| `OMNIVOICE_INTER_CHUNK_SILENCE` | `0.15` | Silence between pieces in seconds, 0–2 |

For a reference voice, place a WAV at `data/voices/reference.wav`, set
`OMNIVOICE_REF_AUDIO=/data/voices/reference.wav`, and supply its transcript. Both
settings must be provided together. Reference recordings and transcripts stay in
your installation and are not included in the image or this repository. Use
recordings you have permission to use.

Eight steps and guidance `1.2` were used for the original Tesla P40 deployment.
Lower step counts can improve latency at the expense of quality. Splitting
short pieces also affects prosody; tune against your own text and voice.

## Diagnostics and updates

```sh
# Run these on the Docker host, using your published port:
python3 test_wyoming.py --port 10200 --synthesize
python3 test_wyoming.py --port 10200 --synthesize --stream
```

`check_gpu.py` is specifically a Tesla P40 compatibility test, including CUDA
matrix multiplication and attention. Run it inside the image with the GPU
assigned. Tests under `tests/` exercise protocol behavior without downloading
weights; see [CONTRIBUTING.md](CONTRIBUTING.md).

Before updating, snapshot or back up the data dataset and record the current
image tag. Pull a new versioned tag, recreate the container, and run both speech
tests. Revert the tag if needed. Do not delete the model cache or reference audio
as part of a routine image update. The legacy private three-image build and SCP
workflow are not required for community installations.

If startup fails, check dataset permissions, free memory, model download access,
and GPU assignment. CUDA architecture errors usually indicate incompatible
PyTorch wheels. Do not install arbitrary newer Torch wheels inside the container.

The service accepts up to 16 connections, limits frames to 64 KiB and requests to
10,000 text characters, and closes idle connections after five minutes. It has
no authentication or TLS: keep the port on a trusted LAN. See [SECURITY.md](SECURITY.md).

## License and attribution

The wrapper is Apache-2.0 licensed. OmniVoice, Wyoming, PyTorch, CUDA components,
and model weights retain their respective licenses. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). This project is independently maintained and is not an official
TrueNAS or k2-fsa release.
