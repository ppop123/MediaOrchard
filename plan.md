# MediaOrchard Grove MVP Implementation Plan

> **For Claude/Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build a reliable local multi-Mac media processing scheduler that can turn video or audio files into transcript and subtitle outputs through structured, policy-controlled worker jobs.

**Architecture:** MediaOrchard Grove uses an authenticated Controller plus Worker Agents. The Controller owns durable state, policy checks, planning, scheduling, and APIs; the scheduler is the only component that assigns queued work to nodes. Workers register with a shared API key, prove their shared-storage mount, report resources, claim only work already assigned to their node, execute validated tool calls, publish durable artifacts to shared work storage, stream progress, and return results. MVP is deterministic first: agent-readable objects exist from day one, but LLM-driven intake and recovery are deferred until the runtime is stable.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, SQLModel or SQLAlchemy, Pydantic, Typer, psutil, uvicorn, subprocess with structured argv only, ffmpeg/ffprobe, and whisper-mlx or mlx-whisper.

---

## 1. Repository Status And Source Of Truth

This document is the repo-level architecture and implementation roadmap. It should stay aligned with the actual codebase, but release readiness is tracked in `docs/RELEASE_CHECKLIST.md` and day-to-day progress is tracked in `progress.md`.

Current implemented foundation:

```text
/Users/wy/MediaOrchard/
  AGENTS.md
  ARCHITECTURE.md
  README.md
  config.example.yaml
  docs/
  mediaorchard/
  plan.md
  progress.md
  pyproject.toml
  scripts/
  tests/
```

MVP package name:

```text
mediaorchard
```

MVP CLI command:

```bash
mediaorchard
```

---

## 2. Product Positioning

MediaOrchard Grove is an agent-native local media processing orchestrator for several Macs on the same trusted local network.

It schedules `ffmpeg`, `ffprobe`, and `whisper-mlx` / `mlx-whisper` work across available machines while respecting resource limits, thermal state, battery state, path safety, retry limits, and user approval boundaries.

Core principle:

```text
Agents decide, tools execute, policies constrain, state persists.
```

MVP interpretation:

```text
Rules plan and schedule first. Agent-shaped records are persisted now. LLM decisions can be added later without changing the execution safety model.
```

---

## 3. MVP Scope

### In Scope

1. Controller FastAPI service.
2. SQLite-backed durable state.
3. Worker registration and heartbeat with shared-secret authentication.
4. CLI for starting Controller, starting Worker, submitting jobs, and inspecting status.
5. Rule-based `video_to_subtitle` pipeline.
6. Step scheduling across registered Workers.
7. Resource-aware node filtering and scoring.
8. Safe structured execution of `ffprobe`, `ffmpeg`, and whisper.
9. Generation of `srt`, `txt`, and `json` outputs.
10. Basic subtitle/transcript quality checks.
11. Per-step logs and human-readable reports.
12. Limited retry and recovery for common failures.
13. Controller restart recovery for unfinished jobs.
14. Shared storage verification before multi-machine scheduling.

### Explicit Non-Goals For MVP

1. Kubernetes, Celery, Redis, or cloud orchestration.
2. Web dashboard.
3. Real LLM intake or autonomous planning.
4. Multi-user or multi-tenant authorization.
5. Long-video multi-machine chunking.
6. Speaker diarization.
7. Translation or bilingual subtitle generation.
8. Automatic upload to external services.
9. Arbitrary shell execution.
10. Overwriting or deleting user source media.

---

## 4. Primary User Flows

### Flow A: Run A Single Worker Demo

```bash
mediaorchard controller start
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard worker start --node-id mac-studio
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard submit /Volumes/MediaOrchard/inbox/demo.mp4 --goal video_to_subtitle --language zh --output srt --output txt --output json
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard jobs
```

Expected output directory:

```text
/Volumes/MediaOrchard/output/<job_id>/
  input_meta.json
  audio.wav
  transcript.txt
  transcript.json
  subtitle.srt
  quality_report.json
  report.md
  logs/
```

### Flow B: Register Three Macs

Each Mac runs one Worker with a stable `node_id`, the same `MEDIAORCHARD_API_KEY`, a verified shared storage mount, and node-specific concurrency limits. The Controller shows all online Workers and schedules work only to eligible nodes.

```bash
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard worker start --node-id mac-studio
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard worker start --node-id mac-mini
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard worker start --node-id macbook-pro
mediaorchard nodes
```

### Flow C: Recover From Failure

If a Worker disappears, the Controller marks assigned or running steps retryable, releases the node assignment, and requeues the step when retry limits permit.

---

## 5. Target Repository Layout

