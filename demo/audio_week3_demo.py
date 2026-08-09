"""Run the Week 3 audio pipeline on deterministic Protocol v2 packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ml.src.audio import analyze_audio_packet
from ml.src.audio_fixtures import all_fixtures
from protocol.chunk import encode_chunk_v2


SAMPLE_RATE_HZ = 16_000


def run_demo(output_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    first_sample_index = 0
    for sequence, (name, samples) in enumerate(all_fixtures(SAMPLE_RATE_HZ).items(), start=1):
        packet = _packet(samples, sequence)
        analysis = analyze_audio_packet(
            packet,
            session_id="week3-synthetic-demo",
            first_sample_index=first_sample_index,
            nominal_sample_rate_hz=SAMPLE_RATE_HZ,
        )
        rows.append({"case": name, **analysis.to_dict()})
        first_sample_index += len(samples)

    rows.append(
        {
            "case": "missing",
            **analyze_audio_packet(None, session_id="week3-synthetic-demo").to_dict(),
        }
    )
    corrupt_packet = bytearray(_packet(all_fixtures(SAMPLE_RATE_HZ)["tone"], 99))
    corrupt_packet[-1] ^= 0xFF
    rows.append(
        {
            "case": "corrupt",
            **analyze_audio_packet(bytes(corrupt_packet), session_id="week3-synthetic-demo").to_dict(),
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return rows


def _packet(samples: np.ndarray, sequence: int) -> bytes:
    return encode_chunk_v2(
        stream_type="audio_pcm",
        device_id=3,
        sequence=sequence,
        device_timestamp_us=sequence * 2_000_000,
        sample_count=len(samples),
        sample_period_us=62,
        payload=samples.astype("<i2").tobytes(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/demo/audio_week3_demo.json"),
        help="JSON report path",
    )
    args = parser.parse_args()
    rows = run_demo(args.output)
    print("case         status                rms dBFS       f0 Hz")
    for row in rows:
        features = row["features"]
        rms = f'{features["rms_dbfs"]:8.2f}' if features else "       -"
        f0 = f'{features["f0_hz"]:8.2f}' if features else "       -"
        print(f'{row["case"]:<12} {row["status"]:<20} {rms} {f0}')
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
