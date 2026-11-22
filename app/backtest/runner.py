from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestResult, run_backtest
from app.core.config import Settings
from app.market_data.archive import ArchiveError, load_wallex_archive
from app.market_data.quality_gate import (
    QualityGateConfig,
    run_quality_gate,
)
from app.market_data.resampling import resample_1h_to_4h
from app.market_data.validation import ValidationIssue
from app.strategies.swing_pullback import SwingPullbackStrategy


ARCHIVE_SYMBOLS = {
    "BTCIRT": "BTCTMN",
    "ETHIRT": "ETHTMN",
}


@dataclass(frozen=True)
class BacktestRunResult:
    symbol: str
    start: int
    end: int
    hourly_candles: int
    four_hour_candles: int
    incomplete_groups: int
    discarded_hourly_candles: int
    quality_warnings: tuple[ValidationIssue, ...]
    backtest: BacktestResult


def _filter_closed_candles(
    candles: dict[str, list[object]],
    *,
    start: datetime,
    cutoff: datetime,
    interval: timedelta,
) -> dict[str, list[object]]:
    timestamps = candles["timestamp"]
    indexes = [
        index
        for index, timestamp in enumerate(timestamps)
        if isinstance(timestamp, datetime)
        and start <= timestamp
        and timestamp + interval <= cutoff
    ]
    return {
        column: [values[index] for index in indexes]
        for column, values in candles.items()
    }


def run_swing_pullback_backtest(
    symbol: str,
    start: int,
    end: int,
    backtest_config: BacktestConfig,
    settings: Settings,
) -> BacktestRunResult:
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError("start must be an integer Unix timestamp.")

    if isinstance(end, bool) or not isinstance(end, int):
        raise ValueError("end must be an integer Unix timestamp.")

    if start < 0 or end <= start:
        raise ValueError("Invalid timestamp range.")

    if symbol not in ARCHIVE_SYMBOLS:
        raise ValueError(f"Unsupported backtest symbol: {symbol}")

    now = datetime.now(UTC)
    start_dt = datetime.fromtimestamp(start, UTC)
    end_dt = datetime.fromtimestamp(end, UTC)
    cutoff = min(now, end_dt)

    hourly_interval = timedelta(hours=1)
    four_hour_interval = timedelta(hours=4)
    gap_ratio = settings.qg_gap_tolerance_ratio

    try:
        archive_result = load_wallex_archive(
            symbol=ARCHIVE_SYMBOLS[symbol],
            start=start_dt,
            end=end_dt,
        )
    except ArchiveError as exc:
        raise ValueError(
            f"Hourly archive validation failed: {exc}"
        ) from exc

    closed_hourly = _filter_closed_candles(
        archive_result.candles,
        start=start_dt,
        cutoff=cutoff,
        interval=hourly_interval,
    )

    hourly_issues = run_quality_gate(
        closed_hourly,
        QualityGateConfig(
            expected_interval=hourly_interval,
            now=cutoff,
            closed_bars_only=True,
            gap_tolerance=hourly_interval * gap_ratio,
            gap_severity="warning",
            zero_volume_policy=settings.qg_zero_volume_severity,
        ),
    )

    hourly_errors = [
        issue for issue in hourly_issues
        if issue.severity == "error"
    ]
    if hourly_errors:
        raise ValueError(f"Hourly data quality failed: {hourly_errors}")

    if not closed_hourly["timestamp"]:
        raise ValueError("No closed hourly candles available.")

    resampled = resample_1h_to_4h(closed_hourly)

    if not resampled.candles["timestamp"]:
        raise ValueError("No complete 4-hour candles available.")

    four_hour_issues = run_quality_gate(
        resampled.candles,
        QualityGateConfig(
            expected_interval=four_hour_interval,
            now=cutoff,
            closed_bars_only=True,
            gap_tolerance=four_hour_interval * gap_ratio,
            gap_severity="warning",
            zero_volume_policy=settings.qg_zero_volume_severity,
        ),
    )

    four_hour_errors = [
        issue for issue in four_hour_issues
        if issue.severity == "error"
    ]
    if four_hour_errors:
        raise ValueError(
            f"4-hour data quality failed: {four_hour_errors}"
        )

    strategy = SwingPullbackStrategy(settings=settings)

    result = run_backtest(
        candles=resampled.candles,
        strategy=strategy,
        config=backtest_config,
        strategy_factory=lambda: SwingPullbackStrategy(
            settings=settings
        ),
        initial_capital=settings.initial_capital_toman,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        risk_max_portfolio_pct=settings.risk_max_portfolio_pct,
    )

    warnings = tuple(
        issue
        for issue in (*hourly_issues, *four_hour_issues)
        if issue.severity == "warning"
    )

    return BacktestRunResult(
        symbol=symbol,
        start=start,
        end=end,
        hourly_candles=len(closed_hourly["timestamp"]),
        four_hour_candles=len(resampled.candles["timestamp"]),
        incomplete_groups=resampled.incomplete_groups,
        discarded_hourly_candles=resampled.discarded_hourly_candles,
        quality_warnings=warnings,
        backtest=result,
    )