```text
mediaorchard/
  pyproject.toml
  README.md
  config.example.yaml
  plan.md

  mediaorchard/
    __init__.py

    cli/
      __init__.py
      main.py

    controller/
      __init__.py
      main.py
      api/
        __init__.py
        jobs.py
        nodes.py
        steps.py
      scheduler/
        __init__.py
        loop.py
        scoring.py
        policies.py
      db/
        __init__.py
        migrations/
        session.py
        models.py
      runtime/
        __init__.py
        planner.py
        state_machine.py
        recovery.py
        reports.py

    worker/
      __init__.py
      agent.py
      heartbeat.py
      executor.py
      metrics.py
      process_manager.py
      tools/
        __init__.py
        ffprobe_tool.py
        ffmpeg_tool.py
        whisper_tool.py
        subtitle_tool.py
        qa_tool.py

    shared/
      __init__.py
      config.py
      enums.py
      logging.py
      paths.py
      schemas.py
      security.py

  scripts/
    benchmark_node.py

  tests/
    test_api.py
    test_mock_pipeline.py
    test_paths.py
    test_policy.py
    test_recovery.py
    test_scheduler.py
    test_state_machine.py
    test_subtitle_qa.py
    test_worker_lifecycle.py
```

Do not create launchd installers in MVP unless the basic CLI demo already works.

---

## 6. Durable Domain Model

Persist every important state transition. The database is the recovery boundary.

### Node

Purpose: current and configured Worker state.

Required fields:

```text
id, name, host, status,
shared_root, auth_key_id,
max_ffmpeg_jobs, max_whisper_jobs,
active_jobs, active_ffmpeg_jobs, active_whisper_jobs,
cpu_percent, memory_percent, free_disk_gb,
thermal_state, on_battery,
last_heartbeat_at, created_at, updated_at
```

### Job

Purpose: user-level work request.

Required fields:

```text
id, goal_type, input_file, output_dir,
status, priority, language, quality,
requested_outputs, user_request,
plan_id, progress, error_message,
created_at, updated_at, completed_at
```

### Plan

Purpose: immutable-ish pipeline snapshot for one Job.

Required fields:

```text
id, job_id, status, created_by, plan_schema_version, plan_json, created_at, updated_at
```

`plan_schema_version` and `plan_json.version` must both be set to `"1"` in MVP. Recovery and reports must reject unknown plan versions instead of guessing.

### Step

Purpose: executable unit scheduled to a Worker.

Required fields:

```text
id, job_id, plan_id,
step_type, tool_name, status,
depends_on, assigned_node_id,
assigned_at, claimed_at, assignment_epoch,
input_json, output_json,
retry_count, max_retries,
started_at, completed_at, error_message
```

`claimed_at` is the claim lease marker for a Step already assigned to a Worker node. `assignment_epoch` is a fencing token. The Controller increments it every time a Step is assigned or requeued. Worker `claim`, `start`, `progress`, `complete`, and `fail` calls must include the epoch they received; Controller must reject stale epochs so late completions from old attempts cannot publish results.

### ToolCall

Purpose: auditable Worker execution record.

Required fields:

```text
id, job_id, step_id, node_id,
tool_name, args_json, status,
stdout_path, stderr_path, exit_code,
started_at, completed_at
```

### AgentDecision

Purpose: explainable decisions now, future LLM decisions later.

Required fields:

```text
id, job_id, agent_name, decision_type,
decision_json, reason, confidence, created_at
```

### QualityReport

Purpose: result validation summary.

Required fields:

```text
id, job_id, status,
checks_json, warnings_json, recommendations_json,
created_at
```

---

## 7. State Machines

### Job Status

```text
created -> planning -> queued -> running -> completed
created -> planning -> waiting_approval -> queued -> running -> completed
running -> failed
running -> retrying -> queued -> running -> completed
running -> cancelled
```

Allowed values:

```text
created, planning, waiting_approval, queued, running, completed, failed, cancelled, retrying
```

MVP retry semantics:

1. Step-level retry does not automatically move the Job to `retrying`; the Job remains `running` while at least one retryable Step is being requeued.
2. Job-level `retrying` is used only when the Job has reached a failed terminal state and the user or recovery policy explicitly retries the Job.
3. `waiting_approval` is part of the durable model, but MVP should enter it only for configured approval triggers such as overwrite, long MacBook battery work, or batch size over threshold. If no approval trigger is implemented in the first demo, no Job should transition into `waiting_approval`.

### Step Status

```text
pending -> queued -> assigned -> running -> completed
pending -> queued -> assigned -> running -> failed -> queued
pending -> queued -> assigned -> failed -> queued
pending -> queued -> assigned -> queued
pending -> skipped
assigned -> cancelled
running -> cancelled
```

Allowed values:

```text
pending, queued, assigned, running, completed, failed, skipped, cancelled
```

