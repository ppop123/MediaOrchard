from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class WorkerTransport(Protocol):
    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
        ...


@dataclass
class WorkerAgent:
    node_id: str
    node_name: str
    shared_root: Path
    transport: WorkerTransport
    max_ffmpeg_jobs: int = 1
    max_whisper_jobs: int = 1

    def register(self) -> dict[str, Any] | None:
        return self.transport.post(
            "/nodes/register",
            {
                "node_id": self.node_id,
                "name": self.node_name,
                "shared_root": str(self.shared_root.expanduser().resolve(strict=False)),
                "max_ffmpeg_jobs": self.max_ffmpeg_jobs,
                "max_whisper_jobs": self.max_whisper_jobs,
            },
        )

    def heartbeat(
        self,
        *,
        cpu_percent: float,
        memory_percent: float,
        free_disk_gb: float,
        active_jobs: int,
        active_ffmpeg_jobs: int,
        active_whisper_jobs: int,
        thermal_state: str,
        on_battery: bool,
    ) -> dict[str, Any] | None:
        return self.transport.post(
            f"/nodes/{self.node_id}/heartbeat",
            {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "free_disk_gb": free_disk_gb,
                "active_jobs": active_jobs,
                "active_ffmpeg_jobs": active_ffmpeg_jobs,
                "active_whisper_jobs": active_whisper_jobs,
                "thermal_state": thermal_state,
                "on_battery": on_battery,
            },
        )

    def claim_next(self) -> dict[str, Any] | None:
        return self.transport.post("/steps/claim-next", {"node_id": self.node_id})

    def start_step(self, *, step_id: str, assignment_epoch: int) -> dict[str, Any] | None:
        return self.transport.post(
            f"/steps/{step_id}/start",
            {"assignment_epoch": assignment_epoch},
        )

    def complete_step(
        self,
        *,
        step_id: str,
        assignment_epoch: int,
        output_json: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.transport.post(
            f"/steps/{step_id}/complete",
            {
                "assignment_epoch": assignment_epoch,
                "output_json": output_json,
            },
        )

    def fail_step(
        self,
        *,
        step_id: str,
        assignment_epoch: int,
        error_message: str,
    ) -> dict[str, Any] | None:
        return self.transport.post(
            f"/steps/{step_id}/fail",
            {
                "assignment_epoch": assignment_epoch,
                "error_message": error_message,
            },
        )

    def report_interrupted(self, *, step_id: str, assignment_epoch: int) -> dict[str, Any] | None:
        return self.fail_step(
            step_id=step_id,
            assignment_epoch=assignment_epoch,
            error_message="interrupted_by_worker_shutdown",
        )
