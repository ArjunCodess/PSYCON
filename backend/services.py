from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import numpy as np

from ml.src.audio import FEATURE_EXTRACTOR, analyze_audio_packet
from protocol.chunk import AudioChunkV2, ChunkV2DecodeError, WristChunkV2, decode_chunk_v2


class IngestError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def decode_or_error(packet: bytes):
    try:
        return decode_chunk_v2(packet)
    except ChunkV2DecodeError as error:
        message = str(error)
        if "version" in message:
            code = "unsupported_version"
        elif "stream" in message:
            code = "unsupported_stream"
        elif "CRC" in message:
            code = "invalid_crc"
        elif "payload" in message:
            code = "invalid_payload"
        else:
            code = "invalid_header"
        raise IngestError(code, message, 400) from error


class IngestionService:
    def __init__(self, repository, storage) -> None:
        self.repository = repository
        self.storage = storage

    def ingest(self, session_id: str, packet: bytes, principal) -> tuple[str, dict]:
        chunk = decode_or_error(packet)
        header = chunk.header
        if principal.role == "device" and principal.device_id != header.device_id:
            raise IngestError("device_mismatch", "Credential is not valid for this device", 403)
        if principal.role == "device" and not self.repository.session_allows_device(session_id, principal.id, header.device_id):
            raise IngestError("session_forbidden", "Device is not assigned to this session", 403)
        existing = self.repository.existing_chunk(header.device_id, header.stream_type, header.sequence)
        if existing:
            if existing["payload_length"] == header.payload_length and existing["crc32"] == header.crc32:
                return "already_present", existing
            raise IngestError("sequence_conflict", "Immutable chunk key already exists with different bytes", 409)
        key = f"sessions/{session_id}/raw/{header.device_id}/{header.stream_type}/{header.sequence:010d}-{header.crc32:08x}.bin"
        try:
            stored = self.storage.put_immutable(key, packet, "application/vnd.psycon.chunk-v2")
            row = self.repository.insert_chunk(session_id, chunk, stored)
        except (LookupError, ValueError):
            try:
                self.storage.delete(key)
            finally:
                raise
        except Exception as error:
            raise IngestError("storage_error", "Chunk could not be stored", 500) from error
        return "accepted", row


class Processor:
    def __init__(self, repository, storage, inference) -> None:
        self.repository = repository
        self.storage = storage
        self.inference = inference

    def process_session(self, session_id: str) -> None:
        for row in self.repository.chunks_for_session(session_id):
            packet = self.storage.get(row["object_key"])
            chunk = decode_chunk_v2(packet)
            if isinstance(chunk, AudioChunkV2):
                analysis = analyze_audio_packet(packet, session_id=session_id)
                payload = analysis.to_dict()
                feature = self.repository.save_feature(
                    session_id, row["id"], "audio", payload["status"], FEATURE_EXTRACTOR,
                    payload["features"], payload["provenance"] or {},
                )
                decision = self.inference.evaluate(payload["features"])
                self.repository.save_inference(session_id, feature["id"], decision)
            elif isinstance(chunk, WristChunkV2):
                values = chunk.samples
                features = {
                    "ppg_red_mean": float(np.mean([sample.ppg_red for sample in values])),
                    "ppg_ir_mean": float(np.mean([sample.ppg_ir for sample in values])),
                    "eda_adc_mean": float(np.mean([sample.eda_adc for sample in values])),
                    "temperature_c_mean": float(np.mean([sample.temperature_centi_c for sample in values]) / 100),
                }
                provenance = {
                    "session_id": session_id,
                    "device_id": chunk.header.device_id,
                    "sequence": chunk.header.sequence,
                    "device_timestamp_us": chunk.header.device_timestamp_us,
                    "sample_count": chunk.header.sample_count,
                    "sample_rate_hz": round(1_000_000 / chunk.header.sample_period_us),
                    "source_sha256": hashlib.sha256(packet).hexdigest(),
                }
                feature = self.repository.save_feature(
                    session_id, row["id"], "wrist", "raw_uncalibrated", "psycon_wrist_raw", features, provenance,
                )
                decision = self.inference.evaluate(features)
                self.repository.save_inference(session_id, feature["id"], decision)


class ExportService:
    def __init__(self, repository, storage) -> None:
        self.repository = repository
        self.storage = storage

    def build(self, session_id: str) -> dict:
        session = self.repository.session(session_id)
        if session is None:
            raise LookupError("session not found")
        rows = self.repository.export_rows(session_id)
        files: dict[str, bytes] = {
            "metadata/session.json": _json_bytes(session),
        }
        for name, records in rows.items():
            files[f"metadata/{name}.json"] = _json_bytes(records)
        for chunk in rows["chunks"]:
            name = f"raw/{chunk['device_id']}/{chunk['stream_type']}/{chunk['sequence']}.bin"
            files[name] = self.storage.get(chunk["object_key"])
        manifest = {
            "format": "psycon-research-export-v1",
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in sorted(files.items())},
        }
        files["manifest.json"] = _json_bytes(manifest)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
        data = buffer.getvalue()
        key = f"sessions/{session_id}/exports/{hashlib.sha256(data).hexdigest()}.zip"
        stored = self.storage.put_immutable(key, data, "application/zip")
        return self.repository.save_export(session_id, stored)


def _json_bytes(value) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8")
