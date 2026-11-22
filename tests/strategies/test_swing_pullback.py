from app.core.config import Settings
from app.strategies.base import BarHistory
from app.strategies.swing_pullback import (
    SetupState,
    SwingPullbackStrategy,
)


def make_history(highs, lows, closes, index):
    return BarHistory.from_candles(
        {
            "high": highs,
            "low": lows,
            "close": closes,
        },
        index,
    )


def feed(strategy, highs, lows, closes, index):
    return strategy.on_bar(
        make_history(highs, lows, closes, index)
    )


def base_data():
    return (
        [101.0, 101.0, 101.0],
        [99.0, 99.0, 99.0],
        [100.0, 100.0, 100.0],
    )


def make_strategy():
    return SwingPullbackStrategy(
        Settings(
            atr_period=2,
            breakout_lookback=3,
            pullback_atr_multiplier=0.5,
            pullback_max_bars=10,
        )
    )


def test_strategy_starts_waiting_for_breakout():
    strategy = make_strategy()

    assert strategy.state == SetupState.WAIT_BREAKOUT
    assert strategy.resistance is None


def test_strategy_waits_when_atr_history_is_insufficient():
    strategy = SwingPullbackStrategy(Settings(atr_period=14))
    highs, lows, closes = base_data()

    signal = feed(strategy, highs, lows, closes, 2)

    assert signal.action == "hold"
    assert signal.reason == "insufficient_atr_history"


def test_breakout_pullback_and_confirmation_sequence():
    strategy = make_strategy()
    highs, lows, closes = base_data()

    # Breakout candle
    highs.append(104.0)
    lows.append(101.0)
    closes.append(103.0)

    signal = feed(strategy, highs, lows, closes, 3)

    assert signal.action == "hold"
    assert signal.reason == "breakout_detected"
    assert strategy.state == SetupState.WAIT_PULLBACK

    # Pullback candle
    highs.append(103.0)
    lows.append(100.5)
    closes.append(102.0)

    signal = feed(strategy, highs, lows, closes, 4)

    assert signal.action == "hold"
    assert signal.reason == "pullback_detected"
    assert strategy.state == SetupState.WAIT_CONFIRMATION

    # Confirmation candle: close exceeds previous high
    highs.append(105.0)
    lows.append(102.0)
    closes.append(104.0)

    signal = feed(strategy, highs, lows, closes, 5)

    assert signal.action == "long"
    assert signal.reason == "swing_pullback_confirmed"
    assert strategy.state == SetupState.IN_POSITION
    assert strategy.resistance is not None
    assert signal.stop_distance is not None
    assert signal.stop_distance > 0


def test_breakout_is_invalidated_below_atr_zone():
    strategy = make_strategy()
    highs, lows, closes = base_data()

    highs.append(104.0)
    lows.append(101.0)
    closes.append(103.0)

    feed(strategy, highs, lows, closes, 3)

    highs.append(100.0)
    lows.append(89.0)
    closes.append(90.0)

    signal = feed(strategy, highs, lows, closes, 4)

    assert signal.action == "hold"
    assert signal.reason == "breakout_invalidated"
    assert strategy.state == SetupState.WAIT_BREAKOUT
    assert strategy.resistance is None


def test_setup_expires_after_maximum_pullback_wait():
    strategy = make_strategy()
    highs, lows, closes = base_data()

    highs.append(104.0)
    lows.append(101.0)
    closes.append(103.0)

    feed(strategy, highs, lows, closes, 3)

    # Ten subsequent candles are allowed; the eleventh expires.
    for _ in range(11):
        highs.append(110.0)
        lows.append(109.0)
        closes.append(109.5)

    signal = feed(strategy, highs, lows, closes, 14)

    assert signal.action == "hold"
    assert signal.reason == "pullback_expired"
    assert strategy.state == SetupState.WAIT_BREAKOUT
    assert strategy.resistance is None
