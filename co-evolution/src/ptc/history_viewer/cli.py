from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from wsgiref.simple_server import make_server

from mhc.config import resolve_experiment_directory, resolve_experiment_name
from .app import create_app
from .repository import HistoryRepository


RELOAD_ENV_VAR = "PTC_HISTORY_VIEWER_NO_RELOAD"
DEFAULT_RELOAD_EXTENSIONS = (".py", ".html", ".css", ".js")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View test vs production method evolution in the browser.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local browser UI")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--workspace-directory", default=None)
    serve_parser.add_argument("--experiment-name", default=None, help="Experiment name. Defaults to ME_EXPERIMENT_NAME.")
    serve_parser.add_argument("--reload", action="store_true", help="Restart the server automatically when viewer Python files change")
    serve_parser.add_argument("--reload-interval", type=float, default=1.0, help="Seconds between file-change checks when --reload is enabled")

    link_parser = subparsers.add_parser("add-revision-links", help="Write revision_url into a sampled CSV")
    link_parser.add_argument("--csv", required=True, help="Absolute path to the sampled CSV")
    link_parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="Viewer base URL used in revision_url")
    link_parser.add_argument("--workspace-directory", default=None)
    link_parser.add_argument("--experiment-name", default=None, help="Experiment name. Defaults to ME_EXPERIMENT_NAME.")

    return parser


def _resolve_viewer_paths(
    workspace_directory: str | None,
    experiment: str | None,
) -> tuple[str | None, str | None]:
    if workspace_directory is None:
        return workspace_directory, None
    experiment_name = resolve_experiment_name(experiment)
    experiment_directory = str(resolve_experiment_directory(workspace_directory, experiment_name))
    return experiment_directory, experiment_directory


def _serve_once(*, host: str, port: int, workspace_directory: str | None, experiment: str | None) -> int:
    workspace_directory, data_directory = _resolve_viewer_paths(workspace_directory, experiment)
    app = create_app(workspace_directory=workspace_directory, data_directory=data_directory)
    with make_server(host, port, app) as server:
        print(f"Method history viewer listening on http://{host}:{port}", flush=True)
        server.serve_forever()
    return 0


def _viewer_source_directory() -> Path:
    return Path(__file__).resolve().parent


def iter_reload_paths(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in DEFAULT_RELOAD_EXTENSIONS and "__pycache__" not in path.parts:
            yield path


def snapshot_mtimes(paths: Iterable[Path]) -> dict[Path, int]:
    snapshot: dict[Path, int] = {}
    for path in paths:
        try:
            snapshot[path] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
    return snapshot


def has_snapshot_changed(previous: dict[Path, int], current: dict[Path, int]) -> bool:
    return previous != current


def build_reload_child_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-m", "ptc.history_viewer.cli", "serve", "--host", args.host, "--port", str(args.port)]
    if args.workspace_directory:
        command.extend(["--workspace-directory", args.workspace_directory])
    if getattr(args, "experiment_name", None):
        command.extend(["--experiment-name", args.experiment_name])
    return command


def run_with_reload(args: argparse.Namespace) -> int:
    watch_root = _viewer_source_directory()
    tracked_snapshot = snapshot_mtimes(iter_reload_paths(watch_root))

    child_env = dict(os.environ)
    child_env[RELOAD_ENV_VAR] = "1"

    child = subprocess.Popen(build_reload_child_command(args), env=child_env)

    def _stop_child(_signum: int, _frame: object) -> None:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop_child)
    signal.signal(signal.SIGTERM, _stop_child)

    try:
        while True:
            time.sleep(max(args.reload_interval, 0.1))
            current_snapshot = snapshot_mtimes(iter_reload_paths(watch_root))
            if has_snapshot_changed(tracked_snapshot, current_snapshot):
                print("Detected viewer code changes. Restarting server...", flush=True)
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                tracked_snapshot = current_snapshot
                child = subprocess.Popen(build_reload_child_command(args), env=child_env)
                signal.signal(signal.SIGINT, _stop_child)
                signal.signal(signal.SIGTERM, _stop_child)
                continue

            child_return_code = child.poll()
            if child_return_code is not None:
                return child_return_code
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        if args.reload and os.environ.get(RELOAD_ENV_VAR) != "1":
            return run_with_reload(args)
        return _serve_once(
            host=args.host,
            port=args.port,
            workspace_directory=args.workspace_directory,
            experiment=args.experiment_name,
        )

    if args.command == "add-revision-links":
        workspace_directory, data_directory = _resolve_viewer_paths(
            args.workspace_directory,
            args.experiment_name,
        )
        repository = HistoryRepository(workspace_directory=workspace_directory, data_directory=data_directory)
        rows = repository.write_revision_links(args.csv, base_url=args.base_url)
        print(f"Wrote revision_url for {rows} row(s) in {args.csv}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
