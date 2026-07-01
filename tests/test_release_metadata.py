import stat
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def collapsed_text(path: Path) -> str:
    return " ".join(path.read_text().split())


def test_project_has_explicit_bsd_2_clause_license_file():
    license_file = ROOT / "LICENSE"
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert license_file.exists()
    text = license_file.read_text()
    assert pyproject["project"]["license"] == "BSD-2-Clause"
    assert "BSD 2-Clause License" in text
    assert "Redistribution and use in source and binary forms" in text
    assert "DISCLAIMED" in text


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


def test_github_actions_release_check_runs_public_release_gate():
    workflow = ROOT / ".github" / "workflows" / "release-check.yml"

    assert workflow.exists()
    text = workflow.read_text()
    assert "macos-" in text
    assert "actions/setup-python" in text
    assert 'python-version: "3.12"' in text
    assert '.venv/bin/python -m pip install -e ".[dev]"' in text
    assert "concurrency:" in text
    assert "cancel-in-progress: true" in text
    assert "PYTHON_FOR_VENV=.venv/bin/python bash scripts/release_check.sh" in text


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


def test_release_docs_define_shared_storage_release_scope():
    release = collapsed_text(ROOT / "RELEASE.md")
    readme = collapsed_text(ROOT / "README.md")

    assert "Single-machine release does not require shared storage" in release
    assert "Multi-machine release requires marker-verified shared storage" in release
    assert "same local path on separate disks is not sufficient" in release
    assert "Single-machine package checks and CLI demos can use a local temporary root" in readme
    assert "Multi-Mac real-media execution requires marker-verified shared storage" in readme


def test_chinese_docs_present_agent_native_release_positioning():
    readme = ROOT / "README.zh-CN.md"
    release = ROOT / "RELEASE.zh-CN.md"

    assert readme.exists()
    assert release.exists()

    combined = readme.read_text() + "\n" + release.read_text()
    assert "agent native" in combined
    assert "Agent 原生" in combined
    assert "192.168.50.8" in combined
    assert "192.168.50.9" in combined


def test_chinese_agent_integration_doc_explains_invocation_contracts():
    doc = ROOT / "docs" / "AGENT_INTEGRATION.zh-CN.md"

    assert doc.exists()
    text = doc.read_text()
    assert "外部 agent 如何调用 MediaOrchard" in text
    assert "操作员 agent" in text
    assert "执行 agent" in text
    assert "POST /jobs" in text
    assert "POST /steps/claim-next" in text
    assert "X-MediaOrchard-Node-Id" in text
    assert "assignment_epoch" in text
    assert "mediaorchard submit" in text
    assert "curl" in text


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
            "REQUIRE_SHARED_ROOT_MARKER": "0",
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


def test_release_env_check_script_passes_shared_root_marker_when_configured(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
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
            "LOCAL_PREFLIGHT_TARGETS": "local",
            "REMOTE_PREFLIGHT_TARGETS": "wangyan@192.168.50.8",
            "BOOTSTRAP_TARGETS": "",
            "SHARED_ROOT_MARKER": ".mediaorchard-shared-root-id",
            "SHARED_ROOT_MARKER_VALUE": "release-root-token",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    calls = calls_log.read_text()
    assert "--shared-root-marker .mediaorchard-shared-root-id" in calls
    assert "--shared-root-marker-value release-root-token" in calls


def test_release_env_check_script_rejects_marker_value_without_marker(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    fake_python.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHON_BIN": str(fake_python),
            "LOCAL_PREFLIGHT_TARGETS": "",
            "REMOTE_PREFLIGHT_TARGETS": "",
            "BOOTSTRAP_TARGETS": "",
            "SHARED_ROOT_MARKER_VALUE": "release-root-token",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SHARED_ROOT_MARKER_VALUE requires SHARED_ROOT_MARKER" in result.stderr


def test_release_env_check_script_requires_marker_by_default_for_multi_machine(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
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
            "LOCAL_PREFLIGHT_TARGETS": "local",
            "REMOTE_PREFLIGHT_TARGETS": "wangyan@192.168.50.8",
            "BOOTSTRAP_TARGETS": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SHARED_ROOT_MARKER and SHARED_ROOT_MARKER_VALUE are required" in result.stderr
    assert not calls_log.exists()


def test_release_env_check_script_requires_marker_for_bootstrap_only_multi_machine(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
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
            "LOCAL_PREFLIGHT_TARGETS": "",
            "REMOTE_PREFLIGHT_TARGETS": "",
            "BOOTSTRAP_TARGETS": "wangyan@192.168.50.8",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SHARED_ROOT_MARKER and SHARED_ROOT_MARKER_VALUE are required" in result.stderr
    assert not calls_log.exists()


def test_release_env_check_script_rejects_invalid_marker_requirement_value(tmp_path):
    script = ROOT / "scripts" / "release_env_check.sh"
    fake_python = tmp_path / "python"
    calls_log = tmp_path / "calls.log"
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
            "LOCAL_PREFLIGHT_TARGETS": "",
            "REMOTE_PREFLIGHT_TARGETS": "",
            "BOOTSTRAP_TARGETS": "",
            "REQUIRE_SHARED_ROOT_MARKER": "maybe",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "REQUIRE_SHARED_ROOT_MARKER must be 0 or 1" in result.stderr
    assert not calls_log.exists()


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
            "REQUIRE_SHARED_ROOT_MARKER": "0",
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
            "REQUIRE_SHARED_ROOT_MARKER": "0",
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


def test_release_docs_require_shared_root_marker_for_multi_machine_claims():
    readme = (ROOT / "README.md").read_text()
    runbook = (ROOT / "RELEASE.md").read_text()

    combined = readme + "\n" + runbook
    assert "SHARED_ROOT_MARKER" in combined
    assert "--shared-root-marker" in combined
    assert "REQUIRE_SHARED_ROOT_MARKER=0" in combined
    assert "same shared storage" in combined


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