State transitions must be centralized in `mediaorchard/controller/runtime/state_machine.py` rather than scattered through API handlers.

Recovery rules:

1. `assigned -> queued` is allowed only when the assigned Worker heartbeat has expired before the Step reached `running`.
2. `assigned -> failed` is allowed for explicit claim/start failures.
3. `running -> failed -> queued` is allowed only while `retry_count < max_retries`.
4. When a Worker heartbeat expires, Controller recovery must inspect both `assigned` and `running` Steps owned by that Worker and release their assignments.
5. A timed-out `running` Step must first become `failed` with reason `worker_heartbeat_timeout`; it may then be requeued as a new attempt only if retry limits allow it.
6. MVP accepts that a timed-out Worker may still finish late. Late completion reports for a failed or requeued attempt must be rejected, and per-attempt shared work directories prevent final output collisions.

---

## 8. Controller API Contract

MVP endpoints:

```text
POST /jobs
GET /jobs
GET /jobs/{job_id}
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry

GET /jobs/{job_id}/steps
GET /jobs/{job_id}/logs
GET /jobs/{job_id}/quality-report

GET /nodes
GET /nodes/{node_id}
POST /nodes/register
POST /nodes/{node_id}/heartbeat

POST /steps/claim-next
POST /steps/{step_id}/claim
POST /steps/{step_id}/start
POST /steps/{step_id}/progress
POST /steps/{step_id}/complete
POST /steps/{step_id}/fail
```

Post-MVP endpoints:

```text
GET /plans/{plan_id}
GET /tools
POST /tools/validate
```

All Worker-facing endpoints require `Authorization: Bearer <api_key>` or an equivalent `X-MediaOrchard-Key` header. Step claim and lifecycle endpoints also require `X-MediaOrchard-Node-Id: <node_id>` so the Controller can bind the call to the Step's assigned node. The API key is configured out-of-band and must never be stored in logs or persisted as plaintext; store only an identifier or hash if needed.

MVP uses a shared API key plus node-id header binding on a trusted local network. Per-node API keys or mTLS are post-MVP hardening unless the network boundary changes.

`POST /steps/claim-next` is the preferred MVP polling endpoint, but it must not choose directly from the global queued pool. The scheduler loop is the only component allowed to move a Step from `queued` to `assigned`; it must apply the hard filters and scoring rules in Section 10 before setting `assigned_node_id`.

`POST /steps/claim-next` payload:

```json
{
  "node_id": "mac-studio"
}
```

The `node_id` payload must match `X-MediaOrchard-Node-Id`.

`claim-next` returns one Step already assigned to the authenticated node. Its database guard must be equivalent to `WHERE status='assigned' AND assigned_node_id=:node_id AND claimed_at IS NULL`; if two processes using the same `node_id` race, exactly one may receive a claim lease. MVP assumes one active Worker process per `node_id`; duplicate active registrations should be rejected or should explicitly replace the previous heartbeat.

When no Step is claimable for the authenticated node, `claim-next` returns `204 No Content`.

`POST /steps/{step_id}/claim` may exist for tests or explicit retries, but it must use the same assigned-node guard. Worker code must not bypass scheduler assignment.

`POST /steps/{step_id}/progress` payload:

```json
{
  "percent": 0.0,
  "message": "extracting audio",
  "assignment_epoch": 3
}
```

`percent` may be `null` when the tool cannot estimate progress. `message` may be `null`; it must be treated as log text, not as executable input.

The Worker should never receive arbitrary shell text from the Controller. It receives a validated `ToolCall` with a known `tool_name` and schema-validated arguments.

---

## 9. Pipeline Planning

MVP planner is rule-based.

### `video_to_subtitle`

```text
probe_media -> extract_audio -> transcribe_audio -> collect_outputs -> quality_check -> write_report
```

`write_report` is a Controller-side terminal operation, not a Worker tool. It is shown in the pipeline because it is a durable step in the Job lifecycle, but it should run in Controller runtime code after quality data and scheduling decisions are available.

### Deferred Pipelines

```text
transcribe_audio_only -> transcribe_audio -> collect_outputs -> quality_check -> write_report
extract_audio_only -> probe_media -> extract_audio
mux_subtitle -> probe_media -> mux_subtitle
burn_subtitle -> probe_media -> burn_subtitle
```

Only implement deferred pipelines after `video_to_subtitle` passes the demo acceptance criteria.

---

## 10. Scheduling Policy

Hard filters run before scoring.

Scheduling ownership:

```text
Only the Controller scheduler loop may move a Step from queued to assigned.
Worker polling may only claim Steps already assigned to that Worker's node_id.
The scheduler must persist rejected-node reasons and selected-node score breakdown before assignment.
The scheduler must re-check the selected node's heartbeat freshness immediately before writing an assignment.
```

