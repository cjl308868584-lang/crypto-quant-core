# Binance secret incident v0.77

Fail closed: disable private transport outside the running process, revoke the
affected venue credential through the owner account and block every activation
bound to its fingerprint. Do not print, copy, commit or inspect secret bytes.

Preserve secret-free hashes, timestamps and authorization evidence; do not
delete evidence. Re-issue only an owner-only, withdrawal-disabled, IP-allowlisted
least-privilege credential after incident review. A new credential never grants
order, funding or Canary authority by itself.
