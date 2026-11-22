from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from app.backtest.config import BacktestConfig
from app.market_data.segments import CandleSegment, split_candle_segments
from app.strategies.base import BarHistory, Signal, Strategy


QUANTITY = 1.0


@dataclass(frozen=True)
class Trade:
    entry_index: int
    exit_index: int
    quantity: float
    entry_price: float
    exit_price: float
    entry_fee: float
    exit_fee: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    exit_reason: str
    stop_price: float | None = None
    capital_before: float | None = None
    risk_budget: float | None = None
    planned_risk: float | None = None
    capital_after: float | None = None
    target_price: float | None = None


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    initial_capital: float | None = None
    ending_capital: float | None = None

    @property
    def total_net_pnl(self) -> float:
        return sum(trade.net_pnl for trade in self.trades)

    @property
    def total_gross_pnl(self) -> float:
        return sum(trade.gross_pnl for trade in self.trades)

    @property
    def total_fees(self) -> float:
        return sum(
            trade.entry_fee + trade.exit_fee for trade in self.trades
        )

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital is not None and self.ending_capital is not None:
            if self.initial_capital == 0:
                return 0.0
            return (
                (self.ending_capital / self.initial_capital) - 1
            ) * 100

        denominator = sum(
            trade.entry_price * trade.quantity for trade in self.trades
        )
        if denominator == 0:
            return 0.0
        return self.total_net_pnl / denominator * 100


