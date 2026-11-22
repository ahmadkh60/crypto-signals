from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from numbers import Real
from typing import Literal

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")

ZeroVolumePolicy = Literal["allow", "warning", "error"]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    row_index: int | None = None
    severity: Literal["warning", "error"] = "error"


def validate_ohlcv(
    candles: Mapping[str, Sequence[object]],
    *,
    zero_volume_policy: ZeroVolumePolicy = "warning",
) -> tuple[ValidationIssue, ...]:
    """Validate OHLCV structure, timestamps, and numeric values."""
    if zero_volume_policy not in ("allow", "warning", "error"):
        raise ValueError("Invalid zero_volume_policy.")

    issues: list[ValidationIssue] = []

    missing = [name for name in REQUIRED_COLUMNS if name not in candles]
    if missing:
        return (
            ValidationIssue(
                code="MISSING_COLUMNS",
                message=f"Missing required columns: {', '.join(missing)}",
            ),
        )

    lengths = {name: len(candles[name]) for name in REQUIRED_COLUMNS}
    if len(set(lengths.values())) != 1:
        return (
            ValidationIssue(
                code="COLUMN_LENGTH_MISMATCH",
                message=f"Column lengths differ: {lengths}",
            ),
        )

    row_count = lengths["timestamp"]
    if row_count == 0:
        return (
            ValidationIssue(
                code="EMPTY_DATA",
                message="No candle rows were provided.",
            ),
        )

    previous_timestamp: datetime | None = None
    seen_timestamps: set[datetime] = set()

    for index in range(row_count):
        timestamp = candles["timestamp"][index]

        if not isinstance(timestamp, datetime):
            issues.append(
                ValidationIssue(
                    "INVALID_TIMESTAMP",
                    "Timestamp must be a datetime object.",
                    index,
                )
            )
        elif timestamp.tzinfo is None or timestamp.utcoffset() is None:
            issues.append(
                ValidationIssue(
                    "NAIVE_TIMESTAMP",
                    "Timestamp must be timezone-aware.",
                    index,
                )
            )
        elif timestamp.utcoffset() != UTC.utcoffset(timestamp):
            issues.append(
                ValidationIssue(
                    "NON_UTC_TIMESTAMP",
                    "Timestamp must use UTC.",
                    index,
                )
            )
        else:

            if timestamp in seen_timestamps:
                issues.append(
                    ValidationIssue(
                        "DUPLICATE_TIMESTAMP",
                        "Timestamp is duplicated.",
                        index,
                    )
                )
            else:
                seen_timestamps.add(timestamp)

            if previous_timestamp is not None and timestamp < previous_timestamp:
                issues.append(
                    ValidationIssue(
                        "NON_MONOTONIC_TIMESTAMP",
                        "Timestamps must be strictly increasing.",
                        index,
                    )
                )

            previous_timestamp = timestamp

        values: dict[str, float] = {}
        row_numeric_valid = True

        for column in (*PRICE_COLUMNS, "volume"):
            value = candles[column][index]

            if isinstance(value, bool) or not isinstance(value, Real):
                issues.append(
                    ValidationIssue(
                        "NON_NUMERIC_VALUE",
                        f"{column} must contain a real numeric value.",
                        index,
                    )
                )
                row_numeric_valid = False
                continue

            try:
                numeric_value = float(value)
            except (OverflowError, ValueError):
                numeric_value = float("inf")

            if not isfinite(numeric_value):
                issues.append(
                    ValidationIssue(
                        "NON_FINITE_VALUE",
                        f"{column} must not be NaN or infinite.",
                        index,
                    )
                )
                row_numeric_valid = False
                continue

            values[column] = numeric_value

        for column in PRICE_COLUMNS:
            if column in values and values[column] <= 0:
                issues.append(
                    ValidationIssue(
                        "NON_POSITIVE_PRICE",
                        f"{column} must be greater than zero.",
                        index,
                    )
                )
                row_numeric_valid = False

        if "volume" in values:
            volume = values["volume"]

            if volume < 0:
                issues.append(
                    ValidationIssue(
                        "NEGATIVE_VOLUME",
                        "Volume must not be negative.",
                        index,
                    )
                )
            elif volume == 0 and zero_volume_policy != "allow":
                issues.append(
                    ValidationIssue(
                        "ZERO_VOLUME",
                        "Volume is zero.",
                        index,
                        "warning" if zero_volume_policy == "warning" else "error",
                    )
                )

        if row_numeric_valid:
            open_price = values["open"]
            high_price = values["high"]
            low_price = values["low"]
            close_price = values["close"]

            if low_price > high_price:
                issues.append(
                    ValidationIssue(
                        "INVALID_HIGH_LOW",
                        "Low price must not exceed high price.",
                        index,
                    )
                )

            if not low_price <= open_price <= high_price:
                issues.append(
                    ValidationIssue(
                        "OPEN_OUT_OF_RANGE",
                        "Open price must be between low and high.",
                        index,
                    )
                )

            if not low_price <= close_price <= high_price:
                issues.append(
                    ValidationIssue(
                        "CLOSE_OUT_OF_RANGE",
                        "Close price must be between low and high.",
                        index,
                    )
                )

    return tuple(issues)
