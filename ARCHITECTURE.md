# MediaOrchard Grove Architecture

## Layers

- `mediaorchard/cli/`: Typer command surface for local development and operator workflows.
- `mediaorchard/shared/`: shared safety primitives, currently API key hashing, secret redaction, path allowlisting, and shared-root validation.
- `mediaorchard/controller/`: planned Controller API, scheduler, database, recovery, and reporting runtime.
- `mediaorchard/worker/`: planned Worker heartbeat, process management, and structured tool execution.
- `tests/`: executable behavior contract for the currently implemented MVP slice.

## Runtime Loops

Current implementation only covers Milestone 0/1 foundations. The planned runtime loops are documented in `plan.md`:

1. Controller scheduler moves `queued -> assigned` after resource and policy checks.
2. Worker `claim-next` only accepts work already assigned to its `node_id`.
3. Workers execute known tools with structured argv and publish cross-step artifacts to shared work storage.
4. Controller recovery fences late completions with `assignment_epoch`.

## Verification Surfaces

- `bash scripts/verify.sh`: harness check plus unit tests.
- `bash scripts/smoke.sh`: CLI import/help smoke test.
- `.venv/bin/python -m pytest`: direct test invocation.
