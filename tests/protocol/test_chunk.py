from __future__ import annotations

from pathlib import Path

import pytest

from protocol.chunk import ChunkV2DecodeError, decode_chunk_v2


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "protocol" / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def changed(packet: bytes, offset: int, value: int) -> bytes:
    mutable = bytearray(packet)
    mutable[offset] = value
    return bytes(mutable)


def test_decodes_audio_fixture_exactly() -> None:
    chunk = decode_chunk_v2(fixture("audio.bin"))

    assert chunk.stream_type == "audio_pcm"
    assert chunk.header.protocol_version == 2
    assert chunk.header.header_length == 40
    assert chunk.header.flags == 0
    assert chunk.header.device_id == 0xE001A001
    assert chunk.header.sequence == 42
    assert chunk.header.device_timestamp_us == 1_700_000_000_123_456
    assert chunk.header.sample_count == 8
    assert chunk.header.sample_period_us == 125
    assert chunk.header.payload_length == 16
    assert chunk.header.crc32 == 0xBAA9F379
    assert chunk.samples == (-32768, -12345, -1, 0, 1, 12345, 32767, 2048)


def test_decodes_wrist_fixture_exactly() -> None:
    chunk = decode_chunk_v2(fixture("wrist.bin"))

    assert chunk.stream_type == "wrist_batch"
    assert chunk.header.device_id == 0xB001C002
    assert chunk.header.sequence == 7
    assert chunk.header.device_timestamp_us == 1_700_000_000_999_000
    assert chunk.header.sample_count == 2
    assert chunk.header.sample_period_us == 40_000
    assert chunk.header.payload_length == 32
    assert chunk.header.crc32 == 0x0BA0F731
    assert [
        (
            sample.sample_index,
            sample.ppg_red,
            sample.ppg_ir,
            sample.eda_adc,
            sample.temperature_centi_c,
        )
        for sample in chunk.samples
    ] == [
        (1000, 50000, 60000, 1234, 3150),
        (1001, 50010, 60020, 1240, 3155),
    ]


def test_rejects_canonical_invalid_crc_fixture() -> None:
    with pytest.raises(ChunkV2DecodeError, match="CRC mismatch"):
        decode_chunk_v2(fixture("invalid_crc.bin"))


@pytest.mark.parametrize(
    ("packet", "message"),
    [
        (bytes(39), "shorter than"),
        (lambda: changed(fixture("audio.bin"), 0, 0), "magic"),
        (lambda: changed(fixture("audio.bin"), 4, 3), "version"),
        (lambda: changed(fixture("audio.bin"), 5, 39), "header length"),
        (lambda: changed(fixture("audio.bin"), 6, 9), "stream type"),
        (lambda: changed(fixture("audio.bin"), 7, 1), "flags"),
        (lambda: changed(fixture("audio.bin"), 32, 15), "packet length"),
        (lambda: changed(fixture("audio.bin"), 40, 1), "CRC"),
    ],
)
def test_rejects_invalid_chunks(packet: bytes | object, message: str) -> None:
    data = packet() if callable(packet) else packet
    with pytest.raises(ChunkV2DecodeError, match=message):
        decode_chunk_v2(data)
