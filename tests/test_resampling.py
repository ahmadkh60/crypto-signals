from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.resampling import (
    ResamplingError,
    resample_1h_to_4h,
)


def make_candles(count=4, start_hour=0):
    return {
        "timestamp": [
            datetime(2026, 1, 1, start_hour + i, tzinfo=UTC)
            for i in range(count)
        ],
        "open": [100 + i for i in range(count)],
        "high": [110 + i for i in range(count)],
        "low": [90 + i for i in range(count)],
        "close": [105 + i for i in range(count)],
        "volume": [10.0, 20.0, 30.0, 40.0][:count],
    }


def test_resamples_four_hourly_candles_correctly():
    result = resample_1h_to_4h(make_candles())

    candles = result.candles

    assert result.complete_groups == 1
    assert result.incomplete_groups == 0
    assert candles["timestamp"] == [
        datetime(2026, 1, 1, 0, tzinfo=UTC)
    ]
    assert candles["open"] == [100.0]
    assert candles["high"] == [113.0]
    assert candles["low"] == [90.0]
    assert candles["close"] == [108.0]
    assert candles["volume"] == [100.0]


def test_discards_incomplete_four_hour_group():
    result = resample_1h_to_4h(make_candles(count=3))

    assert result.complete_groups == 0
    assert result.incomplete_groups == 1
    assert result.discarded_hourly_candles == 3
    assert result.candles["timestamp"] == []


def test_rejects_non_hour_aligned_timestamp():
    candles = make_candles()
    candles["timestamp"][1] += timedelta(minutes=30)

    with pytest.raises(ResamplingError, match="hour-aligned"):
        resample_1h_to_4h(candles)


def test_rejects_unordered_timestamps():
    candles = make_candles()
    candles["timestamp"][2], candles["timestamp"][3] = (
        candles["timestamp"][3],
        candles["timestamp"][2],
    )

    with pytest.raises(ResamplingError, match="strictly increasing"):
        resample_1h_to_4h(candles)
