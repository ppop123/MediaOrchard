from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class PathSecurityError(ValueError):
    """Raised when a user-controlled path violates storage policy."""


@dataclass(frozen=True)
class SharedRootValidation:
    ok: bool
    reason: str
    worker_root: Path
    controller_root: Path


def resolve_allowlisted_path(path: str | Path, allowed_roots: Iterable[str | Path]) -> Path:
    """Resolve a path and ensure it is inside one of the configured roots."""
    candidate = Path(path).expanduser().resolve(strict=False)
    roots = [Path(root).expanduser().resolve(strict=False) for root in allowed_roots]

    if not roots:
        raise PathSecurityError("at least one allowlisted root is required")

    for root in roots:
        if candidate == root or root in candidate.parents:
            return candidate

    raise PathSecurityError(f"path is outside allowlisted roots: {candidate}")


def build_job_output_dir(output_root: str | Path, job_id: str) -> Path:
    """Build a system-owned output directory path from a safe job id."""
    if not job_id or job_id in {".", ".."}:
        raise PathSecurityError("job_id must be a non-empty path segment")

    if Path(job_id).name != job_id or "/" in job_id or "\\" in job_id:
        raise PathSecurityError("job_id must not contain path separators")

    return Path(output_root).expanduser().resolve(strict=False) / job_id


def validate_shared_root(worker_root: str | Path, controller_root: str | Path) -> SharedRootValidation:
    """Validate that a Worker reports the same shared root as the Controller."""
    worker = Path(worker_root).expanduser().resolve(strict=False)
    controller = Path(controller_root).expanduser().resolve(strict=False)

    if not worker.exists():
        return SharedRootValidation(False, "shared_root_missing", worker, controller)

    if not worker.is_dir():
        return SharedRootValidation(False, "shared_root_not_directory", worker, controller)

    if worker != controller:
        return SharedRootValidation(False, "shared_root_mismatch", worker, controller)

    return SharedRootValidation(True, "shared_root_ok", worker, controller)

