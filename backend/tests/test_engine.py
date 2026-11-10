"""T1 acceptance spec: engine-level AC-01..AC-04 from VC-FIN-001 page 4.

Locked by `python -m loop spec T1-engine`; the implementer may not edit this file.
"""
import hashlib
from fractions import Fraction
from pathlib import Path

import pytest

from portfolio.engine import OpError, load_snapshot, original_state, simulate, valuate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def snap():
    return load_snapshot()


def alerts(v):
    return {(a.kind, a.target): a.ratio for a in v.alerts}


def test_seed_is_byte_identical_to_original_attachment():
    seed = ROOT / 'backend/portfolio/seed_portfolio.json'
    original = ROOT / 'context/originals/投资组合示例数据.json'
    assert hashlib.sha256(seed.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest()


def test_snapshot_metadata(snap):
    assert (snap.portfolio_id, snap.snapshot_id, snap.currency) == ('DEMO-001', 'SNAP-20261102', 'CNY')
    assert snap.snapshot_at == '2026-11-02T15:00:00+08:00'
    assert snap.instruments['A01'].price_cents == 10000
    assert snap.instrument_threshold == Fraction(3, 10)
    assert snap.industry_threshold == Fraction(1, 2)


def test_ac01_initial_portfolio(snap):
    v = valuate(snap, original_state(snap))
    assert v.total_cents == 100_000_00
    assert v.cash_cents == 20_000_00
    assert v.positions['A01'].market_value_cents == 40_000_00
    assert v.positions['A01'].weight == Fraction(2, 5)
    assert v.industries['科技'].value_cents == 60_000_00
    assert v.industries['科技'].weight == Fraction(3, 5)
    assert '现金' not in v.industries and len(v.industries) == 5
    # exactly two alerts, nothing else over its threshold
    assert alerts(v) == {('instrument', 'A01'): Fraction(2, 5), ('industry', '科技'): Fraction(3, 5)}
    thresholds = {(a.kind, a.target): a.threshold for a in v.alerts}
    assert thresholds == {('instrument', 'A01'): Fraction(3, 10), ('industry', '科技'): Fraction(1, 2)}


def test_ac02_threshold_boundary_is_strict(snap):
    s = simulate(snap, [{'side': 'sell', 'symbol': 'A01', 'quantity': 100}])
    v = valuate(snap, s)
    assert v.cash_cents == 30_000_00
    assert v.positions['A01'].market_value_cents == 30_000_00
    assert v.total_cents == 100_000_00
    assert v.positions['A01'].weight == Fraction(3, 10)
    assert v.industries['科技'].weight == Fraction(1, 2)
    assert v.alerts == []


def test_ac03_sequential_ops_use_previous_result(snap):
    ops = [{'side': 'sell', 'symbol': 'A01', 'quantity': 100},
           {'side': 'buy', 'symbol': 'A02', 'quantity': 100}]
    v = valuate(snap, simulate(snap, ops))
    assert v.cash_cents == 25_000_00
    assert v.positions['A02'].quantity == 500
    assert v.positions['A02'].market_value_cents == 25_000_00
    assert v.industries['科技'].weight == Fraction(55, 100)
    assert v.total_cents == 100_000_00
    assert alerts(v) == {('industry', '科技'): Fraction(11, 20)}


@pytest.mark.parametrize('op, code', [
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 201}, 'INSUFFICIENT_CASH'),
    ({'side': 'sell', 'symbol': 'A01', 'quantity': 401}, 'INSUFFICIENT_HOLDING'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 0}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': -1}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 1.5}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 1.0}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': True}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': '5'}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01'}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'ZZZ', 'quantity': 1}, 'UNKNOWN_SYMBOL'),
    ({'side': 'short', 'symbol': 'A01', 'quantity': 1}, 'INVALID_SIDE'),
])
def test_ac04_invalid_ops_rejected_without_changing_results(snap, op, code):
    before = valuate(snap, original_state(snap))
    with pytest.raises(OpError) as e:
        simulate(snap, [op])
    assert e.value.code == code and e.value.index == 0 and e.value.message
    assert valuate(snap, original_state(snap)) == before


def test_exact_cash_boundary_buy_is_allowed(snap):
    # 200 × 100.00 = 20,000.00 = all cash → allowed, cash becomes exactly 0
    v = valuate(snap, simulate(snap, [{'side': 'buy', 'symbol': 'A01', 'quantity': 200}]))
    assert v.cash_cents == 0 and v.total_cents == 100_000_00


def test_failure_mid_sequence_reports_index_and_keeps_prefix_valid(snap):
    good = [{'side': 'sell', 'symbol': 'A01', 'quantity': 100}]
    valid = valuate(snap, simulate(snap, good))
    with pytest.raises(OpError) as e:
        simulate(snap, good + [{'side': 'sell', 'symbol': 'A01', 'quantity': 301}])
    assert e.value.index == 1 and e.value.code == 'INSUFFICIENT_HOLDING'
    assert valuate(snap, simulate(snap, good)) == valid  # previous valid result reproducible


def test_simulation_never_mutates_original(snap):
    simulate(snap, [{'side': 'sell', 'symbol': 'A01', 'quantity': 400},
                    {'side': 'buy', 'symbol': 'A03', 'quantity': 100}])
    o = original_state(snap)
    assert o.cash_cents == 20_000_00 and o.holdings['A01'] == 400 and o.holdings['A02'] == 400


def test_sold_out_position_stays_visible_with_zero(snap):
    v = valuate(snap, simulate(snap, [{'side': 'sell', 'symbol': 'A06', 'quantity': 20}]))
    assert v.positions['A06'].quantity == 0 and v.positions['A06'].weight == 0
    assert v.total_cents == 100_000_00


def test_empty_scenario_equals_original(snap):
    assert valuate(snap, simulate(snap, [])) == valuate(snap, original_state(snap))
