"""AC-05 with a real server process: save, kill the process, start a new one, reopen."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AC03 = [{'side': 'sell', 'symbol': 'A01', 'quantity': 100},
        {'side': 'buy', 'symbol': 'A02', 'quantity': 100}]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start(db, port):
    env = dict(os.environ, PORTFOLIO_DB=str(db), PYTHONPATH=str(ROOT / 'backend'))
    p = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'portfolio.main:app', '--port', str(port)],
                         cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            call(port, 'GET', '/api/health')
            return p
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError('server did not start')


def call(port, method, path, body=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_ac05_survives_real_process_restart(tmp_path):
    db = tmp_path / 'restart.db'
    port = free_port()
    p = start(db, port)
    try:
        saved = call(port, 'POST', '/api/scenarios', {'name': 'AC-03', 'ops': AC03})
        before = call(port, 'GET', f"/api/scenarios/{saved['id']}")
    finally:
        p.terminate()
        p.wait(timeout=10)
    assert p.returncode is not None  # the first process is really gone

    port2 = free_port()
    p2 = start(db, port2)
    try:
        after = call(port2, 'GET', f"/api/scenarios/{saved['id']}")
        portfolio = call(port2, 'GET', '/api/portfolio')
    finally:
        p2.terminate()
        p2.wait(timeout=10)
    assert after == before
    assert after['simulated']['cash'] == '25000.00'
    pos = {x['symbol']: x['quantity'] for x in portfolio['valuation']['positions']}
    assert (portfolio['valuation']['cash'], pos['A01'], pos['A02']) == ('20000.00', 400, 400)
