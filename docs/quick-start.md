# From first install to spoken Assist

## 1. Check the two machines

Home Assistant remains where it is. OmniVoice runs on an x86-64 Linux Docker host
with a supported Turing-or-newer NVIDIA GPU, CUDA 13-compatible R580-or-newer driver
and NVIDIA Container Toolkit. The runtime was tested on RTX 3090. Allow at least
8 GB system RAM and 20 GB storage on the server; GPU memory use varies with settings.
Do not install the GPU workload inside HAOS.

## 2. Choose your setup route

**Guided:** [Add OmniVoice Connect](https://github.com/ValentineAlan/omnivoice-connect)
to your Home Assistant app store. Open it and choose Docker or TrueNAS. It generates
a configuration to run on your external server, checks the connection and plays a
fixed test phrase. It does not install the server remotely or require server credentials.

**Direct Docker:** clone this repository, copy `.env.example` to `.env`, create
`data/` writable by UID/GID 568, and start:

```sh
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
docker compose -f compose.yaml -f compose.nvidia.yaml ps
docker compose -f compose.yaml -f compose.nvidia.yaml logs --tail=100
```

**TrueNAS:** use Install via YAML with the generated companion configuration, or
merge the repository's two Compose files. Use an absolute dataset path for `/data`,
grant UID/GID 568 access, and select the intended GPU. Catalog inclusion is separate
from this Custom App path. The container has no web interface.

Wait for the model download and healthy status. Download/loading time depends on
your connection and machine; there is no guaranteed five-minute setup.

## 3. Connect Home Assistant

[Open Wyoming setup](https://my.home-assistant.io/redirect/config_flow_start/?domain=wyoming).
Enter the external Docker host's LAN address and published port, normally `10200`.
Manual path: Settings → Devices & services → Add integration → Wyoming Protocol.
Do not enter `localhost` or the HAOS address.

In Settings → Voice assistants, edit the desired assistant and select OmniVoice
for text-to-speech, with its advertised language and voice. Test a spoken response
through your normal Assist device. A browser sample alone does not verify this step.

## 4. Make sure it survives a restart

Restart the container and check that voices/cache survive. If you installed the
companion, stop it and confirm Assist still speaks. Keep the server running; Assist
connects directly to it. Pin versioned images and follow the [update/rollback guide](releasing.md).

## If it does not speak

| Symptom | Check |
| --- | --- |
| Connection refused | External IP, published port, running container and LAN firewall |
| Wyoming responds but no TTS voice | You may have selected an STT service's port |
| Startup stays unready | Server logs, download progress, storage permissions and GPU compatibility |
| Sample works but Assist does not | Wyoming entry and the selected assistant's TTS settings |
| Speech fails after voice change | Matching nonempty WAV/TXT pair; restart after changing voices |

Keep Wyoming on a trusted LAN. For feedback, share reviewed diagnostics rather
than private recordings, credentials or unfiltered logs.
