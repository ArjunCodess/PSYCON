from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WESAD_RAW_DIR = ROOT / "data" / "raw" / "wesad"
PROCESSED_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
CHARTS_DIR = RESULTS_DIR / "charts"

COMMON_HZ = 4
WINDOW_SECONDS = 5
HOP_SECONDS = 1
CHEST_LABEL_HZ = 700

LABEL_CALM = "calm"
LABEL_HIGH_STRESS = "high_stress"
LABEL_UNKNOWN = "unknown"

STATE_THRESHOLDS = {
    LABEL_CALM: [0.0, 0.3],
    "mild_stress": [0.3, 0.6],
    LABEL_HIGH_STRESS: [0.6, 1.0],
}

