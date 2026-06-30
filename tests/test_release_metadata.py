import stat
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_has_explicit_mit_license_file():
    license_file = ROOT / "LICENSE"

    assert license_file.exists()
    text = license_file.read_text()
    assert "MIT License" in text
    assert "Permission is hereby granted" in text


def test_dev_extra_contains_release_build_tools():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]

    assert any(dependency.startswith("build>=") for dependency in dev_dependencies)
    assert any(dependency.startswith("twine>=") for dependency in dev_dependencies)


def test_release_check_script_is_executable_and_references_release_gates():
    script = ROOT / "scripts" / "release_check.sh"

    assert script.exists()
    assert script.stat().st_mode & stat.S_IXUSR

    text = script.read_text()
    assert ".venv/bin/python scripts/check-harness.py" in text
    assert "Run setup first" in text
    assert "-m build" in text
    assert "artifacts=(\"$build_dir\"/*)" in text
    assert "No release artifacts were built." in text
    assert "twine check" in text
    assert "-m venv \"$install_venv\"" in text
    assert "pip install" in text
    assert "\\.db" in text
    assert "\\.env" in text
    assert "\\.pem" in text


def test_release_env_check_script_is_executable_and_read_only():
    script = ROOT / "scripts" / "release_env_check.sh"

    assert script.exists()
    assert script.stat().st_mode & stat.S_IXUSR

    text = script.read_text()
    assert "doctor worker" in text
    assert "doctor worker-bootstrap" in text
    assert "--copy-wheel" in text
    assert "--execute" not in text
    assert "This script does not execute remote bootstrap" in text


def test_release_env_check_script_runs_preflight_and_bootstrap_dry_run(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHON_BIN": str(fake_python),
            "CALLS_LOG": str(calls_log),
            "MEDIAORCHARD_WHEEL": str(wheel),
            "LOCAL_PREFLIGHT_TARGETS": "local",
            "REMOTE_PREFLIGHT_TARGETS": "wangyan@192.168.50.8",
            "BOOTSTRAP_TARGETS": "wangyan@192.168.50.8",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "read-only" in result.stdout
    calls = calls_log.read_text()
    assert "-m mediaorchard.cli.main doctor worker --target local" in calls
    assert "-m mediaorchard.cli.main doctor worker --target wangyan@192.168.50.8" in calls
    assert "-m mediaorchard.cli.main doctor worker-bootstrap --target wangyan@192.168.50.8" in calls
    assert "--copy-wheel" in calls
    assert "--execute" not in calls


def test_release_env_check_script_uses_built_wheel_without_hardcoded_version(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"build\" ]; then\n"
        "  outdir=''\n"
        "  previous=''\n"
        "  for arg in \"$@\"; do\n"
        "    if [ \"$previous\" = \"--outdir\" ]; then outdir=\"$arg\"; fi\n"
        "    previous=\"$arg\"\n"
        "  done\n"
        "  mkdir -p \"$outdir\"\n"
        "  touch \"$outdir/mediaorchard-9.9.9-py3-none-any.whl\"\n"
        "fi\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHON_BIN": str(fake_python),
            "CALLS_LOG": str(calls_log),
            "LOCAL_PREFLIGHT_TARGETS": "local",
            "REMOTE_PREFLIGHT_TARGETS": "wangyan@192.168.50.8",
            "BOOTSTRAP_TARGETS": "wangyan@192.168.50.8",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    calls = calls_log.read_text()
    assert "mediaorchard-9.9.9-py3-none-any.whl" in calls
    assert "mediaorchard-0.1.0-py3-none-any.whl" not in calls


def test_release_env_check_script_continues_after_preflight_failure(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        "case \"$*\" in\n"
        "  *'doctor worker --target'*) exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHON_BIN": str(fake_python),
            "CALLS_LOG": str(calls_log),
            "MEDIAORCHARD_WHEEL": str(wheel),
            "LOCAL_PREFLIGHT_TARGETS": "local",
            "REMOTE_PREFLIGHT_TARGETS": "wangyan@192.168.50.8",
            "BOOTSTRAP_TARGETS": "wangyan@192.168.50.8",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    calls = calls_log.read_text()
    assert "-m mediaorchard.cli.main doctor worker --target local" in calls
    assert "-m mediaorchard.cli.main doctor worker-bootstrap --target wangyan@192.168.50.8" in calls


def test_release_env_check_script_allows_empty_target_groups(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHON_BIN": str(fake_python),
            "CALLS_LOG": str(calls_log),
            "MEDIAORCHARD_WHEEL": str(wheel),
            "LOCAL_PREFLIGHT_TARGETS": "",
            "REMOTE_PREFLIGHT_TARGETS": "",
            "BOOTSTRAP_TARGETS": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert not calls_log.exists()


def test_release_runbook_documents_public_release_gates():
    runbook = ROOT / "RELEASE.md"

    assert runbook.exists()
    text = runbook.read_text()
    assert "bash scripts/release_check.sh" in text
    assert "bash scripts/release_env_check.sh" in text
    assert "mediaorchard doctor worker-bootstrap" in text
    assert "--copy-wheel" in text
    assert "--execute" in text
    assert "explicit confirmation" in text
    assert "Do not claim multi-machine real-media execution" in text
    assert "/Volumes/MediaOrchard" in text


def test_release_checklist_current_evidence_uses_main_not_feature_branches():
    checklist = ROOT / "docs" / "RELEASE_CHECKLIST.md"

    text = checklist.read_text()
    assert "feature/" not in text
    assert "`main`" in text


def test_release_checklist_current_env_evidence_does_not_keep_resolved_local_whisper_gap():
    checklist = ROOT / "docs" / "RELEASE_CHECKLIST.md"

    text = checklist.read_text()
    assert "local `mlx_whisper`" not in text
    assert "local `.venv/bin/python` lacks `mlx_whisper`" not in text
