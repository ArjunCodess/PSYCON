from __future__ import annotations

from pathlib import Path
from typing import Any


def write_markdown_report(path: Path, report: dict[str, Any], *, dataset_version: str, model_version: str) -> None:
    lines = [
        "# Week 5 fixture evaluation",
        "",
        "This report verifies the research software with deterministic synthetic records. It does not contain participant or hardware data, does not satisfy external validation, and does not support a clinical claim.",
        "",
        "## Versions and split",
        "",
        f"- Dataset: `{dataset_version}`",
        f"- Model run: `{model_version}`",
        f"- Participant assignment hash: `{report['split']['assignment_sha256']}`",
        f"- Participants by split: `{report['split']['participant_counts']}`",
        "",
        "Every modality used the same participant assignment. Preprocessing and model selection stayed inside the development participants, and the test participants were evaluated after selection.",
        "",
        "## Test comparison",
        "",
        "| Modality | Selected model | Accuracy | Precision | Recall | F1 | ROC-AUC | F1 95% CI |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for modality, result in report["modalities"].items():
        metrics = result["test"]
        interval = metrics["confidence_intervals_95"]["f1"]
        interval_text = "not available" if interval is None else f"{interval[0]:.3f} to {interval[1]:.3f}"
        auc = "not available" if metrics["roc_auc"] is None else f"{metrics['roc_auc']:.3f}"
        lines.append(
            f"| {modality} | {result['selected_model']} | {metrics['accuracy']:.3f} | {metrics['precision']:.3f} | "
            f"{metrics['recall']:.3f} | {metrics['f1']:.3f} | {auc} | {interval_text} |"
        )
    ablation = report["ablation"]
    lines.extend([
        "",
        "The combined-minus-physiology F1 difference is "
        f"{ablation['combined_minus_physiology_f1']:.3f}; the combined-minus-speech difference is {ablation['combined_minus_speech_f1']:.3f}. "
        "These fixture differences verify the ablation calculation and say nothing about real multimodal benefit.",
        "",
        "## Data quality and analysis coverage",
        "",
        f"The run contains {report['data_integrity']['windows']} windows from {report['data_integrity']['participants']} synthetic participants. "
        f"It preserves {report['data_integrity']['windows_with_missing_or_bad_modality']} windows with a missing or bad modality. "
        "The machine-readable report contains candidate validation metrics, grouped cross-validation scores, confusion matrices, false-positive and false-negative counts, participant-level bootstrap intervals, environment slices, motion slices, and 10, 30, and 60 second duration summaries.",
        "",
        "## Open gates",
        "",
        _open_gates_text(report),
        "",
        "## Limitations",
        "",
    ])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _open_gates_text(report: dict[str, Any]) -> str:
    external = report["external_validation"]
    if external["status"] == "evaluated":
        external_text = f"The run evaluated a separate dataset with {external['participant_count']} participants."
    else:
        external_text = "External validation remains blocked because no separate compatible dataset was supplied."
    return (
        f"{external_text} Approved participant collection still requires ethics approval, consent, physical calibration, and the earlier hardware safety gates. "
        "The duration analysis is descriptive until the approved protocol freezes its stability tolerance."
    )
