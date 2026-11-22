from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.segments import split_candle_segments


def make_candles():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [
        start,
        start + timedelta(hours=4),
        start + timedelta(hours=8),
        start + timedelta(hours=16),
        start + timedelta(hours=20),
    ]

    return {
        "timestamp": timestamps,
        "open": [100, 101, 102, 103, 104],
        "high": [110, 111, 112, 113, 114],
        "low": [90, 91, 92, 93, 94],
        "close": [105, 106, 107, 108, 109],
        "volume": [10, 20, 30, 40, 50],
    }


def test_splits_candles_at_time_gaps():
    segments = split_candle_segments(make_candles())

    assert [segment.count for segment in segments] == [3, 2]
    assert segments[0].candles["open"] == [100, 101, 102]
    assert segments[1].candles["open"] == [103, 104]


def test_preserves_original_indices():
    segments = split_candle_segments(make_candles())

    assert (segments[0].start_index, segments[0].end_index) == (0, 3)
    assert (segments[1].start_index, segments[1].end_index) == (3, 5)


def test_empty_input_returns_no_segments():
    candles = {key: [] for key in make_candles()}

    assert split_candle_segments(candles) == []


def test_rejects_unordered_timestamps():
    candles = make_candles()
    candles["timestamp"][2], candles["timestamp"][3] = (
        candles["timestamp"][3],
        candles["timestamp"][2],
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        split_candle_segments(candles)


def test_rejects_unequal_column_lengths():
    candles = make_candles()
    candles["volume"].pop()

    with pytest.raises(ValueError, match="equal lengths"):
        split_candle_segments(candles)
