from __future__ import annotations

import os
from pathlib import Path

import typer

from mediaorchard.cli.runtime import (
    ControllerRuntimeConfig,
    WorkerRuntimeConfig,
    list_jobs,
    list_nodes,
    run_controller,
    run_worker,
    submit_job,
)

app = typer.Typer(
    name="mediaorchard",
    help="MediaOrchard Grove local media orchestration CLI.",
    no_args_is_help=True,
)

controller_app = typer.Typer(help="Run and inspect the Controller service.")
worker_app = typer.Typer(help="Run and inspect Worker agents.")


@controller_app.command("start")
def controller_start(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8765, "--port"),
    database_url: str = typer.Option(
        "sqlite:///mediaorchard.db",
        "--database-url",
        envvar="MEDIAORCHARD_DATABASE_URL",
    ),
    api_key_hash: str | None = typer.Option(
        None,
        "--api-key-hash",
        envvar="MEDIAORCHARD_API_KEY_HASH",
    ),
    shared_root: Path = typer.Option(
        Path("/Volumes/MediaOrchard"),
        "--shared-root",
        envvar="MEDIAORCHARD_SHARED_ROOT",
    ),
    log_level: str = typer.Option("info", "--log-level"),
) -> None:
    """Start the Controller service."""
    raw_api_key_hash = _require_api_key_hash(api_key_hash)
    typer.echo(f"Starting Controller on {host}:{port}")
    run_controller(
        ControllerRuntimeConfig(
            host=host,
            port=port,
            database_url=database_url,
            api_key_hash=raw_api_key_hash,
            shared_root=shared_root,
            log_level=log_level,
        )
    )


@worker_app.command("start")
def worker_start(
    node_id: str = typer.Option(..., "--node-id"),
    node_name: str | None = typer.Option(None, "--node-name"),
    controller_url: str = typer.Option(
        "http://127.0.0.1:8765",
        "--controller-url",
        envvar="MEDIAORCHARD_CONTROLLER_URL",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEDIAORCHARD_API_KEY",
    ),
    shared_root: Path = typer.Option(
        Path("/Volumes/MediaOrchard"),
        "--shared-root",
        envvar="MEDIAORCHARD_SHARED_ROOT",
    ),
    max_ffmpeg_jobs: int = typer.Option(1, "--max-ffmpeg-jobs", min=1),
    max_whisper_jobs: int = typer.Option(1, "--max-whisper-jobs", min=1),
    once: bool = typer.Option(False, "--once"),
    max_polls: int | None = typer.Option(None, "--max-polls"),
    claim_interval_seconds: float = typer.Option(2.0, "--claim-interval-seconds", min=0.1),
) -> None:
    """Start a Worker agent."""
    raw_api_key = _require_api_key(api_key)

    typer.echo(f"Starting Worker {node_id}")
    claimed = run_worker(
        WorkerRuntimeConfig(
            node_id=node_id,
            node_name=node_name or node_id,
            shared_root=shared_root,
            controller_url=controller_url,
            api_key=raw_api_key,
            max_ffmpeg_jobs=max_ffmpeg_jobs,
            max_whisper_jobs=max_whisper_jobs,
            poll_once=once,
            max_polls=max_polls,
            claim_interval_seconds=claim_interval_seconds,
        )
    )
    if once or max_polls is not None:
        typer.echo(f"Claimed {len(claimed)} step(s)")


@app.command()
def jobs(
    controller_url: str = typer.Option(
        "http://127.0.0.1:8765",
        "--controller-url",
        envvar="MEDIAORCHARD_CONTROLLER_URL",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEDIAORCHARD_API_KEY",
    ),
) -> None:
    """List jobs."""
    job_rows = list_jobs(controller_url, _require_api_key(api_key))
    if not job_rows:
        typer.echo("No jobs found.")
        return

    typer.echo("ID\tSTATUS\tGOAL\tPRIORITY")
    for job in job_rows:
        typer.echo(
            "\t".join(
                [
                    _display(job.get("id")),
                    _display(job.get("status")),
                    _display(job.get("goal_type")),
                    _display(job.get("priority")),
                ]
            )
        )


@app.command()
def nodes(
    controller_url: str = typer.Option(
        "http://127.0.0.1:8765",
        "--controller-url",
        envvar="MEDIAORCHARD_CONTROLLER_URL",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEDIAORCHARD_API_KEY",
    ),
) -> None:
    """List nodes."""
    node_rows = list_nodes(controller_url, _require_api_key(api_key))
    if not node_rows:
        typer.echo("No nodes found.")
        return

    typer.echo("ID\tSTATUS\tCPU%\tHOST")
    for node in node_rows:
        typer.echo(
            "\t".join(
                [
                    _display(node.get("id")),
                    _display(node.get("status")),
                    _display(node.get("cpu_percent")),
                    _display(node.get("host")),
                ]
            )
        )


@app.command()
def submit(
    input_file: Path = typer.Argument(...),
    controller_url: str = typer.Option(
        "http://127.0.0.1:8765",
        "--controller-url",
        envvar="MEDIAORCHARD_CONTROLLER_URL",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="MEDIAORCHARD_API_KEY",
    ),
    goal: str = typer.Option("video_to_subtitle", "--goal"),
    outputs: list[str] | None = typer.Option(None, "--output"),
    language: str | None = typer.Option(None, "--language"),
    quality: str = typer.Option("standard", "--quality"),
    priority: int = typer.Option(5, "--priority"),
    user_request: str | None = typer.Option(None, "--user-request"),
) -> None:
    """Submit a media job."""
    if not input_file.expanduser().exists():
        raise typer.BadParameter("input_file does not exist")
    payload = {
        "goal_type": goal,
        "input_file": str(input_file),
        "outputs": outputs or ["srt", "txt", "json"],
        "language": language,
        "quality": quality,
        "priority": priority,
        "user_request": user_request,
    }
    job = submit_job(controller_url, _require_api_key(api_key), payload)
    typer.echo(f"Created job {_display(job.get('id'))} ({_display(job.get('status'))})")


def _require_api_key(api_key: str | None) -> str:
    raw_api_key = api_key or os.getenv("MEDIAORCHARD_API_KEY")
    if not raw_api_key:
        raise typer.BadParameter("Controller API key is required via --api-key or MEDIAORCHARD_API_KEY")
    return raw_api_key


def _require_api_key_hash(api_key_hash: str | None) -> str:
    raw_api_key_hash = api_key_hash or os.getenv("MEDIAORCHARD_API_KEY_HASH")
    if not raw_api_key_hash or raw_api_key_hash == "__unset__":
        raise typer.BadParameter(
            "Controller API key hash is required via --api-key-hash or MEDIAORCHARD_API_KEY_HASH"
        )
    return raw_api_key_hash


def _display(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


app.add_typer(controller_app, name="controller")
app.add_typer(worker_app, name="worker")


if __name__ == "__main__":
    app()
