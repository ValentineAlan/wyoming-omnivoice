# Contributing

Open an issue before substantial changes. Include the image tag, device, TrueNAS
version and a small reproducible example. Remove private transcripts, audio,
addresses and credentials from logs and configuration before sharing them.

Run `python -m pip install -r requirements-test.txt` and
`python -m unittest discover -s tests -v`. Protocol tests use a fake engine and do
not download model weights. Changes to inference dependencies additionally need
a real synthesis test on supported hardware, including an NVIDIA GPU for CUDA changes.

Check the current upstream compatibility tables for PyTorch, TorchAudio, TorchCodec
and FlashInfer. TorchAudio 2.11 uses a stable ABI and can accompany newer PyTorch
releases. Update `requirements.lock`, `constraints.txt`, driver requirements,
documentation and image version together. A successful import is insufficient GPU
validation: test normal and streamed speech, finite audio, and first-run voice setup.

Keep catalog controls and their help text in sync with wrapper options. Provide
presets and validated custom values, without editable environment-variable names.
Keep cache paths fixed under /data/cache. Never bundle private reference recordings;
the included example is synthetic and must remain paired with its exact transcript.

Contributions are under this repository's Apache-2.0 license.
