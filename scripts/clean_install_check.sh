#!/usr/bin/env bash
# Clean-environment check: fresh clone of HEAD → README install steps → start → AC-01/AC-05 over HTTP,
# including a real server restart. Uses only committed files (no local .venv / node_modules / db).
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"; PORT="${PORT:-18765}"; PID=""
cleanup() { [ -n "$PID" ] && kill "$PID" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT

git clone -q --no-local "$SRC" "$WORK/app"
cd "$WORK/app"
echo "[1/5] install (uv sync --frozen, npm ci, build)"
uv sync --frozen -q
npm --prefix frontend ci --silent
npm --prefix frontend run build --silent >/dev/null

start() {
  PORTFOLIO_DB="$WORK/data/portfolio.db" uv run --frozen uvicorn portfolio.main:app --app-dir backend --port "$PORT" >"$WORK/server.log" 2>&1 &
  PID=$!
  for _ in $(seq 1 100); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null && return 0; sleep 0.1; done
  cat "$WORK/server.log"; echo "server did not start"; exit 1
}
j() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {}, {'d': d}))" "$1"; }

echo "[2/5] start + AC-01"
start
[ "$(curl -fs "http://127.0.0.1:$PORT/api/portfolio" | j "d['valuation']['total']")" = "100000.00" ]
curl -fs "http://127.0.0.1:$PORT/" | grep -q '<div id="root">'   # built UI served by the backend

echo "[3/5] save AC-03 scenario"
ID=$(curl -fs -X POST -H 'content-type: application/json' "http://127.0.0.1:$PORT/api/scenarios" \
  -d '{"name":"AC-03","ops":[{"side":"sell","symbol":"A01","quantity":100},{"side":"buy","symbol":"A02","quantity":100}]}' | j "d['id']")
BEFORE=$(curl -fs "http://127.0.0.1:$PORT/api/scenarios/$ID")

echo "[4/5] restart server"
kill "$PID"; wait "$PID" 2>/dev/null || true; PID=""
start

echo "[5/5] reopen + isolation"
AFTER=$(curl -fs "http://127.0.0.1:$PORT/api/scenarios/$ID")
[ "$BEFORE" = "$AFTER" ]
[ "$(echo "$AFTER" | j "d['simulated']['cash']")" = "25000.00" ]
[ "$(curl -fs "http://127.0.0.1:$PORT/api/portfolio" | j "[p['quantity'] for p in d['valuation']['positions'][:2]] + [d['valuation']['cash']]")" = "[400, 400, '20000.00']" ]
echo "CLEAN INSTALL CHECK PASSED ($(uv run --frozen python --version), node $(node --version))"