def run_backtest(
    candles: dict[str, list],
    strategy: Strategy,
    config: BacktestConfig,
    strategy_factory: Callable[[], Strategy] | None = None,
    *,
    initial_capital: float | None = None,
    risk_per_trade_pct: float | None = None,
    risk_max_portfolio_pct: float | None = None,
) -> BacktestResult:
    dynamic_sizing = initial_capital is not None

    if dynamic_sizing:
        if (
            isinstance(initial_capital, bool)
            or not isinstance(initial_capital, (int, float))
            or not isfinite(initial_capital)
            or initial_capital <= 0
        ):
            raise ValueError("initial_capital must be finite and positive")

        if (
            isinstance(risk_per_trade_pct, bool)
            or not isinstance(risk_per_trade_pct, (int, float))
            or not isfinite(risk_per_trade_pct)
            or not 0 < risk_per_trade_pct < 1
        ):
            raise ValueError("risk_per_trade_pct must be between 0 and 1")

        if risk_max_portfolio_pct is None:
            risk_max_portfolio_pct = risk_per_trade_pct

        if (
            isinstance(risk_max_portfolio_pct, bool)
            or not isinstance(risk_max_portfolio_pct, (int, float))
            or not isfinite(risk_max_portfolio_pct)
            or not 0 < risk_max_portfolio_pct < 1
        ):
            raise ValueError("risk_max_portfolio_pct must be between 0 and 1")

        if risk_per_trade_pct > risk_max_portfolio_pct:
            raise ValueError(
                "risk_per_trade_pct cannot exceed risk_max_portfolio_pct"
            )
    elif risk_per_trade_pct is not None or risk_max_portfolio_pct is not None:
        raise ValueError("initial_capital is required for dynamic sizing")

    if "open" not in candles or "close" not in candles:
        raise ValueError("candles must contain open and close")

    lengths = {len(values) for values in candles.values()}
    if len(lengths) != 1:
        raise ValueError("all candle columns must have equal lengths")

    count = len(candles["open"])
    if count == 0:
        return BacktestResult(
            trades=(),
            initial_capital=initial_capital,
            ending_capital=initial_capital,
        )

    for column in ("open", "close"):
        for value in candles[column]:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(
                    f"{column} values must be finite and positive"
                )

    if "timestamp" in candles:
        segments = split_candle_segments(candles)
    else:
        segments = [
            CandleSegment(
                start_index=0,
                end_index=count,
                candles=candles,
            )
        ]

    if len(segments) > 1 and strategy_factory is None:
        raise ValueError(
            "strategy_factory is required when candles contain multiple segments"
        )

    trades = []
    position = None
    pending_stop_distance = None
    equity = float(initial_capital) if dynamic_sizing else None

    def close_position(index, raw_price, reason):
        nonlocal position, equity

        exit_price = raw_price * (1 - config.slippage_rate)
        quantity = position["quantity"]
        exit_notional = exit_price * quantity
        exit_fee = exit_notional * config.commission_rate

        gross_pnl = (
            exit_price - position["entry_price"]
        ) * quantity

        net_pnl = (
            gross_pnl
            - position["entry_fee"]
            - exit_fee
        )

        return_pct = (
            net_pnl
            / (position["entry_price"] * quantity)
            * 100
        )

        capital_after = None
        if dynamic_sizing:
            equity += net_pnl
            capital_after = equity

        trades.append(
            Trade(
                entry_index=position["entry_index"],
                exit_index=index,
                quantity=quantity,
                entry_price=position["entry_price"],
                exit_price=exit_price,
                entry_fee=position["entry_fee"],
                exit_fee=exit_fee,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=return_pct,
                exit_reason=reason,
                stop_price=position["stop_price"],
                capital_before=position["capital_before"],
                risk_budget=position["risk_budget"],
                planned_risk=position["planned_risk"],
                capital_after=capital_after,
                target_price=position["target_price"],
            )
        )

        position = None

        on_position_closed = getattr(
            active_strategy, "on_position_closed", None
        )
        if callable(on_position_closed):
            on_position_closed()

    for segment in segments:
        active_strategy = (
            strategy_factory()
            if strategy_factory is not None
            else strategy
        )

        local_count = segment.count
        pending_action = None

        for local_index in range(local_count):
            global_index = segment.start_index + local_index
            segment_candles = segment.candles

            # Execute the previous candle's signal at this candle's open.
            if pending_action == "long" and position is None:
                entry_price = (
                    segment_candles["open"][local_index]
                    * (1 + config.slippage_rate)
                )

                stop_distance = pending_stop_distance
                stop_price = None
                quantity = QUANTITY
                capital_before = None
                risk_budget = None
                planned_risk = None

                if dynamic_sizing:
                    if stop_distance is None:
                        raise ValueError(
                            "dynamic sizing requires stop_distance on long signals"
                        )

                    stop_price = entry_price - stop_distance
                    if stop_price <= 0:
                        raise ValueError("stop price must be positive")

                    # Estimate the loss per unit if the stop is executed.
                    estimated_stop_exit = (
                        stop_price * (1 - config.slippage_rate)
                    )
                    entry_fee_per_unit = (
                        entry_price * config.commission_rate
                    )
                    exit_fee_per_unit = (
                        estimated_stop_exit * config.commission_rate
                    )
                    loss_per_unit = (
                        entry_price
                        - estimated_stop_exit
                        + entry_fee_per_unit
                        + exit_fee_per_unit
                    )

                    if not isfinite(loss_per_unit) or loss_per_unit <= 0:
                        raise ValueError("invalid estimated loss per unit")

                    capital_before = equity
                    risk_budget = equity * min(
                        risk_per_trade_pct,
                        risk_max_portfolio_pct,
                    )

                    quantity_by_risk = risk_budget / loss_per_unit

                    # Spot-only cash cap: include the entry commission.
                    quantity_by_cash = equity / (
                        entry_price * (1 + config.commission_rate)
                    )
                    quantity = min(quantity_by_risk, quantity_by_cash)
                    planned_risk = quantity * loss_per_unit

                    if not isfinite(quantity) or quantity <= 0:
                        raise ValueError("calculated position quantity is invalid")

                else:
                    if stop_distance is not None:
                        stop_price = entry_price - stop_distance
                        if stop_price <= 0:
                            raise ValueError("stop price must be positive")

                target_price = None
                if stop_distance is not None:
                    if config.take_profit_r_multiple is not None:
                        target_price = (
                            entry_price
                            + config.take_profit_r_multiple * stop_distance
                        )

                    if (
                        stop_price is None
                        or not stop_price < entry_price
                        or (
                            target_price is not None
                            and not entry_price < target_price
                        )
                    ):
                        raise ValueError(
                            "invalid long position price invariant: "
                            f"stop={stop_price} entry={entry_price} "
                            f"target={target_price}"
                        )

                entry_fee = (
                    entry_price * quantity * config.commission_rate
                )

                position = {
                    "entry_index": global_index,
                    "entry_price": entry_price,
                    "entry_fee": entry_fee,
                    "quantity": quantity,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "capital_before": capital_before,
                    "risk_budget": risk_budget,
                    "planned_risk": planned_risk,
                }

            elif pending_action in ("exit", "stop_loss", "take_profit_2r") and position is not None:
                close_position(
                    global_index,
                    segment_candles["open"][local_index],
                    pending_action if pending_action in ("stop_loss", "take_profit_2r") else "strategy_exit",
                )

            pending_action = None
            pending_stop_distance = None

            # Do not generate a signal on the segment's final candle.
            if local_index == local_count - 1:
                if position is not None:
                    close_position(
                        global_index,
                        segment_candles["close"][local_index],
                        "end_of_segment",
                    )
                break

            history = BarHistory.from_candles(
                segment_candles,
                local_index,
            )
            signal = active_strategy.on_bar(history)

            if not isinstance(signal, Signal):
                raise TypeError("strategy.on_bar must return Signal")

            if signal.action not in ("long", "exit", "hold"):
                raise ValueError("unsupported signal action")

            if signal.stop_distance is not None:
                if (
                    signal.action != "long"
                    or isinstance(signal.stop_distance, bool)
                    or not isinstance(signal.stop_distance, (int, float))
                    or not isfinite(signal.stop_distance)
                    or signal.stop_distance <= 0
                ):
                    raise ValueError("invalid stop_distance")

            if position is None and signal.action == "long":
                pending_action = "long"
                pending_stop_distance = signal.stop_distance

            elif position is not None and signal.action == "exit":
                pending_action = "exit"

            if (
                position is not None
                and position["stop_price"] is not None
                and float(segment_candles["close"][local_index])
                <= position["stop_price"]
            ):
                pending_action = "stop_loss"
            elif (
                position is not None
                and position["target_price"] is not None
                and float(segment_candles["close"][local_index])
                >= position["target_price"]
            ):
                pending_action = "take_profit_2r"

    return BacktestResult(
        trades=tuple(trades),
        initial_capital=float(initial_capital) if dynamic_sizing else None,
        ending_capital=equity,
    )
