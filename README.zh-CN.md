# MediaOrchard Grove 中文说明

MediaOrchard Grove 是一个本地优先的 Mac 媒体处理编排系统，用来协调可信的 Mac Worker 执行 `ffmpeg`、`ffprobe` 和 `mlx-whisper` 等真实媒体任务。

它的核心定位是 **Agent 原生**（agent native）：系统不是给传统脚本套一层聊天界面，而是从一开始就把 Controller、Scheduler、Worker、工具调用、状态机和发布验证设计成可被 agent 理解、执行、审计和恢复的运行面。

英文主文档见 [README.md](README.md)，中文发布说明见 [RELEASE.zh-CN.md](RELEASE.zh-CN.md)。如果你要把 MediaOrchard 接给 Codex、Claude 或其他自动化 agent，先读 [外部 agent 调用文档](docs/AGENT_INTEGRATION.zh-CN.md)。

## 为什么说它是 Agent 原生

MediaOrchard 的 agent native 体现在几个关键边界：

- Controller 是控制面：负责接收 Job、生成 Plan/Step、持久化状态、执行调度策略和恢复流程。
- Worker 是受信任的执行 agent：注册身份、上报心跳和资源指标，只领取已经分配给自己的 Step，并回报 start/complete/fail 生命周期。
- Step 有明确的 `assignment_epoch`：用于防止旧 Worker、重试流程或并发请求误报状态。
- 工具调用是结构化的：Worker 使用 `list[str]` argv、`shell=False`、超时、stdout/stderr 日志和结果 JSON，而不是让 agent 拼 shell 字符串碰运气。
- 调度策略是可解释的：先做硬过滤，再做 cost scoring；节点优先级、资源压力、并发限制和温控状态都会留下可审计的决策痕迹。
- 发布流程是 agent 可执行的：`scripts/release_check.sh` 和 `scripts/release_env_check.sh` 是固定入口，方便 Codex/Claude 这类 agent 复跑、比对和汇报证据。

外部 agent 调用 MediaOrchard 时有两种角色：操作员 agent 负责提交任务和查状态，执行 agent/Worker 负责注册、心跳、领取 Step 和回报生命周期。完整调用契约见 [docs/AGENT_INTEGRATION.zh-CN.md](docs/AGENT_INTEGRATION.zh-CN.md)。

## 当前能力

- FastAPI Controller，提供节点、Job、Step 生命周期 API。
- SQLite/SQLModel 持久化，适合本地 MVP 和可审计开发。
- Scheduler 支持心跳触发的 Step 分配、硬过滤和节点 scoring。
- Worker 支持注册、心跳、claim-next、Step start/complete/fail 上报。
- CLI 支持启动 Controller/Worker、提交任务、查看 jobs/nodes、执行 Worker 预检和 bootstrap dry-run。
- 确定性 `video_to_subtitle` demo，可在没有真实媒体工具时生成 release-shaped 产物。
- real-media Worker 模式可通过 `ffprobe`、`ffmpeg` 和 `mlx_whisper` 生成 transcript/subtitle 产物。
- 多机器环境预检支持本机、`wangyan@192.168.50.8`、`wangyan@192.168.50.9` 这类 SSH target。

## 运行前提

- Python 3.11+。
- 目标 Worker 环境是 macOS。
- MVP 阶段使用可信局域网和共享 API key。
- 多机器执行必须使用真实共享存储，并且在 Controller 和 Worker 上解析到同一路径，例如 `/Volumes/MediaOrchard`。
- 真实媒体执行需要 `ffmpeg`、`ffprobe` 和可 import `mlx_whisper` 的 Python 环境。

## 快速安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
bash scripts/verify.sh
bash scripts/smoke.sh
```

未安装 console script 时可直接运行：

```bash
.venv/bin/python -m mediaorchard.cli.main --help
```

## Controller 配置示例

```bash
export MEDIAORCHARD_API_KEY_HASH='sha256:replace-with-generated-hash'
export MEDIAORCHARD_SHARED_ROOT='/Volumes/MediaOrchard'
export MEDIAORCHARD_DATABASE_URL='sqlite:///mediaorchard.db'
export MEDIAORCHARD_NODE_PRIORITIES='192.168.50.8=100,192.168.50.9=100,local=0'

mediaorchard controller start --host 0.0.0.0 --port 8765
```

也可以直接传节点优先级：

```bash
mediaorchard controller start \
  --node-priority 192.168.50.8=100 \
  --node-priority 192.168.50.9=100
```

这里的优先级是软偏好：`192.168.50.8` 和 `192.168.50.9` 会在健康且资源达标时优先于本机，但不会绕过心跳、CPU、内存、磁盘、温控和并发这些硬过滤。

## 多机器发布边界

单机 demo 可以使用临时本地目录。多机器真实媒体执行必须满足：

- 所有 target 都能访问同一个真实共享存储，而不是各自机器上路径相同的本地目录。
- 共享根目录中有 marker 文件，例如 `/Volumes/MediaOrchard/.mediaorchard-shared-root-id`。
- 本机、`192.168.50.8`、`192.168.50.9` 都能读到相同 marker token。
- 每台 Worker 都具备 Python 3.11+、`ffmpeg`、`ffprobe` 和 whisper backend。

发布前执行：

```bash
export SHARED_ROOT_MARKER=.mediaorchard-shared-root-id
export SHARED_ROOT_MARKER_VALUE="$(cat /Volumes/MediaOrchard/.mediaorchard-shared-root-id)"
bash scripts/release_env_check.sh
```

## 验证入口

```bash
bash scripts/release_check.sh
bash scripts/release_env_check.sh
```

`release_check.sh` 覆盖 harness check、全量测试、CLI smoke、sdist/wheel 构建、`twine check` 和 clean install smoke。

`release_env_check.sh` 是多机器只读门禁：它会运行 Worker preflight，并打印 bootstrap dry-run；不会执行远程 bootstrap。
