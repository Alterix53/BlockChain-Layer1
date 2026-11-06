# Sơ đồ lớp — Blockchain Layer 1

Các sơ đồ đối chiếu với mã nguồn hiện tại trong `Workspace/src/` và các lớp mạng phục vụ E2E trong `Workspace/tests/e2e/`. Bộ sơ đồ 1–5 bao phủ 19 lớp cấp cao nhất của phần triển khai; mỗi sơ đồ chọn mức chi tiết theo mục đích đọc, không liệt kê toàn bộ phương thức nội bộ.

## Cách đọc và sử dụng

- `A <|-- B`: B kế thừa A.
- `A --> B`: A giữ tham chiếu tới B; nhãn cạnh ghi tên trường hoặc vai trò.
- `A o-- B`: A quản lý tập đối tượng B (aggregation).
- `A *-- B`: B là trạng thái riêng thuộc A (composition).
- `A ..> B`: A sử dụng B hoặc liên hệ qua dữ liệu, không nhất thiết giữ đối tượng B.
- `1`, `0..*`: số lượng đối tượng tại đầu quan hệ. Bội số phản ánh cấu trúc dữ liệu, không thay thế ràng buộc cấu hình của runner.
- `<<module>>` và `<<external>>` phân biệt module hàm và lớp thư viện ngoài với lớp của dự án.
- Dấu `+` biểu diễn khả năng truy cập trong Python; dấu gạch dưới ở tên phương thức giữ quy ước nội bộ của mã nguồn. Chữ ký được rút gọn, bỏ mặc định và một số `**kwargs`. Kiểu trả về được ghi khi hữu ích.

Xem trực tiếp các khối Mermaid trên trình xem Markdown hỗ trợ Mermaid, hoặc mở từng file `.mmd` trong [diagrams/](diagrams/). Với báo cáo ngắn, dùng sơ đồ **1** cho thiết kế tổng quan hoặc sơ đồ **6** cho phần testing; các sơ đồ chi tiết có thể đặt ở phụ lục.

## 1. Tổng quan các lớp chính

Nguồn: `Workspace/src/node.py`, `sim.py`, `execution.py`, `common.py`, `byzantine.py`.

Sơ đồ rút gọn phù hợp chèn vào phần thiết kế của báo cáo. Node giữ trạng thái riêng, tham chiếu mạng và lưu các block/chứng nhận đã chốt.

File riêng: [01-overview.mmd](diagrams/01-overview.mmd).

```mermaid
classDiagram
    direction TB
    class Net {
        +int now
        +list q
        +list nodes
        +send(src, dst, msg)
        +broadcast(src, msg)
        +run(t_end)
    }
    class Node {
        +str name
        +int height
        +int round
        +str step
        +list ledger
        +dict certificates
        +on_message(msg, src)
        +on_timeout(key)
        +finalize(b, cert)
    }
    class State {
        +dict data
        +dict nonces
        +copy() State
        +hash() bytes
    }
    class KeyPair {
        +Ed25519PrivateKey sk
        +bytes pk
    }
    class Block {
        +Header header
        +tuple txs
        +hash() bytes
    }
    class Header
    class Tx
    class Vote
    class CommitCertificate
    class ByzantineBase
    Net "1" o-- "0..*" Node : nodes
    Node --> "1" Net : net
    Node *-- "1" State : state
    Node --> "1" KeyPair : kp
    Node --> "0..*" Block : ledger and block buffers
    Node --> "0..*" CommitCertificate : certificates
    Node --> "0..*" Vote : votes
    Block "0..*" --> "1" Header : header
    Block "0..*" --> "0..*" Tx : txs
    CommitCertificate ..> Block : identifies by block_hash
    Node <|-- ByzantineBase
```

## 2. Mô hình dữ liệu và khóa mật mã

Nguồn: `Workspace/src/common.py`.

Bảy lớp dữ liệu dùng `@dataclass(frozen=True)`. Các trường dict bên trong vẫn có thể thay đổi; frozen không có nghĩa là bất biến sâu. `height` của Tx là property luôn trả về 0 để hỗ trợ log. Quan hệ với block qua hash là phụ thuộc, không phải tham chiếu trực tiếp tới đối tượng.

File riêng: [02-data-models.mmd](diagrams/02-data-models.mmd).

