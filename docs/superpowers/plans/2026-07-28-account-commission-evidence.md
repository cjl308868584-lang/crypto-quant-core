# Account Commission Evidence Implementation Plan

**Goal:** Capture replayable current ETHUSDT Spot and USDⓈ-M account
commission evidence using an IP-restricted, read-only Binance API key, without
adding order or Broker capability.

## Task 1: credential and permission boundary

1. Add strict owner/mode/type/size checks for credential files referenced only
   by fixed environment-variable names.
2. Add an opaque HMAC signer that never exposes secret, key or signature in
   repr, errors, logs, receipt or CLI output.
3. Freeze the API-restriction request and require read-only, IP-restricted,
   no-withdrawal/no-transfer/no-trading permissions.
4. Prove blocked permission scope makes zero commission requests.

## Task 2: signed GET transport

1. Reuse the v0.20 three-sample corrected server-time gate.
2. Freeze exact Spot and Futures commission requests for ETHUSDT.
3. Disable proxy, redirect, retries and arbitrary request overrides.
4. Persist redacted request transcripts and raw response receipts without API
   key, secret, signature or signed URL.

## Task 3: parsers and cost math

1. Strictly parse Spot standard/special/tax/discount components.
2. Compute maker/taker × buyer/seller no-discount account rates.
3. Keep eligible BNB-discount values as non-authoritative scenarios.
4. Parse USDⓈ-M maker/taker rates and compute two-taker-side costs.
5. Report exact per-1000-USDT costs and compare them with the frozen v0.18
   15-bps-per-side assumption.

## Task 4: Artifact and CLI

1. Add mirrored strict JSON Schema.
2. Rebuild permission, observations, cost math and quality from raw receipts.
3. Add self-hash and external attestation hash.
4. Publish mode-0600 Artifact immutably.
5. Expose only `--output-root`; reject key/secret/URL/header/proxy/time/order
   arguments.

## Task 5: release

1. Add signing vectors, mutation, permission, transport and CLI tests.
2. Do not run a real signed request unless compliant credential files already
   exist; never ask for secret values in chat.
3. Freeze explicit no-credential or safe failure evidence.
4. Add ADR-0022, v0.22 implementation status and README update.
5. Bump package/build versions and freeze all new inputs.
6. Run focused tests, full tests, compileall, Golden Vectors and validators.
7. Commit the isolated implementation, fast-forward main and tag v0.22.0.
