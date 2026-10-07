"""Real speech integration check, isolated from scientific evaluation data."""
import argparse
import io
import json
import os
from pathlib import Path
import wave

from ml.src.environment import load_project_environment


def main():
    load_project_environment(override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="instance/group_batch/IMG_3962/shared-16khz.wav")
    parser.add_argument("--root", default="instance/instrument-gpu-check")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()
    runtime = Path(__file__).resolve().parents[1]/".runtime"
    os.environ.setdefault("HF_HOME", str(runtime/"models"/"huggingface"))
    os.environ.setdefault("TORCH_HOME", str(runtime/"models"/"torch"))
    os.environ["PSYCON_INSTRUMENT_DEVICE"] = args.device
    os.environ["PATH"] = str(runtime/"bin")+os.pathsep+os.environ.get("PATH", "")
    from backend.instrument.service import Instrument
    from backend.instrument.store import now
    instrument = Instrument(args.root)
    memory = io.BytesIO()
    with wave.open(args.source, "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("Verification source must be 16 kHz mono PCM16")
        source.setpos(12*16000)
        samples = source.readframes(38*16000)
    with wave.open(memory, "wb") as output:
        output.setparams((1, 2, 16000, len(samples)//2, "NONE", "NONE"))
        output.writeframes(samples)
    session = instrument.ingest(io.BytesIO(memory.getvalue()), "real-speech-verification.wav",
                               dict(recorded_at=now(), consent="not documented", split="reference",
                                    context="group discussion", dataset="Isolated technical verification, not scientific evaluation",
                                    conditions=f"Source {Path(args.source).name}, source interval 12–50s"), allow_unknown_consent=True)
    instrument.process_next()
    result = instrument.detail(session["id"])
    summary = dict(status=result["session"]["status"], error=result["session"]["error"],
                   device=result["session"]["config"]["device"], versions=result["session"]["versions"],
                   speakers=len(result["speakers"]), utterances=len(result["utterances"]), words=len(result["words"]),
                   evidence=len(result["evidence"]), stages={s["name"]:s["status"] for s in result["stages"]},
                   scientific_evaluation="Not evaluated; this checks only runtime integration")
    Path(args.root, "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if summary["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
