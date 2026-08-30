# Task 2 report — v0.78.5 release freeze

## RED / GREEN

RED command:

```bash
PYTHONPATH=src python3 -m unittest -v tests.test_challenger_replacement_v0785_release
```

On the v0.78.4 baseline it ran 2 tests and failed both as intended: the
manifest inventory lacked the v0.78.5 release evidence and
`crypto_quant.__version__` was `0.78.4`, not `0.78.5`.

GREEN command:

```bash
PYTHONPATH=src python3 -m unittest -v \
  tests.test_challenger_replacement_v0785_release \
  tests.test_challenger_replacement_v3_activation_trust \
  tests.test_challenger_replacement_v3_activation_preflight \
  tests.test_challenger_replacement_v3_activation_install \
  tests.test_challenger_replacement_v3_activation_start \
  tests.test_challenger_replacement_v0784_release \
  tests.test_challenger_replacement_v0783_release \
  tests.test_estimators
```

Result: 57 tests passed in 12.635s.

## Release freeze

- Package identity: `0.78.5` in `pyproject.toml`, `setup.py`, and
  `crypto_quant.__version__`.
- Manifest identity: `1.77.0`; deterministic refresh produced build-input tree
  hash `7677df3c6de63c49f3d3c125192f6003bd148c9f9184e1a3af68d615a9acecf5`
  and manifest hash
  `cbbe055170871dfec94ace324e18b811b315670541233bc5b712937c76432f3e`.
- Trust, preflight, installer, schema mirrors and all intentionally
  current-version assertions now bind `v0.78.5` / `1.77.0`.
- `EvaluatorBuild` inventories the new ADR, implementation status and release
  test. The existing v0.78 activation runbook remains in the frozen inventory
  and is asserted by the new release test.
- Added ADR-0083 and the v0.78.5 status document. Both record the observed
  v0.78.4 contract-path conflict and forbid deleting, overwriting, moving,
  renaming or chmodding v0.78.3 evidence.

## Verification

- Schema-mirror `cmp` checks: both release-schema pairs matched exactly.
- `python3 -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- Placeholder scan of the new ADR/status/test: no `TODO`, `TBD`, `FIXME`, or
  `XXX` marker.
- Diff authority/scope scan: no added private execution, credential, Broker,
  order, fund, launchctl, kickstart or bootstrap operation. The only changed
  authority values remain explicit false/zero safeguards.
- `make validate`: command exited successfully. Its release-gate validator
  deliberately reports `result=FAIL` for the frozen design baseline:
  required policy bindings are absent and `PRODUCTION_ACTIVATION_DISABLED` is
  present. Governance templates remain `TEMPLATE_UNAPPROVED`, while the
  evaluator build validates at `1.77.0` and all seven release artifact schemas
  validate. This is the repository's documented safe semantic result, not a
  command failure.

### Final full suite

Exactly one `make test` invocation was started. It ran
`PYTHONPATH=src python3 -m unittest discover -s tests -v`; the process remained
CPU-active for about 27 minutes and exited naturally. A read-only collection
afterward reports 2,635 test cases. The executor returned at its 30-second
yield boundary without preserving the detached process's final stdout or exit
status, so a pass/fail count cannot be honestly asserted from this task's
captured evidence. No second full-suite run was made, to preserve the explicit
one-final-suite constraint.

## Files changed

Release metadata, activation identities and schema mirrors; deterministic build
manifest refresh and inventory; current-version release assertions; README and
activation runbook; new ADR-0083, v0.78.5 implementation status, and v0.78.5
release gate test. No renderer, preflight, installer, service, runtime,
production-root, account, credential, Broker, order or fund action was run.

## Self-review and concerns

Self-review found and corrected one over-broad historical-test replacement:
the v0.78.4 status test again reads the immutable v0.78.4 status document,
while its intentionally current release-identity assertions track v0.78.5.
The release test uses literal v0.78.5 path endings and checks real manifest
inventory plus each schema mirror.

Concern: final full-suite output/exit status was lost by the executor's
detached 30-second yield. Focused/adjacent evidence is green, but this report
does not claim a full-suite pass without that output. External release steps,
including independent review, push, PR/CI, merge/tag, renderer, preflight,
installer and runtime ceremony, remain deliberately unperformed.