```mermaid
classDiagram
    direction TB
    class KeyPair {
        +Ed25519PrivateKey sk
        +bytes pk
        +__init__(seed)
    }
    class Tx {
        <<dataclass>>
        +str sender
        +int nonce
        +str key
        +str value
        +bytes sig
        +int height
        +body() list
    }
    class Header {
        <<dataclass>>
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
        <<dataclass>>
        +Header header
        +tuple txs
        +hash() bytes
    }
    class Vote {
        <<dataclass>>
        +str kind
        +int height
        +int round
        +bytes block_hash
        +str voter
        +bytes sig
        +body() list
    }
    class CommitCertificate {
        <<dataclass>>
        +int height
        +int round
        +bytes block_hash
        +dict signatures
    }
    class SyncReq {
        <<dataclass>>
        +str requester
        +int from_height
        +int to_height
        +int height
    }
    class SyncResp {
        <<dataclass>>
        +str responder
        +tuple chain_data
        +int height
    }
    Block "0..*" --> "1" Header : header
    Block "0..*" --> "0..*" Tx : ordered txs
    Vote ..> Block : block_hash or NIL
    CommitCertificate ..> Block : block_hash
    CommitCertificate ..> Vote : stores PRECOMMIT signatures
    SyncResp "0..*" --> "0..*" Block : chain_data pairs
    SyncResp "0..*" --> "0..*" CommitCertificate : chain_data pairs
    SyncReq ..> SyncResp : request and response
```

## 3. Validator và trạng thái đồng thuận

Nguồn: `Workspace/src/node.py`, `execution.py`, `common.py`.

Chọn các thuộc tính và phương thức chính, không liệt kê mọi helper. Mempool là list, context là dict và proof POLKA là tập Vote trong dict; không có lớp Mempool, Context hay PolkaCertificate riêng. `seal()` trả về Block, không phải Header.

File riêng: [03-consensus.mmd](diagrams/03-consensus.mmd).

```mermaid
classDiagram
    direction LR
    class Node {
        +int idx
        +str name
        +dict ctx
        +KeyPair kp
        +Net net
        +int Q
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
        +dict votes
        +dict proofs
        +dict sync_pending
        +dict pending_headers
        +set requested_bodies
        +__init__(idx, ctx, kp)
        +start()
        +start_height(h)
        +start_round(r)
        +proposer(h, r) str
        +propose()
        +make_block() Block
        +seal(txs, state_hash, pol_round) Block
        +send_proposal(blk)
        +make_vote(kind, target) Vote
        +cast(kind, target)
        +on_message(msg, src)
        +on_tx(tx, gossip)
        +on_header(hd, src)
        +on_request_body(block_hash, src)
        +on_body(payload)
        +on_proposal(b)
        +on_vote(v)
        +polka(h, r, bh) bool
        +polka_votes(h, r, bh) tuple
        +on_polka(votes)
        +check_block(b) tuple
        +prevote_target(b) bytes
        +request_sync()
        +on_sync_request(req)
        +certificate_error(cert, h, bh)
        +on_sync_headers(items, src)
        +on_sync_response(resp)
        +run()
        +on_timeout(key)
        +finalize(b, cert)
    }
    class State {
        +dict data
        +dict nonces
        +copy() State
        +hash() bytes
    }
    class Net
    class KeyPair
    class Block
    class Tx
    class Vote
    class Header
    class CommitCertificate
    class SyncReq
    class SyncResp
    Node *-- "1" State : current state
    Node --> "1" Net : sends and schedules
    Node --> "1" KeyPair : signing key
    Node --> "0..*" Block : ledger and proposals
    Node --> "0..*" Tx : mempool
    Node --> "0..*" Vote : votes and proofs
    Node --> "0..*" Header : pending headers
    Node --> "0..*" CommitCertificate : certificates and sync_pending
    Node ..> SyncReq : creates and handles
    Node ..> SyncResp : creates and handles
```

## 4. Cây kế thừa và phối hợp Byzantine

Nguồn: `Workspace/src/byzantine.py`.

Các phương thức trong lớp con là những hook được ghi đè hoặc bổ sung. ByzantineBase kế thừa `send_to()` từ Node. ForkCoalition phục vụ thí nghiệm quorum, dùng chung Coalition giữa nhiều node; không phải thành phần bắt buộc của mô phỏng chuẩn.

File riêng: [04-byzantine.mmd](diagrams/04-byzantine.mmd).

