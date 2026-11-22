from datetime import UTC, datetime, timedelta

from app.market_data.quality_gate import (
    QualityGateConfig,
    run_quality_gate,
)


def valid_candles():
    start = datetime(2026, 1, 1, tzinfo=UTC)

    return {
        "timestamp": [
            start,
            start + timedelta(hours=4),
        ],
        "open": [100.0, 101.0],
        "high": [110.0, 111.0],
        "low": [90.0, 91.0],
        "close": [105.0, 106.0],
        "volume": [10.0, 12.0],
    }


def make_config(**overrides):
    values = {
        "expected_interval": timedelta(hours=4),
        "now": datetime(2026, 1, 2, tzinfo=UTC),
    }
    values.update(overrides)
    return QualityGateConfig(**values)


def test_accepts_valid_closed_candles():
    issues = run_quality_gate(valid_candles(), make_config())

    assert issues == ()


def test_rejects_unfinished_candle():
    candles = valid_candles()
    config = make_config(
        now=datetime(2026, 1, 1, 5, tzinfo=UTC),
    )

    issues = run_quality_gate(candles, config)

    assert any(issue.code == "UNFINISHED_CANDLE" for issue in issues)


def test_detects_missing_candle_interval_as_warning():
    candles = valid_candles()
    candles["timestamp"][1] += timedelta(hours=4)

    issues = run_quality_gate(candles, make_config(gap_severity="warning"))

    gap_issues = [issue for issue in issues if issue.code == "CANDLE_GAP"]

    assert len(gap_issues) == 1
    assert gap_issues[0].severity == "warning"
    assert not any(issue.severity == "error" for issue in issues)


def test_does_not_check_gaps_when_timestamp_is_invalid():
    candles = valid_candles()
    candles["timestamp"][1] = candles["timestamp"][0]

    issues = run_quality_gate(candles, make_config())

    codes = {issue.code for issue in issues}

    assert "DUPLICATE_TIMESTAMP" in codes
    assert "CANDLE_GAP" not in codes


def test_rejects_empty_data_without_crashing():
    candles = {
        "timestamp": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }

    issues = run_quality_gate(candles, make_config())

    assert any(issue.code == "EMPTY_DATA" for issue in issues)


def test_rejects_naive_now():
    try:
        make_config(now=datetime(2026, 1, 2))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("Naive now must be rejected.")


def test_gap_within_tolerance_is_accepted():
    candles = valid_candles()
    candles["timestamp"][1] += timedelta(seconds=30)

    config = make_config(
        gap_tolerance=timedelta(seconds=30),
    )

    issues = run_quality_gate(candles, config)

    assert not any(issue.code == "CANDLE_GAP" for issue in issues)


def test_utc_offset_zero_timezone_is_accepted():
    from datetime import timezone

    config = make_config(
        now=datetime(2026, 1, 2, tzinfo=timezone(timedelta(0))),
    )

    assert config.now.utcoffset() == timedelta(0)


def test_zero_volume_warning_does_not_block_quality_gate():
    candles = valid_candles()
    candles["volume"][0] = 0

    issues = run_quality_gate(candles, make_config())

    zero_volume_issue = next(
        issue for issue in issues if issue.code == "ZERO_VOLUME"
    )

    assert zero_volume_issue.severity == "warning"
    assert not any(issue.severity == "error" for issue in issues)


def test_rejects_non_monotonic_timestamps_without_gap_check():
    candles = valid_candles()
    candles["timestamp"].reverse()

    issues = run_quality_gate(candles, make_config())

    codes = {issue.code for issue in issues}

    assert "NON_MONOTONIC_TIMESTAMP" in codes
    assert "CANDLE_GAP" not in codes
