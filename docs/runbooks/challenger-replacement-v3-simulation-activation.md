# Replacement v3 simulation activation runbook

Release state: `V3_SIMULATION_ACTIVATION_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`.

Safety assertions before and after every step:

- `production_activation=false`
- `no service installed or started` before the installer step
- `no credentials`
- `no real orders`
- `no funds moved`
- System Paper is non-blocking
- no v0.79 activation-code release is required

## Separately authorized ceremony

The immutable v0.78.3 failed preflight and its bound candidate files, together
with the partial v0.78.5 installation evidence, remain evidence and must not be deleted
or overwritten. v0.78.6 uses only its release-scoped candidate paths;
it does not migrate, rename or chmod old evidence. Existing target-plist
recovery requires a separately approved protocol. Before a new ceremony, the old loaded
`local.crypto-quant.challenger-forward` service must be handled under its own
explicit approval; this runbook does not authorize that action.

1. Verify exact public `origin/main`, annotated `v0.78.6`, clean checkout,
   package `0.78.6`, manifest `1.78.0` and successful release CI. Replay the six
   vendored wheel/native-file SHA-256 values and versions frozen by the manifest
   and `requirements.lock`; no dependency installation or user-site import is
   permitted during the ceremony.
2. Run the fixed no-argument renderer once. Replay the exact snapshot, contract,
   plist, Python identity and empty event-root identity.
3. Run the fixed no-argument preflight only in its frozen four-hour window. It
   may make exactly three public Binance time GETs and must publish one current
   30-minute eligible receipt with all private authority counters zero.
4. Run the fixed installer once. Its only LaunchAgent sequence is
   `print -> bootstrap -> print`; do not use kickstart, start, enable, submit,
   bootout or a direct runtime invocation.
5. Preserve the install receipt and wait for the next natural scheduled
   opportunity. Do not force, backfill or substitute an opportunity.
6. Run the read-only observer. When the first exact natural successful evidence
   exists, publish and strictly replay the fixed start receipt. Its timestamp is
   the only start of the real continuous 72-hour qualification.

## Failure handling

Any identity, permission, clock, disk, network, service, event, transcript,
receipt or loader mismatch fails closed. A plist/bootstrap ambiguity is
`INSTALL_STATE_UNKNOWN_FAILED_CLOSED`: preserve the target and logs, perform no
unlink/chmod rollback, and do not report installation success. Multiple
simultaneously valid preflights are ambiguous and rejected; expired successes
remain immutable history, while an installed system always replays the exact
preflight named by its install receipt binding.
