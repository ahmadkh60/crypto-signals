from datetime import UTC, datetime, timedelta

import pytest

from app.backtest import runner
from app.backtest.config import BacktestConfig
from app.core.config import Settings
from app.market_data.archive import ArchiveError, ArchiveResult


def make_candles(timestamps):
    return {
        "timestamp": timestamps,
        "open": [100.0] * len(timestamps),
        "high": [105.0] * len(timestamps),
        "low": [95.0] * len(timestamps),
        "close": [102.0] * len(timestamps),
        "volume": [10.0] * len(timestamps),
    }


def make_config():
    return BacktestConfig(
        commission_rate=0.001,
        slippage_rate=0.0005,
        cost_basis="hypothetical",
    )


def test_filter_closed_candles_respects_start_and_cutoff():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [
        start - timedelta(hours=1),
        start,
        start + timedelta(hours=1),
        start + timedelta(hours=2),
    ]
    candles = make_candles(timestamps)

    result = runner._filter_closed_candles(
        candles,
        start=start,
        cutoff=start + timedelta(hours=2),
        interval=timedelta(hours=1),
    )

    assert result["timestamp"] == timestamps[1:3]
    assert len(result["close"]) == 2


def test_runner_rejects_archive_errors(monkeypatch):
    now = datetime(2026, 1, 2, tzinfo=UTC)

    monkeypatch.setattr(
        runner,
        "datetime",
        type(
            "FixedDateTime",
            (datetime,),
            {"now": classmethod(lambda cls, tz=None: now)},
        ),
    )

    def fail_archive(**kwargs):
        raise ArchiveError("SHA-256 mismatch")

    monkeypatch.setattr(runner, "load_wallex_archive", fail_archive)

    with pytest.raises(ValueError, match="Hourly archive validation failed"):
        runner.run_swing_pullback_backtest(
            symbol="BTCIRT",
            start=int((now - timedelta(days=1)).timestamp()),
            end=int(now.timestamp()),
            backtest_config=make_config(),
            settings=Settings(),
        )


def test_runner_completes_successful_four_hour_pipeline(monkeypatch):
    current = datetime.now(UTC)
    current_hour = current.replace(minute=0, second=0, microsecond=0)
    base = current_hour.replace(
        hour=(current_hour.hour // 4) * 4
    ) - timedelta(hours=4)
    now = base + timedelta(hours=4)

    timestamps = [
        base + timedelta(hours=offset)
        for offset in range(4)
    ]
    hourly = make_candles(timestamps)

    monkeypatch.setattr(
        runner,
        "load_wallex_archive",
        lambda **kwargs: ArchiveResult(
            symbol="BTCTMN",
            candles=hourly,
            files_loaded=1,
            duplicate_candles=0,
        ),
    )

    expected_backtest = object()
    captured = {}

    def fake_run_backtest(**kwargs):
        captured.update(kwargs)
        return expected_backtest

    monkeypatch.setattr(runner, "run_backtest", fake_run_backtest)

    result = runner.run_swing_pullback_backtest(
        symbol="BTCIRT",
        start=int(base.timestamp()),
        end=int(now.timestamp()),
        backtest_config=make_config(),
        settings=Settings(),
    )

    assert result.hourly_candles == 4
    assert result.four_hour_candles == 1
    assert result.incomplete_groups == 0
    assert result.backtest is expected_backtest

    four_hour = captured["candles"]
    assert four_hour["timestamp"] == [base]
    assert four_hour["open"] == [100.0]
    assert four_hour["high"] == [105.0]
    assert four_hour["low"] == [95.0]
    assert four_hour["close"] == [102.0]
    assert four_hour["volume"] == [40.0]
    assert callable(captured["strategy_factory"])
