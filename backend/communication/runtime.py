"""Private-pilot startup and local account provisioning."""
import argparse
import json
import os
import secrets
from pathlib import Path
from urllib.request import urlopen

from ml.src.environment import load_project_environment, PROJECT_ROOT


def configure_local():
    """Preserve existing secrets while pinning the locally installed model."""
    from dotenv import set_key
    path = PROJECT_ROOT / ".env"
    load_project_environment(override=False)
    if not os.getenv("PSYCON_PROFILE_KEY"):
        set_key(str(path), "PSYCON_PROFILE_KEY", secrets.token_urlsafe(48))
    url = os.getenv("PSYCON_OLLAMA_URL", "http://127.0.0.1:11434")
    from .llm import LocalInterpreter
    LocalInterpreter()  # Reject public or malformed endpoints before making a request.
    model = os.getenv("PSYCON_OLLAMA_MODEL", "qwen3.5:4b")
    with urlopen(url.rstrip("/")+"/api/tags", timeout=10) as response:
        tags = json.load(response)["models"]
    row = next((r for r in tags if r["name"] == model), None)
    if not row:
        raise ValueError("Pull qwen3.5:4b into the local Ollama service first")
    for key, value in (("PSYCON_OLLAMA_MODEL", model), ("PSYCON_OLLAMA_DIGEST", row["digest"]), ("PSYCON_OLLAMA_URL", url)):
        set_key(str(path), key, value)
    print("Local model pinned; profile encryption key preserved. Restart the web server and worker.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web")
    web.add_argument("--port", type=int, default=8000)
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--device-only", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=1.0)
    commands.add_parser("configure-local")
    account = commands.add_parser("create-wearer")
    account.add_argument("--label", required=True)
    account.add_argument("--role", default="general")
    args = parser.parse_args()
    load_project_environment(override=False)
    if args.command == "configure-local":
        configure_local()
        return
    if args.command == "worker":
        from backend.worker import run_worker
        run_worker(once=args.once, device_only=args.device_only, poll_seconds=args.poll_seconds)
        return
    from backend.app import create_app
    app = create_app()
    if args.command == "create-wearer":
        print(json.dumps(app.extensions["psycon_communication"].provision(args.role, args.label)))
    else:
        app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
