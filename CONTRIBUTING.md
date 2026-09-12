# Contributing

Open an issue before substantial changes. Include the image tag, device, TrueNAS
version and a small reproducible example. Remove private transcripts, audio,
addresses and credentials from logs and configuration before sharing them.

Run `python -m pip install -r requirements-test.txt` and
`python -m unittest discover -s tests -v`. Protocol tests use a fake engine and do
not download model weights. Changes to inference dependencies additionally need
a real synthesis test on supported hardware, including Pascal for CUDA changes.

Keep PyTorch and TorchAudio on their matching CUDA 12.6 wheels. Update
`requirements.lock`, `p40-constraints.txt`, compatibility documentation and image
version together. A successful import is insufficient GPU validation.

Contributions are under this repository's Apache-2.0 license.
