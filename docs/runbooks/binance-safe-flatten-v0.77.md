# Binance safe flatten v0.77

Fail closed and reject all risk-increasing intent. First replay the canonical
event chain and query the exact client IDs; reconcile venue position, fills,
fees, funding, balance and the confirmed protective stop. Never guess quantity
or cancel protection before a reconciled replacement or flat state exists.

Use only reduce-only close authority bound by the exact activation. Verify flat
Spot and perpetual positions, zero economic open orders and stop cleanup, then
append the immutable reconciliation. Do not delete evidence. A failed block
remains failed after flatness and needs a separate incident unlock.