A node is ineligible when any condition is true:

```text
node is offline
heartbeat age > scheduler.heartbeat_timeout_seconds
node shared_root is missing or does not match the Controller storage contract
cpu_percent > scheduler.max_cpu_percent
memory_percent > scheduler.max_memory_percent
free_disk_gb < scheduler.min_free_disk_gb
thermal_state in serious, critical
node_id is in job constraints avoid_nodes
node is on battery and estimated runtime exceeds battery limit
active_whisper_jobs >= max_whisper_jobs for whisper steps
active_ffmpeg_jobs >= max_ffmpeg_jobs for ffmpeg steps
```

Lightweight Steps such as `collect_outputs` and `quality_check` may run on any node with verified shared storage. Prefer the lowest-load eligible node, or the node that produced the latest required artifact when that reduces shared-storage IO.

Eligible nodes are scored with a simple deterministic cost:

```text
node_cost =
  0.30 * cpu_load
+ 0.20 * memory_pressure
+ 0.15 * active_same_type_jobs
+ 0.10 * thermal_penalty
+ 0.10 * disk_io_penalty
+ 0.10 * recent_usage_penalty
- 0.10 * file_locality_bonus
- 0.10 * benchmark_speed_bonus
```

MVP may stub `disk_io_penalty`, `recent_usage_penalty`, `file_locality_bonus`, and `benchmark_speed_bonus` as `0.0`, but the scoring function should keep named components so decisions stay explainable. The numeric cost is used only for ordering eligible nodes; its absolute value has no product meaning and should not be shown as a normalized health score.

Every assignment must persist an `AgentDecision` or scheduling decision record with:

```text
step_id, selected_node_id, rejected_nodes, score_breakdown, reason
```

---

## 11. Safety And Policy Rules

### Always Allowed

```text
read media metadata
extract audio to job work/cache directory
generate transcript and subtitle files in job output directory
write logs for the current job
clean this job's own local cache
query node state
perform bounded retry
```

### Controller-Worker Communication Security

```text
Worker registration, heartbeat, step claim, progress, completion, and failure endpoints require a shared API key.
The shared API key is passed through environment variable or local config, never as a CLI positional argument.
The Controller logs only the node_id and auth_key_id/hash prefix, never the raw key.
Unknown or missing keys receive 401 and must not create Node or Step records.
MVP may use HTTP on a trusted local network; TLS or mTLS is post-MVP unless the network boundary changes.
```

### Requires Explicit User Approval

```text
overwrite existing output files
delete intermediate files outside this job's cache
burn subtitles while overwriting a source video
change global default model
run long heavy work on a MacBook while on battery
batch process more than the configured approval threshold
```

### Forbidden

```text
execute arbitrary shell strings
access files outside configured allowlisted roots
delete source media
delete user home files
modify system security settings
install unknown dependencies from Worker execution
bypass scheduler and run a task directly
upload media to external services without explicit authorization
```

Safety implementation belongs in:

```text
mediaorchard/shared/paths.py
mediaorchard/shared/security.py
mediaorchard/controller/scheduler/policies.py
mediaorchard/worker/executor.py
```

---

## 12. Path And Storage Contract

Default shared root:

```text
/Volumes/MediaOrchard
```

Default layout:

```text
/Volumes/MediaOrchard/
  inbox/
  work/
  output/
  logs/
  cache/
```

Per-job output:

```text
/Volumes/MediaOrchard/output/<job_id>/
  input_meta.json
  audio.wav
  transcript.txt
  transcript.json
  subtitle.srt
  subtitle.vtt
  quality_report.json
  report.md
  logs/
```

Per-job shared work directory:

```text
/Volumes/MediaOrchard/work/<job_id>/
  probe_media/
    input_meta.json
  extract_audio/
    attempt_1/
      audio.wav
  transcribe_audio/
    attempt_1/
      transcript.txt
      transcript.json
      subtitle.srt
      subtitle.vtt
```

Worker local cache:

```text
/tmp/mediaorchard-cache/<job_id>/
  input.mp4
  audio.wav
  partial/
  output/
```

Rules:

1. User inputs must resolve under configured allowlisted roots.
2. Output directories are created by the Controller or Worker from `job_id`, not from raw user strings.
3. The default policy is no overwrite.
4. Cleanup is limited to this job's cache directory.
5. Original media is read-only.
6. MVP multi-machine mode requires all Workers to report a reachable shared root compatible with the Controller storage config.
7. Worker registration must fail or mark the node ineligible when the shared root is not mounted, not writable where writes are required, or not the same logical storage.
8. Single-machine mode is allowed for the first demo; multi-machine scheduling should not be enabled until the shared-root check passes for each Worker.
9. Worker local cache is scratch space only. Any artifact needed by a later Step must be copied or written to the shared work directory before the producing Step is marked completed.
10. Each retry attempt writes to a distinct shared work attempt directory. `attempt_N` is derived from `assignment_epoch` or `retry_count + 1`; choose one representation in implementation and use it consistently. Final outputs are published only by `collect_outputs` after the producing Step has completed successfully.

