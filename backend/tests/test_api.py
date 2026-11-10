"""T2 acceptance spec: HTTP contract, backend validation (FR-05), persistence + isolation (FR-04)."""
import pytest
from fastapi.testclient import TestClient

from portfolio.api import create_app

AC03 = [{'side': 'sell', 'symbol': 'A01', 'quantity': 100},
        {'side': 'buy', 'symbol': 'A02', 'quantity': 100}]


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path / 'test.db'))


def by_symbol(v):
    return {p['symbol']: p for p in v['positions']}


def by_industry(v):
    return {i['industry']: i for i in v['industries']}


def test_health(client):
    assert client.get('/api/health').json() == {'status': 'ok'}


def test_ac01_portfolio_overview(client):
    body = client.get('/api/portfolio').json()
    assert body['snapshot'] == {'id': 'SNAP-20261102', 'at': '2026-11-02T15:00:00+08:00', 'currency': 'CNY'}
    v = body['valuation']
    assert (v['total'], v['cash'], v['cash_weight']) == ('100000.00', '20000.00', '20.00')
    a01 = by_symbol(v)['A01']
    assert (a01['quantity'], a01['price'], a01['market_value'], a01['weight']) == (400, '100.00', '40000.00', '40.00')
    assert a01['name'] == '星河科技' and a01['industry'] == '科技'
    assert by_industry(v)['科技']['weight'] == '60.00'
    assert [(a['kind'], a['target'], a['ratio'], a['threshold']) for a in v['alerts']] == [
        ('instrument', 'A01', '40.00', '30.00'), ('industry', '科技', '60.00', '50.00')]
    assert all(a['message'] for a in v['alerts'])


def test_ac02_ac03_simulation_compares_original_and_simulated(client):
    r = client.post('/api/simulate', json={'ops': AC03[:1]})
    assert r.status_code == 200
    sim = r.json()['simulated']
    assert (sim['cash'], by_symbol(sim)['A01']['weight'], by_industry(sim)['科技']['weight']) == ('30000.00', '30.00', '50.00')
    assert sim['alerts'] == []
    r = client.post('/api/simulate', json={'ops': AC03}).json()
    sim, orig = r['simulated'], r['original']
    assert (sim['cash'], by_symbol(sim)['A02']['quantity'], by_symbol(sim)['A02']['market_value']) == ('25000.00', 500, '25000.00')
    assert by_industry(sim)['科技']['weight'] == '55.00' and sim['total'] == '100000.00'
    assert [a['target'] for a in sim['alerts']] == ['科技']
    assert (orig['cash'], by_symbol(orig)['A01']['quantity']) == ('20000.00', 400)


@pytest.mark.parametrize('op, code', [
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 201}, 'INSUFFICIENT_CASH'),
    ({'side': 'sell', 'symbol': 'A01', 'quantity': 401}, 'INSUFFICIENT_HOLDING'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 0}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': -5}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': 2.5}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A01', 'quantity': '5'}, 'INVALID_QUANTITY'),  # no silent coercion
    ({'side': 'buy', 'symbol': 'A01', 'quantity': True}, 'INVALID_QUANTITY'),
    ({'side': 'buy', 'symbol': 'A99', 'quantity': 1}, 'UNKNOWN_SYMBOL'),
])
def test_ac04_invalid_ops_get_clear_422_and_change_nothing(client, op, code):
    before = client.get('/api/portfolio').json()
    r = client.post('/api/simulate', json={'ops': [op]})
    assert r.status_code == 422
    err = r.json()['error']
    assert err['code'] == code and err['index'] == 0 and err['message']
    assert client.get('/api/portfolio').json() == before


def test_error_reports_index_of_failing_op(client):
    r = client.post('/api/simulate', json={'ops': AC03 + [{'side': 'buy', 'symbol': 'A01', 'quantity': 300}]})
    assert r.status_code == 422 and r.json()['error']['index'] == 2


@pytest.mark.parametrize('body', [None, [], {'ops': 'x'}, {'nope': []}, {'ops': [1]}])
def test_malformed_bodies_use_same_error_shape(client, body):
    r = client.post('/api/simulate', json=body) if body is not None else \
        client.post('/api/simulate', content=b'{bad json', headers={'content-type': 'application/json'})
    assert r.status_code == 422
    assert set(r.json()['error']) >= {'code', 'message'}


def test_ac05_save_list_reopen_and_isolation(client):
    r = client.post('/api/scenarios', json={'name': '  AC-03 方案  ', 'ops': AC03})
    assert r.status_code == 201
    saved = r.json()
    assert saved['name'] == 'AC-03 方案' and saved['snapshot_id'] == 'SNAP-20261102'
    listing = client.get('/api/scenarios').json()
    assert [(s['id'], s['name'], s['op_count']) for s in listing] == [(saved['id'], 'AC-03 方案', 2)]
    opened = client.get(f"/api/scenarios/{saved['id']}").json()
    assert opened['ops'] == AC03
    assert opened['simulated'] == client.post('/api/simulate', json={'ops': AC03}).json()['simulated']
    orig = by_symbol(client.get('/api/portfolio').json()['valuation'])
    assert (orig['A01']['quantity'], orig['A02']['quantity']) == (400, 400)
    assert client.get('/api/portfolio').json()['valuation']['cash'] == '20000.00'


@pytest.mark.parametrize('body, code', [
    ({'name': '   ', 'ops': AC03}, 'INVALID_NAME'),
    ({'name': 'x' * 81, 'ops': AC03}, 'INVALID_NAME'),
    ({'name': 5, 'ops': AC03}, 'INVALID_NAME'),
    ({'name': 'empty', 'ops': []}, 'EMPTY_SCENARIO'),
    ({'name': 'bad', 'ops': [{'side': 'sell', 'symbol': 'A01', 'quantity': 401}]}, 'INSUFFICIENT_HOLDING'),
])
def test_invalid_scenarios_are_not_saved(client, body, code):
    r = client.post('/api/scenarios', json=body)
    assert r.status_code == 422 and r.json()['error']['code'] == code
    assert client.get('/api/scenarios').json() == []


def test_name_of_exactly_80_chars_is_allowed(client):
    assert client.post('/api/scenarios', json={'name': '名' * 80, 'ops': AC03}).status_code == 201


def test_unknown_scenario_is_404(client):
    r = client.get('/api/scenarios/999')
    assert r.status_code == 404 and r.json()['error']['code'] == 'NOT_FOUND'
