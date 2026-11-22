from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.market_data.validation import (
    ValidationIssue,
    ZeroVolumePolicy,
    validate_ohlcv,
)


@dataclass(frozen=True)
class QualityGateConfig:
    expected_interval: timedelta
    now: datetime
    closed_bars_only: bool = True
    gap_tolerance: timedelta = timedelta(0)
    gap_severity: Literal["error", "warning"] = "error"
    zero_volume_policy: ZeroVolumePolicy = "warning"

    def __post_init__(self) -> None:
        if self.expected_interval <= timedelta(0):
            raise ValueError("expected_interval must be positive.")

        if self.gap_tolerance < timedelta(0):
            raise ValueError("gap_tolerance must not be negative.")
        if self.gap_severity not in {"error", "warning"}:
            raise ValueError("gap_severity must be error or warning.")

        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware.")

        if self.now.utcoffset() != timedelta(0):
            raise ValueError("now must use UTC.")


def run_quality_gate(
    candles: Mapping[str, Sequence[object]],
    config: QualityGateConfig,
) -> tuple[ValidationIssue, ...]:
    """Check OHLCV validity, candle closure, and time gaps."""
    issues = list(
        validate_ohlcv(
            candles,
            zero_volume_policy=config.zero_volume_policy,
        )
    )

    if any(issue.severity == "error" for issue in issues):
        return tuple(issues)

    if any(
        issue.code in {
            "EMPTY_DATA",
            "MISSING_COLUMNS",
            "COLUMN_LENGTH_MISMATCH",
            "INVALID_TIMESTAMP",
            "NAIVE_TIMESTAMP",
            "NON_UTC_TIMESTAMP",
            "DUPLICATE_TIMESTAMP",
            "NON_MONOTONIC_TIMESTAMP",
        }
        for issue in issues
    ):
        return tuple(issues)

    timestamps = candles["timestamp"]

    if config.closed_bars_only:
        for index, timestamp in enumerate(timestamps):
            if timestamp + config.expected_interval > config.now:
                issues.append(
                    ValidationIssue(
                        code="UNFINISHED_CANDLE",
                        message="Candle has not closed yet.",
                        row_index=index,
                    )
                )

    for index in range(1, len(timestamps)):
        previous = timestamps[index - 1]
        current = timestamps[index]

        actual_gap = current - previous
        difference = abs(actual_gap - config.expected_interval)

        if difference > config.gap_tolerance:
            issues.append(
                ValidationIssue(
                    code="CANDLE_GAP",
                    message=(
                        f"Unexpected candle interval: {actual_gap}; "
                        f"expected {config.expected_interval}."
                    ),
                    row_index=index,
                    severity=config.gap_severity,
                )
            )

    return tuple(issues)
