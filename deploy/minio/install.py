"""Install the official pinned Linux amd64 binary for local object storage."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

RELEASE = "RELEASE.2025-09-07T16-13-09Z"
SHA256 = "7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f"
url = f"https://github.com/minio/minio/releases/download/{RELEASE}/minio.linux-amd64.{RELEASE}"
with urlopen(url, timeout=120) as source:
    binary = source.read()
if hashlib.sha256(binary).hexdigest() != SHA256:
    raise RuntimeError("minio_checksum_mismatch")
target = Path("/usr/local/bin/minio")
target.write_bytes(binary)
target.chmod(0o755)
