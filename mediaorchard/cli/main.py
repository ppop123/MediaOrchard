from __future__ import annotations

import typer

app = typer.Typer(
    name="mediaorchard",
    help="MediaOrchard Grove local media orchestration CLI.",
    no_args_is_help=True,
)

controller_app = typer.Typer(help="Run and inspect the Controller service.")
worker_app = typer.Typer(help="Run and inspect Worker agents.")


@controller_app.command("start")
def controller_start() -> None:
    """Start the Controller service."""
    typer.echo("Controller service is not implemented yet.")


@worker_app.command("start")
def worker_start(node_id: str = typer.Option(..., "--node-id")) -> None:
    """Start a Worker agent."""
    typer.echo(f"Worker service is not implemented yet for node {node_id}.")


@app.command()
def jobs() -> None:
    """List jobs."""
    typer.echo("Job listing is not implemented yet.")


@app.command()
def nodes() -> None:
    """List nodes."""
    typer.echo("Node listing is not implemented yet.")


app.add_typer(controller_app, name="controller")
app.add_typer(worker_app, name="worker")


if __name__ == "__main__":
    app()

