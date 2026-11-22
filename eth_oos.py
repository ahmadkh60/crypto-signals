from datetime import datetime, UTC
from collections import Counter
from statistics import mean
from app.backtest.config import BacktestConfig
from app.backtest.runner import run_swing_pullback_backtest
from app.core.config import Settings

start = int(datetime(2026, 3, 21, tzinfo=UTC).timestamp())
end = int(datetime(2026, 11, 16, tzinfo=UTC).timestamp())

r = run_swing_pullback_backtest(
    symbol="ETHIRT",
    start=start,
    end=end,
    backtest_config=BacktestConfig(
        commission_rate=0.001,
        slippage_rate=0.0005,
        cost_basis="hypothetical",
    ),
    settings=Settings(),
)

b = r.backtest
t = b.trades
w = [x.net_pnl for x in t if x.net_pnl > 0]
l = [x.net_pnl for x in t if x.net_pnl < 0]

eq = peak = b.initial_capital
dd_max = dd_pct_max = 0
for x in t:
    eq += x.net_pnl
    peak = max(peak, eq)
    dd = peak - eq
    dd_max = max(dd_max, dd)
    dd_pct_max = max(dd_pct_max, dd / peak * 100)

risks = [x.planned_risk for x in t if x.planned_risk and x.planned_risk > 0]
rs = [x.net_pnl / x.planned_risk for x in t if x.planned_risk and x.planned_risk > 0]

print("\n========== ETH OOS ==========")
print("Hourly candles:", r.hourly_candles)
print("4H candles:", r.four_hour_candles)
print("Incomplete groups:", r.incomplete_groups)
print("Discarded hourly candles:", r.discarded_hourly_candles)
print("Trades:", len(t))
print("Wins:", len(w), "Losses:", len(l))
print("Win rate (%):", round(len(w) / len(t) * 100, 2) if t else 0)
print("Profit factor:", round(sum(w) / abs(sum(l)), 4) if l else "N/A")
print("Gross PnL:", round(b.total_gross_pnl, 2))
print("Fees:", round(b.total_fees, 2))
print("Net PnL:", round(b.total_net_pnl, 2))
print("Average win:", round(mean(w), 2) if w else 0)
print("Average loss:", round(mean(l), 2) if l else 0)
print("Max drawdown:", round(dd_max, 2))
print("Max drawdown (%):", round(dd_pct_max, 2))
print("Average planned risk:", round(mean(risks), 2) if risks else "N/A")
print("Average R-multiple:", round(mean(rs), 4) if rs else "N/A")
print("Exit reasons:", dict(Counter(x.exit_reason for x in t)))
print("Ending capital:", round(b.ending_capital, 2))
print("Return (%):", round(b.total_return_pct, 2))
print("Quality warnings:", len(r.quality_warnings))
for warning in r.quality_warnings:
    print("WARNING:", warning)
