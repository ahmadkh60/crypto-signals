import os
from dataclasses import dataclass, field
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Literal


def _read_env_file(path: str = ".env") -> dict[str, str]:
    result = {}
    env_path = Path(path)

    if not env_path.is_file():
        return result

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key:
            result[key] = value

    return result


def _parse_float(env: dict, key: str, default: float) -> float:
    try:
        value = float(env.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number") from None

    if not isfinite(value):
        raise ValueError(f"{key} must be finite")

    return value


def _parse_int(env: dict, key: str, default: int) -> int:
    try:
        value = int(env.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer") from None

    return value


def _parse_bool(env: dict, key: str, default: bool) -> bool:
    raw = str(env.get(key, str(default))).strip().lower()

    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False

    raise ValueError(f"{key} must be true or false")


@dataclass(frozen=True)
class Settings:
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    wallex_api_base_url: str = "https://api.wallex.ir"
    wallex_api_key: str | None = None
    wallex_request_timeout: float = 10.0

    symbols: list[str] = field(
        default_factory=lambda: ["BTCIRT", "ETHIRT"]
    )
    analysis_timeframe: str = "4h"
    trend_timeframe: str = "1d"

    initial_capital_toman: int = 10_000_000
    risk_per_trade_pct: float = 0.05
    risk_max_portfolio_pct: float = 0.05
    atr_period: int = 14
    atr_stop_multiplier: float | None = 2.0
    breakout_lookback: int = 20
    pullback_atr_multiplier: float = 0.5
    pullback_max_bars: int = 10

    qg_zero_volume_severity: Literal["warning", "error"] = "warning"
    qg_gap_tolerance_ratio: float = 0.0
    qg_allow_unclosed_last_bar: bool = True

    def __post_init__(self):
        if self.environment not in ("dev", "staging", "prod"):
            raise ValueError("environment must be dev, staging, or prod")

        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError("invalid log_level")

        if not isinstance(self.wallex_api_base_url, str) or not self.wallex_api_base_url.strip():
            raise ValueError("wallex_api_base_url must not be empty")

        if self.wallex_api_key is not None and not isinstance(self.wallex_api_key, str):
            raise ValueError("wallex_api_key must be a string or None")

        if not isfinite(self.wallex_request_timeout) or self.wallex_request_timeout <= 0:
            raise ValueError("wallex_request_timeout must be finite and > 0")

        if not self.symbols or any(
            not isinstance(item, str) or not item.strip()
            for item in self.symbols
        ):
            raise ValueError("symbols must contain non-empty strings")

        if (
            isinstance(self.initial_capital_toman, bool)
            or not isinstance(self.initial_capital_toman, int)
            or self.initial_capital_toman <= 0
        ):
            raise ValueError("initial_capital_toman must be a positive integer")

        if not 0 < self.risk_per_trade_pct < 1:
            raise ValueError("risk_per_trade_pct must be between 0 and 1")

        if not 0 < self.risk_max_portfolio_pct < 1:
            raise ValueError("risk_max_portfolio_pct must be between 0 and 1")

        if isinstance(self.atr_period, bool) or self.atr_period <= 0:
            raise ValueError("atr_period must be a positive integer")

        if self.atr_stop_multiplier is not None:
            if (
                not isfinite(self.atr_stop_multiplier)
                or self.atr_stop_multiplier <= 0
            ):
                raise ValueError("atr_stop_multiplier must be finite and > 0")

        if (
            isinstance(self.breakout_lookback, bool)
            or not isinstance(self.breakout_lookback, int)
            or self.breakout_lookback <= 0
        ):
            raise ValueError("breakout_lookback must be a positive integer")

        if (
            isinstance(self.pullback_atr_multiplier, bool)
            or not isinstance(self.pullback_atr_multiplier, (int, float))
            or not isfinite(self.pullback_atr_multiplier)
            or self.pullback_atr_multiplier <= 0
        ):
            raise ValueError("pullback_atr_multiplier must be finite and > 0")

        if (
            isinstance(self.pullback_max_bars, bool)
            or not isinstance(self.pullback_max_bars, int)
            or self.pullback_max_bars <= 0
        ):
            raise ValueError("pullback_max_bars must be a positive integer")

        if self.qg_zero_volume_severity not in ("warning", "error"):
            raise ValueError("qg_zero_volume_severity must be warning or error")

        if not isfinite(self.qg_gap_tolerance_ratio) or self.qg_gap_tolerance_ratio < 0:
            raise ValueError("qg_gap_tolerance_ratio must be finite and >= 0")

        if not isinstance(self.qg_allow_unclosed_last_bar, bool):
            raise ValueError("qg_allow_unclosed_last_bar must be boolean")

    @classmethod
    def from_env(cls) -> "Settings":
        env = _read_env_file()

        # متغیرهای واقعی سیستم بر مقادیر فایل .env اولویت دارند.
        env.update({key.lower(): value for key, value in os.environ.items()})

        symbols_raw = env.get("symbols", "BTCIRT,ETHIRT")
        symbols = [
            item.strip()
            for item in symbols_raw.split(",")
            if item.strip()
        ]

        multiplier_raw = env.get("atr_stop_multiplier", "").strip()

        return cls(
            environment=env.get("environment", "dev").lower(),
            log_level=env.get("log_level", "INFO").upper(),
            wallex_api_base_url=env.get(
                "wallex_api_base_url", "https://api.wallex.ir"
            ),
            wallex_api_key=env.get("wallex_api_key") or None,
            wallex_request_timeout=_parse_float(
                env, "wallex_request_timeout", 10.0
            ),
            symbols=symbols,
            analysis_timeframe=env.get("analysis_timeframe", "4h"),
            trend_timeframe=env.get("trend_timeframe", "1d"),
            initial_capital_toman=_parse_int(
                env, "initial_capital_toman", 10_000_000
            ),
            risk_per_trade_pct=_parse_float(
                env, "risk_per_trade_pct", 0.05
            ),
            risk_max_portfolio_pct=_parse_float(
                env, "risk_max_portfolio_pct", 0.05
            ),
            atr_period=_parse_int(env, "atr_period", 14),
            atr_stop_multiplier=(
                float(multiplier_raw) if multiplier_raw else 2.0
            ),
            breakout_lookback=_parse_int(env, "breakout_lookback", 20),
            pullback_atr_multiplier=_parse_float(
                env, "pullback_atr_multiplier", 0.5
            ),
            pullback_max_bars=_parse_int(env, "pullback_max_bars", 10),
            qg_zero_volume_severity=env.get(
                "qg_zero_volume_severity", "warning"
            ).lower(),
            qg_gap_tolerance_ratio=_parse_float(
                env, "qg_gap_tolerance_ratio", 0.0
            ),
            qg_allow_unclosed_last_bar=_parse_bool(
                env, "qg_allow_unclosed_last_bar", True
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
