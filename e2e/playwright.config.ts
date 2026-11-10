import { defineConfig } from '@playwright/test';

// Runs the production build: backend serves frontend/dist, fresh SQLite file per run.
export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8765', viewport: { width: 1360, height: 900 }, locale: 'zh-CN' },
  webServer: {
    command: 'rm -rf .e2e-data && mkdir .e2e-data && cd .. && PORTFOLIO_DB=e2e/.e2e-data/e2e.db uv run --frozen uvicorn portfolio.main:app --app-dir backend --port 8765',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
