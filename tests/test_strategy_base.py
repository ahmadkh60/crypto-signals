import pytest

from app.strategies.base import BarHistory, Signal


def test_signal_creation():
    signal = Signal(action="long", reason="pullback confirmed")

    assert signal.action == "long"
    assert signal.reason == "pullback confirmed"


def test_default_signal_reason():
    signal = Signal(action="hold")

    assert signal.action == "hold"
    assert signal.reason == ""


def test_bar_history_excludes_future_candles():
    candles = {
        "open": [100, 110, 120, 130],
        "close": [105, 115, 125, 135],
    }

    history = BarHistory.from_candles(candles, 1)

    assert history.index == 1
    assert len(history) == 2
    assert history["close"] == (105, 115)
    assert 125 not in history["close"]


def test_bar_history_is_read_only():
    history = BarHistory.from_candles(
        {"close": [100, 110]},
        1,
    )

    with pytest.raises(TypeError):
        history.candles["close"] = (1, 2)


def test_bar_history_rejects_invalid_index():
    with pytest.raises(ValueError):
        BarHistory.from_candles({"close": [100]}, 1)
