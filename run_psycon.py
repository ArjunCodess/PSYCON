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
    parser.add_argument("command", choices=("web", "worker", "import-groups", "build-references", "migrate", "inventory", "migrate-source", "register-videos", "backup", "restore", "train", "queue-videos", "docker"))
    parser.add_argument("--root", default=os.getenv("PSYCON_INSTRUMENT_ROOT", "instance/instrument"))
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--consent", default="not documented", choices=("not documented", "documented", "public licensed"))
    parser.add_argument('--destination',type=Path)
    parser.add_argument('--source',type=Path,default=Path('instance/instrument/psycon.sqlite3'))
    parser.add_argument('--verification',type=Path)
    parser.add_argument('--snapshot')
    parser.add_argument('--local-destination',type=Path)
    args = parser.parse_args()
    if args.command=='docker':
        import json, subprocess
        os.environ['PSYCON_PATH_MAP']=json.dumps({str(Path(__file__).resolve().parent):'/app'})
        subprocess.run(['docker','compose','-f','docker-compose.instrument.yml','up','--build','-d'],check=True)
        from urllib.request import urlopen
        import json as startup_json
        for attempt in range(60):
            try:
                with urlopen('http://localhost:8008/health',timeout=2) as response:
                    if startup_json.load(response)['status']=='ok': break
            except (OSError,ValueError): pass
            time.sleep(1)
        else:
            raise RuntimeError('Docker started but PostgreSQL readiness failed. Inspect docker compose -f docker-compose.instrument.yml logs.')
        print('PSYCON: http://localhost:8008 (web and GPU worker use the configured PostgreSQL)')
        return
    role={'web':'psycon_web','worker':'psycon_worker','train':'psycon_trainer'}.get(args.command)
    if role:
        os.environ.setdefault('PSYCON_DATABASE_ROLE',role)
        actor_url=os.getenv('PSYCON_'+role.removeprefix('psycon_').upper()+'_DATABASE_URL')
        if actor_url: os.environ['PSYCON_DATABASE_URL']=actor_url
    if args.command in ('migrate','inventory','migrate-source','register-videos','backup','restore','train','queue-videos'):
        from backend.instrument.store import Store,encode
        store=Store(args.root)
        try:
            if args.command=='migrate':
                store.migrate()
                from backend.instrument.forms import install
                from backend.instrument.profiles import initialize_archetypes
                install(store);initialize_archetypes(store)
                print('PostgreSQL migrations applied; readiness:',store.ready())
            elif args.command=='inventory':
                from backend.instrument.backup import inventory
                print(encode(inventory(store.url)))
            elif args.command=='migrate-source':
                from backend.instrument.migrate_legacy import migrate_source
                if not args.verification: parser.error('--verification is required')
                print(encode(migrate_source(store,args.source,args.verification)))
            elif args.command=='queue-videos':
                store.migrate()
                from backend.instrument.forms import install
                from backend.instrument.profiles import initialize_archetypes
                install(store);initialize_archetypes(store)
                from backend.instrument.catalog import queue_group_videos
                from backend.instrument.service import Instrument
                print(encode(queue_group_videos(Instrument(args.root))))
            elif args.command=='register-videos':
                from backend.instrument.catalog import register_group_videos,normalize_retained_claims
                print(encode(dict(videos=register_group_videos(store),text=normalize_retained_claims(store))))
            elif args.command=='backup':
                from backend.instrument.backup import coordinated_backup
                if not args.destination: parser.error('--destination is required')
                result=coordinated_backup(store,args.destination)
                print('Database and registered local assets restored and verified:',result['asset_restoration_verified'])
            elif args.command=='restore':
                from backend.instrument.backup import restore_backup
                if not args.destination or not args.local_destination: parser.error('--destination backup directory and --local-destination new asset root are required')
                print(encode(restore_backup(store.url,args.destination,args.local_destination)))
            elif args.command=='train':
                from backend.instrument.training import queue,process_training
                if args.snapshot: print(encode(queue(store,args.snapshot)))
                print(encode(process_training(store)))
        finally:
            store.pool.close()
        return
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
