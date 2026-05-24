from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_wrist_firmware_contains_locked_i2c_pins() -> None:
    source = (ROOT / "firmware" / "wrist" / "src" / "main.cpp").read_text(encoding="utf-8")
    assert "SDA_PIN = 21" in source
    assert "SCL_PIN = 22" in source
    assert "Serial.begin" in source


def test_ear_firmware_contains_locked_i2s_pins() -> None:
    source = (ROOT / "firmware" / "ear" / "src" / "main.cpp").read_text(encoding="utf-8")
    assert "I2S_WS_PIN = 25" in source
    assert "I2S_SCK_PIN = 26" in source
    assert "I2S_SD_PIN = 33" in source


def test_platformio_configs_exist() -> None:
    assert (ROOT / "firmware" / "wrist" / "platformio.ini").exists()
    assert (ROOT / "firmware" / "ear" / "platformio.ini").exists()

