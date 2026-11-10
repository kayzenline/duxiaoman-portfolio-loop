# AI 协作详细记录

DESIGN.md §7 的完整版本。每一条都可以在 `.loop/runs/<run>/`（`result.json`、`review.md`）、`.loop/journal/` 或 git 历史中核对。

**v1 复盘（为什么重新设计）**：另一个仓库里的 v1 Loop（原始运行结果已归档到 [docs/v1-postmortem/](docs/v1-postmortem/)，包括每次运行的 `result.json`、agent.log 字节数和任务配置） 让 Grok 无人值守地实现代码，四次真实运行全部失败：`4891cdeb` 在 300 秒硬超时时被杀；运行器紧接着自动重试（`9bd3e591`，attempt 2，56 秒后被协调者以 SIGTERM 终止，退出码 143）；改配置后的 `37b31515`、`0c5b4d45` 也都在 300 秒时被杀（归档的 `v1-task-config.json` 是最后这份 `max_attempts: 1` 的配置）。四次的 agent.log 都是 0 字节（归档时用 `wc -c` 记录，空文件本身没有复制），原因是 `--output-format json` 要等进程结束才输出。`max_attempts: 1` 加上工作流签名锁让状态卡死，产品代码为 0。v2 的调整：改为流式输出 + 空闲超时；实现交给交互式会话；审查方只读；按失败签名判断是否阻塞；先写验收测试并用 git tag 锁定。

**关键交互 1 — T0 门禁被审查打回（实际核验）**
- 上下文与完成标准：审查 prompt 包含任务目标、锁定的 spec 文件、允许修改的文件、diff，并要求以 JSON 结论结尾（`loop/gate.py: review_prompt`）。
- 生成结果：`.loop/runs/20261110-224651-T0-loop-7ccc68/review.md` 判定不通过，3 个阻塞问题：①检查失败的错误文本里包含每次都不同的日志路径，导致"同一错误连续 3 次才阻塞"在 checks 阶段永远不会触发；②`mark` 可以在没过 gate 的情况下记录合并；③`git status` 把重命名显示为 `old -> new`，可以绕过干净检查。
- 核验方法：逐条对照代码确认属实后修复，并补充覆盖这些场景的测试（`test_same_failing_check_three_times_blocks`、`test_clean_check_sees_both_sides_of_a_rename` 等；这些测试是修复之后才补的，没有做"修复前先失败"的验证），然后以理由"Grok review round 1 found untested checks-stage stop rule and rename bypass"显式重新锁定 spec（见 `.loop/journal/T0-loop.jsonl`）。
- 采纳依据：3 条都是可复现的 bug，全部采纳。6 条建议中：完全采纳 4 条（拒绝非 ask 的 `--mode`、格式错误的 blocking 条目判为不通过、用 `-z` 解析 git 输出、在 T1 目标中写明现金口径）；部分采纳 1 条（检查命令跑完后再做一次干净检查已实现，"把检查命令也纳入 spec 锁"未实现，理由是 `tasks.json` 只在 loop 自身的任务中允许修改，已由 scope 锁住）；推迟 1 条（"相同 hash 重新锁定 spec 时不应清空失败计数"，第 4 轮审查再次提出；修复在 `fix/T0b-hardening` 分支，PR 待合并，main 上的 `loop/gate.py` 仍是旧行为）。

**关键交互 2 — 审查改进了需求的忠实度（T3）**
- 生成结果：`.loop/runs/20261110-235957-T3-frontend-92e357/review.md` 判定通过，但指出前端用 `Number()` 解析数量，`1.0` 会被序列化成 JSON 的 `1` 而被接受，与后端"拒绝小数"的口径不一致；"持仓标的数"是页面上唯一由浏览器计算的数字。
- 核验方法：用 Node 实际执行 `JSON.stringify({q: Number("1.0")})`，输出 `{"q":1}`；`"1e2"`、`"0x10"` 分别变成 100、16，问题属实。修复：只有规范的整数字符串才转成数字，其余原样提交给后端；`held_count` 改由后端返回。重新过 gate，`.loop/runs/20261111-001322-T3-frontend-92ef26` 判定通过。
- 采纳依据：直接关系到 FR-05"后端执行校验、前端不重复口径"，全部采纳。

**关键交互 3 — 自己的配置错误被门禁拦下**
- 加固时我把 `.loop/` 的白名单收得过窄，导致已提交的审查证据被 scope 拒绝（`.loop/runs/20261110-230625-T0-loop-2631d4`）；T3 漏列了 e2e 配置文件（`.loop/runs/20261110-230628-T3-frontend-779bb4`）。这两次都在调用 Grok 之前就被机械门禁拦下，没有消耗审查额度。教训已写入 `tasks/lessons.md`：改动 scope 规则后，先用 `--skip-review` 跑一遍机械门禁。
- 另一个 Claude 会话指出：T1/T2 的 PR base 开在 main，diff 里混入了还没审查的 T0 代码。处理方式：把 PR base 改成各自的父分支，按 T0 → T1 → T2 的顺序用 merge commit 合并（gate 通过时的 SHA 保持不变），并用 `gh pr merge --match-head-commit` 锁定合并的 HEAD。

