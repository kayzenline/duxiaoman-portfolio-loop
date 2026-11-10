"""Pure calculation core. No I/O besides loading the seed; no floats anywhere.

Money is integer cents. Ratios are exact Fractions, so threshold checks compare the
unrounded value (task §2.1) and 30.00% is never mistaken for 30.0000001%.
Rounding happens only in `present.py` when values are rendered for display.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
from pathlib import Path

SEED = Path(__file__).with_name('seed_portfolio.json')


class SeedError(ValueError):
    """The snapshot file itself is invalid (e.g. missing price, bad threshold)."""


class OpError(ValueError):
    """A simulated operation was rejected. `index` is its position in the sequence."""

    def __init__(self, index, code, message):
        super().__init__(message)
        self.index, self.code, self.message = index, code, message


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    industry: str
    price_cents: int


@dataclass(frozen=True)
class Snapshot:
    portfolio_id: str
    name: str
    snapshot_id: str
    snapshot_at: str
    currency: str
    cash_cents: int
    instruments: dict          # symbol -> Instrument, in seed order
    holdings: dict             # symbol -> quantity at snapshot
    instrument_threshold: Fraction
    industry_threshold: Fraction


@dataclass(frozen=True)
class State:
    cash_cents: int
    holdings: dict


@dataclass(frozen=True)
class Position:
    symbol: str
    name: str
    industry: str
    price_cents: int
    quantity: int
    market_value_cents: int
    weight: Fraction


@dataclass(frozen=True)
class Industry:
    industry: str
    value_cents: int
    weight: Fraction


@dataclass(frozen=True)
class Alert:
    kind: str           # 'instrument' | 'industry'
    target: str         # symbol or industry name
    ratio: Fraction
    threshold: Fraction


@dataclass(frozen=True)
class Valuation:
    total_cents: int
    cash_cents: int
    cash_weight: Fraction
    positions: dict = field(default_factory=dict)
    industries: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)


def to_cents(text, what):
    """'100.00' -> 10000. Strings only, at most 2 decimals, non-negative."""
    if not isinstance(text, str):
        raise SeedError(f'{what} must be a decimal string, got {text!r}')
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise SeedError(f'{what} is not a number: {text!r}') from None
    if not d.is_finite() or d < 0 or d.as_tuple().exponent < -2:
        raise SeedError(f'{what} must be non-negative with at most 2 decimals: {text!r}')
    return int(d * 100)


def to_ratio(text, what):
    try:
        r = Fraction(Decimal(text))
    except (InvalidOperation, TypeError, ValueError):
        raise SeedError(f'{what} is not a ratio: {text!r}') from None
    if not 0 < r < 1:
        raise SeedError(f'{what} must be between 0 and 1: {text!r}')
    return r


def load_snapshot(path=SEED):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    rules = raw['rules']
    if rules.get('comparison') != 'strictly_greater_than' or not rules.get('cash_in_denominator') \
            or rules.get('cash_in_industry'):
        raise SeedError('Unsupported rule set; engine implements the VC-FIN-001 rules only')
    instruments, holdings = {}, {}
    for item in raw['instruments']:
        sym = item['symbol']
        if sym in instruments:
            raise SeedError(f'Duplicate symbol {sym}')
        if not item.get('industry'):
            raise SeedError(f'{sym}: industry missing')  # see DESIGN.md: unknown industry
        price = to_cents(item.get('price'), f'{sym} price')  # missing price -> SeedError
        if price == 0:
            raise SeedError(f'{sym}: price must be positive')
        qty = item['quantity']
        if type(qty) is not int or qty < 0:
            raise SeedError(f'{sym}: quantity must be a non-negative integer')
        instruments[sym] = Instrument(sym, item['name'], item['industry'], price)
        holdings[sym] = qty
    return Snapshot(raw['portfolio_id'], raw['name'], raw['snapshot_id'], raw['snapshot_at'],
                    raw['currency'], to_cents(raw['cash'], 'cash'), instruments, holdings,
                    to_ratio(rules['single_instrument_threshold'], 'single_instrument_threshold'),
                    to_ratio(rules['industry_threshold'], 'industry_threshold'))


def original_state(snap):
    return State(snap.cash_cents, dict(snap.holdings))


def simulate(snap, ops):
    """Replay `ops` in order from the original portfolio. Raises OpError on the first bad op.

    Each op is a dict {side, symbol, quantity}. Nothing is mutated: a failure cannot
    leak a partial result, and the previous valid sequence still replays identically.
    """
    if not isinstance(ops, list):
        raise OpError(0, 'INVALID_OPS', '操作列表格式错误')
    cash, holdings = snap.cash_cents, dict(snap.holdings)
    for i, op in enumerate(ops):
        n = i + 1
        if not isinstance(op, dict):
            raise OpError(i, 'INVALID_OP', f'第 {n} 笔操作格式错误')
        side, sym, qty = op.get('side'), op.get('symbol'), op.get('quantity')
        if side not in ('buy', 'sell'):
            raise OpError(i, 'INVALID_SIDE', f'第 {n} 笔：交易方向必须是买入或卖出')
        if not isinstance(sym, str) or sym not in snap.instruments:
            raise OpError(i, 'UNKNOWN_SYMBOL', f'第 {n} 笔：标的 {sym!r} 不在本行情快照中')
        # bool is a subclass of int and 1.0 == 1, so test the exact type.
        if type(qty) is not int or qty <= 0:
            raise OpError(i, 'INVALID_QUANTITY', f'第 {n} 笔：数量必须是正整数，收到 {qty!r}')
        amount = snap.instruments[sym].price_cents * qty
        if side == 'buy':
            if amount > cash:
                raise OpError(i, 'INSUFFICIENT_CASH',
                              f'第 {n} 笔：买入 {sym} {qty} 股需 {fmt(amount)} 元，可用现金仅 {fmt(cash)} 元')
            cash -= amount
            holdings[sym] += qty
        else:
            if qty > holdings[sym]:
                raise OpError(i, 'INSUFFICIENT_HOLDING',
                              f'第 {n} 笔：卖出 {sym} {qty} 股超过当前模拟持仓 {holdings[sym]} 股')
            cash += amount
            holdings[sym] -= qty
    return State(cash, holdings)


def valuate(snap, state):
    positions, industry_values = {}, {}
    for sym, inst in snap.instruments.items():
        value = inst.price_cents * state.holdings[sym]
        positions[sym] = value
        industry_values[inst.industry] = industry_values.get(inst.industry, 0) + value
    total = sum(positions.values()) + state.cash_cents
    if total <= 0:
        raise SeedError('Total assets must be positive')
    w = lambda cents: Fraction(cents, total)
    pos = {s: Position(s, i.name, i.industry, i.price_cents, state.holdings[s], positions[s], w(positions[s]))
           for s, i in snap.instruments.items()}
    ind = {k: Industry(k, v, w(v)) for k, v in industry_values.items()}
    alerts = [Alert('instrument', p.symbol, p.weight, snap.instrument_threshold)
              for p in pos.values() if p.weight > snap.instrument_threshold]
    alerts += [Alert('industry', i.industry, i.weight, snap.industry_threshold)
               for i in ind.values() if i.weight > snap.industry_threshold]
    return Valuation(total, state.cash_cents, w(state.cash_cents), pos, ind, alerts)


def fmt(cents):
    """Display helper for error messages: 2010000 -> '20,100.00'."""
    return f'{cents // 100:,}.{cents % 100:02d}'
