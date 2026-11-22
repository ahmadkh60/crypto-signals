from dataclasses import dataclass

from app.strategies.base import BarHistory


@dataclass(frozen=True)
class ResistanceBreakout:
    index: int
    resistance: float
    breakout_close: float


def detect_resistance_breakout(
    history: BarHistory,
    lookback: int = 20,
) -> ResistanceBreakout | None:
    if lookback <= 0:
        raise ValueError("lookback must be positive")

    highs = history["high"]
    closes = history["close"]

    if len(highs) != len(closes):
        raise ValueError("high and close lengths do not match")

    if history.index < lookback:
        return None

    start = history.index - lookback
    previous_highs = highs[start:history.index]
    resistance = max(previous_highs)
    current_close = closes[history.index]

    if current_close <= resistance:
        return None

    return ResistanceBreakout(
        index=history.index,
        resistance=resistance,
        breakout_close=current_close,
    )
