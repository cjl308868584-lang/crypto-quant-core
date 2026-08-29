# ADR 0082: v0.78.4 preflight hotfix

## Decision

Release a bounded `v0.78.4` patch for two defects observed during the exact
v0.78.3 installation preflight. First, parse the real UTF-8 output of
`pmset -g custom` by its `AC Power:` and `Battery Power:` sections, requiring
exactly one `sleep` setting with value `0` in every reported section. Aligned
whitespace is accepted; missing, duplicate, nonzero or malformed sleep values,
unknown section headers and invalid UTF-8 fail closed.

Second, truncate the preflight observation to an exact UTC second before any
receipt identity is built. Canonical receipt timestamps therefore retain the
existing millisecond form ending in `.000Z`; the schema and canonical JSON
rules are unchanged. Both eligible and failed receipts must pass the same
strict loader replay.

## Evidence and reason

The exact v0.78.3 ceremony published one immutable failed preflight receipt at
`2026-08-29T16:13:03.149Z`. The target Mac reported a safe aligned line
`sleep                0`, but the old implementation searched for the literal
bytes ` sleep 0`. The receipt then failed its own schema because the builder
preserved `.149Z` while the existing schema permits only `.000Z`.

That receipt and all v0.78.2/v0.78.3 snapshots remain immutable evidence.
The old `local.crypto-quant.challenger-forward` LaunchAgent is separately
loaded but not running; this patch does not unload, disable, delete or modify
it. Its disposition remains an external approval gate.

## Safety boundary

- `production_activation=false`
- no replacement service installed or started
- no credential created or read
- no private Binance request made
- no order submitted
- no funds moved

The patch does not execute renderer, preflight, installer, LaunchAgent or
start-receipt ceremony. A future ceremony must bind exact annotated v0.78.4
and separately resolve the old loaded LaunchAgent.
