# ADR-001: Stop-Loss Execution Contract

- Status: ACCEPTED
- Date: 2026-11-20
- Scope: Current backtesting engine (Swing Pullback)
- Execution mode: Historical simulation only

## 1. Context

The backtesting engine uses ATR-based stop distances for risk-based
position sizing. Stop execution must have deterministic semantics so
that planned risk and realized trade outcomes can be interpreted
correctly.

The current MVP uses candle-close confirmation and next-candle-open
execution. It does not simulate resting intrabar stop orders.

## 2. Decision

The following rules define stop-loss behavior in the current MVP:

1. A stop is triggered when a candle closes at or below the position's
   stop price (`close <= stop_price`).

2. Intrabar Low crossing the stop price does not trigger a stop if that
   candle closes above the stop price.

3. Once triggered, the position is closed at the next candle's Open.

4. A triggered stop remains active for the next candle even if that
   candle opens above the stop price. The position is still closed at
   that Open; the trigger is not cancelled.

5. If a stop trigger and a strategy exit occur on the same candle,
   stop-loss takes precedence.

6. The actual realized loss may exceed the planned stop risk when the
   next candle opens beyond the stop price. The difference depends on
   the gap between the stop-triggering close and the next candle's Open.
   No fixed maximum overshoot is assumed.

## 3. Explicitly Out of Scope

- Intrabar stop execution based on candle High/Low.
- Guaranteed execution at the stop price.
- Take-profit logic.
- Short positions.
- Live trading or exchange order execution.

Intrabar stop behavior may be considered in a separate future ADR.

## 4. Consequences

- `planned_risk` is an estimate based on the configured stop distance
  and assumed execution costs; it is not a guaranteed maximum loss.
- Backtest reports must distinguish planned risk from realized PnL.
- Stop exits must be identifiable separately from strategy exits.
- Tests must cover the trigger condition, execution timing, gap behavior,
  and stop priority.

## 5. Required Tests

- Stop triggers on close and executes at the next candle Open.
- A close above the stop does not trigger a stop.
- Intrabar Low below the stop is ignored when the close is above it.
- A triggered stop executes even when the next Open is above the stop.
- Stop-loss takes precedence over a simultaneous strategy exit.
