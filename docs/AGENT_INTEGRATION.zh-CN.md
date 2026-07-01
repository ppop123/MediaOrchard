# 外部 agent 如何调用 MediaOrchard

本文面向 Codex、Claude、脚本型调度器、内部运营 agent 等外部调用方，说明如何把 MediaOrchard 当作一个 **agent native** 媒体处理后端来调用。

MediaOrchard 当前有两类 agent 角色：

- 操作员 agent：提交媒体任务、查询 Job/Node 状态、读取输出产物。
- 执行 agent：作为 Worker 注册、上报心跳、领取已分配 Step、执行工具并回报生命周期。

两类角色都必须运行在可信网络内，并持有 Controller 的 raw API key。MVP 阶段没有公网多租户授权模型，不要把 Controller 暴露给不可信调用方。

## 0. 调用前置条件

调用前先准备：

```bash
export MEDIAORCHARD_CONTROLLER_URL='http://127.0.0.1:8765'
export MEDIAORCHARD_API_KEY='replace-with-raw-api-key'
export MEDIAORCHARD_SHARED_ROOT='/Volumes/MediaOrchard'
```

所有提交给 Controller 的媒体输入路径必须位于 `MEDIAORCHARD_SHARED_ROOT` 下。多机器模式下，本机、`192.168.50.8`、`192.168.50.9` 必须看到同一个共享存储 marker，而不是各自机器上路径相同的本地目录。

推荐 Controller 启动方式：

```bash
export MEDIAORCHARD_API_KEY_HASH='sha256:replace-with-generated-hash'
export MEDIAORCHARD_NODE_PRIORITIES='192.168.50.8=100,192.168.50.9=100,local=0'

mediaorchard controller start \
  --host 0.0.0.0 \
  --port 8765 \
  --shared-root "$MEDIAORCHARD_SHARED_ROOT"
```

## 接口速查

操作员 agent 常用接口：

- `POST /jobs`：创建媒体处理 Job。
- `GET /jobs`：列出 Job。
- `GET /jobs/{job_id}`：查询单个 Job。
- `GET /nodes`：查看 Worker 节点状态。

执行 agent/Worker 常用接口：

- `POST /nodes/register`：注册 Worker。
- `POST /nodes/{node_id}/heartbeat`：上报资源心跳，并触发调度。
- `POST /steps/claim-next`：领取已经分配给自己的 Step。
- `POST /steps/{step_id}/start`：报告 Step 开始执行。
- `POST /steps/{step_id}/complete`：报告 Step 完成。
- `POST /steps/{step_id}/fail`：报告 Step 失败。

## 1. 操作员 agent：用 CLI 调用

这是最稳的调用方式，适合 Codex/Claude 这类能执行 shell 命令的 agent。

### 1.1 提交任务

```bash
mediaorchard submit "$MEDIAORCHARD_SHARED_ROOT/inbox/demo.mp4" \
  --controller-url "$MEDIAORCHARD_CONTROLLER_URL" \
  --api-key "$MEDIAORCHARD_API_KEY" \
  --goal video_to_subtitle \
  --output srt \
  --output txt \
  --output json \
  --language zh \
  --priority 5
```

成功后 CLI 会输出 Job id，例如：

```text
Created job job_abc123 (queued)
```

### 1.2 查询状态

```bash
mediaorchard jobs \
  --controller-url "$MEDIAORCHARD_CONTROLLER_URL" \
  --api-key "$MEDIAORCHARD_API_KEY"

mediaorchard nodes \
  --controller-url "$MEDIAORCHARD_CONTROLLER_URL" \
  --api-key "$MEDIAORCHARD_API_KEY"
```

操作员 agent 的循环通常是：

1. 确认输入文件在共享根目录下。
2. 调用 `mediaorchard submit`。
3. 周期性调用 `mediaorchard jobs`。
4. Job 进入 `completed` 后，从 `output_dir` 读取 `transcript.txt`、`subtitle.srt`、`transcript.json`、`quality_report.json`。
5. Job 进入 `failed` 时读取 Job/Step 的错误信息和 Worker 日志。

## 2. 操作员 agent：用 HTTP API 调用

适合不方便执行 CLI、但可以发 HTTP 请求的 agent。

认证方式二选一：

```text
Authorization: Bearer <raw-api-key>
X-MediaOrchard-Key: <raw-api-key>
```

### 2.1 创建 Job

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/jobs" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "goal_type": "video_to_subtitle",
    "input_file": "/Volumes/MediaOrchard/inbox/demo.mp4",
    "outputs": ["srt", "txt", "json"],
    "language": "zh",
    "quality": "standard",
    "priority": 5,
    "user_request": "生成字幕和转写"
  }'
