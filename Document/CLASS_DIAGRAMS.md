# BỘ SƠ ĐỒ LỚP CHI TIẾT HỆ THỐNG BLOCKCHAIN LAYER 1
## Tendermint BFT Consensus Engine & Discrete Event Simulation (DES)

Tài liệu này cung cấp đầy đủ và chính xác 100% các sơ đồ lớp (UML Class Diagrams) của hệ thống Blockchain Layer 1 theo cấu trúc mã nguồn trong thư mục `Workspace/src/`. Hệ thống được thiết kế theo mô hình hướng đối tượng kết hợp kiến trúc hướng sự kiện (Event-Driven Architecture) với 4 cụm sơ đồ chính:

1. **Sơ đồ Data Models & Cryptography (`src/common.py`)**
2. **Sơ đồ Consensus Engine & Byzantine Fault Injection (`src/node.py`, `src/byzantine.py`)**
3. **Sơ đồ Network Simulation & State Machine Execution (`src/sim.py`, `src/execution.py`)**
4. **Sơ đồ Kiến trúc Tổng thể Hệ thống 5 Lớp (System Architecture)**

---

## 1. SƠ ĐỒ DATA MODELS & CRYPTOGRAPHY (`src/common.py`)

Cụm mô hình dữ liệu định nghĩa các thực thể cốt lõi bất biến (Immutable Data Transfer Objects - `@dataclass(frozen=True)`), đảm bảo tính toàn vẹn thông qua chữ ký số Ed25519 và phân tách miền (Domain Separation).

```mermaid
classDiagram
    direction TB

    class KeyPair {
        +Ed25519PrivateKey sk
        +bytes pk
        +__init__(seed: bytes)
    }

    class Tx {
        +str sender
        +int nonce
        +str key
        +str value
        +bytes sig
        +int height
        +body() list
    }

    class Header {
        +int height
        +int round
        +int pol_round
        +bytes parent
        +bytes state_hash
        +bytes tx_root
        +str proposer
        +bytes sig
        +body() list
    }

    class Block {
        +Header header
        +tuple txs
        +hash() bytes
    }

    class Vote {
        +str kind
        +int height
        +int round
        +bytes block_hash
        +str voter
        +bytes sig
        +body() list
    }

    class CommitCertificate {
        +int height
        +int round
        +bytes block_hash
        +dict signatures
    }

    class SyncReq {
        +str requester
        +int from_height
        +int to_height
        +int height
    }

    class SyncResp {
        +str responder
        +tuple chain_data
        +int height
    }

    class CryptoUtils {
        <<module common.py>>
        +encode(o) bytes
        +H(data: bytes) bytes
        +sign(kp: KeyPair, domain: str, body: list) bytes
        +verify(pk: bytes, domain: str, body: list, sig: bytes) bool
        +tx_root(txs: tuple) bytes
    }

    Block *-- Header : chứa (1-to-1)
    Block o-- Tx : chứa tập giao dịch (0-to-n)
    CommitCertificate ..> Vote : tổng hợp >= 2f+1 chữ ký PRECOMMIT
    CommitCertificate ..> Block : tham chiếu block_hash
    SyncResp o-- Block : chứa các block đồng bộ
    SyncResp o-- CommitCertificate : chứa chứng chỉ cam kết chốt
    CryptoUtils ..> KeyPair : ký và xác thực
    CryptoUtils ..> Tx : tính Merkle tx_root và verify
    CryptoUtils ..> Header : verify chữ ký proposer
    CryptoUtils ..> Vote : verify chữ ký voter
```

### Đặc điểm thiết kế & Tính đúng đắn của Data Models:
- **`Block.hash()`**: Chỉ băm các trường nội dung cốt lõi `[height, parent, state_hash, tx_root]`. Không băm `round`, `pol_round`, `proposer` để đảm bảo cùng một nội dung khối khi đề xuất lại ở các round sau vẫn giữ nguyên mã định danh `block_hash`.
- **`Domain Separation`**:
  - `Tx.sig`: Ký với miền `"TX:" + chain_id`.
  - `Header.sig`: Ký với miền `"HEADER:" + chain_id`.
  - `Vote.sig`: Ký với miền `"VOTE:" + chain_id`.
  - Chống tuyệt đối tấn công giả mạo hoặc phát lại chéo ngữ cảnh (Cross-protocol Replay).
