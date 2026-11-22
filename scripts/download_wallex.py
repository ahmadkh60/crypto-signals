from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.wallex.ir/v1/udf/history"
SYMBOLS = ("BTCTMN", "ETHTMN")
RESOLUTION = "60"
CHUNK_SECONDS = 72 * 3600
DELAY_SECONDS = 1.0

START = int(datetime(2023, 3, 20, tzinfo=UTC).timestamp())
END = int(datetime(2026, 3, 21, tzinfo=UTC).timestamp())

ROOT = Path("data/raw/wallex")
MANIFEST = ROOT / "manifest.jsonl"

FIELDS = ("t", "o", "h", "l", "c", "v")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unwrap(payload: object) -> dict:
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]

    if not isinstance(payload, dict):
        raise ValueError("Unexpected API response structure.")

    return payload


def validate(payload: dict) -> tuple[int, int, int]:
    status = payload.get("s")

    if status == "no_data":
        return 0, 0, 0

    if status != "ok":
        raise ValueError(f"Unexpected API status: {status}")

    for field in FIELDS:
        if not isinstance(payload.get(field), list):
            raise ValueError(f"Invalid or missing array: {field}")

    count = len(payload["t"])

    if count == 0:
        raise ValueError("Empty response with status ok.")

    for field in FIELDS[1:]:
        if len(payload[field]) != count:
            raise ValueError(f"Array length mismatch: {field}")

    timestamps = payload["t"]

    if any(type(ts) is not int for ts in timestamps):
        raise ValueError("Non-integer timestamp found.")

    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("Duplicate or unordered timestamps.")

    gaps = sum(
        1 for a, b in zip(timestamps, timestamps[1:])
        if b - a != 3600
    )

    return count, timestamps[0], gaps


def download(url: str) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "crypto-signals-wallex-archive/1.0"},
    )

    last_error = None

    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Download failed: {last_error}")


def load_manifest_paths() -> set[str]:
    paths: set[str] = set()

    if MANIFEST.exists():
        with MANIFEST.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    paths.add(json.loads(line)["path"])
                except (ValueError, KeyError):
                    raise RuntimeError("Invalid manifest entry.")

    return paths


def save_manifest(record: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    with MANIFEST.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=SYMBOLS, action="append")
    parser.add_argument("--start", type=int, help="Range start (Unix timestamp)")
    parser.add_argument("--end", type=int, help="Range end (Unix timestamp)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if (args.start is None) != (args.end is None):
        parser.error("--start and --end must be provided together.")

    range_start = START if args.start is None else args.start
    range_end = END if args.end is None else args.end

    if range_start >= range_end:
        parser.error("--start must be smaller than --end.")

    symbols = args.symbol or list(SYMBOLS)

    chunks = []
    current = range_start

    while current < range_end:
        chunk_end = min(current + CHUNK_SECONDS, range_end)
        chunks.append((current, chunk_end))
        current = chunk_end

    print(f"Symbols: {', '.join(symbols)}")
    print(f"Chunks per symbol: {len(chunks)}")
    print(f"Range: {range_start} -> {range_end}")
    print(f"Total requests: {len(chunks) * len(symbols)}")

    if args.dry_run:
        print("DRY RUN: no network requests or files written.")
        return

    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_paths = load_manifest_paths()

    for symbol in symbols:
        for index, (start, end) in enumerate(chunks, 1):
            directory = ROOT / symbol / "1h"
            directory.mkdir(parents=True, exist_ok=True)

            filename = f"{symbol}_1h_{start}_{end}.json"
            destination = directory / filename
            relative_path = str(destination)

            if destination.exists():
                raw = destination.read_bytes()
                payload = unwrap(json.loads(raw))
                count, first, gaps = validate(payload)
                digest = sha256(raw)

                if relative_path not in manifest_paths:
                    save_manifest({
                        "symbol": symbol,
                        "path": relative_path,
                        "sha256": digest,
                        "status": payload["s"],
                        "candles": count,
                        "first_timestamp": first,
                        "gaps": gaps,
                        "recovered_existing": True,
                    })
                    manifest_paths.add(relative_path)

                print(f"[{symbol} {index}/{len(chunks)}] EXISTS")
                continue

            query = urlencode({
                "symbol": symbol,
                "resolution": RESOLUTION,
                "from": start,
                "to": end,
            })

            url = f"{BASE_URL}?{query}"

            print(f"[{symbol} {index}/{len(chunks)}] Downloading...")

            raw = download(url)
            payload = unwrap(json.loads(raw))
            count, first, gaps = validate(payload)

            temporary = destination.with_suffix(".json.tmp")
            temporary.write_bytes(raw)
            temporary.replace(destination)

            digest = sha256(raw)

            save_manifest({
                "symbol": symbol,
                "path": relative_path,
                "from": start,
                "to": end,
                "downloaded_at": datetime.now(UTC).isoformat(),
                "sha256": digest,
                "status": payload["s"],
                "candles": count,
                "first_timestamp": first,
                "gaps": gaps,
            })

            manifest_paths.add(relative_path)

            print(
                f"  status={payload['s']} "
                f"candles={count} gaps={gaps} "
                f"sha256={digest[:16]}"
            )

            time.sleep(DELAY_SECONDS)

    print("Download process completed.")


if __name__ == "__main__":
    main()
