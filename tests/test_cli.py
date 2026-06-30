from typer.testing import CliRunner

from mediaorchard.cli.main import app


def test_cli_help_loads():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "MediaOrchard" in result.output
    assert "controller" in result.output
    assert "worker" in result.output

