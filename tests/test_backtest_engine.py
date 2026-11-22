import pytest

from app.backtest.config import BacktestConfig
from app.backtest.engine import run_backtest
from app.strategies.base import Signal


class DummyStrategy:
    def __init__(self, signals):
        self.signals = signals
        self.seen_indices = []
        self.seen_lengths = []

    def on_bar(self, history):
        self.seen_indices.append(history.index)
        self.seen_lengths.append(len(history))
        return self.signals.get(history.index, Signal("hold"))


def make_config(commission=0.0, slippage=0.0):
    return BacktestConfig(
        commission_rate=commission,
        slippage_rate=slippage,
        cost_basis="hypothetical",
    )


def make_candles():
    return {
        "open": [100.0, 110.0, 120.0],
        "close": [105.0, 115.0, 125.0],
    }


def test_entry_and_exit_execute_on_next_bar_open():
    strategy = DummyStrategy({
        0: Signal("long"),
        1: Signal("exit"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(),
    )

    assert len(result.trades) == 1

    trade = result.trades[0]

    assert trade.entry_index == 1
    assert trade.exit_index == 2
    assert trade.entry_price == 110.0
    assert trade.exit_price == 120.0
    assert trade.gross_pnl == 10.0
    assert trade.net_pnl == 10.0
    assert trade.exit_reason == "strategy_exit"


def test_commission_and_slippage_are_applied():
    strategy = DummyStrategy({
        0: Signal("long"),
        1: Signal("exit"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(commission=0.001, slippage=0.01),
    )

    trade = result.trades[0]

    assert trade.entry_price == pytest.approx(111.1)
    assert trade.exit_price == pytest.approx(118.8)
    assert trade.entry_fee == pytest.approx(0.1111)
    assert trade.exit_fee == pytest.approx(0.1188)
    assert trade.gross_pnl == pytest.approx(7.7)
    assert trade.net_pnl == pytest.approx(7.4701)


def test_open_position_closes_at_segment_end():
    strategy = DummyStrategy({
        0: Signal("long"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(commission=0.01),
    )

    assert len(result.trades) == 1

    trade = result.trades[0]

    assert trade.entry_index == 1
    assert trade.exit_index == 2
    assert trade.exit_price == 125.0
    assert trade.exit_reason == "end_of_segment"
    assert trade.gross_pnl == 15.0
    assert trade.entry_fee == pytest.approx(1.1)
    assert trade.exit_fee == pytest.approx(1.25)
    assert trade.net_pnl == pytest.approx(12.65)


def test_strategy_never_receives_future_candles():
    strategy = DummyStrategy({})

    run_backtest(
        make_candles(),
        strategy,
        make_config(),
    )

    assert strategy.seen_indices == [0, 1]
    assert strategy.seen_lengths == [1, 2]


def test_last_candle_signal_is_not_generated_or_executed():
    strategy = DummyStrategy({
        2: Signal("long"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(),
    )

    assert strategy.seen_indices == [0, 1]
    assert result.trades == ()


def test_empty_candles_return_empty_result():
    strategy = DummyStrategy({})

    result = run_backtest(
        {"open": [], "close": []},
        strategy,
        make_config(),
    )

    assert result.trades == ()


def test_multiple_segments_require_strategy_factory():
    from datetime import datetime

    candles = {
        "timestamp": [
            datetime(2025, 1, 1, 0),
            datetime(2025, 1, 1, 4),
            datetime(2025, 1, 1, 12),
            datetime(2025, 1, 1, 16),
        ],
        "open": [100.0, 101.0, 110.0, 111.0],
        "close": [100.5, 101.5, 110.5, 111.5],
    }

    with pytest.raises(ValueError, match="strategy_factory"):
        run_backtest(candles, DummyStrategy({}), make_config())


def test_strategy_factory_resets_state_at_segment_boundary():
    from datetime import datetime

    instances = []

    class StatefulStrategy:
        def __init__(self):
            self.calls = 0
            instances.append(self)

        def on_bar(self, history):
            self.calls += 1
            if self.calls == 1:
                return Signal("long")
            return Signal("hold")

    candles = {
        "timestamp": [
            datetime(2025, 1, 1, 0),
            datetime(2025, 1, 1, 4),
            datetime(2025, 1, 1, 12),
            datetime(2025, 1, 1, 16),
        ],
        "open": [100.0, 101.0, 110.0, 111.0],
        "close": [100.5, 101.5, 110.5, 111.5],
    }

    result = run_backtest(
        candles,
        StatefulStrategy(),
        make_config(),
        strategy_factory=StatefulStrategy,
    )

    assert len(instances) == 3
    assert [instance.calls for instance in instances] == [0, 1, 1]
    assert len(result.trades) == 2
    assert result.trades[0].entry_index == 1
    assert result.trades[0].exit_index == 1
    assert result.trades[1].entry_index == 3
    assert result.trades[1].exit_index == 3
    assert all(
        trade.exit_reason == "end_of_segment"
        for trade in result.trades
    )


def test_dynamic_sizing_respects_risk_budget_and_records_capital():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
        1: Signal("exit"),
    })
    initial_capital = 10_000_000.0
    config = make_config(commission=0.001, slippage=0.0005)

    result = run_backtest(
        make_candles(),
        strategy,
        config,
        initial_capital=initial_capital,
        risk_per_trade_pct=0.05,
        risk_max_portfolio_pct=0.05,
    )

    trade = result.trades[0]
    entry = 110.0 * 1.0005
    stop = entry - 10.0
    stop_exit = stop * 0.9995
    loss_per_unit = (
        entry - stop_exit
        + entry * 0.001
        + stop_exit * 0.001
    )
    expected_quantity = 500_000.0 / loss_per_unit

    assert trade.quantity == pytest.approx(expected_quantity)
    assert trade.capital_before == pytest.approx(initial_capital)
    assert trade.risk_budget == pytest.approx(500_000.0)
    assert trade.planned_risk == pytest.approx(500_000.0)
    assert trade.stop_price == pytest.approx(stop)
    assert trade.capital_after == pytest.approx(
        initial_capital + trade.net_pnl
    )
    assert result.initial_capital == pytest.approx(initial_capital)
    assert result.ending_capital == pytest.approx(
        initial_capital + result.total_net_pnl
    )
    assert result.total_return_pct == pytest.approx(
        (result.ending_capital / initial_capital - 1) * 100
    )


def test_dynamic_sizing_respects_spot_cash_limit():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=0.01),
        1: Signal("exit"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(),
        initial_capital=10_000_000.0,
        risk_per_trade_pct=0.05,
        risk_max_portfolio_pct=0.05,
    )

    trade = result.trades[0]
    maximum_cash_quantity = (
        trade.capital_before / trade.entry_price
    )

    assert trade.quantity == pytest.approx(maximum_cash_quantity)
    assert trade.planned_risk < trade.risk_budget


def test_dynamic_risk_budget_uses_updated_equity():
    candles = {
        "open": [100.0, 100.0, 110.0, 110.0, 110.0],
        "close": [100.0, 100.0, 110.0, 110.0, 110.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
        1: Signal("exit"),
        2: Signal("long", stop_distance=10.0),
        3: Signal("exit"),
    })

    result = run_backtest(
        candles,
        strategy,
        make_config(),
        initial_capital=10_000_000.0,
        risk_per_trade_pct=0.05,
        risk_max_portfolio_pct=0.05,
    )

    assert len(result.trades) == 2
    first, second = result.trades

    assert first.capital_before == pytest.approx(10_000_000.0)
    assert first.risk_budget == pytest.approx(500_000.0)
    assert second.capital_before == pytest.approx(
        first.capital_after
    )
    assert second.risk_budget == pytest.approx(
        second.capital_before * 0.05
    )
    assert second.risk_budget > first.risk_budget


def test_dynamic_sizing_rejects_entry_without_stop_distance():
    strategy = DummyStrategy({
        0: Signal("long"),
    })

    with pytest.raises(ValueError, match="requires stop_distance"):
        run_backtest(
            make_candles(),
            strategy,
            make_config(),
            initial_capital=10_000_000.0,
            risk_per_trade_pct=0.05,
            risk_max_portfolio_pct=0.05,
        )


def test_stop_loss_triggers_on_close_and_executes_next_open():
    candles = {
        "open": [100.0, 100.0, 100.0, 80.0],
        "close": [100.0, 100.0, 85.0, 80.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(candles, strategy, make_config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_index == 1
    assert trade.stop_price == pytest.approx(90.0)
    assert trade.exit_index == 3
    assert trade.exit_price == pytest.approx(80.0)
    assert trade.exit_reason == "stop_loss"


def test_close_above_stop_does_not_trigger():
    candles = {
        "open": [100.0, 100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 95.0, 96.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(candles, strategy, make_config())

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end_of_segment"
    assert result.trades[0].exit_price == pytest.approx(96.0)


def test_intraday_low_below_stop_is_ignored_in_mvp():
    candles = {
        "open": [100.0, 100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 95.0, 96.0],
        "low": [99.0, 99.0, 80.0, 94.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(candles, strategy, make_config())

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end_of_segment"
    assert result.trades[0].exit_price == pytest.approx(96.0)


def test_stop_loss_fires_when_open_gaps_up():
    candles = {
        "open": [100.0, 100.0, 100.0, 95.0],
        "close": [100.0, 100.0, 85.0, 96.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(candles, strategy, make_config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_index == 3
    assert trade.exit_price == pytest.approx(95.0)
    assert trade.exit_price > trade.stop_price
    assert trade.exit_reason == "stop_loss"


def test_stop_loss_takes_precedence_over_strategy_exit_in_same_bar():
    candles = {
        "open": [100.0, 100.0, 100.0, 80.0],
        "close": [100.0, 100.0, 85.0, 80.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
        2: Signal("exit", reason="strategy_exit"),
    })

    result = run_backtest(candles, strategy, make_config())

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].exit_price == pytest.approx(80.0)


def make_2r_candles(next_open):
    return {
        "open": [100.0, 110.0, 120.0, next_open],
        "close": [105.0, 115.0, 131.0, next_open],
    }


def test_take_profit_2r_triggers_on_close_and_executes_next_open():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(
        make_2r_candles(128.0),
        strategy,
        make_config(),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_index == 1
    assert trade.exit_index == 3
    assert trade.entry_price == 110.0
    assert trade.target_price == 130.0
    assert trade.exit_price == 128.0
    assert trade.exit_reason == "take_profit_2r"


def test_take_profit_2r_not_triggered_when_close_below_target():
    candles = {
        "open": [100.0, 110.0, 120.0],
        "close": [105.0, 115.0, 129.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(candles, strategy, make_config())

    trade = result.trades[0]
    assert trade.target_price == 130.0
    assert trade.exit_index == 2
    assert trade.exit_reason == "end_of_segment"


def test_take_profit_2r_gap_down_can_realize_less_than_2r():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(
        make_2r_candles(128.0),
        strategy,
        make_config(),
    )

    trade = result.trades[0]
    realized_r = trade.net_pnl / (trade.entry_price - 100.0)
    assert trade.exit_reason == "take_profit_2r"
    assert realized_r == pytest.approx(1.8)


def test_take_profit_2r_gap_up_can_realize_more_than_2r():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })

    result = run_backtest(
        make_2r_candles(140.0),
        strategy,
        make_config(),
    )

    trade = result.trades[0]
    realized_r = trade.net_pnl / (trade.entry_price - 100.0)
    assert trade.exit_reason == "take_profit_2r"
    assert realized_r == pytest.approx(3.0)


def test_no_take_profit_2r_without_stop_distance():
    strategy = DummyStrategy({
        0: Signal("long"),
    })

    result = run_backtest(
        make_candles(),
        strategy,
        make_config(),
    )

    trade = result.trades[0]
    assert trade.stop_price is None
    assert trade.target_price is None
    assert trade.exit_reason == "end_of_segment"


def test_take_profit_2r_overrides_strategy_exit_on_same_close():
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
        2: Signal("exit"),
    })

    result = run_backtest(
        make_2r_candles(140.0),
        strategy,
        make_config(),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "take_profit_2r"
    assert trade.exit_index == 3


def test_take_profit_can_be_disabled_without_disabling_stop_loss():
    candles = {
        "open": [100.0, 110.0, 90.0, 95.0],
        "close": [105.0, 115.0, 99.0, 96.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })
    config = BacktestConfig(
        commission_rate=0.0,
        slippage_rate=0.0,
        cost_basis="hypothetical",
        take_profit_r_multiple=None,
    )

    result = run_backtest(candles, strategy, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.target_price is None
    assert trade.stop_price == 100.0
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == 95.0


def test_take_profit_uses_configured_3r_multiple():
    # Backward compatibility: this legacy label does not encode the
    # configured multiple. Use target_price and config for the actual R.
    candles = {
        "open": [100.0, 110.0, 120.0, 140.0, 145.0],
        "close": [105.0, 115.0, 135.0, 141.0, 145.0],
    }
    strategy = DummyStrategy({
        0: Signal("long", stop_distance=10.0),
    })
    config = BacktestConfig(
        commission_rate=0.0,
        slippage_rate=0.0,
        cost_basis="hypothetical",
        take_profit_r_multiple=3.0,
    )

    result = run_backtest(candles, strategy, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.target_price == 140.0
    assert trade.exit_reason == "take_profit_2r"
    assert trade.exit_index == 4
    assert trade.exit_price == 145.0


@pytest.mark.parametrize(
    "value",
    [0, -1, float("inf"), float("-inf"), float("nan"), True, "2"],
)
def test_take_profit_r_multiple_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="take_profit_r_multiple"):
        BacktestConfig(
            commission_rate=0.0,
            slippage_rate=0.0,
            cost_basis="hypothetical",
            take_profit_r_multiple=value,
        )
