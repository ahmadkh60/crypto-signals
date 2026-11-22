import pytest

from app.strategies.indicators import calculate_atr


def test_atr_uses_simple_average_for_initial_value():
    highs = (10.0, 12.0, 13.0)
    lows = (8.0, 9.0, 11.0)
    closes = (9.0, 11.0, 12.0)

    result = calculate_atr(highs, lows, closes, period=3)

    assert result[:2] == (None, None)
    assert result[2] == pytest.approx(2.3333333333333335)


def test_atr_uses_wilder_smoothing():
    highs = (10.0, 12.0, 13.0, 15.0)
    lows = (8.0, 9.0, 11.0, 13.0)
    closes = (9.0, 11.0, 12.0, 14.0)

    result = calculate_atr(highs, lows, closes, period=3)

    assert result[2] == pytest.approx(2.3333333333333335)
    assert result[3] == pytest.approx(2.5555555555555554)


def test_atr_returns_none_until_enough_candles_exist():
    result = calculate_atr(
        (10.0, 11.0),
        (8.0, 9.0),
        (9.0, 10.0),
        period=3,
    )

    assert result == (None, None)


def test_previous_close_is_used_for_true_range():
    result = calculate_atr(
        (10.0, 15.0),
        (8.0, 13.0),
        (9.0, 14.0),
        period=2,
    )

    assert result[1] == pytest.approx(4.0)


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError):
        calculate_atr((10.0,), (8.0, 9.0), (9.0,))


def test_invalid_period_is_rejected():
    with pytest.raises(ValueError):
        calculate_atr((10.0,), (8.0,), (9.0,), period=0)


def test_non_finite_values_are_rejected():
    with pytest.raises(ValueError):
        calculate_atr((float("inf"),), (8.0,), (9.0,))


def test_high_below_low_is_rejected():
    with pytest.raises(ValueError):
        calculate_atr((8.0,), (10.0,), (9.0,))
