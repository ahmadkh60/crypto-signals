from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.market_data.candles import (
    CandleParseError,
    parse_wallex_response,
)

REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

DEFAULT_START = datetime(2023, 3, 20, 20, 30, tzinfo=UTC)
DEFAULT_END = datetime(2026, 3, 20, 20, 30, tzinfo=UTC)


class ArchiveError(ValueError):
    """Raised when the raw archive cannot be loaded safely."""


@dataclass(frozen=True)
class ArchiveResult:
    symbol: str
    candles: dict[str, list[object]]
    files_loaded: int
    duplicate_candles: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _read_manifest(path: Path) -> list[dict[str, object]]:
    records = []

    if not path.is_file():
        raise ArchiveError(f"Manifest not found: {path}")

    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ArchiveError(
                    f"Invalid manifest JSON at line {line_number}."
                ) from exc

            if not isinstance(record, dict):
                raise ArchiveError(
                    f"Manifest record at line {line_number} is not an object."
                )

            records.append(record)

    return records


def load_wallex_archive(
    symbol: str,
    root: Path = Path("data/raw/wallex"),
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
) -> ArchiveResult:
    """Load, verify, merge, and filter archived Wallex hourly candles."""
    if symbol not in {"BTCTMN", "ETHTMN"}:
        raise ArchiveError(f"Unsupported symbol: {symbol}")

    if start.tzinfo is None or end.tzinfo is None:
        raise ArchiveError("Start and end must be timezone-aware.")

    start = start.astimezone(UTC)
    end = end.astimezone(UTC)

    if start >= end:
        raise ArchiveError("Start must be earlier than end.")

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    manifest = _read_manifest(root / "manifest.jsonl")

    selected = [
        record
        for record in manifest
        if record.get("symbol") == symbol
        and record.get("status") == "ok"
        and isinstance(record.get("from"), int)
        and isinstance(record.get("to"), int)
        and record["from"] < end_ts
        and record["to"] >= start_ts
    ]

    if not selected:
        raise ArchiveError(f"No manifest entries found for {symbol}.")

    merged: dict[int, tuple[float, float, float, float, float]] = {}
    loaded = 0
    duplicates = 0

    for record in selected:
        relative_path = record.get("path")
        expected_hash = record.get("sha256")

        if not isinstance(relative_path, str):
            raise ArchiveError("Manifest contains an invalid file path.")

        if not isinstance(expected_hash, str):
            raise ArchiveError("Manifest contains an invalid SHA-256.")

        path = Path.cwd() / relative_path

        if not path.is_file() or path.suffix != ".json":
            raise ArchiveError(f"Archive file missing or invalid: {path}")

        if _sha256(path) != expected_hash:
            raise ArchiveError(f"SHA-256 mismatch: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            candles = parse_wallex_response(payload)
        except (json.JSONDecodeError, CandleParseError) as exc:
            raise ArchiveError(f"Invalid archive file: {path}") from exc

        loaded += 1

        for index, timestamp in enumerate(candles["timestamp"]):
            timestamp_value = int(timestamp.timestamp())

            values = tuple(
                float(candles[column][index])
                for column in REQUIRED_COLUMNS[1:]
            )

            previous = merged.get(timestamp_value)

            if previous is not None:
                if previous != values:
                    raise ArchiveError(
                        f"Conflicting overlapping candle at {timestamp}."
                    )

                duplicates += 1
                continue

            merged[timestamp_value] = values

    filtered = [
        (timestamp, values)
        for timestamp, values in sorted(merged.items())
        if start_ts <= timestamp < end_ts
    ]

    if not filtered:
        raise ArchiveError(f"No candles found in requested range for {symbol}.")

    result: dict[str, list[object]] = {
        column: [] for column in REQUIRED_COLUMNS
    }

    for timestamp, values in filtered:
        result["timestamp"].append(
            datetime.fromtimestamp(timestamp, tz=UTC)
        )

        for column, value in zip(REQUIRED_COLUMNS[1:], values):
            result[column].append(value)

    return ArchiveResult(
        symbol=symbol,
        candles=result,
        files_loaded=loaded,
        duplicate_candles=duplicates,
    )
