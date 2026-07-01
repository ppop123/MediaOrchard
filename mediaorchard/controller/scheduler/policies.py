from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from mediaorchard.controller.db.models import Node, Step
from mediaorchard.shared.enums import NodeStatus


@dataclass(frozen=True)
class SchedulerConfig:
    shared_root: str
    heartbeat_timeout_seconds: int = 30
    max_cpu_percent: float = 85.0
    max_memory_percent: float = 85.0
    min_free_disk_gb: float = 20.0
    max_runtime_on_battery_minutes: int = 20
    node_priorities: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str


def is_whisper_step(step: Step) -> bool:
    return step.tool_name in {"transcribe_audio", "mlx_whisper", "whisper", "whisper_tool"}


def is_ffmpeg_step(step: Step) -> bool:
    return step.tool_name in {"probe_media", "extract_audio", "ffprobe", "ffmpeg"} or step.tool_name.startswith(
        "ffmpeg_"
    )


def step_constraints(step: Step) -> dict:
    return step.input_json.get("constraints", {}) if step.input_json else {}


def estimated_runtime_minutes(step: Step) -> float:
    if not step.input_json:
        return 0.0
    value = step.input_json.get("estimated_runtime_minutes", 0)
    return float(value or 0)


def parse_node_priorities(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}

    priorities: dict[str, int] = {}
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError("node priority must use key=value")
        try:
            priority = int(value)
        except ValueError as exc:
            raise ValueError(f"node priority for {key.strip()} must be an integer") from exc
        if priority < 0:
            raise ValueError(f"node priority for {key.strip()} must be non-negative")
        priorities[key.strip()] = priority
    return priorities


def format_node_priorities(priorities: dict[str, int]) -> str:
    return ",".join(f"{key}={value}" for key, value in priorities.items())


def heartbeat_expired(node: Node, config: SchedulerConfig, now: datetime) -> bool:
    if node.last_heartbeat_at is None:
        return True
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    last = node.last_heartbeat_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return (now - last).total_seconds() > config.heartbeat_timeout_seconds


def is_node_eligible(step: Step, node: Node, config: SchedulerConfig, now: datetime | None = None) -> EligibilityResult:
    now = now or datetime.now(UTC)

    if node.status != NodeStatus.ONLINE:
        return EligibilityResult(False, "node_offline")

    if heartbeat_expired(node, config, now):
        return EligibilityResult(False, "heartbeat_expired")

    if node.shared_root != config.shared_root:
        return EligibilityResult(False, "shared_root_mismatch")

    if node.cpu_percent > config.max_cpu_percent:
        return EligibilityResult(False, "cpu_too_high")

    if node.memory_percent > config.max_memory_percent:
        return EligibilityResult(False, "memory_too_high")

    if node.free_disk_gb < config.min_free_disk_gb:
        return EligibilityResult(False, "disk_too_low")

    if node.thermal_state in {"serious", "critical"}:
        return EligibilityResult(False, "thermal_blocked")

    if node.id in step_constraints(step).get("avoid_nodes", []):
        return EligibilityResult(False, "node_avoided")

    if node.on_battery and estimated_runtime_minutes(step) > config.max_runtime_on_battery_minutes:
        return EligibilityResult(False, "battery_runtime_blocked")

    if is_whisper_step(step) and node.active_whisper_jobs >= node.max_whisper_jobs:
        return EligibilityResult(False, "whisper_concurrency_full")

    if is_ffmpeg_step(step) and node.active_ffmpeg_jobs >= node.max_ffmpeg_jobs:
        return EligibilityResult(False, "ffmpeg_concurrency_full")

    return EligibilityResult(True, "eligible")
