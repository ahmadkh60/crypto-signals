import pytest

from app.strategies.base import BarHistory
from app.strategies.breakout import detect_resistance_breakout


def make_history(highs, closes, index=None):
    if index is None:
        index = len(highs) - 1

    return BarHistory.from_candles(
        {"high": highs, "close": closes},
        index,
    )


def test_breakout_above_previous_twenty_bar_highs():
    highs = [100.0] * 20 + [105.0]
    closes = [99.0] * 20 + [101.0]

    result = detect_resistance_breakout(make_history(highs, closes))

    assert result is not None
    assert result.index == 20
    assert result.resistance == 100.0
    assert result.breakout_close == 101.0


def test_equal_close_does_not_count_as_breakout():
    highs = [100.0] * 20 + [105.0]
    closes = [99.0] * 20 + [100.0]

    result = detect_resistance_breakout(make_history(highs, closes))

    assert result is None


def test_close_below_resistance_does_not_count_as_breakout():
    highs = [100.0] * 20 + [110.0]
    closes = [99.0] * 20 + [100.0]

    result = detect_resistance_breakout(make_history(highs, closes))

    assert result is None


def test_current_candle_high_is_excluded_from_resistance():
    highs = [100.0] * 20 + [150.0]
    closes = [99.0] * 20 + [120.0]

    result = detect_resistance_breakout(make_history(highs, closes))

    assert result is not None
    assert result.resistance == 100.0


def test_insufficient_history_returns_none():
    highs = [100.0] * 19
    closes = [110.0] * 19

    result = detect_resistance_breakout(make_history(highs, closes))

    assert result is None


@pytest.mark.parametrize("lookback", [0, -1])
def test_invalid_lookback_is_rejected(lookback):
    history = make_history([100.0] * 21, [99.0] * 21)

    with pytest.raises(ValueError):
        detect_resistance_breakout(history, lookback=lookback)