Shared-root check at Worker registration:

```text
Worker reports shared_root path, realpath, filesystem id if available, and read/write probe results.
Controller verifies the path matches configured storage expectations.
Controller persists shared_root and marks mismatched nodes as offline or ineligible with a readable reason.
```

---

## 13. Worker Execution Contract

Worker responsibilities:

1. Register with Controller.
2. Send heartbeat with resource metrics at `worker.heartbeat_interval_seconds`.
3. Poll or claim queued steps.
4. Validate ToolCall schema again locally.
5. Resolve and validate paths.
6. Execute known tools using structured argv lists.
7. Capture stdout/stderr to log files.
8. Report start, progress, completion, and failure.
9. Terminate child process on cancellation.
10. Clear only this job's cache when safe.
11. On graceful shutdown, stop claiming new work, report active Step interruption, and terminate the child process group.

Allowed tool names for MVP:

```text
probe_media
extract_audio
transcribe_audio
collect_outputs
quality_check
```

`subprocess` usage must pass `list[str]` argv with `shell=False`.

Worker shutdown behavior:

```text
SIGINT/SIGTERM -> set draining flag
draining Worker does not claim new Steps
if a child process is running, terminate the process group
report active Step as failed with reason interrupted_by_worker_shutdown
exit only after reporting or after a short bounded timeout
```

---

## 14. Tool Behavior

### `probe_media`

Runs `ffprobe` and returns duration, stream, codec, resolution, and audio metadata.

### `extract_audio`

Runs `ffmpeg` to create mono 16 kHz audio for transcription.

Required argv shape:

```bash
ffmpeg -y -i <input_video> -vn -ac 1 -ar 16000 <output_audio>
```

The `-y` flag is allowed only for system-owned cache/output paths after overwrite policy passes.

### `transcribe_audio`

Runs configured whisper backend and writes requested transcript/subtitle outputs. The first implementation may support one backend, but the config should keep the backend explicit.

### `collect_outputs`

Copies or registers successful shared-work artifacts into the job output directory. It must not transform media content. It verifies requested output formats, records final paths in `output_json`, and refuses to overwrite existing files unless approval policy allows it. It must read from `/Volumes/MediaOrchard/work/<job_id>/...`, not from another Worker's local `/tmp` cache.

### `quality_check`

Reads inputs from the shared job output directory and shared work directory, never from another Worker's local cache.

Checks at minimum:

```text
output files exist
output files are non-empty
SRT timestamps are monotonic
subtitle text is not empty
subtitle count is plausible for media duration
last subtitle timestamp roughly matches media duration
obvious repeated-failure patterns are absent
```

Quality outcome levels:

```text
passed: Job may complete.
warning: Job may complete, but report must list warnings and recommendations.
failed: Job must not complete until retry or user intervention resolves the issue.
```

### `write_report`

Controller-side operation that writes `quality_report.json` and `report.md` with job duration, node assignments, outputs, warnings, and scheduling explanation. It should not be scheduled to a Worker because it needs authoritative Controller state.

---

## 15. Configuration Contract

Create `config.example.yaml` in the first implementation milestone.

Expected shape:

```yaml
controller:
  host: "0.0.0.0"
  port: 8765
  database_url: "sqlite:///mediaorchard.db"
  api_key_hash: "replace-with-generated-hash"
  api_key_hash_algorithm: "sha256"

worker:
  heartbeat_interval_seconds: 10
  claim_interval_seconds: 2
  shutdown_grace_seconds: 10

storage:
  shared_root: "/Volumes/MediaOrchard"
  inbox_dir: "/Volumes/MediaOrchard/inbox"
  output_dir: "/Volumes/MediaOrchard/output"
  logs_dir: "/Volumes/MediaOrchard/logs"
  local_cache_dir: "/tmp/mediaorchard-cache"

scheduler:
  heartbeat_timeout_seconds: 30
  schedule_interval_seconds: 5
  default_priority: 5
  cooldown_minutes: 10
  max_cpu_percent: 85
  max_memory_percent: 85
  min_free_disk_gb: 20

recovery:
  default_max_retries: 2
  retry_backoff_seconds: 10

logging:
  format: "json"
  level: "INFO"
  redact_fields: ["api_key", "authorization", "token", "secret"]

whisper:
  backend: "mlx-whisper"
  default_model: "mlx-community/whisper-large-v3-turbo"
  fallback_model: "mlx-community/whisper-medium"
  default_language: "auto"
  output_formats: ["txt", "srt", "json"]

ffmpeg:
  audio_sample_rate: 16000
  audio_channels: 1
  overwrite_outputs: false

nodes:
  mac-studio:
    max_ffmpeg_jobs: 2
    max_whisper_jobs: 1
    avoid_on_battery: false

  mac-mini:
    max_ffmpeg_jobs: 1
    max_whisper_jobs: 1
    avoid_on_battery: false

  macbook-pro:
    max_ffmpeg_jobs: 1
    max_whisper_jobs: 1
    avoid_on_battery: true
    max_runtime_on_battery_minutes: 20
```

