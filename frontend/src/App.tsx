import { useCallback, useEffect, useRef, useState } from 'react';
import { api, RequestFailed, type Alert, type ApiError, type Op, type Portfolio, type Scenario,
  type ScenarioSummary, type Side, type Simulation, type Valuation } from './api';
import { money, pct, sideLabel, snapshotTime } from './format';

type Load<T> = { status: 'loading' } | { status: 'error'; error: ApiError } | { status: 'ready'; data: T };

const asError = (e: unknown): ApiError =>
  e instanceof RequestFailed ? e.error : { code: 'UNKNOWN', message: String(e) };

// Only a canonical digit string becomes a JSON integer; anything else ("1.0", "1e2", "0x10", "abc",
// or an integer beyond JS's safe range) is sent verbatim so the backend - not the browser - rejects it.
const parseQty = (text: string): unknown => {
  const t = text.trim();
  if (/^-?(0|[1-9]\d*)$/.test(t)) {
    const n = Number(t);
    if (Number.isSafeInteger(n)) return n;
  }
  return t;
};

export default function App() {
  const [portfolio, setPortfolio] = useState<Load<Portfolio>>({ status: 'loading' });
  const [ops, setOps] = useState<Op[]>([]);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [viewing, setViewing] = useState<Scenario | null>(null);
  const [scenarios, setScenarios] = useState<Load<ScenarioSummary[]>>({ status: 'loading' });
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const seq = useRef(0); // only the latest request may update the screen

  const loadPortfolio = useCallback(() => {
    setPortfolio({ status: 'loading' });
    api.portfolio().then(data => setPortfolio({ status: 'ready', data }),
      e => setPortfolio({ status: 'error', error: asError(e) }));
  }, []);
  const loadScenarios = useCallback(() => {
    api.scenarios().then(data => setScenarios({ status: 'ready', data }),
      e => setScenarios({ status: 'error', error: asError(e) }));
  }, []);
  useEffect(() => { loadPortfolio(); loadScenarios(); }, [loadPortfolio, loadScenarios]);

  // Every change replays the whole sequence on the backend; the draft only advances on success.
  const replay = async (next: Op[]) => {
    const id = ++seq.current;
    setBusy(true); setNotice(null);
    try {
      if (next.length === 0) { setOps([]); setSim(null); setError(null); return; }
      const result = await api.simulate(next);
      if (id !== seq.current) return;
      setOps(next); setSim(result); setError(null);
    } catch (e) {
      if (id === seq.current) setError(asError(e));
    } finally { if (id === seq.current) setBusy(false); }
  };

  const save = async (name: string) => {
    setBusy(true); setNotice(null);
    try {
      const saved = await api.save(name, ops);
      setError(null); setNotice(`已保存方案「${saved.name}」`);
      loadScenarios();
      return true;
    } catch (e) { setError(asError(e)); return false; } finally { setBusy(false); }
  };

  const open = async (scenarioId: number) => {
    const id = ++seq.current;
    setBusy(true); setNotice(null);
    try {
      const s = await api.scenario(scenarioId);
      if (id === seq.current) { setViewing(s); setError(null); }
    } catch (e) {
      if (id === seq.current) setError(asError(e));
    } finally { if (id === seq.current) setBusy(false); }
  };

  if (portfolio.status === 'loading') return <main className="state">正在加载组合…</main>;
  if (portfolio.status === 'error') return (
    <main className="state" role="alert">
      <p>组合加载失败：{portfolio.error.message}</p>
      <button onClick={() => { loadPortfolio(); loadScenarios(); }}>重试</button>
    </main>);

  const p = portfolio.data;
  const shown: Simulation | null = viewing ?? sim;
  return (
    <div className="app">
      <header>
        <div>
          <h1>{p.portfolio.name} <span className="muted">{p.portfolio.id}</span></h1>
          <p className="muted">固定行情快照 {p.snapshot.id} · <span data-testid="snapshot-at">{snapshotTime(p.snapshot.at)}</span> · {p.snapshot.currency}</p>
        </div>
        <p className="muted rules">提醒规则：单一标的 &gt; {pct(p.thresholds.instrument)}，行业 &gt; {pct(p.thresholds.industry)}（等于阈值不提醒）</p>
      </header>

      <div className="layout">
        <section className="col">
          <Overview v={p.valuation} />
          <Alerts alerts={p.valuation.alerts} testId="alerts" title="原组合集中度提醒（快照持仓）" />
          <Holdings v={p.valuation} />
        </section>

        <aside className="col side">
          {viewing ? (
            <div className="panel viewing" data-testid="viewing">
              <h2>已保存方案：{viewing.name}</h2>
              <p className="muted">只读查看 · 快照 {viewing.snapshot_id} · 保存于 {viewing.created_at.slice(0, 19).replace('T', ' ')} UTC</p>
              <OpsList ops={viewing.ops} />
              <button onClick={() => setViewing(null)}>返回编辑草稿</button>
            </div>
          ) : (
            <Builder p={p} ops={ops} busy={busy} onAdd={op => replay([...ops, op])}
              onRemove={i => replay(ops.filter((_, j) => j !== i))} onClear={() => replay([])} onSave={save} />
          )}
          {error && (
            <div className="error" role="alert">
              {error.index !== undefined && !viewing ? <strong>操作未生效。</strong> : null}{error.message}
            </div>)}
          {notice && <div className="notice" role="status">{notice}</div>}
          <Saved list={scenarios} onOpen={open} activeId={viewing?.id} busy={busy} onRetry={loadScenarios} />
        </aside>
      </div>

      <section className="panel">
        <h2>原组合 vs 模拟组合 {viewing ? <span className="muted">（{viewing.name}）</span> : null}</h2>
        {shown ? <Compare s={shown} /> : <p className="muted">添加至少一笔操作后，这里显示调仓前后的持仓、现金与集中度对比。</p>}
      </section>
    </div>
  );
}

