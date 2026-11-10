// T3 acceptance spec: the reviewer's path 组合查看 → 超限识别 → 模拟操作 → 前后对比 → 保存与重开 (task §4.3).
// Screenshots go to $SCREENSHOT_DIR (T4 sets docs/screenshots); default is a gitignored folder.
import { expect, test, type Page } from '@playwright/test';

const shots = process.env.SCREENSHOT_DIR ?? 'test-results/screens';
const shot = (page: Page, name: string) => page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });

async function addOp(page: Page, side: 'buy' | 'sell', symbol: string, qty: string) {
  await page.getByTestId('op-side').selectOption(side);
  await page.getByTestId('op-symbol').selectOption(symbol);
  await page.getByTestId('op-qty').fill(qty);
  await page.getByTestId('op-add').click();
}

test.describe.configure({ mode: 'serial' });

test('AC-01 overview shows totals, distribution, snapshot time and exactly two alerts', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('total')).toHaveText(/100,000\.00/);
  await expect(page.getByTestId('cash')).toHaveText(/20,000\.00/);
  await expect(page.getByTestId('snapshot-at')).toContainText('2026-11-02 15:00');
  await expect(page.getByTestId('position-A01')).toContainText('40.00%');
  await expect(page.getByTestId('industry-科技')).toContainText('60.00%');
  const alerts = page.getByTestId('alerts').getByTestId('alert');
  await expect(alerts).toHaveCount(2);
  await expect(alerts.nth(0)).toContainText('A01');
  await expect(alerts.nth(0)).toContainText('40.00%');
  await expect(alerts.nth(0)).toContainText('30.00%');
  await expect(alerts.nth(1)).toContainText('科技');
  await expect(alerts.nth(1)).toContainText('50.00%');
  await expect(page.getByTestId('ops-empty')).toBeVisible(); // empty-scenario state
  await shot(page, '01-initial');
});

test('AC-02/03 sequential ops update the comparison; AC-04 errors keep the valid result', async ({ page }) => {
  await page.goto('/');
  await addOp(page, 'sell', 'A01', '100');
  await expect(page.getByTestId('sim-cash')).toHaveText(/30,000\.00/);
  await expect(page.getByTestId('sim-alerts').getByTestId('alert')).toHaveCount(0);

  await addOp(page, 'buy', 'A02', '100');
  await expect(page.getByTestId('sim-cash')).toHaveText(/25,000\.00/);
  await expect(page.getByTestId('compare-A02')).toContainText('500');
  await expect(page.getByTestId('compare-industry-科技')).toContainText('55.00%');
  await expect(page.getByTestId('sim-alerts').getByTestId('alert')).toHaveCount(1);
  await expect(page.getByTestId('ops-list').getByRole('listitem')).toHaveCount(2);
  await shot(page, '02-compare');

  // AC-04: each invalid op shows a backend error and leaves the two valid ops/results untouched.
  for (const [side, qty, text] of [['buy', '300', '可用现金'], ['sell', '401', '超过当前模拟持仓'],
                                   ['buy', '0', '正整数'], ['buy', '-1', '正整数'], ['buy', '1.5', '正整数']] as const) {
    await addOp(page, side, 'A01', qty);
    await expect(page.getByRole('alert')).toContainText(text);
    await expect(page.getByTestId('sim-cash')).toHaveText(/25,000\.00/);
    await expect(page.getByTestId('ops-list').getByRole('listitem')).toHaveCount(2);
  }
  await shot(page, '03-error');
});

test('AC-05 save, refresh and reopen give the same result; original untouched', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('save').click();          // empty scenario cannot be saved
  await expect(page.getByRole('alert')).toBeVisible();
  await addOp(page, 'sell', 'A01', '100');
  await addOp(page, 'buy', 'A02', '100');
  await page.getByTestId('scenario-name').fill('AC-03 调仓方案');
  await page.getByTestId('save').click();
  await expect(page.getByTestId('saved-list')).toContainText('AC-03 调仓方案');

  await page.reload();
  await expect(page.getByTestId('ops-empty')).toBeVisible();   // fresh page starts from the original
  await expect(page.getByTestId('cash')).toHaveText(/20,000\.00/);
  await page.getByTestId('saved-list').getByRole('button', { name: /AC-03 调仓方案/ }).click();
  await expect(page.getByTestId('viewing')).toContainText('AC-03 调仓方案');
  await expect(page.getByTestId('sim-cash')).toHaveText(/25,000\.00/);
  await expect(page.getByTestId('compare-A02')).toContainText('500');
  await expect(page.getByTestId('compare-A01')).toContainText('400');  // original column still 400
  await expect(page.getByTestId('cash')).toHaveText(/20,000\.00/);
  await shot(page, '04-saved');
});