```mermaid
classDiagram
    direction TB
    class Node {
        +bool is_byzantine
        +send_to(dst, msg)
        +cast(kind, target)
        +propose()
        +on_message(msg, src)
        +on_timeout(key)
    }
    class ByzantineBase {
        +bool is_byzantine
        +int attack_height
        +int attack_round
        +tuple groups
        +list evidence
        +configure(height, round, groups)
        +active() bool
        +sign_header(hd) Header
        +build_block(txs) Block
        +first_valid_tx()
        +send_to_many(msg, dsts)
        +send_vote(vote, dsts)
        +send_proposal(block, dsts)
    }
    class Silent {
        +str mode
        +configure(mode)
        +start()
        +propose()
        +on_message(msg, src)
        +on_timeout(key)
    }
    class EquivocateVoter {
        +tuple targets
        +tuple phases
        +configure(targets, phases)
        +cast(kind, target)
    }
    class EquivocateProposer {
        +propose()
    }
    class InvalidBlock {
        +str mode
        +configure(mode)
        +on_request_body(block_hash, src)
        +propose()
    }
    class Replay {
        +tuple kinds
        +int delay
        +int limit
        +list recorded
        +configure(kinds, delay, limit)
        +msg_height(msg) int
        +on_message(msg, src)
        +on_timeout(key)
    }
    class ForkCoalition {
        +Coalition coalition
        +configure(coalition)
        +start()
        +on_timeout(key)
        +on_message(msg, src)
    }
    class Coalition {
        +tuple left
        +tuple right
        +tuple blocks
        +__init__(left, right)
    }
    Node <|-- ByzantineBase
    ByzantineBase <|-- Silent
    ByzantineBase <|-- EquivocateVoter
    ByzantineBase <|-- EquivocateProposer
    ByzantineBase <|-- InvalidBlock
    ByzantineBase <|-- Replay
    ByzantineBase <|-- ForkCoalition
    ForkCoalition "0..*" --> "1" Coalition : shared attack plan
    Coalition --> "0..2" Block : blocks
    class Block
```

## 5. Mạng mô phỏng, thực thi và điểm vào chương trình

Nguồn: `Workspace/src/sim.py`, `execution.py`, `main.py`, `configuration.py`, `identities.py`, `validation.py`.

Các hộp mang stereotype `module` biểu diễn hàm cấp module để làm rõ phụ thuộc; chúng không phải lớp Python. Các sự kiện nằm trong list/heap `Net.q`, không có lớp Event riêng. Net gọi các hook của Node, còn Node gọi API gửi tin và timeout của Net.

File riêng: [05-network-execution.mmd](diagrams/05-network-execution.mmd).

```mermaid
classDiagram
    direction TB
    class MainModule {
        <<module>>
        +run_sim(cfg) Net
        +main()
    }
    class ConfigurationModule {
        <<module>>
        +validate_config(cfg) dict
    }
    class IdentitiesModule {
        <<module>>
        +identity_keys(cfg) tuple
    }
    class ValidationModule {
        <<module>>
        +check_safety(nodes)
        +check_completion(nodes, heights)
        +snapshot(nodes)
    }
    class ByzantineModule {
        <<module>>
        +make_node(behavior, idx, ctx, kp) Node
    }
    class Net {
        +Random rng
        +int n
        +int delta
        +int gst
        +list peers
        +dict link_delays
        +list q
        +int seq
        +int now
        +list nodes
        +list logs
        +dict send_times
        +dict peer_send_times
        +dict receive_times
        +dict blocked_peers
        +__init__(cfg)
        +log(node, ev)
        +push(t, kind, args)
        +broadcast(src, msg)
        +send(src, dst, msg)
        +set_timeout(idx, delay, key)
        +run(t_end)
    }
    class Node {
        +State state
        +start()
        +on_message(msg, src)
        +on_timeout(key)
    }
    class State {
        +dict data
        +dict nonces
        +copy() State
        +hash() bytes
    }
    class ExecutionModule {
        <<module>>
        +valid_tx_fields(tx) bool
        +apply_tx(state, tx, chain_id, acct_pks)
        +apply_txs(state, txs, chain_id, acct_pks) tuple
    }
    class CommonModule {
        <<module>>
        +encode(o) bytes
        +H(data) bytes
        +sign(kp, domain, body) bytes
        +verify(pk, domain, body, sig) bool
        +tx_root(txs) bytes
    }
    MainModule ..> ConfigurationModule : validates config
    MainModule ..> IdentitiesModule : loads keys
    MainModule ..> ByzantineModule : creates configured nodes
    MainModule ..> Node : creates honest nodes
    MainModule ..> Net : creates and runs
    MainModule ..> ValidationModule : CLI result checks
    Net "1" o-- "0..*" Node : nodes and event dispatch
    Node --> "1" Net : transport and timeouts
    Node *-- "1" State : application state
    Node ..> ExecutionModule : validates and executes
    Node ..> CommonModule : signs and verifies
    ExecutionModule ..> State : copies and updates
    ExecutionModule ..> CommonModule : validates signatures
    State ..> CommonModule : hashes canonical state
```

