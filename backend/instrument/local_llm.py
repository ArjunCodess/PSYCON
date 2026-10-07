"""Recover the installed local Ollama service without downloading or changing models."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_start_lock = threading.Lock()


class LocalLLMError(ValueError):
    pass


class LocalLLMUnavailable(LocalLLMError):
    pass


def _models(url, timeout=3):
    try:
        with urlopen(url + "/api/tags", timeout=timeout) as response:
            models = json.load(response)["models"]
        if not isinstance(models, list):
            raise ValueError("Invalid model list")
        return models
    except HTTPError as exc:
        raise LocalLLMError(f"Local Ollama returned HTTP {exc.code}. Check its service logs.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LocalLLMUnavailable(
            f"Cannot connect to local Ollama at {url}. Start Ollama and retry; no interpretation was generated."
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise LocalLLMError("Local Ollama returned an invalid model list. Check its service logs.") from exc


def local_models(url):
    try:
        return _models(url)
    except LocalLLMUnavailable:
        endpoint = urlsplit(url)
        runtime = PROJECT_ROOT / ".runtime"
        binary = runtime / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
        # Container endpoints and independently installed services remain operator-managed.
        if endpoint.hostname not in ("127.0.0.1", "localhost") or endpoint.path or not binary.is_file():
            raise
    with _start_lock:
        try:
            return _models(url)  # Another request may already have recovered the service.
        except LocalLLMUnavailable:
            pass
        logs = runtime / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(OLLAMA_HOST=f"127.0.0.1:{endpoint.port or 80}",
                           OLLAMA_MODELS=str(runtime / "models" / "ollama"),
                           OLLAMA_KEEP_ALIVE="0", OLLAMA_NO_CLOUD="1")
        try:
            with (logs / "ollama-stdout.log").open("ab") as stdout, (logs / "ollama-stderr.log").open("ab") as stderr:
                process = subprocess.Popen([str(binary), "serve"], cwd=PROJECT_ROOT, env=environment,
                                           stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                           start_new_session=os.name != "nt")
        except OSError as exc:
            raise LocalLLMUnavailable("The bundled Ollama service could not start. Check .runtime/logs/ollama-stderr.log.") from exc
        for _ in range(40):
            try:
                return _models(url, timeout=.5)
            except LocalLLMUnavailable:
                if process.poll() is not None:
                    break
                time.sleep(.25)
        raise LocalLLMUnavailable("The bundled Ollama service did not become ready. Check .runtime/logs/ollama-stderr.log and retry.")
