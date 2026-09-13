"""Resolve friendly voice names using paired WAV/transcript files."""
from pathlib import Path


def seed_example(directory, bundled_directory='/opt/omnivoice/example-voices'):
    """Seed the example once; never replace either half of an existing pair."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    names = ('example_reference.wav', 'example_reference.txt')
    if any((root / name).exists() for name in names):
        return False
    contents = [(name, (Path(bundled_directory) / name).read_bytes()) for name in names]
    created = []
    try:
        for name, data in contents:
            path = root / name
            with path.open('xb') as f:
                created.append(path)
                f.write(data)
    except Exception:
        for path in created:
            path.unlink()
        raise
    return True


def discover_voices(directory):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f'Voice folder is not a directory: {root}')
    voices = {}
    for wav in sorted(root.iterdir()):
        if not wav.is_file() or wav.suffix.lower() != '.wav':
            continue
        name = wav.stem.removesuffix('_reference')
        if name in voices:
            raise ValueError(f'Ambiguous voice name {name!r}: more than one WAV matches')
        voices[name] = wav
    return voices


def resolve_voice(directory, name):
    voices = discover_voices(directory)
    if name not in voices:
        available = ', '.join(voices) or '(none)'
        raise ValueError(f'Unknown voice {name!r}. Available voices: {available}')
    root = Path(directory).resolve(strict=True)
    wav = voices[name]
    transcript = wav.with_suffix('.txt')
    for path in (wav, transcript):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'Voice files must stay inside {root}')
        if not path.is_file():
            raise ValueError(f'Voice {name!r} requires the paired file {path.name}')
    text = transcript.read_text(encoding='utf-8-sig').strip()
    if not text:
        raise ValueError(f'Transcript is empty: {transcript.name}')
    return str(wav), text
