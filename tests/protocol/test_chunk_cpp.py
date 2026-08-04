from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_cpp_codec_decodes_canonical_fixtures(tmp_path: Path) -> None:
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("g++ is required for the host C++ protocol conformance test")

    executable = tmp_path / "test_chunk_v2.exe"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "protocol" / "cpp" / "test_chunk_v2.cpp"),
            "-o",
            str(executable),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run(
        [str(executable), str(ROOT / "protocol" / "fixtures")],
        check=True,
        cwd=ROOT,
    )
