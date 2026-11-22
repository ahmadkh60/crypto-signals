from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.market_data.candles import parse_wallex_response
from app.market_data.quality_gate import (
    QualityGateConfig,
    run_quality_gate,
)
from app.market_data.validation import ValidationIssue
from app.market_data.wallex import fetch_history


@dataclass(frozen=True)
class MarketDataResult:
    symbol: str
    candles: dict[str, list[object]]
    issues: tuple[ValidationIssue, ...]

    @property
    def accepted(self) -> bool:
        return not any(
            issue.severity == "error"
            for issue in self.issues
        )


def fetch_and_validate(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    quality_config: QualityGateConfig,
    settings: Settings | None = None,
) -> MarketDataResult:
    """Fetch, parse, and quality-check market candles."""
    payload = fetch_history(
        symbol=symbol,
        resolution=resolution,
        start=start,
        end=end,
        settings=settings,
    )

    candles = parse_wallex_response(payload)

    issues = run_quality_gate(
        candles,
        quality_config,
    )

    return MarketDataResult(
        symbol=symbol,
        candles=candles,
        issues=issues,
    )
