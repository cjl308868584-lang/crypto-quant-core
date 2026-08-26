# ADR 0076: Public simulation and research bundle

## Status

Accepted for the v0.76 code release. This decision freezes a credential-free
public-market simulation, replacement-v3 candidate deployment contract,
operational qualification, final 90-day evaluator, tail-blind operations
projection, and deterministic offline fault campaign. It does not activate any
runtime or grant account authority.

## Decision

The append-only canonical DecisionOpportunity event log remains the sole fact
source. Public capture is restricted to frozen credential-free GET requests.
Simulation outputs, operational qualification, economic evaluation, and
operations views are replayed derivatives. The evaluator reads the exact
`[start, tail)` economic window and uses the tail observation only as the
terminal mark; it cannot expose interim outcomes.

The reviewed executable core is the 75-path identity rooted at code checkpoint
`1cfddb9a6455416903f4e967ca5d4eb036f01409`, with aggregate SHA-256
`1483cc08fde2e39ff46ddf5f9bca4a799410ebb7866341a7226556d4dc6075dc`.
The exact deployment artifact SHA-256 is
`28eec0ee5f424952ee96e0c711abc68d7d1cab592859515ba8f79958971d288b`.
Adding that artifact produces the 76-path runtime core
`e9d148aab3bfa7376873650b37d827d3612d507acf07b9f10088ec0e5aadf329`.
The single 36-case offline campaign receipt SHA-256 is
`98c900ca8cba6afb8c79c06be2487baa52ea6d2a113dbcffc5d9bb961bf96226`;
all cases report `passed=true`.

An earlier local, unpublished freeze attempt serialized a trailing LF that the
strict fixed-source loaders reject. It was invalidated before release and is
not evidence; the hashes above bind the corrected no-trailing-LF canonical
bytes and their one replacement campaign.

These results prove deterministic offline conformance against frozen fixtures.
They do not prove live availability, real execution quality, profitability, or
an AI advantage. A future v0.77 private-account boundary remains independent.

## No-authority boundary

`PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED`

`CODE_COMPLETE_NOT_ACTIVATED_NOT_YET_REACHED`

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`credentials_allowed=false`

`account_requests_allowed=false`

`real_orders_allowed=false`

`fund_movement_allowed=false`

`production_state_writes=0`

`economic_outcome_reads=0`

`no 72-hour timer started`

`no 90-day timer started`

`no profitability or AI-advantage conclusion`
