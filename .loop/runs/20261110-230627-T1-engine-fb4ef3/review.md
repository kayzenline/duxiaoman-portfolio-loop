I'll review the engine against the brief and the original portfolio data, then check the implementation for rule mismatches rather than relying on the passing tests.The engine meets the T1 calculation rules. Valuation stays in integer cents, thresholds are exact strict comparisons, and failed trades do not touch the original portfolio or a previously valid replay.

`★ Insight ─────────────────────────────────────`
Cash is part of total assets and part of no industry, so a weight is `Fraction(market_value_cents, position_sum + cash)`. Selling A01 down to 30,000.00 against a 100,000.00 book is exactly `3/10`, and `>` on that fraction leaves the alert off. A binary float division of the same ratio is the case the task warns can look like 30.0000001%.
`─────────────────────────────────────────────────`

Checked against the task sheet (§2.1–2.2 and AC-01..AC-04) and the seed file:

- Prices and cash are parsed from decimal strings into cents. A01 is 4,000,000 cents (40,000.00) on a 10,000,000-cent book; cash stays in that denominator and is never added to an industry bucket. Initial tech weight is `60,000 / 100,000`.
- Alerts use `weight > threshold` on `Fraction`s. After selling 100 A01, A01 is exactly 30% and 科技 is exactly 50%, and both alerts clear. AC-03 then buys 100 A02 on that running state: cash 25,000.00, A02 quantity 500, tech `55%`, industry alert only.
- `simulate` always copies the snapshot and replays from the original book. Buys use `amount > cash` (cash may hit 0). Sells use the running quantity. The first bad operation raises `OpError` with its index before that operation is applied, so the snapshot and a replay of the valid prefix stay as they were.
- Trade quantity must be a real `int` greater than 0, so `True`, `1.0`, and numeric strings are rejected. Snapshot bytes match the attachment.

The locked AC-03 numbers are commutative (sell A01 and buy A02 do not fight over the same cash or shares), so that test alone would also pass a parallel apply. The running `cash` / `holdings` loop is what actually enforces sequential cash and the mid-sequence oversell (sell 100 A01, then sell 301 against the remaining 300).

```json
{"verdict": "pass", "blocking": [], "suggestions": ["to_cents does int(d * 100) under the process-wide Decimal context. The seed amounts are well inside the default precision of 28, but a lowered context would silently drop digits. Parse the integer and the two fractional digits instead.", "rules.fees is never read. The engine is fee-free, which matches this seed's \"0.00\", but any other fees value would still be valued as zero. Reject a non-zero fees field at load.", "State.holdings is a plain dict inside a frozen dataclass, so a caller can edit a successful result in place. The failure path does not do this. A mapping proxy would keep that result immutable at the boundary."]}
```