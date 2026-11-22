
import pytest

from app.strategies.base import BarHistory
from app.strategies.pivots import find_confirmed_pivots


def make_history(highs, lows, index=None):
    if index is None:
        index = len(highs) - 1

    candles = {
        "high": highs,
        "low": lows,
    }

    return BarHistory.from_candles(candles, index)


def test_pivot_high_is_confirmed_after_two_right_bars():
    highs = [10, 12, 15, 11, 13]
    lows = [5, 6, 7, 6, 8]

    history = make_history(highs, lows)

    pivot_highs, pivot_lows = find_confirmed_pivots(history)

    assert len(pivot_highs) == 1
    assert pivot_highs[0].index == 2
    assert pivot_highs[0].price == 15
    assert pivot_highs[0].confirmed_at == 4
    assert pivot_lows == ()


def test_pivot_low_is_confirmed_after_two_right_bars():
    highs = [15, 14, 13, 14, 16]
    lows = [10, 8, 5, 7, 9]

    history = make_history(highs, lows)

    pivot_highs, pivot_lows = find_confirmed_pivots(history)

    assert pivot_highs == ()
    assert len(pivot_lows) == 1
    assert pivot_lows[0].index == 2
    assert pivot_lows[0].price == 5
    assert pivot_lows[0].confirmed_at == 4


def test_pivot_is_not_visible_before_two_right_bars_close():
    highs = [10, 12, 15, 11, 13]
    lows = [5, 6, 7, 6, 8]

    history = make_history(highs, lows, index=3)

    pivot_highs, pivot_lows = find_confirmed_pivots(history)

    assert pivot_highs == ()
    assert pivot_lows == ()


def test_equal_high_does_not_confirm_pivot():
    highs = [10, 12, 15, 11, 15]
    lows = [5, 6, 7, 6, 8]

    history = make_history(highs, lows)

    pivot_highs, _ = find_confirmed_pivots(history)

    assert pivot_highs == ()


def test_equal_low_does_not_confirm_pivot():
    highs = [15, 14, 13, 14, 16]
    lows = [10, 8, 5, 7, 5]

    history = make_history(highs, lows)

    _, pivot_lows = find_confirmed_pivots(history)

    assert pivot_lows == ()


@pytest.mark.parametrize(
    ("left", "right"),
    [(0, 2), (2, 0), (-1, 2), (2, -1)],
)
def test_invalid_pivot_widths_are_rejected(left, right):
    history = make_history([10, 12, 15, 11, 13], [5, 6, 7, 6, 8])

    with pytest.raises(ValueError):
        find_confirmed_pivots(history, left=left, right=right)