- **`CommitCertificate`**: Gom tối thiểu $Q = 2f + 1$ chữ ký `PRECOMMIT` hợp lệ. Đóng vai trò là bằng chứng mật mã (Finality Proof) cho giao thức bắt kịp dữ liệu (`Catch-up Sync`).

---

## 2. SƠ ĐỒ CONSENSUS ENGINE & BYZANTINE FAULT INJECTION (`src/node.py`, `src/byzantine.py`)

Cụm đồng thuận cài đặt cỗ máy trạng thái Tendermint BFT với 7 quy tắc vàng. Cây phân cấp Byzantine kế thừa toàn diện từ `Node` nhằm kiểm thử khả năng chịu lỗi và an toàn mạng.

```mermaid
classDiagram
    direction TB

    class Node {
        +int idx
        +str name
        +dict ctx
        +KeyPair kp
        +Net net
        +int Q
        +int max_ahead
        +int max_round
        +State state
        +list ledger
        +dict certificates
        +list mempool
        +set seen_tx_hashes
        +bool done
        +int height
        +int round
        +str step
        +dict signed
        +tuple locked
        +dict proposals
        +dict blocks
        +dict checked
        +set scheduled
        +dict peer_round
        +dict votes
        +dict future
        +dict future_blocks
        +dict bodies
        +list future_headers
        +dict pending_headers
        +set requested_bodies
        +bool is_byzantine
        +__init__(idx: int, ctx: dict, kp: KeyPair)
        +log(ev: str, **kw)
        +last_hash() bytes
        +proposer(h: int, r: int) str
        +in_window(h: int, r: int) bool
        +start()
        +start_height(h: int)
        +start_round(r: int)
        +timeout_len(r: int) int
        +set_timeout(kind: str, mult: int)
        +skip_target() int
        +maybe_skip_round()
        +polka(h: int, r: int, bh: bytes) bool
        +best_polka() tuple
        +propose()
        +make_block() Block
        +seal(txs: tuple, state_hash: bytes, pol_round: int) Header
        +send_proposal(blk: Block)
        +make_vote(kind: str, target: bytes) Vote
        +send_vote(v: Vote)
        +on_message(msg: tuple, src: int)
        +on_tx(tx: Tx)
        +request_sync()
        +on_sync_request(req: SyncReq)
        +send_to(dst: int, msg: tuple)
        +on_sync_response(resp: SyncResp)
        +keep_first(book: dict, b: Block) bool
        +on_header(hd: Header, src: int)
        +on_request_body(block_hash: bytes, src: int)
        +on_body(payload: tuple)
        +on_proposal(b: Block)
        +on_vote(v: Vote)
        +check_block(b: Block) tuple
        +_check(b: Block) tuple
        +prevote_target(b: Block) bytes
        +cast(kind: str, target: bytes)
        +run()
        +on_timeout(key: tuple)
        +finalize(b: Block, cert: CommitCertificate)
    }

    class ByzantineBase {
        +bool is_byzantine
        +int attack_height
        +int attack_round
        +list groups
        +list evidence
        +configure(height: int, round: int, groups: list)
        +_check_groups(groups: list)
        +active() bool
        +sign_header(hd: Header) bytes
        +build_block(txs: tuple) Block
        +first_valid_tx() Tx
        +send_to(dst: any, msg: any)
        +send_to_many(msg: tuple, dsts: list)
        +send_vote(vote: Vote, dsts: list)
        +send_proposal(block: Block, dsts: list)
    }

    class Silent {
        +str mode
        +configure(mode: str, **base)
        +start()
        +propose()
        +on_message(msg: tuple, src: int)
        +on_timeout(key: tuple)
    }

    class EquivocateVoter {
        +tuple targets
        +tuple phases
        +configure(targets: tuple, phases: tuple, **base)
        +cast(kind: str, target: bytes)
    }

    class EquivocateProposer {
        +propose()
    }

    class InvalidBlock {
        +str mode
        +configure(mode: str, **base)
        +propose()
    }

    class Replay {
        +tuple kinds
        +int delay
        +int limit
        +list recorded
        +configure(kinds: tuple, delay: int, limit: int, **base)
        +msg_height(msg: tuple) int
        +on_message(msg: tuple, src: int)
        +on_timeout(key: tuple)
    }

    class Coalition {
        +list left
        +list right
        +__init__(left: list, right: list)
    }

    class ForkCoalition {
        +Coalition coalition
        +configure(coalition: Coalition, **base)
        +start()
        +on_timeout(key: tuple)
        +on_message(msg: tuple, src: int)
    }

    Node <|-- ByzantineBase : kế thừa trực tiếp
    ByzantineBase <|-- Silent : Proposer sập / im lặng (T6)
    ByzantineBase <|-- EquivocateVoter : Bỏ phiếu 2 mặt (T7)
    ByzantineBase <|-- EquivocateProposer : Đề xuất 2 khối mâu thuẫn (T7)
    ByzantineBase <|-- InvalidBlock : Khối lỗi chữ ký/root/state (T3)
    ByzantineBase <|-- Replay : Phát lại thông điệp (T2)
    ByzantineBase <|-- ForkCoalition : Tấn công liên minh ranh giới Quorum
    ForkCoalition o-- Coalition : điều phối phân vùng
```