function Overview({ v }: { v: Valuation }) {
  return (
    <div className="cards">
      <Card label="总资产（元）" value={money(v.total)} testId="total" />
      <Card label="现金（元）" value={money(v.cash)} sub={`占比 ${pct(v.cash_weight)}`} testId="cash" />
      <Card label="持仓标的" value={`${v.held_count} 只`} />
      <Card label="超限提醒" value={`${v.alerts.length} 项`} warn={v.alerts.length > 0} />
    </div>);
}

function Card({ label, value, sub, testId, warn }: { label: string; value: string; sub?: string; testId?: string; warn?: boolean }) {
  return <div className={`card${warn ? ' warn' : ''}`}><div className="muted">{label}</div>
    <div className="big" data-testid={testId}>{value}</div>{sub && <div className="muted">{sub}</div>}</div>;
}

function Alerts({ alerts, testId, title }: { alerts: Alert[]; testId: string; title: string }) {
  return (
    <div className="panel" data-testid={testId}>
      <h2>{title}</h2>
      {alerts.length === 0 ? <p className="ok">无超限对象</p> : (
        <ul className="alerts">
          {alerts.map(a => (
            <li key={a.kind + a.target} data-testid="alert">
              <span className="tag">{a.kind === 'instrument' ? '单一标的' : '行业'}</span>
              <b>{a.kind === 'instrument' ? `${a.target} ${a.label}` : a.label}</b>
              <span>实际 {pct(a.ratio)}</span><span className="muted">阈值 {pct(a.threshold)}</span>
            </li>))}
        </ul>)}
    </div>);
}

function Holdings({ v }: { v: Valuation }) {
  return (
    <div className="panel">
      <h2>持仓明细</h2>
      <table>
        <thead><tr><th>标的</th><th>行业</th><th className="r">价格</th><th className="r">数量</th><th className="r">市值</th><th className="r">占比</th></tr></thead>
        <tbody>
          {v.positions.map(x => (
            <tr key={x.symbol} data-testid={`position-${x.symbol}`} className={x.over_threshold ? 'over' : ''}>
              <td>{x.symbol} {x.name}</td><td>{x.industry}</td><td className="r">{money(x.price)}</td>
              <td className="r">{x.quantity}</td><td className="r">{money(x.market_value)}</td><td className="r">{pct(x.weight)}</td>
            </tr>))}
          <tr className="cashrow"><td>现金</td><td className="muted">不计入行业</td><td /><td /><td className="r">{money(v.cash)}</td><td className="r">{pct(v.cash_weight)}</td></tr>
        </tbody>
      </table>
      <h2>行业分布</h2>
      <div className="bars">
        {v.industries.map(i => (
          <div key={i.industry} className={`bar${i.over_threshold ? ' over' : ''}`} data-testid={`industry-${i.industry}`}>
            <span className="name">{i.industry}</span>
            <span className="track"><span style={{ width: pct(i.weight) }} /></span>
            <span className="r">{pct(i.weight)}</span><span className="r muted">{money(i.value)}</span>
          </div>))}
      </div>
    </div>);
}

function Builder({ p, ops, busy, onAdd, onRemove, onClear, onSave }: {
  p: Portfolio; ops: Op[]; busy: boolean; onAdd: (op: Op) => void; onRemove: (i: number) => void;
  onClear: () => void; onSave: (name: string) => Promise<boolean> }) {
  const [side, setSide] = useState<Side>('sell');
  const [symbol, setSymbol] = useState(p.instruments[0].symbol);
  const [qty, setQty] = useState('');
  const [name, setName] = useState('');
  return (
    <div className="panel">
      <h2>调仓模拟（草稿）</h2>
      <p className="muted">操作从原组合起按顺序执行，所有计算与校验由后端完成。</p>
      <form className="opform" onSubmit={e => { e.preventDefault(); onAdd({ side, symbol, quantity: parseQty(qty) }); }}>
        <select data-testid="op-side" value={side} onChange={e => setSide(e.target.value as Side)}>
          <option value="buy">买入</option><option value="sell">卖出</option>
        </select>
        <select data-testid="op-symbol" value={symbol} onChange={e => setSymbol(e.target.value)}>
          {p.instruments.map(i => <option key={i.symbol} value={i.symbol}>{i.symbol} {i.name} · {money(i.price)}</option>)}
        </select>
        <input data-testid="op-qty" inputMode="numeric" placeholder="数量（正整数）" value={qty} onChange={e => setQty(e.target.value)} />
        <button data-testid="op-add" disabled={busy}>添加</button>
      </form>
      {ops.length === 0 ? <p className="muted" data-testid="ops-empty">尚未添加操作，当前即原组合。</p>
        : <OpsList ops={ops} onRemove={busy ? undefined : onRemove} />}
      {ops.length > 0 && <button className="link" onClick={onClear} disabled={busy}>清空操作</button>}
      <form className="saveform" onSubmit={async e => { e.preventDefault(); if (await onSave(name)) setName(''); }}>
        <input data-testid="scenario-name" placeholder="方案名称（1–80 字）" value={name} onChange={e => setName(e.target.value)} />
        <button data-testid="save" disabled={busy}>保存方案</button>
      </form>
    </div>);
}

