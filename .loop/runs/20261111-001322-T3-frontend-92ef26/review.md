I'll review this as an independent pass against the brief and the sample data, reading the requirements and the changed frontend and backend files rather than trusting the diff summary.The frontend meets the T3 requirements. Business figures stay on the backend, a rejected operation leaves the last valid scenario in place, and the original portfolio stays isolated from every simulation.

`★ Insight ─────────────────────────────────────`
- A draft advances only after `POST /api/simulate` succeeds. The server replays the whole sequence from the original snapshot, so a 422 cannot patch cash or holdings on screen, and Save persists that same sequence.
- `parseQty` emits a JSON integer only for a canonical value inside `Number.isSafeInteger`. Inputs such as `1.5`, `1e2`, or an oversized digit string are forwarded unchanged, so the engine’s `type(qty) is int` check is what rejects them.
- Thousand separators and a trailing `%` are display formatting of backend strings. Row highlighting and alerts use the backend `over_threshold` flag, which is the unrounded strict `>` comparison (30% and 50% produce no alert).
`─────────────────────────────────────────────────`

Overview data comes from `GET /api/portfolio`: total, cash and cash weight, per-name price, quantity, market value and weight, industry weights and values, snapshot time `2026-11-02 15:00` kept as the `+08:00` clock time, and alerts that show object, actual ratio, and threshold. The header states that equality does not alert. Cash is its own row and is omitted from the industry bars; the weights themselves already use total assets, including cash, as the denominator.

The builder sends ordered buy/sell operations and replays the full list from the original portfolio. Removing one operation does the same. On any failure the previous `ops` and `sim` stay put, and the backend message is shown in an alert. Empty draft, empty saved-scenario list, no alerts, and “no comparison yet” are explicit empty states. The initial portfolio load and the scenario list have explicit loading and error states, with retry.

Save posts the current operations and the name. The list is reloaded from the server. Reopening a row loads that scenario and renders its server-computed original and simulated valuations. Refresh starts again from the original portfolio because the draft is only in memory; the SQLite row is what survives a process restart. The left-hand totals stay on the original valuation (`cash` remains `20,000.00` while `sim-cash` shows the scenario).

The small backend edits match that contract. Non-zero fees are rejected at seed load. `held_count` is computed on the server. Framework validation errors use the same `{"error": {code, message}}` body. The SPA is served only when `frontend/dist` is actually built, and the catch-all always returns `index.html` rather than a path taken from the URL. Scenario names are rendered as text.

The locked end-to-end spec covers the demo path (two alerts, the AC-03 comparison, rejected follow-up operations, save, reload, reopen, original cash and quantity). It does not by itself show the from-scratch buy-201 / sell-401 cases or a process restart; those are in the backend tests, and the UI uses the same error and reload paths.

```json
{"verdict": "pass", "blocking": [], "suggestions": ["Give loadScenarios the same request-generation guard as replay/open. A slower list response can still overwrite a newer one after save, so the name that was just saved can vanish from the list until the next reload.", "While simulate, save, or reopen is in flight, the controls only disable. A one-line 正在计算/正在保存 state would match the explicit loading copy already used for the initial portfolio and the scenario list.", "Compare assumes every original symbol and industry exists on the simulated valuation (find(...)!). The engine currently always emits the full set, including zero quantities; if that ever changes, the page throws instead of showing the error state."]}
```