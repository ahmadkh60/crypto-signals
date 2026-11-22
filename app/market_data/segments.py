from dataclasses import dataclass
from datetime import timedelta
from typing import Any


@dataclass(frozen=True)
class CandleSegment:
    start_index: int
    end_index: int
    candles: dict[str, list[Any]]

    @property
    def count(self) -> int:
        return self.end_index - self.start_index


def split_candle_segments(
    candles: dict[str, list[Any]],
    expected_interval: timedelta = timedelta(hours=4),
) -> list[CandleSegment]:
    if expected_interval.total_seconds() <= 0:
        raise ValueError("expected_interval must be positive")

    if "timestamp" not in candles:
        raise ValueError("Missing timestamp column")

    timestamps = candles["timestamp"]
    if not timestamps:
        return []

    lengths = {len(values) for values in candles.values()}
    if len(lengths) != 1:
        raise ValueError("Candle columns must have equal lengths")

    starts = [0]

    for index in range(1, len(timestamps)):
        delta = timestamps[index] - timestamps[index - 1]

        if delta <= timedelta(0):
            raise ValueError("Timestamps must be strictly increasing")

        if delta != expected_interval:
            starts.append(index)

    ends = starts[1:] + [len(timestamps)]

    return [
        CandleSegment(
            start_index=start,
            end_index=end,
            candles={
                column: values[start:end]
                for column, values in candles.items()
            },
        )
        for start, end in zip(starts, ends)
    ]
