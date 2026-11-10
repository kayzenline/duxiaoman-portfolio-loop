# Todo
- [x] T0-loop：门禁 + Grok 只读审查 + CI（#3，4 次 gate）
- [x] T0b-hardening：SHA 校验 PR、冻结审查范围、远端 fail closed（#5，4 次 gate）
- [x] T1-engine：整数分计算核心，AC-01..04（#1）
- [x] T2-api：FastAPI + SQLite，AC-04 HTTP、AC-05 真实重启（#2）
- [x] T3-frontend：React UI + e2e（#4）
- [x] T4-delivery：README / DESIGN / VERIFY / 截图 / 干净安装（#6）

## Review
所有切片都经过 `loop gate`（spec 锁 → 范围 → 干净 → 检查 → Grok 只读审查）后才合并，并用 merge commit 保留 gate 通过时的 SHA。
后续可做（DESIGN §6）：T3 第 2 轮的 3 条前端打磨建议、CI 加入 e2e 与干净安装、Dockerfile、价格缺失/行业未知的实现。
