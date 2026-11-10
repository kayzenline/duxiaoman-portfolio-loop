// Typed client for the FastAPI backend. Every business number arrives as a ready string;
// the UI only formats (thousand separators) and never recomputes values.
export type Side = 'buy' | 'sell';
export interface Op { side: Side; symbol: string; quantity: unknown }
export interface Position { symbol: string; name: string; industry: string; price: string; quantity: number;
  market_value: string; weight: string; over_threshold: boolean }
export interface IndustryRow { industry: string; value: string; weight: string; over_threshold: boolean }
export interface Alert { kind: 'instrument' | 'industry'; target: string; label: string; ratio: string;
  threshold: string; message: string }
export interface Valuation { total: string; cash: string; cash_weight: string; held_count: number; positions: Position[];
  industries: IndustryRow[]; alerts: Alert[] }
export interface Portfolio { portfolio: { id: string; name: string };
  snapshot: { id: string; at: string; currency: string };
  thresholds: { instrument: string; industry: string };
  instruments: { symbol: string; name: string; price: string }[]; valuation: Valuation }
export interface Simulation { ops: Op[]; original: Valuation; simulated: Valuation }
export interface Scenario extends Simulation { id: number; name: string; snapshot_id: string; created_at: string }
export interface ScenarioSummary { id: number; name: string; snapshot_id: string; op_count: number; created_at: string }
export interface ApiError { code: string; message: string; index?: number }

export class RequestFailed extends Error {
  error: ApiError;
  constructor(error: ApiError) { super(error.message); this.error = error; }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, body === undefined ? undefined : {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch {
    throw new RequestFailed({ code: 'NETWORK', message: '无法连接后端服务，请确认服务已启动' });
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new RequestFailed(data?.error ?? { code: `HTTP_${res.status}`, message: `请求失败（HTTP ${res.status}）` });
  }
  return data as T;
}

export const api = {
  portfolio: () => call<Portfolio>('/api/portfolio'),
  simulate: (ops: Op[]) => call<Simulation>('/api/simulate', { ops }),
  save: (name: string, ops: Op[]) => call<Scenario>('/api/scenarios', { name, ops }),
  scenarios: () => call<ScenarioSummary[]>('/api/scenarios'),
  scenario: (id: number) => call<Scenario>(`/api/scenarios/${id}`),
};