**门禁运行统计**（每一次 gate 运行都在 `.loop/runs/` 中有 `result.json`）
| 切片 | gate 运行 | 结果明细 | Grok 阻塞问题 | 建议处理 |
| --- | --- | --- | --- | --- |
| T0 Loop | 4 | Grok 不通过 1（`7ccc68`）· scope 失败 1（`2631d4`，我的白名单写错）· 审查超时 1（`b2a309`，不计入失败）· 通过 1（`f8bdc6`） | 3 | 第 1 轮见上；第 4 轮 10 条进入 T0b |
| T1 引擎 | 1 | 通过（`fb4ef3`） | 0 | 3 条中采纳 1 条（拒绝非零手续费）；Decimal 上下文、不可变持仓未采纳（种子数据量级远低于默认精度；结果对象不对外暴露） |
| T2 API | 1 | 通过（`34235b`） | 0 | 4 条中采纳 2 条（框架层校验错误统一格式、SPA 挂载保护）；改同步函数、整数百分比舍入未采纳（单用户场景；当前实现精确） |
| T3 前端 | 6 | scope 失败 3（`779bb4` 漏列 e2e 配置；`460924` 本地 main 过期；`bd3f56` gate 自身未跟踪目录的 bug）· 仅机械检查 1（`945960`）· Grok 通过 2（`92e357`、`92ef26`） | 0 | 第 1 轮 4/4 采纳；第 2 轮 0/3（见 §6） |
| T4 交付 | 多轮 | 仅机械检查（`4887d3`）→ Grok 通过（`d8583a`，6 条建议）→ 修改文档 → 仅机械检查（`ea6321`）→ Grok 通过（`7fe998`，4 条文档准确性建议）→ 再次修改。最终一轮的运行 ID 无法写进被它审查的文档本身，见 `.loop/journal/T4-delivery.jsonl` 和 PR 描述 | 0 | 第 1 轮 5 条采纳、1 条经核验不成立（见下文交互 4）；第 2 轮 4 条全部采纳 |

**关键交互 4 — 核验后不采纳 AI 的说法（T4）**
- 生成结果：`.loop/runs/20261111-003155-T4-delivery-d8583a/review.md` 认为原始 JSON 请求体 `{"quantity": 1.0}` 会被 `json.loads` 解析成 Python int `1`，因此 HTTP 层会接受它。
- 核验方法：实际执行 `json.loads('{"q":1.0}')`，得到 `1.0 float`；向 `/api/simulate` 发送原始请求体，得到 HTTP 422 `INVALID_QUANTITY`（记录见 `docs/verify/api-ac04.txt`）。
- 结论：说法不成立，不修改代码；但把 `1.0` 和 `true` 的原始 HTTP 用例补进验证记录，消除 VERIFY 中的歧义。同一次审查里其余 5 条（文档统计口径、干净安装脚本只检查总资产、§3 措辞、缺少证据文件）属实，全部修改。

此外，Claude Code 的自动安全审查插件对 loop 代码提出了 15 条意见，逐条转录及对应 commit 见 [docs/security-review-log.md](docs/security-review-log.md)：12 条已在 main 中修复，2 条在 T0b 中修复，1 条（证据伪造）超出"单一可信操作者"的威胁模型，不修复。另有一次核验也值得记录：T0b 中"未跟踪证据目录"的测试，我临时回退了修复，确认测试会失败，然后再恢复修复。

**关键交互 5 — 再次核验后不采纳（T4 第 3 轮）**
- `.loop/runs/20261111-010541-T4-delivery-faa64f/review.md` 认为 `docs/verify/clean-install.txt` 最后一行只有 `CLEAN INSTALL CHECK PASSED`，缺少版本号。
- 核验方法（可复现）：该轮审查的 HEAD 是 `fe7b8e3`；执行 `git show fe7b8e3:docs/verify/clean-install.txt | tail -1`，输出为 `CLEAN INSTALL CHECK PASSED (Python 3.12.9, node v22.22.0)`，所以说法不成立。
- 后续：同一轮还建议在日志中记录 uv/npm 版本，这条成立，因此脚本的结束行改为同时输出 uv 和 npm 版本并重新生成，**当前**文件最后一行是 `CLEAN INSTALL CHECK PASSED (Python 3.12.9, uv 0.12.23, node v22.22.0, npm 10.9.4)`。同一轮"DESIGN 超出 2–4 页"也成立，因此把本详细记录从 DESIGN.md 中拆出。
- 下一轮（`.loop/runs/20261111-012002-T4-delivery-0162c4`）指出：上面的旧引用和当前文件内容对不上，读者无法复现。于是把核验方法改写成上面这种带 commit 的形式。

**T4 门禁运行全表**：`4887d3` 仅机械检查 → `d8583a` 通过（6 条建议）→ `ea6321` 仅机械检查 → `7fe998` 通过（4 条）→ `43b9c5` 仅机械检查 → `faa64f` 通过（5 条，1 条不成立）→ `1be7d1` 仅机械检查 → `0162c4` 不通过（2 个阻塞问题，即上一条的可复现性问题）→ 修复后再次过 gate，最终结果见 PR 描述。
