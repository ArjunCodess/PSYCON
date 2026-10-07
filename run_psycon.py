"""Run the audio-only research instrument or its durable local worker."""
import argparse
import os
from pathlib import Path
import time

from ml.src.environment import load_project_environment


def main():
    load_project_environment(override=False)
    runtime = Path(__file__).resolve().parent/".runtime"
    if runtime.exists():
        os.environ.setdefault("HF_HOME", str(runtime/"models"/"huggingface"))
        os.environ.setdefault("TORCH_HOME", str(runtime/"models"/"torch"))
        os.environ["PATH"] = str(runtime/"bin")+os.pathsep+os.environ.get("PATH", "")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("web", "worker", "import-groups", "build-references"))
    parser.add_argument("--root", default=os.getenv("PSYCON_INSTRUMENT_ROOT", "instance/instrument"))
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--consent", default="not documented", choices=("not documented", "documented", "public licensed"))
    args = parser.parse_args()
    if args.command == "web":
        from backend.instrument.app import create_app
        create_app(args.root).run(host="127.0.0.1", port=args.port, debug=False)
    elif args.command in ("import-groups", "build-references"):
        from backend.instrument.service import Instrument
        from backend.instrument.corpus import import_group, build_group_lenses
        service = Instrument(args.root)
        if args.command == "import-groups":
            import av
            project = Path(__file__).resolve().parent
            source = project/"instance"/"group_batch"
            for directory in sorted(source.iterdir()):
                if not directory.is_dir() or not (directory/"shared-16khz.wav").exists():
                    continue
                videos = [v for v in (project/"group_discussions").iterdir() if v.stem == directory.name]
                if not videos:
                    print(f"Skipped {directory.name}: original video unavailable", flush=True)
                    continue
                with av.open(str(videos[0])) as container:
                    stamp = container.metadata.get("creation_time")
                if not stamp:
                    print(f"Skipped {directory.name}: original recording time unavailable", flush=True)
                    continue
                try:
                    result = import_group(service, directory, videos[0], stamp, args.consent)
                    print(f"Imported {result['filename']}: {result['status']}", flush=True)
                except ValueError as exc:
                    print(f"Skipped {directory.name}: {exc}", flush=True)
        else:
            print("Built reference lenses:", [a["name"] for a in build_group_lenses(service)])
    else:
        import torch
        os.environ.setdefault("PSYCON_INSTRUMENT_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        from backend.instrument.service import Instrument
        from backend.instrument.worker import run
        service = Instrument(args.root)
        run(service, once=args.once)


if __name__ == "__main__":
    main()
