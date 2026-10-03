"""Explicit, operator-reviewed links to existing research and device sources."""
import hashlib
import io
import wave

import numpy as np

from backend.auth import Principal
from ml.src.audio_recording import decode_audio, analyze_decoded_recording
from protocol.chunk import AudioChunkV2, decode_chunk_v2
from .analysis import observations


def assemble_device_audio(packets, rows):
    if len(packets) != len(rows):
        raise ValueError("every audio packet needs a timing record")
    pairs = sorted(zip(rows, packets), key=lambda pair: int(pair[0].get("synchronized_timestamp_us") or 0))
    if not pairs or any(row.get("synchronized_timestamp_us") is None for row, _ in pairs):
        raise ValueError("synchronized audio is required")
    blocks, previous_end, device = [], None, None
    for row, raw in pairs:
        packet = decode_chunk_v2(raw)
        if not isinstance(packet, AudioChunkV2) or packet.header.sample_period_us not in {62, 63}:
            raise ValueError("only 16 kHz PCM audio is supported")
        if device is not None and packet.header.device_id != device:
            raise ValueError("one audio device per conversation is required")
        device = packet.header.device_id
        start = int(row["synchronized_timestamp_us"])
        uncertainty = row.get("sync_uncertainty_us")
        if uncertainty is None or not 0 <= int(uncertainty) <= 5000:
            raise ValueError("audio clock uncertainty exceeds 5 ms")
        if previous_end is not None and abs(start-previous_end) > 5000:
            raise ValueError("audio gaps or overlap require separate conversations; never concatenate them")
        samples = np.asarray(packet.samples, dtype="<i2")
        blocks.append(samples)
        previous_end = start+len(samples)/16000*1_000_000
    pcm = np.concatenate(blocks)
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm.tobytes())
    return output.getvalue()


class SourceAdapters:
    def __init__(self, group, repository, storage):
        self.group, self.repository, self.storage = group, repository, storage

    def group_descriptor(self, session_id, slot):
        actor = Principal("communication-source-link", "operator", None, "Communication operator")
        self.group.get_session(actor, session_id)
        stored = self.group.store.session(session_id)
        if stored["consent_status"] != "recorded":
            raise ValueError("group recording consent is required")
        participant = next((p for p in self.group.store.participants(session_id) if p["slot_number"] == slot), None)
        if not participant or participant.get("withdrawn_at"):
            raise ValueError("participant is unavailable or withdrawn")
        details = self.group.face_voice_details(actor, session_id, "psycon")
        person = next((p for p in details["people"] if p["slot_number"] == slot), None)
        if not person or (person.get("voice") or {}).get("status") != "ready":
            raise ValueError("current guarded PSYCON profile must be ready")
        recording = self.group.store.recording_for_session(session_id)
        return {"type": "group_reference", "session_id": session_id, "slot": slot,
                "participant_id": participant["id"], "recording_sha256": recording["sha256"],
                "occurred_at": stored["recording_start_time"], "fingerprint": recording["sha256"]+f":slot:{slot}"}

    def group_analysis(self, source):
        # Recheck consent, withdrawal and current matching when the job actually runs.
        self.group_descriptor(source["session_id"], source["slot"])
        record = self.group.store.recording_for_session(source["session_id"])
        audio_key = record.get("audio_object_key")
        if not audio_key:
            raise ValueError("shared source audio unavailable")
        decoded = decode_audio(self.storage.get(audio_key))
        quality = analyze_decoded_recording(decoded, "group.wav", source["recording_sha256"])
        segments = self.group.store.voice_segments_for(source["session_id"], "psycon")
        selected = [s for s in segments if s.get("slot_number") == source["slot"] and s.get("status") == "assigned"
                    and (s.get("evidence") or {}).get("training_eligible", True)]
        own = [{"start_s": s["start_s"], "end_s": s["end_s"], "speaker_id": "wearer"} for s in selected]
        other = [{"start_s": s["start_s"], "end_s": s["end_s"], "speaker_id": "other"} for s in segments
                 if s.get("slot_number") != source["slot"] and s.get("status") == "assigned"]
        turns = sorted(own+other, key=lambda t:t["start_s"])
        profile = next(p for p in self.group.store.voice_profiles_for(source["session_id"], "psycon") if p["slot_number"] == source["slot"])
        transcription = profile.get("metrics", {}).get("transcription", {})
        words = [{**w, "speaker_id": "wearer"} for w in transcription.get("words", [])
                 if any(w["start_s"] >= t["start_s"] and w["end_s"] <= t["end_s"] for t in own)]
        result = observations(decoded.samples, decoded.sample_rate_hz, turns, turns, words, "wearer", quality["windows"], "verified")
        # Clean assigned windows omit ambiguous overlap. Missing timing evidence isn't a zero.
        for metric in ("candidate_interruptions_per_min", "response_gap_s", "pause_mean_s", "mean_turn_duration_s"):
            result["metrics"].pop(metric, None)
        result.update(language=transcription.get("language"), attribution_status="operator_linked_guarded_profile",
                      engines={"source": "guarded_psycon"}, limitations=["Assigned windows do not establish complete turn boundaries; conversational timing abstains."])
        return result

    def device_descriptor(self, session_id, pid):
        row = self.repository.session(session_id)
        if not row or row["state"] != "complete":
            raise ValueError("close the device session before import")
        metadata = row.get("metadata", {})
        if metadata.get("communication_profile_id") != pid:
            raise ValueError("device session must explicitly name this communication profile")
        rows = self.repository.chunks_for_session(session_id, "audio_pcm")
        digest = hashlib.sha256("".join(r["sha256"] for r in rows).encode()).hexdigest()
        return {"type": "device_reference", "session_id": session_id, "fingerprint": digest,
                "recording_sha256": digest, "occurred_at": row["started_at"]}

    def device_audio(self, source):
        rows = self.repository.chunks_for_session(source["session_id"], "audio_pcm")
        if sum(r["payload_length"] for r in rows) > 32*1024*1024:
            raise ValueError("split device sessions into uploads of at most 32 MB")
        return assemble_device_audio([self.storage.get(r["object_key"]) for r in rows], rows)
