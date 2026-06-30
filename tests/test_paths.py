from pathlib import Path

import pytest

from mediaorchard.shared.paths import (
    PathSecurityError,
    build_job_output_dir,
    resolve_allowlisted_path,
    validate_shared_root,
)


def test_resolve_allowlisted_path_accepts_file_under_allowed_root(tmp_path):
    allowed_root = tmp_path / "inbox"
    allowed_root.mkdir()
    media_file = allowed_root / "demo.mp4"
    media_file.write_text("placeholder")

    resolved = resolve_allowlisted_path(media_file, [allowed_root])

    assert resolved == media_file.resolve()


def test_resolve_allowlisted_path_rejects_outside_allowed_root(tmp_path):
    allowed_root = tmp_path / "inbox"
    allowed_root.mkdir()
    outside_file = tmp_path / "outside.mp4"
    outside_file.write_text("placeholder")

    with pytest.raises(PathSecurityError):
        resolve_allowlisted_path(outside_file, [allowed_root])


def test_build_job_output_dir_is_derived_from_job_id(tmp_path):
    output_root = tmp_path / "output"

    path = build_job_output_dir(output_root, "job_001")

    assert path == output_root.resolve() / "job_001"


def test_build_job_output_dir_rejects_path_like_job_id(tmp_path):
    with pytest.raises(PathSecurityError):
        build_job_output_dir(tmp_path / "output", "../escape")


def test_validate_shared_root_requires_matching_resolved_path(tmp_path):
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()

    result = validate_shared_root(shared_root, shared_root)

    assert result.ok is True
    assert result.reason == "shared_root_ok"


def test_validate_shared_root_rejects_mismatch(tmp_path):
    controller_root = tmp_path / "controller"
    worker_root = tmp_path / "worker"
    controller_root.mkdir()
    worker_root.mkdir()

    result = validate_shared_root(worker_root, controller_root)

    assert result.ok is False
    assert result.reason == "shared_root_mismatch"

