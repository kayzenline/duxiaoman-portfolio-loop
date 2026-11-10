# 投资组合分析与调仓模拟（VC-FIN-001）

基于固定行情快照 SNAP-20261102 的组合分析原型：组合概览、集中度提醒、顺序调仓模拟、前后对比、方案保存与重开。后端（FastAPI）负责全部计算、校验与保存，前端（React）只负责展示。

- 设计说明：[DESIGN.md](DESIGN.md)（含 AI 协作记录、完成情况与复盘）
- 验证记录：[VERIFY.md](VERIFY.md)（AC-01 至 AC-05、截图）
- 初始方案：[PLAN.md](PLAN.md)（实现前原版，未改写）
- 开发流程：[loop/README.md](loop/README.md)（Claude Code 实现、Grok 只读审查的 Agent Loop）

## 环境（实测版本）

| 组件 | 版本 |
| --- | --- |
| Python | 3.12.9（uv 自动下载，`requires-python >= 3.12`） |
| uv | 0.12.23 |
| Node.js / npm | 22.22.0 / 10.9.4 |
| FastAPI / uvicorn | 0.162.2 / 0.54.0（`uv.lock` 锁定） |
| React / Vite / TypeScript | 19 / 6 / 5.8（`frontend/package-lock.json` 锁定） |

开发与验证在 macOS（Apple Silicon）上完成；Linux/Windows 未实测。

## 安装与初始化

```sh
git clone https://github.com/kayzenline/duxiaoman-portfolio-loop.git
cd duxiaoman-portfolio-loop
uv sync --frozen                      # 后端依赖（含 pytest）
npm --prefix frontend ci              # 前端依赖
npm --prefix frontend run build       # 生成 frontend/dist，由后端托管
```

初始化数据为 `backend/portfolio/seed_portfolio.json`（与邮件附件逐字节一致，测试校验 SHA-256），启动时只读加载，无需导入。方案数据库在首次启动时自动创建，默认路径为 `data/portfolio.db`，可通过环境变量 `PORTFOLIO_DB` 修改。

## 启动

```sh
uv run uvicorn portfolio.main:app --app-dir backend --port 8000
```

访问地址：**http://127.0.0.1:8000** （同一进程提供页面和 `/api/*`）。

前端开发模式（可选，热更新）：保持上面的后端运行，另开终端执行 `npm --prefix frontend run dev`，访问 http://127.0.0.1:5173（`/api` 自动代理到 8000）。

## 方案保存与重开步骤

1. 打开页面，右侧"调仓模拟"中选择 卖出 / A01 / 100 → 添加；再选择 买入 / A02 / 100 → 添加。
2. 底部对比表显示现金 25,000.00、A02 数量 500、科技 55.00%（行业提醒恢复）。
3. 在"方案名称"中输入名称 → 保存方案；"已保存方案"列表出现该方案。
4. 刷新页面（草稿清空，回到原组合），或停止并重新启动服务。
5. 点击"已保存方案"中的名称 → 只读重开，对比结果与保存时一致；左侧原组合仍为现金 20,000.00、A01 400、A02 400。

## 测试

```sh
uv run --frozen pytest -q backend/tests                     # 引擎 + API + 真实进程重启
npm --prefix e2e ci && npx --prefix e2e playwright install chromium
npm --prefix e2e test                                       # 浏览器端到端（需先构建前端）
bash scripts/clean_install_check.sh                         # 干净克隆 → 安装 → 启动 → AC-01/05 + 重启
python3 -m unittest discover -s loop/tests -t .             # Agent Loop 门禁自身
```

## 目录

```
backend/portfolio/  engine.py 计算核心 · present.py 展示舍入 · storage.py SQLite · api.py 接口 · seed_portfolio.json
backend/tests/      引擎、API、真实重启测试
frontend/           React + TypeScript 单页
e2e/                Playwright 流程测试（生成四类截图）
loop/               Agent Loop 门禁；.loop/ 为每轮证据
context/originals/  任务书 PDF、示例 JSON、招聘截图原件
```