### Các quy tắc Tendermint được hiện thực trong `Node`:
1. **Rule 1 & 2 (Không ký 2 phiếu)**: `signed[(h, r, kind)]` đảm bảo mỗi validator chỉ ký duy nhất 1 lần cho mỗi giai đoạn.
2. **Rule 3 (Thẩm định khối toàn diện)**: Hàm `_check(b)` kiểm tra chữ ký proposer, hash khối cha `b.header.parent == self.last_hash()`, Merkle root `tx_root`, và tính hợp lệ của mọi transaction.
3. **Rule 4 (Khóa khối - Lock Rule)**: Khi quan sát thấy $\ge Q$ phiếu `PREVOTE` cho một block $B \neq \text{NIL}$, node lập tức khóa vào block đó (`self.locked = (B, round)`).
4. **Rule 5 (Mở khóa / Đổi mục tiêu - Unlock Rule)**: Node bị khóa ở block $A$ chỉ được phép prevote cho block $B \neq A$ nếu thấy Polka ($\ge Q$ prevote cho $B$) ở một vòng `pol_round > self.locked[1]`.
5. **Rule 6 (Đúng ngữ cảnh)**: Loại bỏ các thông điệp ngoài cửa sổ trượt `in_window(h, r)` hoặc sai `chain_id`.
6. **Rule 7 (Chống đếm 2 lần & Phát hiện Equivocation)**: Bỏ qua phiếu bầu lặp lại từ cùng một validator; ghi nhận log `EQUIVOCATION` nếu nhận được 2 phiếu mâu thuẫn trong cùng slot.

---

## 3. SƠ ĐỒ NETWORK SIMULATION & EXECUTION (`src/sim.py`, `src/execution.py`)

Cụm mô phỏng mạng biến cố rời rạc (DES) điều phối thời gian ảo, mô phỏng mạng bán đồng bộ (GST, rớt gói, trễ tin, đảo thứ tự, DoS Rate Limiting), kết hợp với Máy trạng thái ứng dụng Key-Value Copy-on-Write.

