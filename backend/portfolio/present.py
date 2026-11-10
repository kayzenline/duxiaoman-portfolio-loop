"""Rendering of engine values for the API. The only place where rounding happens."""
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

KIND_LABEL = {'instrument': '单一标的', 'industry': '行业'}


def money(cents):
    sign = '-' if cents < 0 else ''
    cents = abs(cents)
    return f'{sign}{cents // 100}.{cents % 100:02d}'


def pct(ratio: Fraction):
    """Exact fraction -> percentage string with 2 decimals, half-up (display only)."""
    d = Decimal(ratio.numerator) * 100 / Decimal(ratio.denominator)
    return str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def valuation(snap, v):
    positions = [{'symbol': p.symbol, 'name': p.name, 'industry': p.industry, 'price': money(p.price_cents),
                  'quantity': p.quantity, 'market_value': money(p.market_value_cents), 'weight': pct(p.weight),
                  'over_threshold': p.weight > snap.instrument_threshold}
                 for p in v.positions.values()]
    industries = [{'industry': i.industry, 'value': money(i.value_cents), 'weight': pct(i.weight),
                   'over_threshold': i.weight > snap.industry_threshold}
                  for i in sorted(v.industries.values(), key=lambda i: (-i.value_cents, i.industry))]
    alerts = []
    for a in v.alerts:
        label = snap.instruments[a.target].name if a.kind == 'instrument' else a.target
        target = f'{a.target} {label}' if a.kind == 'instrument' else label
        alerts.append({'kind': a.kind, 'target': a.target, 'label': label, 'ratio': pct(a.ratio),
                       'threshold': pct(a.threshold),
                       'message': f'{KIND_LABEL[a.kind]}超限：{target} 占比 {pct(a.ratio)}%，超过阈值 {pct(a.threshold)}%'})
    return {'total': money(v.total_cents), 'cash': money(v.cash_cents), 'cash_weight': pct(v.cash_weight),
            'positions': positions, 'industries': industries, 'alerts': alerts}
