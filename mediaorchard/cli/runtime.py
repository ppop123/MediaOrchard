from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psutil
import uvicorn

from mediaorchard.worker.agent import WorkerAgent, WorkerTransport
from mediaorchard.worker.mock_pipeline import run_mock_video_to_subtitle_pipeline


@dataclass(frozen=True)
class ControllerRuntimeConfig:
    host: str
    port: int
    database_url: str
    api_key_hash: str
    shared_root: Path
    log_level: str = "info"
    env_file: str | None = None


@dataclass(frozen=True)
class WorkerRuntimeConfig:
    node_id: str
    node_name: str
    shared_root: Path
    controller_url: str
    api_key: str
    max_ffmpeg_jobs: int = 1
    max_whisper_jobs: int = 1
    poll_once: bool = False
    max_polls: int | None = None
    claim_interval_seconds: float = 2.0
    execute_claimed_steps: bool = True


StepRunner = Callable[[dict[str, Any], WorkerRuntimeConfig], dict[str, Any]]


class HttpWorkerTransport:
    def __init__(
        self,
        *,
        controller_url: str,
        api_key: str,
        node_id: str,
        timeout_seconds: float = 10.0,
    ):
        self.controller_url = controller_url.rstrip("/")
        self.api_key = api_key
        self.node_id = node_id
        self.timeout_seconds = timeout_seconds

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
        payload = b""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-MediaOrchard-Node-Id": self.node_id,
        }
        if json is not None:
            payload = _json_bytes(json)
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.controller_url}{path}",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status == 204:
                    return None
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"Controller request failed: {exc.code} {detail}") from exc

        if not body:
            return None
        decoded = json_loads(body)
        if not isinstance(decoded, dict):
            raise RuntimeError("Controller response must be a JSON object")
        return decoded


class ControllerApiClient:
    def __init__(
        self,
        *,
        controller_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
    ):
        self.controller_url = controller_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = _json_bytes(payload)

        request = Request(
            f"{self.controller_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status == 204:
                    return None
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"Controller request failed: {exc.code} {detail}") from exc

        if not body:
            return None
        return json_loads(body)


def run_controller(
    config: ControllerRuntimeConfig,
    *,
    uvicorn_run: Callable[..., Any] = uvicorn.run,
) -> None:
    os.environ["MEDIAORCHARD_DATABASE_URL"] = config.database_url
    os.environ["MEDIAORCHARD_API_KEY_HASH"] = config.api_key_hash
    os.environ["MEDIAORCHARD_SHARED_ROOT"] = str(config.shared_root.expanduser().resolve(strict=False))
    uvicorn_run(
        "mediaorchard.controller.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        env_file=config.env_file,
    )


