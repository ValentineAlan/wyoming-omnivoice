# Security

The Wyoming TCP endpoint has no authentication or encryption. Bind it only to a
trusted private network and do not forward it to the internet. It can cause
model inference and consume CPU/GPU resources. The server limits connections,
frame sizes, accumulated text and individual synthesis pieces.

The image runs as UID/GID 568 and needs write access only to its data and temporary
directories. It does not require privileged mode, the Docker socket or TrueNAS API
credentials. Model downloads require outbound HTTPS on first startup.

For a sensitive vulnerability, use GitHub's private vulnerability reporting when
enabled. Do not post private voice samples or credentials in public issues.