README must document API key creation and hashing. MVP may provide a CLI helper such as `mediaorchard auth hash-key` or a documented Python one-liner that writes only `api_key_hash` to config while Workers receive the raw key through `MEDIAORCHARD_API_KEY`.

---

## 16. Implementation Roadmap

### Milestone 0: Repo Bootstrap

**Status:** implemented.

**Files:**

```text
Create: pyproject.toml
Create: README.md
Create: config.example.yaml
Create: mediaorchard/__init__.py
Create: mediaorchard/cli/main.py
Create: tests/
```

**Done when:**

```bash
python -m pytest
mediaorchard --help
```

both run successfully in a fresh environment.

### Milestone 1: Shared Types, Config, And Path Safety

**Status:** implemented for the current foundation.

**Files:**

```text
Create: mediaorchard/shared/config.py
Create: mediaorchard/shared/enums.py
Create: mediaorchard/shared/paths.py
Create: mediaorchard/shared/schemas.py
Create: mediaorchard/shared/security.py
Create: tests/test_paths.py
Create: tests/test_policy.py
```

**Focus:** path allowlists, no-overwrite defaults, API-key config and redaction, shared-root validation, Pydantic request/response schemas, enum definitions.

**Done when:** path traversal, outside-root access, overwrite cases, API-key validation helpers, secret redaction, and shared-root mismatch cases are covered by tests.

### Milestone 2: Database Models And State Machine

**Status:** implemented for core models, state transitions, and broad persistence coverage.

**Files:**

```text
Create: mediaorchard/controller/db/session.py
Create: mediaorchard/controller/db/models.py
Create: mediaorchard/controller/runtime/state_machine.py
Create: tests/test_recovery.py
Create: tests/test_state_machine.py
```

**Focus:** Node, Job, Plan, Step, ToolCall, AgentDecision, QualityReport; plan schema version; centralized legal transitions; assigned/running Step recovery rules.

**Done when:** invalid status transitions fail deterministically, legal transitions persist, unknown plan versions are rejected, and assigned/running Steps can be recovered after Worker timeout.

MVP database migration rule:

```text
During pre-release development, destructive drop-and-recreate is acceptable only for local disposable databases.
Before any real job history is kept, add Alembic migrations or an explicit schema_version migration path.
README must state which mode the current build uses.
```

### Milestone 3: Controller API

**Status:** implemented for node registration, heartbeat, job create/list/get, automatic deterministic Plan/Step creation, heartbeat-triggered queued Step assignment, assigned Step claim, and Step lifecycle updates. Job cancellation/retry and richer read APIs are still pending.

**Files:**

```text
Create: mediaorchard/controller/main.py
Create: mediaorchard/controller/api/jobs.py
Create: mediaorchard/controller/api/nodes.py
Create: mediaorchard/controller/api/steps.py
Create: tests/test_api.py
```

**Focus:** create/list/get jobs, authenticated register/list/get nodes, authenticated heartbeat, atomic step claim, step lifecycle updates.

**Done when:** API tests can create a job, reject unauthenticated Worker calls, register a node, heartbeat it, atomically claim one Step under simulated concurrent requests, and inspect stored state.

### Milestone 4: Planner And Scheduler

**Status:** scheduler policies, scoring, assignment helper, and heartbeat-triggered assignment are implemented. General planner abstractions and persistent scheduling decision records are still pending.

**Files:**

```text
Create: mediaorchard/controller/runtime/planner.py
Create: mediaorchard/controller/scheduler/scoring.py
Create: mediaorchard/controller/scheduler/policies.py
Create: mediaorchard/controller/scheduler/loop.py
Create: tests/test_scheduler.py
```

**Focus:** create `video_to_subtitle` steps, enforce hard filters, score eligible nodes, persist reasons.

**Done when:** tests prove overloaded, offline, low-disk, hot, battery-constrained, and shared-root-mismatched nodes do not receive new work.

### Milestone 5: Worker Runtime And Tools

**Status:** WorkerAgent registration, heartbeat, assigned-step claim, start/complete/fail reporting, shutdown interruption reporting, live metrics collection, structured command execution, deterministic pipeline artifacts, and local real-media smoke coverage are implemented. Worker-orchestrated real `ffmpeg`/`mlx_whisper` multi-step execution is still a hardening item.

