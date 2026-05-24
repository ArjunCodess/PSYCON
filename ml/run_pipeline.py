from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.src.config import PROCESSED_DIR, WESAD_RAW_DIR
from ml.src.features import extract_windows
from ml.src.models.train import train_all
from ml.src.preprocess import subject_to_frame
from ml.src.wesad import discover_subjects, load_subject


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Psycon WESAD feature extraction and model training.")
    parser.add_argument("--raw-dir", type=Path, default=WESAD_RAW_DIR)
    parser.add_argument("--limit-subjects", type=int, default=None)
    parser.add_argument("--features-only", action="store_true")
    args = parser.parse_args()

    subjects = discover_subjects(args.raw_dir)
    if args.limit_subjects:
        subjects = subjects[: args.limit_subjects]
    if not subjects:
        raise SystemExit(f"No WESAD subject pickle files found in {args.raw_dir}")

    feature_frames = []
    for subject in subjects:
        print(f"Loading {subject.subject_id} from {subject.path}")
        data = load_subject(subject)
        frame = subject_to_frame(subject.subject_id, data)
        windows = extract_windows(frame)
        print(f"  extracted {len(windows)} labeled windows")
        feature_frames.append(windows)

    features = pd.concat(feature_frames, ignore_index=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "wesad_features.csv"
    features.to_csv(output_path, index=False)
    print(f"Wrote {len(features)} windows to {output_path}")

    if not args.features_only:
        metrics = train_all(features)
        print(f"Wrote metrics for {len(metrics['models'])} model/modality runs")


if __name__ == "__main__":
    main()
