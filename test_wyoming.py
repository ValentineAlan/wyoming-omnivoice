import argparse
import json
import socket
import struct
import time

p = argparse.ArgumentParser()
p.add_argument('--port', type=int, default=10201)
p.add_argument('--synthesize', action='store_true')
p.add_argument('--stream', action='store_true')
args = p.parse_args()

def send(sock, kind, data=None):
    header = {'type': kind}
    if data is not None:
        header['data'] = data
    sock.sendall((json.dumps(header) + '\n').encode())

def receive(reader):
    line = reader.readline()
    if not line:
        raise RuntimeError('Connection closed before completion')
    header = json.loads(line)
    n = header.get('data_length', 0)
    if n:
        header.setdefault('data', {}).update(json.loads(reader.read(n)))
    n = header.get('payload_length', 0)
    payload = reader.read(n) if n else b''
    if len(payload) != n:
        raise RuntimeError('Truncated audio payload')
    return header, payload

with socket.create_connection(('127.0.0.1', args.port), timeout=180) as sock:
    reader = sock.makefile('rb')
    send(sock, 'describe')
    info, _ = receive(reader)
    assert info['type'] == 'info', info
    print(json.dumps({'discovery': info['data'].get('tts')}), flush=True)
    if not args.synthesize:
        raise SystemExit(0)
    started = time.monotonic()
    if args.stream:
        send(sock, 'synthesize-start')
        send(sock, 'synthesize-chunk', {'text': 'The voice update test is complete. '})
        send(sock, 'synthesize-stop')
    else:
        send(sock, 'synthesize', {'text': 'The voice update test is complete.'})
    events, audio, first_audio, rate = [], bytearray(), None, None
    while True:
        event, payload = receive(reader)
        kind = event['type']
        events.append(kind)
        if kind == 'audio-start':
            rate = event['data']['rate']
            assert event['data']['width'] == 2 and event['data']['channels'] == 1
        if kind == 'audio-chunk':
            if first_audio is None:
                first_audio = time.monotonic() - started
            audio.extend(payload)
        if kind == ('synthesize-stopped' if args.stream else 'audio-stop'):
            break
        if kind == 'error':
            raise RuntimeError(event)
    assert 'audio-start' in events and 'audio-stop' in events and len(audio) > 0, events
    values = struct.unpack('<' + 'h' * (len(audio) // 2), audio)
    assert max(abs(x) for x in values) > 0, 'Audio is silent'
    print(json.dumps({'mode': 'stream' if args.stream else 'normal', 'bytes': len(audio),
                      'sample_rate': rate, 'audio_seconds': len(audio) / 2 / rate,
                      'first_audio_seconds': first_audio, 'total_seconds': time.monotonic() - started,
                      'peak_pcm': max(abs(x) for x in values), 'event_count': len(events)}), flush=True)
