from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from numbers import Real

WALLEX_FIELDS = ("t", "o", "h", "l", "c", "v")


class CandleParseError(ValueError):
    """Raised when a raw Wallex response cannot be parsed."""


def parse_wallex_response(
    payload: Mapping[str, object],
) -> dict[str, list[object]]:
    """Convert a raw Wallex UDF history response into standard OHLCV columns."""
    if payload.get("s") != "ok":
        raise CandleParseError(
            f"Wallex response status is not ok: {payload.get('s')!r}"
        )

    missing = [field for field in WALLEX_FIELDS if field not in payload]
    if missing:
        raise CandleParseError(
            f"Missing Wallex response fields: {', '.join(missing)}"
        )

    arrays: dict[str, Sequence[object]] = {}

    for field in WALLEX_FIELDS:
        value = payload[field]

        if not isinstance(value, (list, tuple)):
            raise CandleParseError(f"Field {field!r} must be an array.")

        arrays[field] = value

    lengths = {field: len(values) for field, values in arrays.items()}

    if len(set(lengths.values())) != 1:
        raise CandleParseError(f"Wallex array lengths differ: {lengths}")

    if not arrays["t"]:
        raise CandleParseError("Wallex response contains no candles.")

    result: dict[str, list[object]] = {
        "timestamp": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }

    field_mapping = {
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
    }

    previous_timestamp: int | None = None

    for index, raw_timestamp in enumerate(arrays["t"]):
        if (
            isinstance(raw_timestamp, bool)
            or not isinstance(raw_timestamp, Real)
            or not float(raw_timestamp).is_integer()
        ):
            raise CandleParseError(
                f"Invalid Unix timestamp at row {index}."
            )

        timestamp_value = int(raw_timestamp)

        if previous_timestamp is not None and timestamp_value <= previous_timestamp:
            raise CandleParseError(
                f"Timestamps are not strictly increasing at row {index}."
            )

        try:
            timestamp = datetime.fromtimestamp(timestamp_value, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise CandleParseError(
                f"Timestamp out of range at row {index}."
            ) from exc

        result["timestamp"].append(timestamp)
        previous_timestamp = timestamp_value

        for source_field, target_field in field_mapping.items():
            raw_value = arrays[source_field][index]

            if isinstance(raw_value, bool):
                raise CandleParseError(
                    f"Boolean value in {source_field!r} at row {index}."
                )

            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise CandleParseError(
                    f"Invalid numeric value in {source_field!r} at row {index}."
                ) from exc

            if not isfinite(numeric_value):
                raise CandleParseError(
                    f"Non-finite value in {source_field!r} at row {index}."
                )

            result[target_field].append(numeric_value)

    return result
