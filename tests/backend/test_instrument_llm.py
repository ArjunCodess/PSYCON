"""Local service recovery must preserve the experiment's pinned model identity."""
import io
import json
import os
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from backend.instrument import local_llm, research


def test_connection_failure_identifies_service_and_does_not_replace_model(monkeypatch, tmp_path):
    monkeypatch.setattr(local_llm, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(local_llm, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError(ConnectionRefusedError())))
    with pytest.raises(local_llm.LocalLLMUnavailable, match="Cannot connect to local Ollama"):
        research.Ollama().digest()


def test_server_failure_is_not_treated_as_a_stopped_service(monkeypatch):
    monkeypatch.setattr(local_llm, "urlopen", lambda *a, **k: (_ for _ in ()).throw(HTTPError("local", 500, "error", {}, None)))
    monkeypatch.setattr(local_llm.subprocess, "Popen", lambda *a, **k: pytest.fail("must not replace a running server"))
    with pytest.raises(local_llm.LocalLLMError, match="HTTP 500"):
        local_llm.local_models("http://127.0.0.1:11434")


@pytest.mark.parametrize("models, expected, message", [
    ([], "pin", "not installed"),
    ([{"name": "qwen3.5:4b", "digest": "changed"}], "pin", "differs from PSYCON_OLLAMA_DIGEST"),
    ([{"name": "qwen3.5:4b", "digest": ""}], "", "did not supply a model digest"),
])
def test_model_readiness_failure_remains_specific(monkeypatch, models, expected, message):
    monkeypatch.setenv("PSYCON_OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setenv("PSYCON_OLLAMA_DIGEST", expected)
    monkeypatch.setattr(research, "local_models", lambda url: models)
    with pytest.raises(local_llm.LocalLLMError, match=message):
        research.Ollama().digest()


def test_stopped_bundled_service_recovers_with_private_local_configuration(monkeypatch, tmp_path):
    binary = tmp_path / ".runtime" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(local_llm, "PROJECT_ROOT", tmp_path)
    attempts = iter([False, False, True])
    def models(url, **kwargs):
        if not next(attempts):
            raise local_llm.LocalLLMUnavailable("stopped")
        return [{"name": "qwen3.5:4b", "digest": "pin"}]
    monkeypatch.setattr(local_llm, "_models", models)
    started = []
    def start(args, **kwargs):
        started.append((args, kwargs))
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(local_llm.subprocess, "Popen", start)
    assert local_llm.local_models("http://127.0.0.1:11434")[0]["digest"] == "pin"
    assert len(started) == 1 and started[0][0] == [str(binary), "serve"]
    environment = started[0][1]["env"]
    assert environment["OLLAMA_MODELS"] == str(tmp_path / ".runtime" / "models" / "ollama")
    assert environment["OLLAMA_NO_CLOUD"] == "1"
    assert environment["OLLAMA_HOST"] == "127.0.0.1:11434"


def test_available_service_is_reused_without_starting_another_process(monkeypatch):
    monkeypatch.setattr(local_llm, "urlopen", lambda *a, **k: io.BytesIO(json.dumps({"models": [{"name": "qwen3.5:4b", "digest": "pin"}]}).encode()))
    monkeypatch.setattr(local_llm.subprocess, "Popen", lambda *a, **k: pytest.fail("must reuse the service"))
    assert local_llm.local_models("http://127.0.0.1:11434")[0]["digest"] == "pin"


def test_failed_background_start_reports_log_location(monkeypatch, tmp_path):
    binary = tmp_path / ".runtime" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(local_llm, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(local_llm, "_models", lambda *a, **k: (_ for _ in ()).throw(local_llm.LocalLLMUnavailable("stopped")))
    monkeypatch.setattr(local_llm.subprocess, "Popen", lambda *a, **k: SimpleNamespace(poll=lambda: 1))
    with pytest.raises(local_llm.LocalLLMUnavailable, match="ollama-stderr.log"):
        local_llm.local_models("http://127.0.0.1:11434")


def test_generation_restricts_citations_to_target_without_removing_interaction_context(monkeypatch):
    monkeypatch.setattr(research.Ollama, "digest", lambda self: "pin")
    requests = []
    def reply(request, **kwargs):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"message": {"content": '{"claims": [], "summary": "Limited evidence", "limitations": []}'}}).encode())
    monkeypatch.setattr(research, "urlopen", reply)
    packet = {"target_speaker_id": "target", "transcript": [
        {"id": "own-turn", "speaker_id": "target"}, {"id": "response", "speaker_id": "other"}],
        "evidence": [{"id": "own-event", "speaker_id": "target"}, {"id": "other-event", "speaker_id": "other"}]}
    research.Ollama().generate(packet, "pin")
    payload = requests[0]
    allowed = payload["format"]["properties"]["claims"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
    assert allowed == ["own-turn", "own-event"]
    assert json.loads(payload["messages"][1]["content"])["transcript"] == packet["transcript"]
    assert payload["options"]["num_predict"] == research.GENERATION_OPTIONS["num_predict"]


def test_truncated_generation_is_withheld_with_specific_error(monkeypatch):
    monkeypatch.setattr(research.Ollama, "digest", lambda self: "pin")
    monkeypatch.setattr(research, "urlopen", lambda *a, **k: io.BytesIO(json.dumps({
        "done_reason": "length", "message": {"content": '{"claims": ['}}).encode()))
    with pytest.raises(ValueError, match="output limit.*partial interpretation withheld"):
        research.Ollama().generate({"target_speaker_id": "target", "transcript": [{"id": "own", "speaker_id": "target"}]}, "pin")