def run_worker(
    config: WorkerRuntimeConfig,
    *,
    transport: WorkerTransport | None = None,
    metrics_provider: Callable[[], dict[str, Any]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    step_runner: StepRunner | None = None,
) -> list[dict[str, Any]]:
    transport = transport or HttpWorkerTransport(
        controller_url=config.controller_url,
        api_key=config.api_key,
        node_id=config.node_id,
    )
    metrics_provider = metrics_provider or collect_worker_metrics
    worker = WorkerAgent(
        node_id=config.node_id,
        node_name=config.node_name,
        shared_root=config.shared_root,
        transport=transport,
        max_ffmpeg_jobs=config.max_ffmpeg_jobs,
        max_whisper_jobs=config.max_whisper_jobs,
    )
    worker.register()

    claimed_steps: list[dict[str, Any]] = []
    runner = step_runner or run_claimed_pipeline_step
    polls = 0
    while True:
        worker.heartbeat(**metrics_provider())
        claimed = worker.claim_next()
        if claimed is not None:
            claimed_steps.append(claimed)
            if config.execute_claimed_steps:
                execute_claimed_step(worker, claimed, config, runner)

        polls += 1
        if config.poll_once:
            break
        if config.max_polls is not None and polls >= config.max_polls:
            break
        sleep(config.claim_interval_seconds)

    return claimed_steps


def execute_claimed_step(
    worker: WorkerAgent,
    step: dict[str, Any],
    config: WorkerRuntimeConfig,
    step_runner: StepRunner,
) -> None:
    step_id = _required_step_str(step, "id")
    assignment_epoch = _required_step_int(step, "assignment_epoch")
    try:
        worker.start_step(step_id=step_id, assignment_epoch=assignment_epoch)
        output_json = step_runner(step, config)
        if output_json.get("status") == "failed":
            worker.fail_step(
                step_id=step_id,
                assignment_epoch=assignment_epoch,
                error_message=str(output_json.get("error_message") or "step failed"),
            )
            return
        worker.complete_step(
            step_id=step_id,
            assignment_epoch=assignment_epoch,
            output_json=output_json,
        )
    except Exception as exc:
        worker.fail_step(
            step_id=step_id,
            assignment_epoch=assignment_epoch,
            error_message=str(exc),
        )


def run_claimed_pipeline_step(step: dict[str, Any], config: WorkerRuntimeConfig) -> dict[str, Any]:
    if step.get("tool_name") != "video_to_subtitle_pipeline":
        raise RuntimeError(f"unsupported claimed step tool: {step.get('tool_name')}")

    input_json = step.get("input_json")
    if not isinstance(input_json, dict):
        raise RuntimeError("claimed step is missing input_json")

    requested_outputs = input_json.get("requested_outputs")
    if not isinstance(requested_outputs, list) or any(not isinstance(item, str) for item in requested_outputs):
        raise RuntimeError("claimed step requested_outputs must be list[str]")

    result = run_mock_video_to_subtitle_pipeline(
        input_file=_required_json_str(input_json, "input_file"),
        output_dir=_required_json_str(input_json, "output_dir"),
        work_dir=_required_json_str(input_json, "work_dir"),
        requested_outputs=requested_outputs,
        language=input_json.get("language") if isinstance(input_json.get("language"), str) else None,
        job_id=_required_step_str(step, "job_id"),
    )
    if result.status != "completed":
        return {
            "status": "failed",
            "error_message": result.error_message or "pipeline failed",
            "output_dir": str(result.output_dir),
            "work_dir": str(result.work_dir),
        }

    return {
        "status": result.status,
        "pipeline_steps": result.steps,
        "output_dir": str(result.output_dir),
        "work_dir": str(result.work_dir),
        "node_id": config.node_id,
    }


def collect_worker_metrics() -> dict[str, Any]:
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "free_disk_gb": disk.free / (1024**3),
        "active_jobs": 0,
        "active_ffmpeg_jobs": 0,
        "active_whisper_jobs": 0,
        "thermal_state": "unknown",
        "on_battery": False,
    }


def list_nodes(controller_url: str, api_key: str) -> list[dict[str, Any]]:
    decoded = ControllerApiClient(controller_url=controller_url, api_key=api_key).get("/nodes")
    return _json_object_list(decoded, "nodes")


def list_jobs(controller_url: str, api_key: str) -> list[dict[str, Any]]:
    decoded = ControllerApiClient(controller_url=controller_url, api_key=api_key).get("/jobs")
    return _json_object_list(decoded, "jobs")


def submit_job(controller_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    decoded = ControllerApiClient(controller_url=controller_url, api_key=api_key).post("/jobs", payload)
    if not isinstance(decoded, dict):
        raise RuntimeError("Controller job creation response must be a JSON object")
    return decoded


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode()


def json_loads(payload: bytes) -> Any:
    decoded = json.loads(payload.decode())
    return decoded


def _json_object_list(decoded: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(decoded, list):
        raise RuntimeError(f"Controller {name} response must be a JSON list")
    if not all(isinstance(item, dict) for item in decoded):
        raise RuntimeError(f"Controller {name} response must contain JSON objects")
    return decoded


def _required_step_str(step: dict[str, Any], key: str) -> str:
    value = step.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"claimed step is missing {key}")
    return value


def _required_step_int(step: dict[str, Any], key: str) -> int:
    value = step.get(key)
    if not isinstance(value, int):
        raise RuntimeError(f"claimed step is missing integer {key}")
    return value


def _required_json_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"claimed step input_json is missing {key}")
    return value
