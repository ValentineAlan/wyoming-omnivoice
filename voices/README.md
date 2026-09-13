# Bundled example voice

`example_reference.wav` is synthetic speech generated with k2-fsa/OmniVoice
(commit `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`), without reference audio or
voice cloning. The design tags were `female, british accent, moderate pitch`,
using 32 generation steps. `example_reference.txt` contains the spoken text.

This example is intended for redistribution with Wyoming OmniVoice. No personal
voice recordings are included. The accompanying text is original example text.

On a fresh installation, selecting `example` copies this pair to `/data/voices`.
Existing files are never overwritten. Add your own paired WAV and UTF-8 TXT files
to that folder, then set `OMNIVOICE_VOICE` to the filename without `_reference.wav`
(or without `.wav` for names that do not use the `_reference` suffix).
