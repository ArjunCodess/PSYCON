from __future__ import annotations

import pytest

from backend.services import IngestError, decode_or_error
from backend.simulator import audio_packet, wrist_packet
from protocol.chunk import AudioChunkV2, WristChunkV2, decode_chunk_v2


def test_simulator_builds_full_protocol_v2_audio_and_wrist_packets() -> None:
    audio = decode_chunk_v2(audio_packet(101, 4, 9_000_000))
    wrist = decode_chunk_v2(wrist_packet(202, 7, 9_000_000))
    assert isinstance(audio, AudioChunkV2)
    assert audio.header.sample_count == 8_000
    assert isinstance(wrist, WristChunkV2)
    assert wrist.header.sample_count == 25


def test_ingest_decoder_classifies_crc_errors_without_payload_values() -> None:
    packet = audio_packet(101, 4, 9_000_000, corrupt=True)
    with pytest.raises(IngestError) as captured:
        decode_or_error(packet)
    assert captured.value.code == "invalid_crc"
    assert captured.value.status_code == 400
    assert "CRC" in str(captured.value)
    assert "7500" not in str(captured.value)
