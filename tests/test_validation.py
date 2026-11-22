from datetime import UTC, datetime, timedelta

from app.market_data.validation import validate_ohlcv


def valid_candles():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "timestamp": [start, start + timedelta(hours=4)],
        "open": [100.0, 105.0],
        "high": [110.0, 115.0],
        "low": [95.0, 102.0],
        "close": [105.0, 110.0],
        "volume": [10.0, 12.0],
    }


def codes(data):
    return {issue.code for issue in validate_ohlcv(data)}


def test_valid_data():
    assert validate_ohlcv(valid_candles()) == ()


def test_missing_column():
    data = valid_candles()
    del data["volume"]
    assert "MISSING_COLUMNS" in codes(data)


def test_column_length_mismatch():
    data = valid_candles()
    data["close"].pop()
    assert "COLUMN_LENGTH_MISMATCH" in codes(data)


def test_duplicate_timestamp():
    data = valid_candles()
    data["timestamp"][1] = data["timestamp"][0]
    assert "DUPLICATE_TIMESTAMP" in codes(data)


def test_naive_timestamp():
    data = valid_candles()
    data["timestamp"][0] = datetime(2026, 1, 1)
    assert "NAIVE_TIMESTAMP" in codes(data)


def test_nan_price():
    data = valid_candles()
    data["close"][0] = float("nan")
    assert "NON_FINITE_VALUE" in codes(data)


def test_negative_volume():
    data = valid_candles()
    data["volume"][0] = -1.0
    assert "NEGATIVE_VOLUME" in codes(data)


def test_invalid_high_low():
    data = valid_candles()
    data["high"][0] = 90.0
    assert "INVALID_HIGH_LOW" in codes(data)


def test_boolean_price_rejected():
    data = valid_candles()
    data["open"][0] = True
    assert "NON_NUMERIC_VALUE" in codes(data)


def test_accepts_numpy_numeric_values():
    import numpy as np

    candles = valid_candles()
    candles["open"] = [np.float64(100), np.float64(101)]
    candles["high"] = [np.float64(110), np.float64(111)]
    candles["low"] = [np.float64(90), np.float64(91)]
    candles["close"] = [np.float64(105), np.float64(106)]
    candles["volume"] = [np.int64(10), np.int64(12)]

    assert validate_ohlcv(candles) == ()


def test_rejects_non_utc_timestamp():
    from datetime import datetime, timedelta, timezone

    candles = valid_candles()
    candles["timestamp"][0] = datetime(
        2026, 1, 1, tzinfo=timezone(timedelta(hours=3, minutes=30))
    )

    issues = validate_ohlcv(candles)

    assert any(issue.code == "NON_UTC_TIMESTAMP" for issue in issues)


def test_rejects_non_monotonic_timestamps():
    candles = valid_candles()
    candles["timestamp"].reverse()

    issues = validate_ohlcv(candles)

    assert any(issue.code == "NON_MONOTONIC_TIMESTAMP" for issue in issues)


def test_rejects_infinite_price():
    candles = valid_candles()
    candles["close"][0] = float("inf")

    issues = validate_ohlcv(candles)

    assert any(issue.code == "NON_FINITE_VALUE" for issue in issues)


def test_rejects_non_positive_price():
    candles = valid_candles()
    candles["close"][0] = 0

    issues = validate_ohlcv(candles)

    assert any(issue.code == "NON_POSITIVE_PRICE" for issue in issues)


def test_zero_volume_policy_warning_and_allow():
    candles = valid_candles()
    candles["volume"][0] = 0

    warning_issues = validate_ohlcv(candles, zero_volume_policy="warning")
    allow_issues = validate_ohlcv(candles, zero_volume_policy="allow")

    zero_volume_issue = next(
        issue for issue in warning_issues if issue.code == "ZERO_VOLUME"
    )

    assert zero_volume_issue.severity == "warning"
    assert not any(issue.code == "ZERO_VOLUME" for issue in allow_issues)


def test_zero_volume_policy_error():
    candles = valid_candles()
    candles["volume"][0] = 0

    issues = validate_ohlcv(candles, zero_volume_policy="error")

    zero_volume_issue = next(
        issue for issue in issues if issue.code == "ZERO_VOLUME"
    )

    assert zero_volume_issue.severity == "error"
