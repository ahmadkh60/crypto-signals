from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings
from app.strategies.base import BarHistory, Signal
from app.strategies.breakout import detect_resistance_breakout
from app.strategies.indicators import calculate_atr


class SetupState(StrEnum):
    WAIT_BREAKOUT = "wait_breakout"
    WAIT_PULLBACK = "wait_pullback"
    WAIT_CONFIRMATION = "wait_confirmation"
    IN_POSITION = "in_position"


@dataclass
class SwingPullbackStrategy:
    settings: Settings

    def __post_init__(self):
        self.state = SetupState.WAIT_BREAKOUT
        self.resistance = None
        self.breakout_index = None
        self.pullback_index = None

    def _reset(self):
        self.state = SetupState.WAIT_BREAKOUT
        self.resistance = None
        self.breakout_index = None
        self.pullback_index = None

    def on_position_closed(self):
        self._reset()

    def on_bar(self, history: BarHistory) -> Signal:
        if self.state == SetupState.IN_POSITION:
            return Signal("hold", "position_open")

        highs = history["high"]
        lows = history["low"]
        closes = history["close"]

        atr_values = calculate_atr(
            highs,
            lows,
            closes,
            period=self.settings.atr_period,
        )
        atr = atr_values[-1]

        if atr is None:
            return Signal("hold", "insufficient_atr_history")

        index = history.index
        close = float(closes[index])
        high = float(highs[index])
        low = float(lows[index])

        if self.state == SetupState.WAIT_BREAKOUT:
            breakout = detect_resistance_breakout(
                history,
                lookback=self.settings.breakout_lookback,
            )
            if breakout is None:
                return Signal("hold", "waiting_for_breakout")

            self.resistance = breakout.resistance
            self.breakout_index = index
            self.state = SetupState.WAIT_PULLBACK
            return Signal("hold", "breakout_detected")

        if self.state == SetupState.WAIT_PULLBACK:
            age = index - self.breakout_index

            if age > self.settings.pullback_max_bars:
                self._reset()
                return Signal("hold", "pullback_expired")

            tolerance = atr * self.settings.pullback_atr_multiplier

            if close < self.resistance - tolerance:
                self._reset()
                return Signal("hold", "breakout_invalidated")

            zone_low = self.resistance - tolerance
            zone_high = self.resistance + tolerance

            if low <= zone_high and high >= zone_low:
                self.pullback_index = index
                self.state = SetupState.WAIT_CONFIRMATION
                return Signal("hold", "pullback_detected")

            return Signal("hold", "waiting_for_pullback")

        if self.state == SetupState.WAIT_CONFIRMATION:
            if close < self.resistance - atr * self.settings.pullback_atr_multiplier:
                self._reset()
                return Signal("hold", "pullback_invalidated")

            if index <= self.pullback_index:
                return Signal("hold", "waiting_for_confirmation")

            if close > float(highs[index - 1]):
                self.state = SetupState.IN_POSITION
                multiplier = self.settings.atr_stop_multiplier
                stop_distance = (
                    atr * multiplier if multiplier is not None else None
                )
                return Signal(
                    "long",
                    "swing_pullback_confirmed",
                    stop_distance=stop_distance,
                )

            return Signal("hold", "waiting_for_confirmation")

        self._reset()
        return Signal("hold", "invalid_state")