```mermaid
classDiagram
    direction TB

    class Net {
        +Random rng
        +int n
        +int delta
        +int gst
        +int pre_gst_max_delay
        +float pre_gst_drop_probability
        +float duplicate_probability
        +float pre_gst_reorder_probability
        +dict rate_limit
        +dict peer_block
        +list peers
        +dict link_delays
        +list q
        +int seq
        +int now
        +list nodes
        +list logs
        +dict block_heights
        +dict send_times
        +dict receive_times
        +dict blocked_peers
        +__init__(cfg: dict)
        +log(node: str, ev: str, **kw)
        +_node_name(idx: int) str
        +push(t: int, kind: str, *args)
        +_message_height(msg: tuple) int
        +broadcast(src: int, msg: tuple)
        +send(src: int, dst: int, msg: tuple)
        +_reserve_send_time(src: int, dst: int) int
        +_transmit(src: int, dst: int, msg: tuple)
        +_delivery_delay(src: int, dst: int, before_gst: bool) int
        +_receive(src: int, dst: int, msg: tuple)
        +set_timeout(idx: int, delay: int, key: tuple)
        +run(t_end: int)
    }

    class State {
        +dict data
        +dict nonces
        +__init__()
        +copy() State
        +hash() bytes
    }

    class Executor {
        <<module execution.py>>
        +apply_tx(state: State, tx: Tx, chain_id: str, acct_pks: dict) str
        +apply_txs(state: State, txs: tuple, chain_id: str, acct_pks: dict) tuple
    }

    Net o-- Node : quản lý danh sách validator (n nodes)
    Node --> Net : phát thông điệp và lập lịch timeout
    Node *-- State : sở hữu máy trạng thái ứng dụng
    Node ..> Executor : thực thi kiểm tra block (apply_txs)
    Executor ..> State : cập nhật data & nonces (Copy-on-Write)
```

### Đặc tính nổi bật của Tầng Mô phỏng & Thực thi:
- **Đồng hồ ảo (`now`) & Priority Queue (`heapq`)**: Mạng vận hành bằng biến cố rời rạc không dùng `sleep()`, đảm bảo mô phỏng siêu nhanh và tất định 100% (T8).
- **Mô hình Bán đồng bộ (Partial Synchrony)**:
  - Trước $GST$: Rớt gói ngẫu nhiên (`pre_gst_drop_probability`), trễ lớn (`pre_gst_max_delay`), đảo thứ tự tin (`pre_gst_reorder_probability`).
  - Sau $GST$: Giao vận tin cậy với cận trễ cố định $\Delta$ (`delta`).
- **Phòng vệ DoS (Mục 6 đề bài)**:
  - `Outbound Rate Limiting`: Cửa sổ trượt hoãn gửi các gói vượt định mức `max_messages` qua sự kiện `SEND_READY`.
  - `Inbound Peer Blocking`: Chặn các peer spam dồn dập trong thời gian `duration`, tự động `UNBLOCK` sau đó.
- **Thực thi Nguyên tử (Atomic Execution)**: Hàm `apply_txs` sử dụng `state.copy()`. Bất kỳ lỗi nonce (`bad_nonce`), chữ ký (`bad_tx_sig`), hoặc phân quyền (`not_owner`) đều hủy toàn bộ thay đổi.

---

## 4. SƠ ĐỒ KIẾN TRÚC TỔNG THỂ HỆ THỐNG 5 LỚP (FULL ARCHITECTURE)

Sơ đồ thể hiện bức tranh toàn cảnh và mối quan hệ phụ thuộc giữa 5 tầng module:

