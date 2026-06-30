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
from mediaorchard.worker.bootstrap import DEFAULT_PACKAGE_SPEC, WorkerBootstrapConfig, run_worker_bootstrap
from mediaorchard.worker.preflight import WorkerPreflightConfig, run_worker_preflight

app = typer.Typer(
    name="mediaorchard",
    help="MediaOrchard Grove local media orchestration CLI.",
    no_args_is_help=True,
)

controller_app = typer.Typer(help="Run and inspect the Controller service.")
worker_app = typer.Typer(help="Run and inspect Worker agents.")
doctor_app = typer.Typer(help="Run release-readiness diagnostics.")


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
    execution_mode: str = typer.Option("deterministic", "--execution-mode"),
    python_executable: str = typer.Option("python3", "--python"),
    whisper_model: str = typer.Option("mlx-community/whisper-tiny", "--whisper-model"),
    tool_timeout_seconds: int = typer.Option(120, "--tool-timeout-seconds", min=1),
) -> None:
    """Start a Worker agent."""
    raw_api_key = _require_api_key(api_key)
    if execution_mode not in {"deterministic", "real"}:
        raise typer.BadParameter("execution-mode must be deterministic or real")

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
            execution_mode=execution_mode,
            python_executable=python_executable,
            whisper_model=whisper_model,
            tool_timeout_seconds=tool_timeout_seconds,
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


@doctor_app.command("worker")
def doctor_worker(
    targets: list[str] | None = typer.Option(None, "--target"),
    shared_root: Path = typer.Option(Path("/Volumes/MediaOrchard"), "--shared-root"),
    runtime_python: str = typer.Option("python3", "--runtime-python"),
    whisper_python: str = typer.Option("python3", "--whisper-python"),
    timeout_seconds: int = typer.Option(10, "--timeout-seconds", min=1),
) -> None:
    """Check local or SSH Worker runtime requirements."""
    target_values = targets or ["local"]
    results = [
        run_worker_preflight(
            WorkerPreflightConfig(
                target=target,
                shared_root=shared_root,
                runtime_python_executable=runtime_python,
                whisper_python_executable=whisper_python,
                timeout_seconds=timeout_seconds,
            )
        )
        for target in target_values
    ]

    for result in results:
        typer.echo(f"{result.target} {'PASS' if result.ok else 'FAIL'}")
        for check in result.checks:
            typer.echo(f"  {'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}")

    if not all(result.ok for result in results):
        raise typer.Exit(code=1)


@doctor_app.command("worker-bootstrap")
def doctor_worker_bootstrap(
    targets: list[str] | None = typer.Option(None, "--target"),
    install_root: Path = typer.Option(Path("~/.mediaorchard"), "--install-root"),
    shared_root: Path = typer.Option(Path("/Volumes/MediaOrchard"), "--shared-root"),
    python_executable: str = typer.Option("python3", "--python"),
    package_spec: str = typer.Option(DEFAULT_PACKAGE_SPEC, "--package-spec"),
    package_wheel: Path | None = typer.Option(None, "--wheel"),
    copy_wheel: bool = typer.Option(False, "--copy-wheel"),
    whisper_package: str = typer.Option("mlx-whisper", "--whisper-package"),
    execute: bool = typer.Option(False, "--execute"),
    timeout_seconds: int = typer.Option(300, "--timeout-seconds", min=1),
) -> None:
    """Print or execute Worker environment bootstrap commands."""
    if package_wheel is not None and not package_wheel.expanduser().exists():
        raise typer.BadParameter("wheel does not exist")
    if package_wheel is not None and package_spec != DEFAULT_PACKAGE_SPEC:
        raise typer.BadParameter("--package-spec cannot be combined with --wheel")
    if copy_wheel and package_wheel is None:
        raise typer.BadParameter("--copy-wheel requires --wheel")
    target_values = targets or ["local"]
    results = [
        run_worker_bootstrap(
            WorkerBootstrapConfig(
                target=target,
                install_root=install_root,
                shared_root=shared_root,
                python_executable=python_executable,
                package_spec=package_spec,
                package_wheel=package_wheel,
                copy_wheel=copy_wheel,
                whisper_package=whisper_package,
                timeout_seconds=timeout_seconds,
            ),
            execute=execute,
        )
        for target in target_values
    ]

    for result in results:
        if result.executed:
            typer.echo(f"{result.target} {'PASS' if result.ok else 'FAIL'}")
            if result.stdout.strip():
                typer.echo(result.stdout.strip())
            if result.stderr.strip():
                typer.echo(result.stderr.strip(), err=True)
        else:
            typer.echo(f"{result.target} DRY-RUN")
            typer.echo(result.script)

    if not all(result.ok for result in results):
        raise typer.Exit(code=1)


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
app.add_typer(doctor_app, name="doctor")


if __name__ == "__main__":
    app()
