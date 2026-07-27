"""Encoder and decoder for the Psycon binary chunk contract."""

from __future__ import annotations

import binascii
import struct
from dataclasses import dataclass
from typing import Literal, TypeAlias


HEADER_LENGTH = 40
MAX_PAYLOAD_LENGTH = 65_536
WRIST_RECORD_LENGTH = 16

StreamType: TypeAlias = Literal["audio_pcm", "wrist_batch"]
_STREAM_CODES: dict[StreamType, int] = {"audio_pcm": 1, "wrist_batch": 2}
_CODE_STREAMS = {code: name for name, code in _STREAM_CODES.items()}
_HEADER = struct.Struct("<4sBBBBIIQIIII")
_HEADER_WITHOUT_CRC = struct.Struct("<4sBBBBIIQIII")
_WRIST_RECORD = struct.Struct("<IIIHh")


class ChunkV2DecodeError(ValueError):
    """Raised when bytes do not satisfy the Protocol v2 contract."""


@dataclass(frozen=True)
class ChunkV2Header:
    protocol_version: int
    header_length: int
    stream_type: StreamType
    flags: int
    device_id: int
    sequence: int
    device_timestamp_us: int
    sample_count: int
    sample_period_us: int
    payload_length: int
    crc32: int


@dataclass(frozen=True)
class WristSampleV2:
    sample_index: int
    ppg_red: int
    ppg_ir: int
    eda_adc: int
    temperature_centi_c: int


@dataclass(frozen=True)
class AudioChunkV2:
    stream_type: Literal["audio_pcm"]
    header: ChunkV2Header
    samples: tuple[int, ...]


@dataclass(frozen=True)
class WristChunkV2:
    stream_type: Literal["wrist_batch"]
    header: ChunkV2Header
    samples: tuple[WristSampleV2, ...]


ChunkV2: TypeAlias = AudioChunkV2 | WristChunkV2


def _crc32(packet: bytes) -> int:
    crc = binascii.crc32(packet[:36])
    return binascii.crc32(packet[HEADER_LENGTH:], crc) & 0xFFFFFFFF


def decode_chunk_v2(packet: bytes) -> ChunkV2:
    """Decode and fully validate one complete Protocol v2 packet."""

    if not isinstance(packet, bytes):
        raise TypeError("Protocol v2 packet must be bytes")
    if len(packet) < HEADER_LENGTH:
        raise ChunkV2DecodeError("Protocol v2 packet is shorter than its 40-byte header")

    (
        magic,
        protocol_version,
        header_length,
        stream_code,
        flags,
        device_id,
        sequence,
        device_timestamp_us,
        sample_count,
        sample_period_us,
        payload_length,
        stored_crc32,
    ) = _HEADER.unpack_from(packet)

    if magic != b"PSY2":
        raise ChunkV2DecodeError(f"invalid Protocol v2 magic: {magic!r}")
    if protocol_version != 2:
        raise ChunkV2DecodeError(f"unsupported Protocol version: {protocol_version}")
    if header_length != HEADER_LENGTH:
        raise ChunkV2DecodeError(f"invalid Protocol v2 header length: {header_length}")
    if stream_code not in _CODE_STREAMS:
        raise ChunkV2DecodeError(f"unsupported Protocol v2 stream type: {stream_code}")
    if flags != 0:
        raise ChunkV2DecodeError(f"unsupported Protocol v2 flags: {flags}")
    if payload_length > MAX_PAYLOAD_LENGTH:
        raise ChunkV2DecodeError(f"Protocol v2 payload exceeds {MAX_PAYLOAD_LENGTH} bytes")
    if len(packet) != HEADER_LENGTH + payload_length:
        raise ChunkV2DecodeError(
            f"Protocol v2 packet length {len(packet)} does not match "
            f"header payload length {payload_length}"
        )
    if sample_count == 0:
        raise ChunkV2DecodeError("Protocol v2 sample count must be nonzero")
    if sample_period_us == 0:
        raise ChunkV2DecodeError("Protocol v2 sample period must be nonzero")

    computed_crc32 = _crc32(packet)
    if stored_crc32 != computed_crc32:
        raise ChunkV2DecodeError(
            f"Protocol v2 CRC mismatch: stored 0x{stored_crc32:08x}, "
            f"computed 0x{computed_crc32:08x}"
        )

    stream_type = _CODE_STREAMS[stream_code]
    header = ChunkV2Header(
        protocol_version=protocol_version,
        header_length=header_length,
        stream_type=stream_type,
        flags=flags,
        device_id=device_id,
        sequence=sequence,
        device_timestamp_us=device_timestamp_us,
        sample_count=sample_count,
        sample_period_us=sample_period_us,
        payload_length=payload_length,
        crc32=stored_crc32,
    )
    payload = packet[HEADER_LENGTH:]

    if stream_type == "audio_pcm":
        if payload_length != sample_count * 2:
            raise ChunkV2DecodeError(
                "Protocol v2 audio payload must contain one signed 16-bit value per sample"
            )
        samples = struct.unpack(f"<{sample_count}h", payload)
        return AudioChunkV2(stream_type="audio_pcm", header=header, samples=samples)

    if payload_length != sample_count * WRIST_RECORD_LENGTH:
        raise ChunkV2DecodeError(
            "Protocol v2 wrist payload must contain one 16-byte record per sample"
        )
    wrist_samples = tuple(
        WristSampleV2(*values)
        for values in _WRIST_RECORD.iter_unpack(payload)
    )
    return WristChunkV2(
        stream_type="wrist_batch",
        header=header,
        samples=wrist_samples,
    )


def encode_chunk_v2(
    *,
    stream_type: StreamType,
    device_id: int,
    sequence: int,
    device_timestamp_us: int,
    sample_count: int,
    sample_period_us: int,
    payload: bytes,
) -> bytes:
    """Build a Protocol v2 packet and validate the result through the decoder."""

    if len(payload) > MAX_PAYLOAD_LENGTH:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_LENGTH} bytes")
    prefix = _HEADER_WITHOUT_CRC.pack(
        b"PSY2",
        2,
        HEADER_LENGTH,
        _STREAM_CODES[stream_type],
        0,
        device_id,
        sequence,
        device_timestamp_us,
        sample_count,
        sample_period_us,
        len(payload),
    )
    crc32 = binascii.crc32(prefix)
    crc32 = binascii.crc32(payload, crc32) & 0xFFFFFFFF
    packet = prefix + struct.pack("<I", crc32) + payload
    decode_chunk_v2(packet)
    return packet