```mermaid
classDiagram
    direction TB

    %% Tier 1: Điều phối & Runner
    namespace Tier1_Runner {
        class MainCLI {
            <<module main.py>>
            +run_sim(cfg: dict) Net
            +check_safety(nodes: list)
        }
    }

    %% Tier 2: Mạng mô phỏng biến cố
    namespace Tier2_Network_DES {
        class Net {
            +int now
            +list q
            +int delta
            +int gst
            +push(t, kind, *args)
            +broadcast(src, msg)
            +send(src, dst, msg)
            +run(t_end)
        }
    }

    %% Tier 3: Cỗ máy Đồng thuận BFT
    namespace Tier3_Consensus_Engine {
        class Node {
            +int height
            +int round
            +State state
            +list ledger
            +on_header(hd, src)
            +on_body(payload)
            +on_vote(v)
            +on_timeout(key)
            +finalize(b, cert)
        }
        class ByzantineBase {
            +bool is_byzantine
            +send_to(dst, msg)
            +send_vote(vote, dsts)
            +send_proposal(block, dsts)
        }
    }

    %% Tier 4: Máy trạng thái ứng dụng
    namespace Tier4_State_Execution {
        class State {
            +dict data
            +dict nonces
            +copy() State
            +hash() bytes
        }
        class Executor {
            <<module execution.py>>
            +apply_tx(state, tx, chain_id, acct_pks)
            +apply_txs(state, txs, chain_id, acct_pks)
        }
    }

    %% Tier 5: Mật mã & Dữ liệu
    namespace Tier5_Crypto_Models {
        class Block {
            +Header header
            +tuple txs
            +hash() bytes
        }
        class Header {
            +int height
            +int round
            +bytes state_hash
            +bytes tx_root
            +bytes sig
        }
        class Vote {
            +str kind
            +int height
            +int round
            +bytes block_hash
            +bytes sig
        }
        class Tx {
            +str sender
            +int nonce
            +str key
            +str value
            +bytes sig
        }
        class CommitCertificate {
            +int height
            +int round
            +bytes block_hash
            +dict signatures
        }
        class KeyPair {
            +Ed25519PrivateKey sk
            +bytes pk
        }
    }

    %% Mối liên kết giữa các tầng
    MainCLI ..> Net : khởi tạo & điều phối
    MainCLI ..> Node : khởi tạo n validators
    Net o-- Node : chứa các validator node
    Node --> Net : gọi send / broadcast / push
    Node <|-- ByzantineBase : mở rộng hành vi lỗi
    Node *-- State : duy trì trạng thái KV
    Node ..> Executor : áp dụng giao dịch
    Executor ..> State : cập nhật bản sao trạng thái
    Node o-- Block : lưu trữ trong ledger
    Node o-- CommitCertificate : lưu trữ theo height
    Node ..> Vote : ký và xử lý phiếu bầu
    Node ..> KeyPair : định danh mật mã Ed25519
    Block *-- Header : chứa tiêu đề
    Block o-- Tx : chứa giao dịch
    CommitCertificate ..> Block : bằng chứng tối hậu (2f+1 precommits)
```

---

## 5. BẢNG ĐỐI CHIẾU THIẾT KẾ ĐỐI VỚI 8 KỊCH BẢN KIỂM THỬ T1 - T8

| Mã Test | Kịch Bản Kiểm Thử | Các Lớp & Phương Thức Chính Tham Gia | Cơ Chế Bảo Đảm Tính Đúng Đắn |
| :---: | :--- | :--- | :--- |
| **T1** | **Normal Run (No Faults)** | `Node.start_height()`, `Node.propose()`, `Node.on_vote()`, `Node.finalize()` | 8 node hoàn thành 5 block tại Round 0; cùng `state_hash` cuối cùng. |
| **T2** | **Duplicate & Reordered** | `Net._transmit()`, `Node.on_vote()`, `Node.seen_tx_hashes`, `byzantine.Replay` | **Rule 7** bỏ qua phiếu lặp lại; mempool deduplicate $O(1)$; không đếm 2 lần. |
| **T3** | **Invalid Signatures** | `common.verify()`, `byzantine.InvalidBlock`, `execution.apply_tx()` | Ghi log `bad_header_sig`, `bad_vote_sig`, `bad_tx_sig`; từ chối ngay ở cổng vào. |
| **T4** | **Replay Tx Nonce** | `execution.apply_tx()`, `Node.mempool`, `Node.seen_tx_hashes` | Chốt chặn `tx.nonce == current_nonce + 1`; từ chối phát lại với mã `bad_nonce`. |
| **T5** | **Pre-GST Drops & Delays** | `Net.run()`, `Net._delivery_delay()`, `Node.on_timeout()`, `Node.locked` | **Rule 4 & 5 (Lock & Unlock)** giữ vững Safety: không bao giờ phân nhánh khối. |
| **T6** | **Silent Proposer** | `byzantine.Silent`, `Node.on_timeout("PROPOSE")`, `Node.start_round()` | Hết giờ chờ đề xuất, validator bỏ phiếu `NIL`, tăng round và chốt khối ở Round 1. |
| **T7** | **Byzantine Equivocation** | `byzantine.EquivocateVoter`, `byzantine.EquivocateProposer`, `Node.Q` | Định lý giao điểm Quorum ($2f + 1$ với $n \ge 3f + 1$) ngăn chặn 2 khối chốt ở cùng height. |
| **T8** | **Determinism** | `Net.rng`, `Net.push()`, `common.encode()`, `State.hash()` | Cùng seed PRNG và cơ chế mã hóa tất định tạo log và state hash trùng khớp từng byte. |

