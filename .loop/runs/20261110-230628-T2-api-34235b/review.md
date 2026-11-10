I'll review the HTTP and persistence layer against the brief and the locked acceptance tests, starting with the requirements and the engine the API sits on.The HTTP layer meets FR-04/FR-05 and AC-04/AC-05. Business rules stay in the engine, the database stores inputs only, and rejected operations never become a new portfolio.

`★ Insight ─────────────────────────────────────`
Raw `json.loads` on the request body is what makes the integer-quantity rule real at the HTTP boundary. A Pydantic `quantity: int` field would coerce `"5"` or `1.0` before `type(qty) is int` in the engine ever ran. Money and weights leave the process as strings built from integer cents and `Fraction`s, so the JSON encoder cannot turn 30% into a binary float. Scenarios store the ordered ops plus the snapshot id; reopen calls `simulate` again, so a restarted process cannot serve a stale valuation.
`─────────────────────────────────────────────────`

The calculation core is unchanged and the API does not reimplement it. `POST /api/simulate` and scenario reopen both call `engine.simulate` from the seed, then `engine.valuate`. Cash stays in the total-assets denominator (AC-01 is 100,000.00 with A01 at 40.00, not 50). Threshold flags use strict `>` on the unrounded fraction, so AC-02 at exactly 30% and 50% produces an empty alert list. Quantities are whatever JSON actually decoded: `2.5`, `"5"`, and `true` all become `INVALID_QUANTITY` with index 0.

```51:63:backend/portfolio/api.py
    def run(ops):
        try:
            state = engine.simulate(snap, ops)
        except engine.OpError as e:
            raise ApiError(422, e.code, e.message, e.index) from None
        return present.valuation(snap, engine.valuate(snap, state))
    # ...
    def opened(s):
        if s['snapshot_id'] != snap.snapshot_id:
            raise ApiError(409, 'SNAPSHOT_MISMATCH', f"方案基于快照 {s['snapshot_id']}，当前快照为 {snap.snapshot_id}")
        return {**s, 'original': original(), 'simulated': run(s['ops'])}
```

A failed op raises before `run` returns a valuation. `POST /api/scenarios` calls `run` before `INSERT`, so an invalid sequence is never stored. The seed file is only read. `simulate` copies holdings before it mutates that copy, and `GET /api/portfolio` always valuates `original_state`. Saving AC-03 therefore leaves cash at 20,000.00 and A01/A02 at 400.

```8:13:backend/portfolio/storage.py
SCHEMA = '''CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    ops_json TEXT NOT NULL,
    created_at TEXT NOT NULL)'''
```

There is no column for derived holdings or weights. `GET /api/scenarios/{id}` loads that row and replays it. The restart test kills the uvicorn process and opens the same SQLite file in a new process; `add` commits before it returns, so the replay survives the kill. Inserts are parameterized. Business 4xx bodies are `{"error": {"code", "message", "index"?}}`, and the engine messages name the constraint (cash shortfall with both amounts, oversell with the current simulated quantity, bad quantity with the received value).

Display rounding is confined to `present.pct`. Comparison still happens on the fraction. Every acceptance ratio (2/5, 3/5, 3/10, 1/2, 11/20) terminates at two decimal places, so the rendered `40.00` / `30.00` / `55.00` strings match the unrounded values. `over_threshold` is the same `>` test as the alert list, which keeps a displayed `30.00` that is exactly the threshold from raising an alert.

The AC-04 HTTP test only re-reads `GET /api/portfolio` after a 422. That response is rebuilt from the seed on every call, so it would stay equal even if a handler wrote a partial simulation somewhere else. The save path still rejects before `INSERT`, and a failed `simulate` returns only the error object, so the rule holds in the code even though that particular assertion does not pin it down. AC-02’s HTTP assertion also omits A01’s 30,000.00 market value; the same `Position` supplies both `market_value` and `weight`, and the weight check forces that market value.

```json
{"verdict": "pass", "blocking": [], "suggestions": ["Register a RequestValidationError handler so a non-integer scenario id returns the same {error:{code,message}} body as the business 4xxs.", "Declare save and simulate as plain def so the synchronous sqlite3 work runs in FastAPI's threadpool instead of on the event loop.", "Round percentages from the exact fraction with integer arithmetic. The current Decimal division is exact for every acceptance ratio and only becomes context-dependent for huge totals.", "Mount StaticFiles only when frontend/dist/assets exists. create_app raises if frontend/dist is present and assets is not, which will matter once the SPA build lands."]}
```