```

关键字段：

- `goal_type`：MVP 目前支持 `video_to_subtitle`。
- `input_file`：必须在共享根目录内。
- `outputs`：可请求 `srt`、`txt`、`json`。
- `priority`：Job 优先级，当前用于业务排序语义，节点选择由 Scheduler cost 和节点优先级控制。
- `user_request`：保留原始用户意图，方便 agent 追溯。

### 2.2 查询 Job 和 Node

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/jobs" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY"

curl -sS "$MEDIAORCHARD_CONTROLLER_URL/jobs/<job_id>" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY"

curl -sS "$MEDIAORCHARD_CONTROLLER_URL/nodes" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY"
```

推荐状态处理：

- `queued`：等待 Worker 心跳触发调度。
- `running`：至少一个 Step 已被 Worker 领取或执行。
- `completed`：读取 `output_dir` 下的产物。
- `failed`：读取 `error_message`，必要时查看 Worker stdout/stderr 日志。

## 3. 执行 agent：作为 Worker 接入

如果外部 agent 要自己扮演 Worker，它必须遵守 Controller 分配模型：不能随便抢任务，只能领取已经分配给自己 `node_id` 的 Step。

所有 Worker 生命周期请求都需要：

```text
Authorization: Bearer <raw-api-key>
X-MediaOrchard-Node-Id: <node_id>
```

### 3.1 注册 Worker

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/nodes/register" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "agent-worker-1",
    "name": "Agent Worker 1",
    "shared_root": "/Volumes/MediaOrchard",
    "max_ffmpeg_jobs": 1,
    "max_whisper_jobs": 1
  }'
```

### 3.2 上报心跳

心跳会更新资源指标，并触发 Controller 尝试调度 queued Step。

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/nodes/agent-worker-1/heartbeat" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{
    "cpu_percent": 12.5,
    "memory_percent": 40.0,
    "free_disk_gb": 512.0,
    "active_jobs": 0,
    "active_ffmpeg_jobs": 0,
    "active_whisper_jobs": 0,
    "thermal_state": "normal",
    "on_battery": false
  }'
```

### 3.3 领取已分配 Step

```bash
curl -i "$MEDIAORCHARD_CONTROLLER_URL/steps/claim-next" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "agent-worker-1"}'
```

返回 `204 No Content` 表示当前没有分配给该 Worker 的 Step。返回 `200` 时会得到 Step JSON。执行 agent 必须保存其中的：

- `id`
- `job_id`
- `tool_name`
- `input_json`
- `assignment_epoch`

后续 start/complete/fail 都必须带同一个 `assignment_epoch`。

### 3.4 上报 start/complete/fail

开始执行：

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/steps/<step_id>/start" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{"assignment_epoch": 1}'
```

成功完成：

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/steps/<step_id>/complete" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment_epoch": 1,
    "output_json": {
      "status": "completed",
      "output_dir": "/Volumes/MediaOrchard/output/job_abc123",
      "artifacts": ["subtitle.srt", "transcript.txt", "transcript.json"]
    }
  }'
```

失败：

```bash
curl -sS "$MEDIAORCHARD_CONTROLLER_URL/steps/<step_id>/fail" \
  -H "Authorization: Bearer $MEDIAORCHARD_API_KEY" \
  -H "X-MediaOrchard-Node-Id: agent-worker-1" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment_epoch": 1,
    "error_message": "ffmpeg exited nonzero"
  }'
```

## 4. 推荐 agent 调用策略

操作员 agent 优先用 CLI，因为 CLI 已经封装了 URL、认证、JSON 解析和常见参数。HTTP API 适合服务集成。

执行 agent 优先直接运行内置 Worker：

```bash
mediaorchard worker start \
  --node-id agent-worker-1 \
  --controller-url "$MEDIAORCHARD_CONTROLLER_URL" \
  --api-key "$MEDIAORCHARD_API_KEY" \
  --shared-root "$MEDIAORCHARD_SHARED_ROOT" \
  --execution-mode real
```

只有当外部 agent 需要接管具体执行逻辑时，才手写 `register -> heartbeat -> claim-next -> start -> complete/fail`。

## 5. 安全和边界

- 不要把 raw API key 写入仓库、日志、公开 issue 或 release notes。
- 不要把 Controller 暴露到公网。
- 不要让未验证的远端 Worker 直接执行真实媒体任务。
- 不要绕过 `assignment_epoch`；它是防止过期 Worker 污染状态的围栏。
- 不要让高优先级节点绕过硬过滤；节点优先级只影响健康节点之间的排序。
- 多机器执行前必须跑 `bash scripts/release_env_check.sh`，并启用共享存储 marker 校验。
