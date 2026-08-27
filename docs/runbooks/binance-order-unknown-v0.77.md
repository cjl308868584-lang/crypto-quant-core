# Binance order UNKNOWN v0.77

Fail closed immediately: block new risk and retain the exact client order ID,
request identity and send-start evidence. Query only the allowlisted exact-ID
status and replay fills, fees, balances and positions. Never submit another
mutation while the economic order remains unresolved.

Reconcile and flatten only through a separately authorized safe path. Record
the incident and do not delete evidence. An UNKNOWN cannot be cleared by a
restart, a new timestamp, an assumed absence or an operator-selected result.