**Files:**

```text
Create: mediaorchard/worker/agent.py
Create: mediaorchard/worker/heartbeat.py
Create: mediaorchard/worker/executor.py
Create: mediaorchard/worker/metrics.py
Create: mediaorchard/worker/process_manager.py
Create: mediaorchard/worker/tools/ffprobe_tool.py
Create: mediaorchard/worker/tools/ffmpeg_tool.py
Create: mediaorchard/worker/tools/whisper_tool.py
Create: mediaorchard/worker/tools/subtitle_tool.py
Create: mediaorchard/worker/tools/qa_tool.py
Create: tests/test_mock_pipeline.py
Create: tests/test_subtitle_qa.py
Create: tests/test_worker_lifecycle.py
```

**Focus:** heartbeat metrics, polling/claiming steps, structured argv execution, structured JSON log capture, cancellation-safe process handling, graceful shutdown.

**Done when:** local fake or fixture-based tests can execute `probe_media`, validate an SRT, reject unknown tool names, run a mock `video_to_subtitle` pipeline without real media tools, and prove shutdown interrupts active work without leaving orphaned child processes.

### Milestone 6: CLI End-To-End Demo

**Status:** `controller start`, `worker start`, `submit`, `jobs`, and `nodes` are implemented. A process-level single-machine CLI E2E smoke can submit a `video_to_subtitle` job, run one Worker poll, complete the deterministic pipeline, list completed job state, and verify release-shaped artifacts. `job`, `cancel`, `retry`, and JSON output modes remain post-demo hardening.

**Files:**

```text
Modify: mediaorchard/cli/main.py
Modify: README.md
```

**Focus:** `controller start`, `worker start`, `submit`, `jobs`, `job`, `nodes`, `cancel`, `retry`.

**Done when:** one Controller and one Worker can run the demo pipeline from the README.

CLI output contract:

```text
mediaorchard jobs: human-readable table by default, JSON with --json.
mediaorchard job <job_id>: concise status summary by default, full JSON with --json.
mediaorchard nodes: human-readable table by default, JSON with --json.
Errors: one-line human message by default, structured JSON error with --json.
```

### Milestone 7: Recovery And Reports

**Status:** state-machine recovery helpers exist, and deterministic/real-smoke report artifacts are implemented. Runtime recovery loop, retry orchestration, and first-class report APIs are still pending.

**Files:**

```text
Create: mediaorchard/controller/runtime/recovery.py
Create: mediaorchard/controller/runtime/reports.py
Modify: mediaorchard/controller/scheduler/loop.py
Modify: mediaorchard/worker/executor.py
```

**Focus:** bounded retry, Worker timeout handling, failure classification, `quality_report.json`, `report.md`.

**Done when:** simulated Worker failure requeues a retryable assigned or running Step, retry limits are enforced, and final successful jobs produce report artifacts.

---

## 17. Testing And Verification

Use a 60 second timeout for routine test runs.

Recommended commands:

```bash
python -m pytest
python -m pytest tests/test_api.py -v
python -m pytest tests/test_scheduler.py -v
python -m pytest tests/test_recovery.py -v
python -m pytest tests/test_worker_lifecycle.py -v
python -m pytest tests/test_mock_pipeline.py -v
python -m pytest tests/test_paths.py tests/test_policy.py -v
mediaorchard --help
mediaorchard controller start --help
mediaorchard worker start --help
```

Automated test minimums before the manual demo:

```text
API auth rejects missing and invalid Worker credentials
Worker registration verifies shared_root compatibility
Scheduler alone assigns queued Steps to eligible nodes
Worker claim-next only returns Steps already assigned to that node
Step claim is atomic under concurrent requests using the same node_id
stale assignment_epoch completion/failure reports are rejected
assigned Steps recover after Worker heartbeat timeout
running Steps recover or fail after Worker heartbeat timeout according to retry limits
mock ffprobe/ffmpeg/whisper pipeline can complete without real media tools
later Steps read required artifacts from shared work storage, not another Worker's local cache
logging redacts configured secret fields
```

Manual demo verification after MVP:

```bash
mediaorchard controller start
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard worker start --node-id local-dev
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard submit /Volumes/MediaOrchard/inbox/demo.mp4 --goal video_to_subtitle --language zh --output srt --output txt --output json
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard jobs
MEDIAORCHARD_API_KEY=<shared-secret> mediaorchard nodes
```

Success criteria:

```text
job reaches completed
all planned steps have terminal successful status
output directory exists
subtitle.srt exists and is non-empty
transcript.txt exists and is non-empty
transcript.json exists and is non-empty
quality_report.json exists
report.md exists
logs exist for tool execution
logs are structured and do not expose configured secret fields
```

