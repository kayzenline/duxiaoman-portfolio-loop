// Display-only formatting of backend strings. No arithmetic on business values.
export const money = (s: string) => {
  const [int, frac] = s.split('.');
  return `${int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${frac}`;
};
export const pct = (s: string) => `${s}%`;
// "2026-11-02T15:00:00+08:00" -> "2026-11-02 15:00（北京时间）" without timezone conversion.
export const snapshotTime = (iso: string) =>
  `${iso.slice(0, 10)} ${iso.slice(11, 16)}${iso.endsWith('+08:00') ? '（北京时间）' : ` (${iso.slice(19)})`}`;
export const sideLabel = { buy: '买入', sell: '卖出' } as const;
