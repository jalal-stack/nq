def calculate_position_size(equity, entry, stop, risk_pct=0.01):
    return equity * risk_pct / abs(entry - stop)


def check_daily_loss(equity, day_start, limit=0.03):
    return (day_start - equity) / day_start < limit
