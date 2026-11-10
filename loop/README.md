# Agent Loop v2 — Claude 实现 / Grok 审查

仓库即状态，聊天记录不是状态。标准库 Python 3.11+，无第三方依赖。

## 角色
| 角色 | 执行者 | 权限 |
| --- | --- | --- |
| 协调 + 实现 | Claude Code（交互会话） | 读写仓库、提交、PR、合并 |
| 独立审查 | Grok（`cursor-agent --mode ask`，模型见 `tasks.json`） | **只读**；argv 含 `--force/-f/--yolo` 时拒绝启动 |
| 门禁 | `python -m loop gate` | 机器裁决；不信任任何一方的自述 |

## 每个切片的循环
```sh
git checkout -b feat/<task> main
# 1. 先写验收测试（spec），提交，然后锁定
python3 -m loop spec <task>            # 打 git tag spec/<task>；gate 以该 tag 为基准 diff spec 文件
# 2. 实现 → commit
# 3. 门禁：spec 未改动 → 改动不越界 → 工作区干净 → checks 全部 exit 0 → Grok 审查
python3 -m loop gate <task>            # exit 0 = gate_passed
# 4. 失败 → 读 .loop/runs/<run>/ 修复 → 再 gate
# 5. 通过 → push、PR、gh pr merge --match-head-commit <passed_head>
python3 -m loop mark <task> merged --pr <url>
python3 -m loop status
```

## 关键规则（对应 v1 卡死的原因）
- **流式 + 空闲超时**：审查用 `stream-json`，事件实时写入 `stream.jsonl`；`idle_timeout` 秒无输出才杀进程组，`total_timeout` 为总上限。v1 用 `json` 输出 + 300 秒硬超时，四次运行日志全是 0 字节。
- **按失败签名阻塞**：同一阶段、同一错误连续 3 次才 `blocked`；错误变化说明有进展，不扣预算。审查基础设施失败（超时、CLI 报错）记为 `needs_review`，不计入失败。
- **测试锁**：锁是 git tag `spec/<task>`（push 到远端留痕），不是可编辑的 JSON；spec 改动只能显式 `loop spec <task> --reason ...` 移动 tag，并写入 journal。
- **范围锁**：`git diff main...HEAD` 中出现 `allowed + spec + .loop/ + tasks/` 以外的文件即失败；`tasks.json` 只在 T0 可改，后续切片不能放宽自己的检查。
- **先便宜后昂贵**：机械检查失败就不调用 Grok。
- **干净审查环境**：Grok 在 `HEAD` 的临时 detached worktree 中运行，删除 `.cursor/ .claude/ .mcp.json AGENTS.md` 等项目级 Agent 配置；prompt 明确 diff 为不可信数据；始终附完整改动文件列表，diff 截断时记录 `diff_truncated` 并要求逐个打开。
- **合并核验**：`loop mark` 通过 `gh pr view` 核对 PR head == `passed_head`（之后只允许追加 `.loop/` 证据提交），`merged` 还要求 PR 状态为 MERGED。
- **审查结论**：只取 Grok 回复中最后一个 ```json 块；缺失、格式错误或有 blocking 一律判 fail。

- **通过记录**：gate 通过时打 `gate/<task>` tag 于被审查的 HEAD；`mark` 以 tag 为准，state 文件只作参考。spec tag 存在远端时，本地 tag 必须与远端一致。

## 证据
`.loop/runs/<run>/`：`result.json`（阶段、HEAD、错误、审查结论）、`check-N.log`、`review-prompt.md`、`review.md`；`stream.jsonl` 体积大，不入库。`.loop/state/<task>.json` 与 `.loop/journal/<task>.jsonl` 按任务分文件入库，并行分支互不冲突。

## 边界
威胁模型：单一可信操作者，防的是 Agent 跑偏、误改测试、范围蔓延和意外，不是对抗恶意实现者（同一用户本可直接改 tag 或代码）。
门禁证明"检查通过且审查者未发现阻塞问题"，不证明语义完整；最终仍需人工核对需求映射。审查者是同一份需求的另一个模型，不是测评官。