---

## 18. MVP Acceptance Criteria

1. Controller can start from CLI.
2. Worker can start from CLI and register with Controller.
3. Missing or invalid Worker API keys are rejected.
4. Controller shows at least one online Worker with a verified shared root.
5. Three Workers with different `node_id` values can be registered only when their shared-root checks pass.
6. CLI can submit a `video_to_subtitle` job.
7. Controller creates a durable versioned plan and steps for the job.
8. Scheduler is the only component that assigns queued Steps and assigns only eligible Workers.
9. Worker claim-next returns only Steps assigned to that Worker node.
10. Concurrent Workers cannot claim the same Step.
11. CPU, memory, disk, thermal, heartbeat, battery, shared-root, and concurrency hard filters are enforced.
12. Worker executes `ffprobe` and `ffmpeg` through structured argv, not shell strings.
13. Worker executes whisper through the configured backend.
14. Cross-step artifacts required by later Steps are available in shared work storage.
15. Job outputs `srt`, `txt`, and `json` when requested.
16. Quality report is generated with passed/warning/failed semantics.
17. Human-readable report is generated by Controller-side runtime code.
18. Structured logs are persisted per step and redact secrets.
19. Failed retryable steps retry only within configured limits and write to per-attempt work directories.
20. Worker disappearance releases assigned/running Step ownership and can requeue work.
21. Late completion from a stale Worker attempt with an old `assignment_epoch` cannot publish final outputs.
22. Worker graceful shutdown interrupts or reports active work without orphaning child processes.
23. Controller restart does not lose unfinished jobs.
24. Scheduling decisions include readable reasons.

---

## 19. Open Decisions

Resolve these during implementation, not before bootstrap:

1. Exact whisper CLI invocation for the installed backend on each Mac.
2. Whether `audio.wav` should be copied to final output by default or kept only as an intermediate artifact.
3. Exact threshold for batch approval.
4. Whether `vtt` is part of MVP default outputs or optional.
5. Whether local HTTP plus shared API key is enough for the first trusted-network deployment, or whether TLS is required before using more than one physical Mac.
6. Whether post-MVP hardening should use per-node API keys, mTLS, or both.

Default choices until changed:

```text
SQLModel
Worker polling
shared storage must be verified before a Worker becomes schedulable
audio.wav retained in output for demo transparency
batch approval threshold = 10 files
vtt optional, not default
local HTTP plus shared API key for MVP trusted network
```

---

## 20. Engineering Rules

1. Keep MVP deterministic and small.
2. Add agent-shaped records without adding autonomous LLM behavior yet.
3. Prefer explicit schemas over loose dictionaries at API boundaries.
4. Keep shell execution impossible by design: structured argv, `shell=False`, known tools only.
5. Authenticate all Worker-to-Controller calls.
6. Validate shared storage before scheduling a Worker.
7. Validate paths in Controller and Worker.
8. Do not write outside configured roots.
9. Do not overwrite by default.
10. Do not delete original media.
11. Put scheduler rules in one place.
12. Put state transitions in one place.
13. Persist enough logs and reasons to debug failures later.
14. Redact secrets from logs.
15. Add tests for safety, API auth, scheduling, recovery, and Worker lifecycle before broad feature work.
16. Do not hardcode the three Mac names; treat them as config examples.

---

## 21. Future Expansion

After MVP stability:

1. Web dashboard.
2. WebSocket logs.
3. LLM Intake Agent.
4. LLM-assisted Planning Agent.
5. LLM-assisted Recovery Agent.
6. Translation and bilingual subtitles.
7. Speaker diarization.
8. Long-video chunking.
9. Multi-machine parallel transcription.
10. Node benchmark learning.
11. ETA prediction.
12. Night batch mode.
13. MCP server for external agent clients.
14. Pause and resume.
15. User preference memory.

---

## 22. First Implementation Command Sequence

Recommended first execution path:

```bash
# 1. create package skeleton and test harness
# 2. implement shared config/path/security tests
python -m pytest tests/test_paths.py tests/test_policy.py -v

# 3. implement database and state machine
python -m pytest tests/test_state_machine.py tests/test_recovery.py -v

# 4. implement authenticated Controller API and atomic claim
python -m pytest tests/test_api.py -v

# 5. implement scheduler
python -m pytest tests/test_scheduler.py -v

# 6. implement Worker lifecycle and CLI/API smoke path
python -m pytest tests/test_worker_lifecycle.py tests/test_mock_pipeline.py -v
mediaorchard --help
mediaorchard controller start --help
mediaorchard worker start --help
```

Do not attempt the full ffmpeg/whisper demo until path safety, state transitions, and scheduling tests pass.
