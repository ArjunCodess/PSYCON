"""Generate the two canonical Protocol v2 binary fixtures."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.chunk import encode_chunk_v2  # noqa: E402


FIXTURES = ROOT / "protocol" / "fixtures"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)

    audio_payload = struct.pack(
        "<8h",
        -32768,
        -12345,
        -1,
        0,
        1,
        12345,
        32767,
        2048,
    )
    audio = encode_chunk_v2(
        stream_type="audio_pcm",
        device_id=0xE001A001,
        sequence=42,
        device_timestamp_us=1_700_000_000_123_456,
        sample_count=8,
        sample_period_us=125,
        payload=audio_payload,
    )

    wrist_payload = b"".join(
        struct.pack("<IIIHh", *record)
        for record in (
            (1000, 50000, 60000, 1234, 3150),
            (1001, 50010, 60020, 1240, 3155),
        )
    )
    wrist = encode_chunk_v2(
        stream_type="wrist_batch",
        device_id=0xB001C002,
        sequence=7,
        device_timestamp_us=1_700_000_000_999_000,
        sample_count=2,
        sample_period_us=40_000,
        payload=wrist_payload,
    )

    (FIXTURES / "audio.bin").write_bytes(audio)
    (FIXTURES / "wrist.bin").write_bytes(wrist)
    print(f"audio.bin: {len(audio)} bytes, crc32=0x{int.from_bytes(audio[36:40], 'little'):08x}")
    print(f"wrist.bin: {len(wrist)} bytes, crc32=0x{int.from_bytes(wrist[36:40], 'little'):08x}")


if __name__ == "__main__":
    main()
