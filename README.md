# Wyoming OmniVoice

![Wyoming OmniVoice](assets/icon.svg)

Run [k2-fsa OmniVoice](https://github.com/k2-fsa/OmniVoice) as a local Wyoming TTS
service for Home Assistant. Supports complete and streamed text requests, named
reference voices, CPU inference, and optional NVIDIA acceleration.
**TrueNAS catalog inclusion is pending review; this is an independent community project.**

OmniVoice runs on an external Docker host with NVIDIA/CUDA support, such as
TrueNAS or a Linux VM. Home Assistant OS connects over Wyoming TCP; the model
and CUDA stack do not run inside HAOS. TrueNAS packaging is optional.

See [release and update guidance](docs/releasing.md) for GHCR tags, large-image
build strategy, publishing, upgrades and rollback.

## Requirements and versions

Use an x86-64 Linux Docker host. Allow at least 8 GB system memory and 20 GB app
storage for the image and model cache. CPU inference uses float32; NVIDIA uses
float16. GPU mode requires a supported Turing-or-newer GPU, including RTX 3090,
and a CUDA 13.0-compatible NVIDIA driver (R580 or newer).

| Component | Version |
| --- | --- |
| OmniVoice | 0.2.1, commit `08be0b4ccbac3e13e374e86fbfead4b4cac343e2` |
| PyTorch | 2.14.0+cu130 |
| TorchAudio | 2.11.0+cu130 |
| TorchCodec | 0.16.0 |
| FlashInfer | 0.6.18.post1 with CUDA 13.0 kernel cache |
| Transformers / Wyoming | 5.17.0 / 1.10.2 |
| Python / base OS | 3.12 / Debian Bookworm |

TorchAudio 2.11 uses PyTorch's stable ABI and supports PyTorch 2.11 and later;
the version numbers need not match. Key packages are listed in `constraints.txt`;
builds use `requirements.lock` to pin the tested environment. Model weights download from
`k2-fsa/OmniVoice` on first startup.

## Install

Create a persistent data directory writable by UID/GID 568:

```sh
git clone https://github.com/ValentineAlan/wyoming-omnivoice.git
cd wyoming-omnivoice
cp .env.example .env
mkdir -p data
sudo chown 568:568 data
docker compose up -d
# NVIDIA GPU:
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
```

Choose either the CPU command or the NVIDIA command. GPU deployments need the
NVIDIA driver and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
configured on the Docker host. The GPU overlay reserves one GPU; replace `count: 1`
with `device_ids: ["GPU-your-uuid"]` to select a particular card. See
[Docker GPU reservations](https://docs.docker.com/compose/how-tos/gpu-support/).
Set the data path, host port and optional LAN bind address in `.env` before starting.
On TrueNAS, grant UID/GID 568 access through the dataset permissions UI.

In Home Assistant:

1. Open **Settings → Devices & services → Add integration → Wyoming Protocol**.
2. Enter the external Docker host's LAN IP and published port (default `10200`).
   Do not enter the HAOS VM address or `localhost`.
3. Open **Settings → Voice assistants**, edit the desired assistant, and select
   OmniVoice as its text-to-speech provider with the advertised language/voice.
4. Test speech, then check `docker compose logs --tail=100` if it fails.

The [Wyoming integration](https://www.home-assistant.io/integrations/wyoming/)
supports external servers. Allow the published TCP port from Home Assistant
through any host/VLAN firewall. Do not forward it from the Internet.

Until catalog approval, use TrueNAS **Apps → Discover Apps → Custom App → Install
via YAML**, based on `compose.yaml`. Replace `./data` with an absolute dataset path.
For NVIDIA, merge in the environment and GPU reservation from `compose.nvidia.yaml`.
Select the intended GPU UUID on systems with multiple cards.

The proposed catalog form provides fixed labels, dropdown presets, help text,
validated custom values, storage permissions, and GPU selection. It has no editable
environment-variable-name list. Defaults are 4 CPUs and 8192 MB RAM. CPU thread counts
follow the CPU limit. Host-path automatic permissions are opt-in. The image runs as
a non-root user and has a Wyoming readiness health check.

First startup can take several minutes while weights download into `/data/cache`.
In Home Assistant add **Wyoming Protocol**, using the host address and published
port: `10200` in Compose or `30490` in the catalog definition. Then select OmniVoice
as TTS in your voice assistant pipeline. The app has no browser UI; keep its
unauthenticated Wyoming endpoint on a trusted network.

Audio is mono 16-bit PCM at 24 kHz with the default model. One generation runs at a
time. Streaming generates successive text pieces and sends their PCM when ready;
it does not stream audio tokens directly from the model.

## Choose a voice

A fresh install uses **example**, a bundled synthetic voice generated without a
reference recording. When first selected, the app copies `example_reference.wav`
and `example_reference.txt` to `/data/voices`, without overwriting existing files.
The example is reference audio only; model weights still download on first use.

Add a pair to that same voices folder:

```text
/data/voices/david_reference.wav
/data/voices/david_reference.txt
```

Choose **Custom voice name** and enter `david`. In the Generic Custom App form use
`OMNIVOICE_VOICE=david`. The UTF-8 TXT file contains the exact words spoken in the WAV.
Plain names such as `jess.wav` and `jess.txt` also work with `jess`. Names are
case-sensitive. Restart after changing the selected voice or transcript.

TrueNAS cannot scan a mounted folder to populate its installation form. The catalog
therefore offers **Example** or a typed **Custom voice name**. Missing, empty, or
ambiguous pairs produce a clear startup error. No personal recordings are bundled.
Use recordings you have permission to use.

Advanced controls also accept a manual reference path and transcript.
A named voice takes precedence. Voice design can generate speech without a
reference: use supported tags such as `female, british accent, moderate pitch`,
not free-form instructions. See [upstream guidance](https://github.com/k2-fsa/OmniVoice).
One selected voice and language are advertised per instance; per-request selection
is not implemented.

## Settings

TrueNAS shows presets with a **Custom value** option where useful. These variable
names are for Docker and Generic Custom Apps; catalog users edit fixed controls.
Run the wrapper with `--help` for command-line equivalents.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OMNIVOICE_DEVICE` | `cpu` | CPU or `cuda`; assign a GPU separately |
| `OMNIVOICE_MODEL` | `k2-fsa/OmniVoice` | Compatible model ID or local directory |
| `OMNIVOICE_LANGUAGE` | `English` | Synthesis language |
| `OMNIVOICE_LANGUAGE_CODE` | `en` | Matching BCP 47 code advertised to HA |
| `OMNIVOICE_VOICE` | `example` without manual reference/design | Friendly voice name |
| `OMNIVOICE_VOICES_DIR` | `/data/voices` | Paired WAV/TXT folder |
| `OMNIVOICE_REF_AUDIO` | empty | Advanced manual reference WAV path |
| `OMNIVOICE_REF_TEXT` | empty | Exact transcript, required with manual WAV |
| `OMNIVOICE_INSTRUCT` | empty | Supported design tags; leave empty for a reference voice |
| `OMNIVOICE_NUM_STEP` | `32` | Steps, 1–100; fewer trade quality for latency |
| `OMNIVOICE_GUIDANCE_SCALE` | `2.0` | Guidance, 0–10; higher is not always better |
| `OMNIVOICE_SPEED` | `1.0` | Speech speed, 0.25–4; above 1 is faster |
| `OMNIVOICE_T_SHIFT` | `0.1` | Diffusion time shift, 0–1; advanced tuning |
| `OMNIVOICE_FULL_TEXT_CHARS` | `100` | Complete-request chunk target, 20–500 characters |
| `OMNIVOICE_FIRST_STREAM_CHARS` | `100` | First streamed chunk target, 20–500 characters |
| `OMNIVOICE_STREAM_CHARS` | `100` | Subsequent streamed chunk target, 20–500 characters |
| `OMNIVOICE_INTER_CHUNK_SILENCE` | `0.15` | Pause between pieces, 0–2 seconds |
| `OMNIVOICE_AUDIO_PACKET_BYTES` | `8192` | Even network packet size, 1024–65536 bytes |
| `OMNIVOICE_LOG_LEVEL` | `INFO`; catalog `WARNING` | DEBUG, INFO, WARNING, ERROR, CRITICAL; third-party output is separate |
| `OMNIVOICE_FLASHINFER` | `false` | Fused GPU operations and packed attention; CUDA only |
| `OMNIVOICE_CUDA_GRAPH` | `false` | GPU capture/replay; requires FlashInfer |
| `OMNIVOICE_CUDA_GRAPH_CACHE_SIZE` | `4` | Maximum cached shapes, 1–16; bounds VRAM growth |

Smaller chunks can reduce first-audio latency but affect prosody and pauses.
Packet size controls transport framing, not model generation. Benchmark FlashInfer
and graphs with your voice/GPU; initial compilation or capture can be slower than
warm requests. More cached graphs use more VRAM.

`HF_HOME`, `TORCH_HOME`, and `XDG_CACHE_HOME` are fixed at `/data/cache` in the image.
Choose the persistent storage backing `/data` rather than exposing these paths as
settings. Voice files and caches survive container replacement.

## Build and validate

```sh
docker build -t ghcr.io/valentinealan/wyoming-omnivoice:1.1.0 .
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

See `VALIDATION.md` and the proposed catalog definition in `truenas/`.
The wrapper is Apache-2.0 licensed. Dependencies retain their upstream licenses;
see `NOTICE` and `voices/README.md`.
