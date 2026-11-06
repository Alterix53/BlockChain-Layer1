# Test acceptance gate

From the submission root (the folder containing `src/` and `tests/`), run the single entry point:

```powershell
python -X utf8 -B -m unittest discover -s tests -v
```

Run one group from the submission root (the folder containing `src/` and `tests/`) (use `-t .` to keep package imports consistent):

```powershell
python -X utf8 -B -m unittest discover -s tests/unit -t . -v
python -X utf8 -B -m unittest discover -s tests/integration -t . -v
python -X utf8 -B -m unittest discover -s tests/e2e -t . -v
python -X utf8 -B -m unittest discover -s tests/regression -t . -v
```

This uses standard-library unittest and the simulator's cryptography dependency. It includes T1–T8, unit tests, deterministic regressions, CLI subprocess tests and the mutation gate. CLI tests write only into automatically cleaned temporary directories; `-B` avoids bytecode artifacts.

## Save event logs for each test

From the submission root (the folder containing `src/` and `tests/`), run the same suite with the optional logging runner:

```powershell
python -X utf8 -B -m tests -v
```

Each invocation creates `logs/tests/run-<unique>/`. Open `summary.json`
to map complete test IDs and outcomes to their individual `.log` files. The runner
prints both paths when it finishes. Use `--log-dir <directory>` to change the parent
directory, or select a single test by its unittest ID:

```powershell
python -X utf8 -B -m tests -v tests.e2e.test_t1_normal
```

Event files observe the real simulator and unit-test logger without replacing their
behavior. A `network=N` prefix distinguishes simulator instances within one test,
including repeated T8 runs. CLI subprocess logs and captured output are copied
before temporary files are removed. Failures include their original traceback;
tests without network activity still have an outcome record. Mutation tests can
contain deliberately faulty events: their PASS means the designated assertion
detected the mutant, not that every recorded simulation succeeded.

The standard unittest command above remains available without persistent event
logs. Generated files under `logs/` are ignored by Git. Logging itself has regression
tests for preserving event collections, assertion failures, fixture errors, CLI
exit codes and the result index.

## Independent checks

`independent_oracle.py` computes canonical bytes, SHA-256 commitments, transaction replay and Ed25519 verification independently of production `encode`, `hash`, `verify`, execution and safety-check functions. It checks every honest node's ledger, parent links, transaction ownership/nonces, state, proposer and finality certificate. Explicit expected application data is also required in transaction-admission and sparse-topology scenarios.

Do not use production output as the expected answer without a separate contract or known input/output. All-honest convergence alone can accept the same wrong result on every node.

## Organization

- `unit/`: executor, network transport with dummy nodes, Byzantine behavior with
  RecordingNet, T3 signature/domain guards, sync handlers, safety helpers and
  event-logging/result handling. No full consensus simulation or CLI subprocesses.
- `integration/test_event_logging_cli.py`: CLI subprocess logging and the logged
  test runner's result index.
- `e2e/`: T1–T8, Byzantine attack scenarios, consensus over faulty networks,
  catch-up and quorum-boundary experiments using real simulations.
- `regression/test_consensus.py`: vote, lock, proof and BODY regressions.
- `regression/test_network.py`: partition, routing, limits and isolation regressions.
- `regression/test_cli.py`: configuration and subprocess CLI regressions.
- `regression/test_review_fixes.py`: audit counterexamples for header-buffer starvation,
  malformed sync, cached-block finality and future relay reservations.
- `regression/fixtures.py`: shared regression inputs, without production expected-value logic.
- `test_mutation_gate.py`: seven in-memory mutation gates.
- `independent_oracle.py`: separate expected-value implementation.

Tests are grouped by scope; `regression/` keeps the existing bug-prevention
contracts together and may contain component, integration and full-network cases.
Shared helpers stay at the `tests/` level, and regression-only fixtures stay in
`regression/fixtures.py`. Import shared helpers through `tests.c_helpers`.

T3 is split into `unit/test_t3_signatures.py` and
`e2e/test_t3_invalid_signatures.py`. Byzantine tests are split into
`unit/test_byzantine.py` and `e2e/test_byzantine_scenarios.py`. Transport tests are
in `unit/test_sim.py`; full consensus/network cases are in
`e2e/test_consensus_network.py`. Sync handler tests are in
`unit/test_sync_request.py`, while catch-up scenarios stay in `e2e/test_sync_catchup.py`.

Run the quorum experiment report from the submission root (the folder containing `src/` and `tests/`):

```powershell
python -X utf8 -B -m tests.e2e.test_quorum_boundary --report
```

## Fault schedules

- T1 explicitly uses GST=0, bounded nonzero delay, no Byzantine, no drop/duplicate/reorder
  and no throttling pressure. It asserts the absence of fault/timeout events and keeps
  the exact chain/state/nonce and round-zero checks, including certificate rounds.
- Every T8 scenario requires both runs to finish on all expected honest nodes, checks
  state/data/nonces and ledger agreement using the independent oracle, and compares
  serialized UTF-8 log bytes. Negative controls reject identical incomplete runs and
  errors on V9 even when V0 and the logs remain unchanged.

- T4 starts with empty mempools and seen sets, sends the first valid transaction through `Net.send`, observes dissemination, and replays before and after commit.
- Byzantine E2E scenarios use the production JSON factory. They do not replace `src.main.Node`.
- Isolation and partition fixtures intercept `_transmit`, including unicast traffic in both directions; they retain the production transport pipeline and log the injected loss/delay.
- Selective pre-GST PREVOTE loss leaves one honest node locked. Three Byzantine validators then withhold messages; authenticated POLKA evidence must restore honest progress.
- Focused cases cover late quorum without signing twice, round 1001, poisoned/missing bodies, sync header/certificate/body order, isolated certificate dictionaries, global post-GST delivery bounds including routed traffic under outbound pressure, bootstrap deduplication, config/namespace guards, incomplete CLI runs and independent-process determinism.

## Mutation semantics

The initial five audit regression methods failed against f089931 before the fixes,
including malformed-sync exceptions. A sixth case checks current-header admission
under future-round pressure while preserving proven headers. These cases require
honest completion, logged rejection with continued execution, authenticated exactly-once
sync, every actual SEND window and the global delivery bound. Existing assertions
and the seven mutation gates were not relaxed.

`test_mutation_gate.py` applies and restores seven in-memory patches: disabled transaction admission/gossip, bypassed production Byzantine factory, invalid-signature acceptance, wrong-domain acceptance, nonce-guard bypass, duplicate-vote counting and state-root-check bypass. Each must fail its designated behavioral assertion. An unrelated exception or fixture crash does not count as a killed mutant.

Before accepting a change:

1. Run the whole entry point and require zero failures/errors.
2. Confirm the intended attack actually occurred in logs, then check safety and required post-GST progress separately.
3. Keep first admission and replay separate; never pre-seed the state under test.
4. Diagnose a failing assertion against Lab01.pdf before changing its expected result. A replacement mock must not remove the production path being tested.
5. Keep the independent oracle and mutation gate effective when adding protocol fields or changing interfaces.

These deterministic examples and representative mutants are regression evidence, not a proof covering every Byzantine strategy or an exhaustive mutation score. Round 1001 is a controlled boundary test, not a long randomized stress run. The specification is Lab01.pdf §§3,5–9; the lecture slides supply architectural context and do not automatically mandate RPC, WAL or a Merkle Patricia Trie.
