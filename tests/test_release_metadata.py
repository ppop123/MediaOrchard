import stat
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
