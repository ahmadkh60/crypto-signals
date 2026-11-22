from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

HOUR_SECONDS = 3600
FOUR_HOURS_SECONDS = 4 * HOUR_SECONDS


class ResamplingError(ValueError):
    """Raised when hourly candles cannot be safely resampled."""


@dataclass(frozen=True)
class ResamplingResult:
    candles: dict[str, list[object]]
    complete_groups: int
    incomplete_groups: int
    discarded_hourly_candles: int


def resample_1h_to_4h(
    candles: Mapping[str, Sequence[object]],
) -> ResamplingResult:
    """Aggregate complete UTC-aligned groups of four hourly candles."""
    missing = [column for column in REQUIRED_COLUMNS if column not in candles]
    if missing:
        raise ResamplingError(f"Missing columns: {missing}")

    lengths = {len(candles[column]) for column in REQUIRED_COLUMNS}
    if len(lengths) != 1:
        raise ResamplingError("OHLCV column lengths do not match.")

    count = len(candles["timestamp"])
    if count == 0:
        raise ResamplingError("No hourly candles supplied.")

    groups: dict[int, dict[int, tuple[float, float, float, float, float]]]
    groups = defaultdict(dict)

    previous_timestamp: int | None = None

    for index, raw_timestamp in enumerate(candles["timestamp"]):
        if not isinstance(raw_timestamp, datetime):
            raise ResamplingError(f"Invalid timestamp at row {index}.")

        if raw_timestamp.tzinfo is None or raw_timestamp.utcoffset() != timedelta(0):
            raise ResamplingError(f"Timestamp is not UTC at row {index}.")

        if (
            raw_timestamp.minute != 0
            or raw_timestamp.second != 0
            or raw_timestamp.microsecond != 0
        ):
            raise ResamplingError(f"Timestamp is not hour-aligned at row {index}.")

        timestamp = int(raw_timestamp.timestamp())

        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ResamplingError(
                f"Timestamps are not strictly increasing at row {index}."
            )

        previous_timestamp = timestamp

        values = []

        for column in REQUIRED_COLUMNS[1:]:
            raw_value = candles[column][index]

            if isinstance(raw_value, bool):
                raise ResamplingError(
                    f"Invalid {column} value at row {index}."
                )

            try:
                value = float(raw_value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ResamplingError(
                    f"Invalid {column} value at row {index}."
                ) from exc

            if not isfinite(value):
                raise ResamplingError(
                    f"Non-finite {column} value at row {index}."
                )

            values.append(value)

        bucket = timestamp - timestamp % FOUR_HOURS_SECONDS
        groups[bucket][timestamp] = tuple(values)

    result: dict[str, list[object]] = {
        column: [] for column in REQUIRED_COLUMNS
    }

    complete_groups = 0
    incomplete_groups = 0
    discarded_hourly_candles = 0

    for bucket, hourly in sorted(groups.items()):
        expected = [
            bucket + offset * HOUR_SECONDS
            for offset in range(4)
        ]

        if any(timestamp not in hourly for timestamp in expected):
            incomplete_groups += 1
            discarded_hourly_candles += len(hourly)
            continue

        rows = [hourly[timestamp] for timestamp in expected]

        result["timestamp"].append(
            datetime.fromtimestamp(bucket, tz=UTC)
        )
        result["open"].append(rows[0][0])
        result["high"].append(max(row[1] for row in rows))
        result["low"].append(min(row[2] for row in rows))
        result["close"].append(rows[-1][3])
        result["volume"].append(sum(row[4] for row in rows))

        complete_groups += 1

    return ResamplingResult(
        candles=result,
        complete_groups=complete_groups,
        incomplete_groups=incomplete_groups,
        discarded_hourly_candles=discarded_hourly_candles,
    )
