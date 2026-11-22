from datetime import UTC, datetime

import pytest

from app.market_data.candles import (
    CandleParseError,
    parse_wallex_response,
)


def valid_payload():
    return {
        "s": "ok",
        "t": [1700000000, 1700003600],
        "o": ["100", "105"],
        "h": ["110", "115"],
        "l": ["95", "100"],
        "c": ["105", "110"],
        "v": ["1.5", "2.5"],
    }


def test_converts_wallex_response_to_ohlcv():
    result = parse_wallex_response(valid_payload())

    assert result["timestamp"] == [
        datetime.fromtimestamp(1700000000, UTC),
        datetime.fromtimestamp(1700003600, UTC),
    ]
    assert result["open"] == [100.0, 105.0]
    assert result["high"] == [110.0, 115.0]
    assert result["low"] == [95.0, 100.0]
    assert result["close"] == [105.0, 110.0]
    assert result["volume"] == [1.5, 2.5]


def test_preserves_missing_candle_gap_without_filling():
    payload = valid_payload()
    payload["t"] = [1700000000, 1700007200]

    result = parse_wallex_response(payload)

    assert len(result["timestamp"]) == 2
    assert (
        result["timestamp"][1] - result["timestamp"][0]
    ).total_seconds() == 7200


def test_rejects_non_ok_status():
    payload = valid_payload()
    payload["s"] = "no_data"

    with pytest.raises(CandleParseError, match="status"):
        parse_wallex_response(payload)


def test_rejects_missing_field():
    payload = valid_payload()
    del payload["v"]

    with pytest.raises(CandleParseError, match="Missing"):
        parse_wallex_response(payload)


def test_rejects_non_array_field():
    payload = valid_payload()
    payload["o"] = "100"

    with pytest.raises(CandleParseError, match="array"):
        parse_wallex_response(payload)


def test_rejects_different_array_lengths():
    payload = valid_payload()
    payload["v"] = ["1.5"]

    with pytest.raises(CandleParseError, match="lengths"):
        parse_wallex_response(payload)


def test_rejects_empty_response():
    payload = {
        "s": "ok",
        "t": [],
        "o": [],
        "h": [],
        "l": [],
        "c": [],
        "v": [],
    }

    with pytest.raises(CandleParseError, match="no candles"):
        parse_wallex_response(payload)


@pytest.mark.parametrize(
    "timestamps",
    [
        [1700000000, 1700000000],
        [1700003600, 1700000000],
    ],
)
def test_rejects_duplicate_or_unordered_timestamps(timestamps):
    payload = valid_payload()
    payload["t"] = timestamps

    with pytest.raises(CandleParseError, match="strictly increasing"):
        parse_wallex_response(payload)


@pytest.mark.parametrize("value", ["invalid", True])
def test_rejects_invalid_numeric_values(value):
    payload = valid_payload()
    payload["o"][0] = value

    with pytest.raises(CandleParseError):
        parse_wallex_response(payload)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_values(value):
    payload = valid_payload()
    payload["c"][0] = value

    with pytest.raises(CandleParseError, match="Non-finite"):
        parse_wallex_response(payload)


def test_rejects_invalid_timestamp():
    payload = valid_payload()
    payload["t"][0] = True

    with pytest.raises(CandleParseError, match="timestamp"):
        parse_wallex_response(payload)
