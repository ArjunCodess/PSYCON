from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.src.config import CHARTS_DIR, PROCESSED_DIR, RESULTS_DIR, WESAD_RAW_DIR
from ml.src.features import add_subject_baseline_features, extract_windows
from ml.src.models.train import train_all
from ml.src.preprocess import subject_to_frame
from ml.src.wesad import discover_subjects, load_subject


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PSYCON WESAD feature extraction and model training.")
    parser.add_argument("--raw-dir", type=Path, default=WESAD_RAW_DIR)
    parser.add_argument("--limit-subjects", type=int, default=None)
    parser.add_argument("--features-only", action="store_true")
    args = parser.parse_args()

    subjects = discover_subjects(args.raw_dir)
    if args.limit_subjects:
        subjects = subjects[: args.limit_subjects]
    if not subjects:
        raise SystemExit(f"No WESAD subject pickle files found in {args.raw_dir}")

    print("\nPSYCON WESAD pipeline")
    print("=====================")
    print(f"Raw data: {args.raw_dir}")
    print(f"Subjects discovered: {len(subjects)}")
    print("")

    feature_frames = []
    for subject in subjects:
        print(f"Loading {subject.subject_id} from {subject.path}")
        data = load_subject(subject)
        frame = subject_to_frame(subject.subject_id, data)
        windows = extract_windows(frame)
        print(f"  extracted {len(windows)} labeled windows")
        feature_frames.append(windows)

    features = add_subject_baseline_features(pd.concat(feature_frames, ignore_index=True))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "wesad_features.csv"
    features.to_csv(output_path, index=False)
    print("")
    print("Feature dataset")
    print("---------------")
    print(f"Total windows: {len(features):,}")
    print(f"Subjects used: {features['subject'].nunique()}")
    for label, count in features["label"].value_counts().sort_index().items():
        print(f"{label}: {count:,}")
    print(f"Processed CSV: {output_path}")

    if not args.features_only:
        metrics = train_all(features)
        _print_results_summary(metrics)


def _print_results_summary(metrics: dict) -> None:
    comparison = pd.DataFrame(metrics["models"]).sort_values(
        ["accuracy", "recall", "precision"],
        ascending=[False, False, False],
    )
    best_multimodal = comparison[comparison["modality"] == "multimodal"].head(1)

    print("")
    print("Model results")
    print("-------------")
    print(f"Evaluated runs: {len(comparison)}")
    print("")
    print("Top results:")
    print(comparison[["name", "modality", "accuracy", "precision", "recall", "false_positive_rate", "actual_stress", "predicted_stress"]].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    if not best_multimodal.empty:
        row = best_multimodal.iloc[0]
        print("")
        print(
            "Best multimodal: "
            f"{row['name']} "
            f"(accuracy={row['accuracy']:.3f}, precision={row['precision']:.3f}, "
            f"recall={row['recall']:.3f}, fpr={row['false_positive_rate']:.3f})"
        )

    print("")
    print("Generated artifacts")
    print("-------------------")
    for path in [
        RESULTS_DIR / "metrics.json",
        RESULTS_DIR / "model_comparison.csv",
        RESULTS_DIR / "app_model.json",
        RESULTS_DIR / "logistic_multimodal.joblib",
        CHARTS_DIR / "model_comparison.png",
    ]:
        print(path)


if __name__ == "__main__":
    main()
