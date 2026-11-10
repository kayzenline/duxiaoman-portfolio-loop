# Lessons

## 2026-11-10 堆叠 PR 的 base 必须等于 gate 的 --base
- 现象：T1/T2 用 `loop gate --base <父分支>` 审查，PR 却开到 main，PR diff 含有未审查的 T0 代码。（另一会话指出）
- 规则：堆叠切片的 PR base = gate 时的 `--base`；父 PR 用 merge commit 合并后再自动 retarget 到 main。
- 待做：`loop mark` 核对 PR `baseRefName` 与 gate 记录的 base 一致（或该 base 已并入 main）。

## 2026-11-10 收窄白名单时要回归检查 gate 自己写的路径
- 现象：加固时把 ALWAYS_ALLOWED 收窄，导致已提交的 `.loop/runs/` 证据被 scope 拒绝；T3 漏列 e2e 配置。
- 规则：改 scope 规则后，用"真实分支 + --skip-review"先跑一遍机械门禁，再花 Grok 的额度。
