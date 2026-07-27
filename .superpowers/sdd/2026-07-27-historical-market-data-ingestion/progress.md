# SDD ledger — plan: docs/superpowers/plans/2026-07-27-historical-market-data-ingestion.md

Baseline: f098ba0; 215 tests passed.
Task 1: fix round 1/5 (2 addressed, 1 open — verified-capability interface must be reconciled with the plan signature; commits 6e5ab18..4497648)
Task 1: fix round 2/5 (1 addressed, 0 open — explicit VerifiedArchive contract; commit baa19ea)
Task 1: complete (commits f098ba0..baa19ea, review clean)
Task 2: fix round 0 review (5 open — full Kline validation, Funding monthly coverage, coordinated-rehash lineage, strict family schemas, runtime/schema parity; commits baa19ea..cf40132)
Task 2: fix round 1/5 (3 addressed, 2 open — strict UTC/fact-family schema and complete runtime/schema parity; commit 79aa3f8)
Task 2: fix round 2/5 (2 addressed, 1 open — installed-wheel schema resources; commit 0252d9c)
Task 2: fix round 3/5 (1 addressed, 1 open — wheel smoke must be provably offline; commit 9df9e30)
Task 2: fix round 4/5 (1 addressed, 0 open — offline wheel smoke; commit 74eec21)
Task 2: complete (commits baa19ea..74eec21, review clean)
Task 3: fix round 0 review (5 open — disable proxies, checksum read cap, URL parse stability, dirfd/no-follow publishing, rollback after publish; commit 9b96b0a)
Task 3: fix round 1/5 (3 addressed, 3 open — all idempotent returns recheck attachment; no fallible post-commit work; early temp failures clean partial; commit 1b97501)
Task 3: fix round 2/5 (3 addressed, 1 open — initial temp fstat/nlink failure cleanup; commit e06ca1b)
Task 3: fix round 3/5 (1 addressed, 0 open — invalid initial temp inode cleanup; commit 86d7eca)
Task 3: complete (commits 74eec21..86d7eca, review clean)
Task 4: minor (deferred): wheel smoke mock filename still contains 0.15.0
Task 4: complete (commits 86d7eca..ca92b6f, review clean with 1 deferred minor)
Final review: repaired (1 Critical, 4 Important addressed — source-row replay and verified-archive construction; complete receipt/quality/fact/snapshot contracts including fact-level ingested_at; complete fee-tier contract with production unsupported; source-driven Funding schedule plus research-only degradation; final-name inode/bytes commit checks; implementation commit b09ff96)
Final review residual: repaired (1 additional load-bearing Important — receipt-only trust replaced by an external snapshot-attestation envelope/hash binding receipt_hash plus complete snapshot_hash and explicit schema/parser/identity/time; legacy receipt-only trust is insufficient; recorded_at and snapshot_id rewrite probes fail closed; CLI exposes the anchor before immutable publish; implementation commit cc2dc45)
Final verification: 75 focused and 291 full tests passed; offline wheel/schema 3 passed; evaluator manifest 1.11.0 build 2538bc3eec3a33a921cc7141d118bd4277eb9d703eeabeedf3d71d3267c8121f; Golden 41/41 passed
