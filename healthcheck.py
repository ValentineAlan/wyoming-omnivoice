"""A ready model must answer a Wyoming describe request."""
import json
import socket

with socket.create_connection(("127.0.0.1", 10200), timeout=5) as sock:
    sock.sendall(b'{"type":"describe"}\n')
    header = json.loads(sock.makefile("rb").readline(65536))
    if header.get("type") != "info":
        raise SystemExit(1)
