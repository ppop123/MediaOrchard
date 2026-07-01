# MediaOrchard 0.1 中文 Release 说明

MediaOrchard 0.1 的发布定位是：**本地优先、Mac Worker 优先、Agent 原生**（agent native）的媒体处理编排系统。

这里的 agent native 不是一句包装话，而是发布边界：系统的 Job、Plan、Step、调度、Worker 生命周期、工具执行和验证脚本，都要能被 agent 可靠读取、执行、复核和恢复。

## 本次发布口径

0.1 是 MVP release hardening 版本，重点不是做一个大而全的媒体平台，而是把 agent native 的控制面和执行面打牢：

- Controller 负责策略、调度、状态持久化和恢复。
- Worker 作为受信任执行 agent，只领取分配给自己的 Step。
- Step 生命周期有 `assignment_epoch` 防护，避免过期上报污染状态。
- 工具执行使用结构化 argv、`shell=False`、超时和日志文件。
- 调度有硬过滤和可解释 scoring，不依赖不可审计的临时脚本判断。
- release gate 有固定命令，可由人或 agent 重复执行并给出证据。

## 已包含能力

- Controller/Worker CLI 基础运行链路。
- Job 创建、Plan/Step 创建、Step 分配、claim、start、complete、fail。
- 确定性 pipeline demo，适合快速 smoke test。
- real-media Worker path，调用 `ffprobe`、`ffmpeg`、`mlx_whisper` 生成 transcript 和 subtitle。
- Worker runtime preflight。
- 多机器 bootstrap dry-run。
- 共享存储 marker 校验。
- 节点优先级配置，例如让 `192.168.50.8` 和 `192.168.50.9` 优先于本机。

## 发布门禁

本地包发布门禁：

```bash
bash scripts/release_check.sh
```

该命令必须通过：

- harness check
- 全量 pytest
- CLI smoke
- sdist/wheel build
- `twine check`
- clean wheel install smoke
- tracked-file hygiene guard

多机器发布门禁：

```bash
export SHARED_ROOT_MARKER=.mediaorchard-shared-root-id
export SHARED_ROOT_MARKER_VALUE='replace-with-token-from-the-shared-root-marker'
bash scripts/release_env_check.sh
```

该命令是只读检查。它会验证本机和 SSH target 的 Python、媒体工具、whisper backend、共享根目录和 marker token，并输出 `mediaorchard doctor worker-bootstrap --copy-wheel` dry-run。

## 多机器声明边界

不要只因为路径都叫 `/Volumes/MediaOrchard` 就宣称多机器可用。多机器真实媒体执行必须证明所有机器读到的是同一个共享存储：

- 本机可访问 `/Volumes/MediaOrchard`。
- `wangyan@192.168.50.8` 可访问同一路径。
- `wangyan@192.168.50.9` 可访问同一路径。
- 三者读取同一个 marker 文件并得到同一个 token。

推荐 marker 生成方式：

```bash
uuidgen > /Volumes/MediaOrchard/.mediaorchard-shared-root-id
```

## 节点优先级发布口径

节点优先级是调度层软偏好，不是强制执行：

```bash
export MEDIAORCHARD_NODE_PRIORITIES='192.168.50.8=100,192.168.50.9=100,local=0'
```

或者：

```bash
mediaorchard controller start \
  --node-priority 192.168.50.8=100 \
  --node-priority 192.168.50.9=100
```

只有节点通过在线、心跳、共享根目录、CPU、内存、磁盘、温控和并发硬过滤后，优先级才参与 cost scoring。高优先级机器不健康时不会被选中。

## 发布结论

可以发布的表述：

- MediaOrchard 0.1 是 agent native 的本地媒体编排 MVP。
- 单机 deterministic demo 和本地包验证已经有固定 release gate。
- real-media path 已接入 `ffprobe`、`ffmpeg` 和 `mlx_whisper`。
- 多机器能力以 `release_env_check.sh` 和共享存储 marker 为准。

暂不应夸大的表述：

- 不应说任意公网或不可信 Worker 可接入。
- 不应说没有共享存储也能做多机器真实媒体执行。
- 不应说高优先级机器可以绕过资源和健康检查。

