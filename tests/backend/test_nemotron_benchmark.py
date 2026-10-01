import numpy as np
import pytest

from backend.group import nemotron_benchmark, psycon
from ml.src.speaker_analysis import SpeakerTurn
from ml.src.transcription import TranscriptionResult, TranscriptionStatus


def test_raw_channel_diagnostics_do_not_stretch_time_or_merge_overlap():
    probabilities = np.zeros((201, 8))
    probabilities[:150, 0] = .8
    probabilities[100:, 1] = .6
    stats = nemotron_benchmark.activity_diagnostics(probabilities, 2.005)
    assert stats["speech_union_s"] == pytest.approx(2.005)
    assert stats["overlap_s"] == pytest.approx(.5)
    assert stats["channels"][0]["isolated_s"] == pytest.approx(1.)
    assert stats["channels"][1]["speech_s"] == pytest.approx(1.005)
    assert nemotron_benchmark.activity_diagnostics(probabilities, 2.005, threshold=.7)["channels_over_one_second"] == 1
    with pytest.raises(ValueError, match="timing_mismatch"):
        nemotron_benchmark.activity_diagnostics(probabilities, 10.)


def test_guarded_nemotron_profiles_are_isolated_benchmark_outputs():
    samples = (1000*np.sin(2*np.pi*180*np.arange(12*16000)/16000)).astype(np.int16)
    rows = psycon.clean_windows([SpeakerTurn(0, 4, "nemotron-speaker-0"),
                                SpeakerTurn(8, 12, "nemotron-speaker-0"),
                                SpeakerTurn(9, 10, "nemotron-speaker-1")], 12)
    clean = [row for row in rows if row["cluster_label"] == "nemotron-speaker-0"]
    vector = np.zeros(192)
    vector[0] = 1.
    embeddings = {row["id"]: vector for row in clean}
    observations = [{"source_segment_id": row["id"], "cluster_label": row["cluster_label"],
                     "slot_number": 1, "start_s": row["start_s"], "end_s": row["end_s"],
                     "reliable": True, "score": .95, "competing_score": .05}
                    for row in (clean[0], clean[-1])]
    class Embedder:
        engine_name = "fake-ecapa"
        def embed(self, *_):
            return vector
    class Transcriber:
        def transcribe(self, *_):
            return TranscriptionResult(TranscriptionStatus.NO_SPEECH, "", None, 0., 0., (), "fake")
    profiles, _ = nemotron_benchmark.attribute(
        samples, rows, observations, embeddings, [{"slot_number": 1}],
        embedder=Embedder(), transcriber=Transcriber())
    assert profiles[0]["status"] == "ready"
    assert profiles[0]["usable_seconds"] >= 3
    assert profiles[0]["metrics"]["benchmark_only"] is True
    assert psycon.training_vector([0.]*80, profiles[0]) is None
    assert all(row["status"] == "unknown" for row in rows if row["overlap_refused_s"])