function OpsList({ ops, onRemove }: { ops: Op[]; onRemove?: (i: number) => void }) {
  return (
    <ol className="ops" data-testid="ops-list">
      {ops.map((o, i) => (
        <li key={i}>
          <span className={`side ${o.side}`}>{sideLabel[o.side]}</span> {o.symbol} × {String(o.quantity)}
          {onRemove && <button className="link" aria-label={`删除第 ${i + 1} 笔`} onClick={() => onRemove(i)}>删除</button>}
        </li>))}
    </ol>);
}

function Saved({ list, onOpen, activeId, busy, onRetry }: { list: Load<ScenarioSummary[]>; onOpen: (id: number) => void;
  activeId?: number; busy: boolean; onRetry: () => void }) {
  return (
    <div className="panel" data-testid="saved-list">
      <h2>已保存方案</h2>
      {list.status === 'loading' && <p className="muted">加载中…</p>}
      {list.status === 'error' && <p className="error">方案列表加载失败：{list.error.message} <button className="link" onClick={onRetry}>重试</button></p>}
      {list.status === 'ready' && (list.data.length === 0 ? <p className="muted">暂无已保存方案。</p> : (
        <ul className="saved">
          {list.data.map(s => (
            <li key={s.id}><button className={s.id === activeId ? 'active' : ''} disabled={busy} onClick={() => onOpen(s.id)}>
              {s.name} <span className="muted">· {s.op_count} 笔 · #{s.id}</span></button></li>))}
        </ul>))}
    </div>);
}

function Compare({ s }: { s: Simulation }) {
  const o = s.original, m = s.simulated;
  const diff = (a: string | number, b: string | number) => (a === b ? '' : 'changed');
  return (
    <div className="compare">
      <table>
        <thead><tr><th>项目</th><th className="r">原数量</th><th className="r">模拟数量</th><th className="r">原市值</th><th className="r">模拟市值</th><th className="r">原占比</th><th className="r">模拟占比</th></tr></thead>
        <tbody>
          {o.positions.map(x => { const y = m.positions.find(q => q.symbol === x.symbol)!; return (
            <tr key={x.symbol} data-testid={`compare-${x.symbol}`}>
              <td>{x.symbol} {x.name}</td><td className="r">{x.quantity}</td><td className={`r ${diff(x.quantity, y.quantity)}`}>{y.quantity}</td>
              <td className="r">{money(x.market_value)}</td><td className={`r ${diff(x.market_value, y.market_value)}`}>{money(y.market_value)}</td>
              <td className={`r${x.over_threshold ? ' overtxt' : ''}`}>{pct(x.weight)}</td>
              <td className={`r ${diff(x.weight, y.weight)}${y.over_threshold ? ' overtxt' : ''}`}>{pct(y.weight)}</td>
            </tr>); })}
          <tr className="cashrow"><td>现金</td><td /><td /><td className="r">{money(o.cash)}</td>
            <td className={`r ${diff(o.cash, m.cash)}`} data-testid="sim-cash">{money(m.cash)}</td>
            <td className="r">{pct(o.cash_weight)}</td><td className={`r ${diff(o.cash_weight, m.cash_weight)}`}>{pct(m.cash_weight)}</td></tr>
          <tr className="total"><td>总资产</td><td /><td /><td className="r">{money(o.total)}</td><td className="r">{money(m.total)}</td><td /><td /></tr>
        </tbody>
      </table>
      <div className="compare-side">
        <table>
          <thead><tr><th>行业</th><th className="r">原占比</th><th className="r">模拟占比</th></tr></thead>
          <tbody>
            {o.industries.map(x => { const y = m.industries.find(i => i.industry === x.industry)!; return (
              <tr key={x.industry} data-testid={`compare-industry-${x.industry}`}>
                <td>{x.industry}</td><td className={`r${x.over_threshold ? ' overtxt' : ''}`}>{pct(x.weight)}</td>
                <td className={`r ${diff(x.weight, y.weight)}${y.over_threshold ? ' overtxt' : ''}`}>{pct(y.weight)}</td>
              </tr>); })}
          </tbody>
        </table>
        <Alerts alerts={m.alerts} testId="sim-alerts" title="模拟后集中度提醒" />
      </div>
    </div>);
}