## 6. Các lớp hỗ trợ kiểm thử end-to-end

Nguồn: `Workspace/tests/e2e/test_sync_catchup.py`, `test_t3_invalid_signatures.py`, `test_quorum_boundary.py`.

Sơ đồ minh họa các lớp test và lớp mạng chèn lỗi thực tế, không phải danh sách đầy đủ mọi test case. Hai test class dùng mock.patch để thay Net trong `src.main` rồi gọi hàm `run_sim()`. PartitionNet được runner thí nghiệm quorum khởi tạo riêng. Assertion nằm trong test method hoặc các hàm hỗ trợ; không có lớp Assertion/Scenario riêng.

File riêng: [06-e2e-testing.mmd](diagrams/06-e2e-testing.mmd).

```mermaid
classDiagram
    direction TB
    class TestCase {
        <<external>>
        +assertEqual(first, second)
        +assertTrue(expr)
        +assertNotIn(member, container)
    }
    class TestSyncCatchUpNetwork {
        +test_isolated_node_catches_up()
        +test_normal_run_never_asks()
    }
    class TestT3EndToEnd {
        +test_rejected_and_logged_and_chain_continues()
    }
    class Net {
        +list nodes
        +list logs
        +run(t_end)
    }
    class IsolateNet {
        +int ISOLATED
        +int GST
        +_transmit(src, dst, msg)
    }
    class InjectNet {
        +list bad
        +Block fake_block
        +Tx fake_tx
        +run(t_end)
    }
    class PartitionNet {
        +int gst
        +dict side
        +__init__(cfg, side)
        +_transmit(src, dst, msg)
    }
    class MainModule {
        <<module>>
        +run_sim(cfg) Net
    }
    class QuorumExperimentModule {
        <<module>>
        +run_experiment(n, q, right, f, seed, gst, network)
    }
    TestCase <|-- TestSyncCatchUpNetwork
    TestCase <|-- TestT3EndToEnd
    Net <|-- IsolateNet
    Net <|-- InjectNet
    Net <|-- PartitionNet
    TestSyncCatchUpNetwork ..> MainModule : invokes run_sim
    TestSyncCatchUpNetwork ..> IsolateNet : patches network class
    TestT3EndToEnd ..> MainModule : invokes run_sim
    TestT3EndToEnd ..> InjectNet : patches network class
    QuorumExperimentModule ..> PartitionNet : creates partition network
```

## Các chi tiết cần giữ đúng khi viết báo cáo

- `tx_root(txs)` là SHA-256 của danh sách `[tx.body(), tx.sig]` đã mã hóa, theo đúng thứ tự giao dịch; implementation hiện tại không dựng cây Merkle.
- `Block.hash()` băm `[height, parent, state_hash, tx_root]`; round, pol_round và proposer không thuộc định danh nội dung block.
- `CommitCertificate.signatures` lưu ánh xạ tên validator → chữ ký PRECOMMIT, không chứa danh sách đối tượng Vote. POLKA dùng các phiếu PREVOTE, là cơ chế khác.
- `Node.Q = 2 * f + 1`. Runner chuẩn kiểm tra `n = 3f + 1`, `n >= 8`; thí nghiệm quorum có runner riêng cho điều kiện ngoài giả định.
- `KeyPair` giữ khóa ký; các hàm encode/hash/sign/verify là hàm trong `common.py`. Không có lớp CryptoUtils thật.
- `State` có data/nonces và copy/hash. Các hàm `apply_tx`, `apply_txs` thuộc module `execution.py`, không phải phương thức của State hay lớp Executor.
- Các mô hình dữ liệu có thể được dùng lại giữa các block/node; vì thế quan hệ từ Block tới Header/Tx dùng association, không áp đặt quyền sở hữu độc quyền.
- File `blockchain.py` ở root là khung PoW với các hàm chưa triển khai, không nằm trong luồng Tendermint do `run_sim()` chạy, nên không đưa vào các sơ đồ hệ thống này.

