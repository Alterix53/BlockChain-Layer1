# Project: Lab 01 Blockchain Layer 1 Minimal (Tendermint BFT & DES)

## Architecture
- **Consensus Engine (`src/node.py`, `src/byzantine.py`)**: Tendermint BFT finite state machine implementing 7 golden rules (Proposal, Prevote, Precommit, Commit, Round timeout, 2-step block propagation with Header and Body, Locking and ValidRound rules).
- **Discrete Event Simulation (`src/sim.py`)**: Event queue with virtual time `now`, priority queue by timestamp, network delays, packet drops, rate limiting, and Global Stabilization Time (GST).
- **Cryptography & Data Models (`src/crypto.py`, `src/models.py`)**: Ed25519 digital signatures, canonical CBOR encoding, strict domain separation prefixes (`TX:`, `HEADER:`, `VOTE:`), SHA-256 state hashing and Merkle root calculation.
- **Application & State (`src/app.py`, `src/mempool.py`, `src/executor.py`)**: State key-value store, account nonce tracking (`tx.nonce == current_nonce + 1`), mempool deduplication and replay protection.
- **Logging & Determinism (`src/logger.py`, `src/main.py`)**: Structured key-value event logs (`t=... ev=...`), deterministic sorting and tie-breaking, seed-based reproducibility.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | M0_CoreFixes | Fix `sim.py` Net.push signature, `byzantine.py` send_to signature, `node.py` liveness requested_bodies stall | M0 | Survey (Explorer 2 & 3) |
| 2 | T1_Normal | Normal run, 4+ nodes, no faults, 5 blocks finalized at round 0, identical state hash | M1 | Lab 01 Spec §9 |
| 3 | T2_DuplicateReorder | Network duplicates/reorders messages, Rule 7 prevents double voting, no forks | M2 | Lab 01 Spec §9 |
| 4 | T3_InvalidSignatures | Reject invalid signatures / wrong domain tags with logs `bad_header_sig`, `bad_vote_sig`, `bad_tx_sig` | M3 | Lab 01 Spec §9 |
| 5 | T4_ReplayTxNonce | Reject duplicate/replayed transactions with `bad_nonce`, execute at most once | M4 | Lab 01 Spec §9 |
| 6 | T5_DropDelayGST | Drops and delays before GST, absolute safety preserved (no conflicting blocks at same height) | M5 | Lab 01 Spec §9 |
| 7 | T6_SilentProposer | Proposer crashes/silent at round 0, timeout propose triggers, round advances, V2 commits block (liveness) | M6 | Lab 01 Spec §9 |
| 8 | T7_ByzantineEquivocation | Up to f Byzantine equivocate, Quorum Intersection Theorem prevents double finalization | M7 | Lab 01 Spec §9 |
| 9 | T8_Determinism | Same seed rerun twice produces byte-for-byte identical logs and equal state hash | M8 | Lab 01 Spec §9 |
| 10 | M_LifecycleIntegration | Full automated lifecycle: Code -> Review -> Final -> Tối ưu hoá, 100% pytest green | M9 | ORIGINAL_REQUEST |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Core Engine & Interface Fixes | Sửa lỗi `sim.py`, `byzantine.py`, `node.py` liveness bug | none | IN_PROGRESS |
| M1 | T1-T8 Test Suite Implementation | Xây dựng/chuẩn hóa đầy đủ 8 test scenarios T1-T8 trong `Workspace/tests/` | M0 | PLANNED |
| M2 | Review Stage | 2 Reviewers độc lập đánh giá tính đúng đắn, adherence đặc tả Section 9 | M1 | PLANNED |
| M3 | Final Stage (Adversarial & T8) | 2 Challengers kiểm chứng tính tất định T8 và tấn công kiểm thử biên | M2 | PLANNED |
| M4 | Tối ưu hoá & Integrity Audit | Worker tối ưu mã nguồn/log, Forensic Auditor kiểm chứng tính chân thực (Clean) | M3 | PLANNED |

## Interface Contracts
### `Net.push` (`src/sim.py`)
- Signature: `def push(self, t, kind, src, dst=None, payload=None)`
- Tương thích ngược: Cho phép gọi 4 tham số `push(t, kind, dst, payload)` (với `src=None` hoặc node gửi tương ứng) và 5 tham số `push(t, kind, src, dst, payload)`.
- Hành vi: Lập lịch sự kiện tại thời điểm `t` với nhãn `kind` và nội dung `payload`.

### `ByzantineBase.send_to` (`src/byzantine.py`)
- Signature: `def send_to(self, dst, msg)` (nhất quán tuyệt đối với `Node.send_to(self, dst, msg)` trong `node.py`).
- Cung cấp thêm phương thức bổ trợ nếu gửi nhiều node: `def send_to_many(self, msg, dsts)` hoặc nhận diện kiểu dữ liệu tham số để không văng ngoại lệ `TypeError`.

### `Node.on_header` & Proposal Recovery (`src/node.py`)
- Khi nhận `HEADER` cho block đã có trong `self.blocks[block_hash]`, tự động kích hoạt `self.on_proposal(self.blocks[block_hash])` cho round tương ứng, không bị chặn bởi `self.requested_bodies`.
- Giải phóng hoặc quản lý `requested_bodies` theo round/height để không gây stall liveness khi round tăng lên.

### Log Error Codes (`src/logger.py`, `src/node.py`, `src/app.py`)
- Header signature invalid: ghi log `bad_header_sig`
- Vote signature invalid: ghi log `bad_vote_sig`
- Transaction signature invalid: ghi log `bad_tx_sig`
- Nonce invalid / replay: ghi log `bad_nonce`

## Code Layout
```
Workspace/
├── src/
│   ├── app.py           # Application state store & execution
│   ├── byzantine.py     # Byzantine behaviors (Silent, Equivocate, InvalidBlock)
│   ├── crypto.py        # Ed25519 signatures, keys, domain separation tags
│   ├── executor.py      # Transaction batch executor
│   ├── logger.py        # Structured deterministic logger
│   ├── main.py          # Entry point CLI & run_sim driver
│   ├── mempool.py       # Transaction pool & nonce deduplication
│   ├── models.py        # Block, Header, Vote, Tx, CommitCertificate data classes
│   ├── node.py          # Tendermint BFT consensus engine & state machine
│   └── sim.py           # Discrete Event Simulator & Net
└── tests/
    ├── c_helpers.py     # Common test fixtures, signers, cert verifiers
    ├── e2e/
    │   ├── test_sync_catchup.py
    │   ├── test_t1_normal.py          # [M1] New T1 scenario
    │   ├── test_t2_duplicate_reorder.py # [M1] Dedicated T2 scenario
    │   ├── test_t4_replay_tx.py       # [M1] Fixed T4 scenario
    │   ├── test_t5_gst_safety.py      # [M1] Dedicated T5 scenario
    │   ├── test_t6_silent_proposer.py # [M1] Dedicated T6 scenario
    │   ├── test_t7_equivocation.py    # [M1] Dedicated T7 scenario
    │   └── test_t8_determinism.py     # [M1] New T8 scenario
    ├── test_byzantine.py              # [M0] Fixed Byzantine tests
    ├── test_quorum_boundary.py        # [M0] Fixed PartitionNet push calls
    ├── test_sim.py                    # DES network tests
    ├── test_t3.py                     # [M0/M1] Fixed T3 signatures & error logs
    └── unit/                          # Component unit tests
```
