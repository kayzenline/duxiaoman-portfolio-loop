# 自动安全审查记录（Claude Code security-guidance 插件）

这些意见来自开发会话中 Claude Code 安全审查插件的自动通知。插件不会把结果写入仓库，所以下面是从会话中**逐条转录**的摘要。每条的处理结果都可以在对应 commit 中核对。

| # | 级别 | 意见 | 处理 | Commit |
| --- | --- | --- | --- | --- |
| 1 | 中 | spec 锁的 hash 存在实现者可以编辑的 `.loop/state.json` 中 | 改为 git tag `spec/<task>`，并推送到远端 | `43d80c4` |
| 2 | 中 | diff 被截断时审查可能漏看 | 始终附完整的改动文件列表；截断时记录 `diff_truncated`，并要求审查者逐个打开文件 | `43d80c4` |
| 3 | 中 | `mark` 没有核对 gate 状态和 PR head | `mark` 改为要求 gate 已通过，且 PR head 等于 `passed_head` | `43d80c4` |
| 4 | 中 | 审查者带 `--trust` 运行在实现者的工作区 | 改为在 HEAD 的临时 detached worktree 中运行，并删除项目级 Agent 配置 | `43d80c4` |
| 5 | 高 | gate 的通过状态可以伪造（state 文件可编辑） | 增加 `gate/<task>` tag 作为权威记录，state 只作参考 | `f55b6d5` |
| 6 | 中 | 本地 spec tag 可以被移动 | 本地 tag 必须与远端一致 | `f55b6d5` |
| 7 | 中 | Agent 配置只在根目录清理 | 任意深度都清理，残留时 fail closed | `f55b6d5` |
| 8 | 中 | 重命名会隐藏源路径（`--name-only`） | 统一使用 `--no-renames -z` | `a533ad8` |
| 9 | 中 | T3 允许修改 `e2e/*`，可以绕过 spec 锁 | e2e 配置和 lock 文件纳入 T3 的 spec | `77b1ee7` |
| 10 | 中 | `.loop/runs/*` 白名单可能被用来伪造证据 | **不修复**：超出"单一可信操作者"的威胁模型，见 `loop/README.md`；后来在 #13 中改为严格布局校验 | — |
| 11 | 中 | 旧审查 prompt 混入 diff，导致截断 | 审查 diff 排除 `.loop/` | `77b1ee7` |
| 12 | 中 | 排除 `.loop/` 之后审查者看不到这些路径 | 只列出路径，省略内容 | `68ab4e8` |
| 13 | 中 | `.loop/` 路径清单可能成为 prompt 注入渠道 | `LOOP_LAYOUT` 严格校验 gate 生成的路径；清单放进标明"不可信"的区域 | `8b3d0a1` |
| 14 | 中 | 远端 tag 查询失败时 fail open | 改为 fail closed（T0b）：配置了 origin 却连不上时拒绝通过 | `fix/T0b-hardening` |
| 15 | 中 | `base_sha` 在 gate 结束时才计算（TOCTOU） | gate 开始时固定 merge-base，并写入 annotated `gate/<task>` tag（T0b） | `fix/T0b-hardening` |

另外，在旧仓库中，插件对 v1 适配器的 `--force` 也提出过意见（不是本仓库的代码）。v2 的审查者只运行在 `--mode ask` 下，并拒绝 `--force/-f/--yolo`，从结构上避开了这个问题。

合计：本仓库 15 条。12 条已在 main 中修复；#14、#15 在 T0b 中修复；#10 不修复（威胁模型之外，后来由 #13 部分覆盖）。
