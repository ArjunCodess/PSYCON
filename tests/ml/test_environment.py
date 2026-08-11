from __future__ import annotations

import os

from ml.src.environment import load_project_environment


def test_loads_dotenv_without_overriding_process_environment(tmp_path, monkeypatch) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text(
        "HF_TOKEN=hf_from_file\nPSYCON_PROFILE_KEY=profile_from_file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("PSYCON_PROFILE_KEY", "profile_from_process")

    assert load_project_environment(environment_file) is True
    assert os.environ["HF_TOKEN"] == "hf_from_file"
    assert os.environ["PSYCON_PROFILE_KEY"] == "profile_from_process"

    assert load_project_environment(environment_file, override=True) is True
    assert os.environ["PSYCON_PROFILE_KEY"] == "profile_from_file"
