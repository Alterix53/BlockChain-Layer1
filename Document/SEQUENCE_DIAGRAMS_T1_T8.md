# Sequence diagram kiểm thử T1–T8

Tài liệu mô tả luồng thực thi của **20 test method**, chia thành **14 sequence diagram**. Nguồn đối chiếu là mã hiện tại trong `Workspace/tests/e2e/`, `Workspace/src/`, `tests/c_helpers.py` và `tests/independent_oracle.py`.

## Phạm vi và cách đọc

- Đây là sơ đồ từ mã nguồn, **không phải trace của một lần chạy test đã được ghi nhận**. Tài liệu không công bố kết quả PASS/FAIL thực tế.
- Mũi tên liền biểu diễn lời gọi hoặc gửi yêu cầu; nét đứt biểu diễn trả kết quả hoặc giao thông điệp đã được lên lịch. Nhãn chỉ rõ handler và loại thông điệp.
- `Net` là bộ mô phỏng sự kiện rời rạc. Mọi validator chạy bằng callback trong cùng vòng lặp mô phỏng; các lifeline không có nghĩa mỗi node là một thread.
- Một lifeline nhóm honest có thể đại diện nhiều node. Mỗi node xác minh và đếm quorum cục bộ. Một broadcast được rút gọn thành một mũi tên.
- Trừ nhánh T3 cố tình inject `PROPOSAL` lỗi, việc phát tán block bình thường dùng **HEADER → REQUEST_BODY → BODY**, không gửi nguyên proposal ngay từ đầu.
- Các sơ đồ rút gọn xen kẽ sự kiện; `loop`, `alt`, `opt` mô tả nhánh và điều kiện của code. Không gán một thứ tự mạng cụ thể, block thắng hoặc round commit khi test không assert điều đó.
- Các nhánh phục hồi ở T5–T7 là khả năng của engine, không phải khẳng định mọi nhánh đều xuất hiện trong từng lần chạy.
- `run_with_byzantine` chuyển behaviors thành config JSON và gọi `run_sim` với production factory. Helper này không thay thế Node của runner.
- `assert_honest_certificates` kiểm certificate và, với mô hình chuẩn, gọi oracle độc lập để kiểm lại ledger/state. Nó không tự yêu cầu hoàn tất đủ height nếu không truyền ràng buộc completion tương ứng.

## Điều kiện nền

Các trường không bị test ghi đè được lấy từ [default.json](../Workspace/config/default.json): n=10, f=3, Q=7, heights=5, seed=42, GST=1000, delta=20, duplicate=0.05, reorder=0.1, rate limit 50 thông điệp/100 đơn vị thời gian, peer block 100 thông điệp/100 và duration=50, base_timeout=200, timeout_inc=100, t_end=100000. Ba account Alice/Bob/Carol có 5 giao dịch mỗi account, tối đa 10 giao dịch/block.

Đây là **điều kiện test**, không phải cấu hình sản xuất. `Q = 2f + 1`; runner chuẩn yêu cầu `n = 3f + 1`. Identity fixture cố định độc lập seed mạng.

## Chỉ mục và mức kiểm tra

| Nhóm | Sơ đồ | Phạm vi assertion cần lưu ý |
|---|---|---|
| T1 | T1 | Không lỗi, đủ 5 height, round 0, data/nonce/hash chuẩn |
| T2 | T2a, T2b, T2c | T2a/T2c không bắt buộc completion; T2b gọi handler trực tiếp |
| T3 | T3 | Sáu thông điệp lỗi/node ở t=1; các mã từ chối chính xác và progress(5) |
| T4 | T4 | Admission thật qua mạng, gossip, replay trước/sau commit, thực thi đúng một lần |
| T5 | T5 | Safety/certificates của khối đã chốt, không assert progress đủ height |
| T6 | T6 | Một hoặc ba Silent, honest phải tiến đủ 5 height |
| T7 | T7a, T7b, T7c | Safety/progress(5)/certificates; log tấn công được assert tùy method |
| T8 | T8a, T8b, T8c | Hai lần hoàn tất đúng và giống nhau; đối chứng incomplete/V9 bị hỏng |

Mỗi sơ đồ có ba định dạng trong [sequence-diagrams/](sequence-diagrams/README.md): `.mmd` để chỉnh sửa, `.svg` để phóng to hoặc đưa vào báo cáo, `.png` để chèn ảnh. Cả 14 sơ đồ đã được kiểm cú pháp và render thành SVG/PNG.

## T1 — Mạng bình thường

Nguồn: [test_t1_normal.py](../Workspace/tests/e2e/test_t1_normal.py).

**Test method:**

- `test_t1_normal_execution`

**Thiết lập:** seed=42, GST=0, delta=1; không Byzantine/drop/duplicate/reorder; rate_limit=None, peer_block=None; 10 node, 5 height.

**Điểm cần đọc đúng:** Luồng HEADER → REQUEST_BODY → BODY được vẽ rõ. Nhóm H đại diện các node nhận; quorum được đếm riêng tại từng node, không có bộ đếm tập trung.

[Mermaid](sequence-diagrams/t1-normal.mmd) · [SVG](sequence-diagrams/t1-normal.svg) · [PNG](sequence-diagrams/t1-normal.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT1Normal
    participant R as main.run_sim
    participant N as Net
    participant P as Proposer Node
    participant H as Các validator nhận
    participant E as execution.apply_txs
    participant A as Assertion và oracle
    T->>T: load_cfg và ghi đè cấu hình không lỗi
    T->>R: run_sim(cfg)
    R->>R: validate_config, identity_keys, tạo ctx
    R->>N: Net(cfg)
    R->>P: Tạo Node(idx, ctx, kp)
    R->>H: Tạo các Node còn lại
    R->>P: on_tx(tx, gossip=False) cho giao dịch ban đầu
    R->>H: on_tx(tx, gossip=False)
    R->>N: run(t_end)
    N->>P: START → start() → start_height(1)
    N->>H: START → start() → start_height(1)
    loop h = 1 đến 5, round = 0
        Note over P,H: Proposer luân phiên theo (height + round) modulo n
        P->>P: propose() → make_block() → seal()
        P->>P: send_proposal(B), lưu body và on_proposal(B)
        P->>N: broadcast(HEADER, B.header)
        N-->>H: on_message(HEADER, src) → on_header()
        H->>H: Kiểm trường, cửa sổ, chữ ký, proposer, parent
        H->>N: send(REQUEST_BODY, B.hash)
        N-->>P: on_request_body(hash, src)
        P->>N: send(BODY, (hash, txs))
        N-->>H: on_body() → on_proposal(B)
        H->>E: check_block(B) → apply_txs(state, txs)
        E-->>H: State thử hợp lệ, state_hash khớp
        H->>H: run() → prevote_target(B) → cast(PREVOTE, hash)
        H->>N: broadcast(VOTE PREVOTE)
        P->>N: broadcast(VOTE PREVOTE)
        N-->>H: on_vote() xác thực và lưu phiếu theo voter
        H->>H: run() thấy Q PREVOTE → LOCK
        H->>N: cast và broadcast PRECOMMIT cho cùng hash
        N-->>P: Giao các phiếu hợp lệ
        N-->>H: Giao các phiếu hợp lệ
        H->>H: Q PRECOMMIT → tạo CommitCertificate
        H->>E: finalize(B, cert) → apply_txs()
        E-->>H: State mới, hash đúng
        H->>H: Ghi ledger/certificate, dọn mempool, FINALIZE
        H->>H: start_height(h + 1), done khi vượt 5
        Note over P,H: Proposer cũng chạy cùng quy tắc nhận phiếu và finalize
    end
    N-->>R: Hết sự kiện, hết t_end hoặc mọi honest done
    R-->>T: net
    T->>A: Không Byzantine, DROP, DUPLICATE, reorder, TIMEOUT
    T->>A: Mọi node done, ledger giống nhau và dài 5
    T->>A: Safety, progress(5), certificates và oracle độc lập
    T->>A: Round của block và certificate đều bằng 0
    T->>A: Alice/Bob/Carol msg=v5, nonce=5, state hash thống nhất
    T->>A: Hash hex bắt đầu bằng 0b837be96db72e1f
```

## T2a — Nhân bản và đảo thứ tự trên mạng

Nguồn: [test_t2_duplicate_reorder.py](../Workspace/tests/e2e/test_t2_duplicate_reorder.py).

**Test method:**

- `test_t2_network_duplicate_and_reorder_safety`

**Thiết lập:** seed=42, GST=5000, pre_gst_max_delay=50, drop=0, duplicate=0.25, reorder=0.35.

**Điểm cần đọc đúng:** Test này xác nhận lỗi mạng xảy ra, safety, certificate và ledger bằng nhau. Không có assertion bắt buộc đủ 5 height hoặc tất cả done.

[Mermaid](sequence-diagrams/t2a-duplicate-reorder.mmd) · [SVG](sequence-diagrams/t2a-duplicate-reorder.svg) · [PNG](sequence-diagrams/t2a-duplicate-reorder.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT2DuplicateReorder
    participant R as main.run_sim
    participant N as Net
    participant S as Node gửi
    participant H as Node nhận
    participant A as Assertion và oracle
    T->>R: run_sim(cfg đã đặt duplicate và reorder)
    R->>N: Khởi tạo mạng và node, run(t_end)
    loop Mỗi thông điệp, lịch cụ thể do seed quyết định
        S->>N: send hoặc broadcast(msg)
        opt Trúng nhánh duplicate_probability
            N->>N: Ghi DUPLICATE, lên lịch bản sao
        end
        opt Trước GST và trúng nhánh reorder
            N->>N: Tăng trễ, ghi DELAY reason=reorder
        end
        N-->>H: Giao thông điệp theo hàng đợi (t, seq)
        alt VOTE mới hợp lệ
            H->>H: on_vote(), lưu slot[voter]
        else VOTE cùng voter, cùng slot đã có
            H->>H: Giữ phiếu đầu, không đếm thêm
        else HEADER hoặc BODY
            H->>H: Xử lý proposal và bộ đệm theo handler
        end
        H->>H: run(), áp dụng khóa và quorum
        opt Đủ Q PRECOMMIT cho khối đã kiểm
            H->>H: finalize(B, cert)
        end
    end
    N-->>R: Kết thúc mô phỏng
    R-->>T: net
    T->>A: Có DUPLICATE và DELAY reason=reorder
    T->>A: assert_honest_safety và assert_honest_certificates
    A->>A: Oracle kiểm ledger, chữ ký, thực thi và state
    T->>A: Ledger của mỗi node bằng ledger node đầu
    Note over T,A: Không suy ra completion chỉ từ safety hoặc ledger bằng nhau
```

## T2b — Kiểm tra trực tiếp chống đếm phiếu trùng

Nguồn: [test_t2_duplicate_reorder.py](../Workspace/tests/e2e/test_t2_duplicate_reorder.py).

**Test method:**

- `test_t2_rule7_anti_double_voting_and_equivocation`

**Thiết lập:** make_nodes() tạo Node thật trên RecordingNet; receiver=V0, voter=V1, slot=(1,0,PREVOTE).

**Điểm cần đọc đúng:** Đây là kiểm thử handler trực tiếp nằm trong file E2E: không gọi run_sim và không có vòng lặp Net.run. Phiếu A/B có chữ ký hợp lệ của cùng V1.

[Mermaid](sequence-diagrams/t2b-rule7.mmd) · [SVG](sequence-diagrams/t2b-rule7.svg) · [PNG](sequence-diagrams/t2b-rule7.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT2DuplicateReorder
    participant F as c_helpers.make_nodes
    participant V as V1 và khóa ký
    participant H as V0 receiver
    participant N as RecordingNet
    T->>F: make_nodes()
    F-->>T: nodes, net đã start và clear log khởi tạo
    T->>V: Tạo và ký vote_a cho hash A
    V-->>T: PREVOTE(1,0,A,V1)
    T->>V: Tạo và ký vote_b cho hash B
    V-->>T: PREVOTE(1,0,B,V1)
    T->>H: on_vote(vote_a)
    H->>H: Kiểm định dạng, cửa sổ và chữ ký
    H->>H: votes[(1,0,PREVOTE)][V1] = vote_a
    loop Hai lần gửi lại vote_a
        T->>H: on_vote(vote_a)
        H->>H: Slot đã có V1, hash giống → return
    end
    T->>T: Assert V1 chỉ có đúng một phiếu, hash vẫn A
    T->>H: on_vote(vote_b)
    H->>H: Slot đã có V1, hash B khác A
    H->>N: log(EQUIVOCATION, voter=V1, height=1, round=0)
    H->>H: return, không thay vote_a
    T->>T: Assert phiếu đầu vẫn A
    T->>N: events(EQUIVOCATION, voter=V1)
    N-->>T: Có ít nhất một sự kiện
```

## T2c — Byzantine phát lại thông điệp

Nguồn: [test_t2_duplicate_reorder.py](../Workspace/tests/e2e/test_t2_duplicate_reorder.py).

**Test method:**

- `test_t2_byzantine_replay_attack_node`

**Thiết lập:** V2=Replay(delay=20, limit=10), seed=42; các tham số khác kế thừa default.json.

**Điểm cần đọc đúng:** Replay phát lại nguyên thông điệp, không ký lại bằng danh tính người gửi gốc. Test yêu cầu BYZ_REPLAY, safety và certificate trên honest; không gọi assert_honest_progress.

[Mermaid](sequence-diagrams/t2c-replay-node.mmd) · [SVG](sequence-diagrams/t2c-replay-node.svg) · [PNG](sequence-diagrams/t2c-replay-node.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT2DuplicateReorder
    participant F as run_with_byzantine
    participant R as main.run_sim
    participant N as Net
    participant B as V2 Replay
    participant H as Honest Node
    participant A as Assertion và oracle
    T->>F: behaviors V2=Replay, delay=20, limit=10
    F->>F: Đổi lớp hành vi thành config byzantine JSON
    F->>R: run_sim(load_cfg(byzantine, seed=42))
    R->>B: make_node(replay) → configure()
    R->>N: run(t_end)
    N-->>B: on_message(msg, src)
    opt Loại tin phù hợp, đúng attack_height, chưa ghi, chưa đủ limit
        B->>B: recorded.append(msg)
        B->>N: set_timeout(20, BYZ_REPLAY, index)
    end
    B->>B: super().on_message(msg, src)
    N-->>B: on_timeout(BYZ_REPLAY, index)
    B->>B: evidence.append(msg), log BYZ_REPLAY
    B->>N: broadcast nguyên msg đã ghi
    N-->>H: on_message(msg)
    alt Vote cùng slot và voter đã tồn tại
        H->>H: Không đếm thêm, phát hiện mâu thuẫn nếu có
    else Thông điệp ngoài cửa sổ hoặc trùng dữ liệu
        H->>H: Áp dụng kiểm tra cửa sổ hoặc bộ đệm tương ứng
    else Thông điệp còn hợp lệ
        H->>H: Xử lý theo handler và run()
    end
    N-->>R: Kết thúc mô phỏng
    R-->>F: net
    F-->>T: net
    T->>A: BYZ_REPLAY có ít nhất một sự kiện
    T->>A: Safety và certificates, loại V2 khỏi nhóm kiểm tra
```

## T3 — Chèn chữ ký và chứng nhận sai

Nguồn: [test_t3_invalid_signatures.py](../Workspace/tests/e2e/test_t3_invalid_signatures.py).

**Test method:**

- `test_rejected_and_logged_and_chain_continues`

**Thiết lập:** mock.patch src.main.Net=InjectNet; dùng cấu hình nền; chèn 6 thông điệp lỗi tới mỗi node ở t=1.

**Điểm cần đọc đúng:** V3 được dùng làm nguồn chèn lỗi và bị loại khỏi tập assertion cuối. Trong test này run_sim không cấu hình V3 thành lớp Byzantine: các node vẫn được tạo theo cấu hình nền. Lỗi được đưa thẳng vào hàng đợi MSG, không phải gửi qua Net.send.

[Mermaid](sequence-diagrams/t3-invalid-signatures.mmd) · [SVG](sequence-diagrams/t3-invalid-signatures.svg) · [PNG](sequence-diagrams/t3-invalid-signatures.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT3EndToEnd
    participant R as main.run_sim
    participant N as InjectNet
    participant K as Khóa của V3
    participant H as Mỗi node nhận
    participant C as common.verify
    participant A as Assertion và oracle
    T->>T: mock.patch(src.main.Net, InjectNet)
    T->>R: run_sim(load_cfg())
    R->>N: Khởi tạo và gọi run(t_end)
    N->>K: Ký vote, header và một PRECOMMIT bằng khóa V3
    K-->>N: Chữ ký làm đầu vào để tạo ca lỗi
    N->>N: Tạo 3 VOTE lỗi và 1 PROPOSAL sai domain
    N->>N: Tạo cert chép chữ ký V3 sang Q tên khác nhau
    N->>N: Tạo TX Alice có chữ ký hỏng
    loop Mỗi thông điệp lỗi và mỗi node đích
        N->>N: push(t=1, MSG, src=3, dst, msg)
    end
    N->>N: super().run(t_end), START tại t=0
    loop Mỗi node, xử lý các MSG ở t=1
        N-->>H: 3 VOTE lỗi
        H->>C: verify với VOTE:chain_id
        C-->>H: False cho chữ ký hỏng, sai loại domain, sai chain
        H->>N: REJECT bad_vote_sig, height=1 (3 lần)
        N-->>H: PROPOSAL ký dưới VOTE:chain_id
        H->>C: verify với HEADER:chain_id
        C-->>H: False
        H->>N: REJECT bad_header_sig, height=1
        N-->>H: SYNC_RESP có block và cert giả
        H->>H: on_sync_response(), kiểm header và certificate_error()
        H->>C: Kiểm chữ ký theo từng voter trong cert
        C-->>H: Chữ ký sao chép không hợp lệ với khóa người khác
        H->>N: REJECT_SYNC invalid_cert_sig, height=1
        N-->>H: TX giả danh Alice
        H->>C: verify với khóa Alice và TX:chain_id
        C-->>H: False
        H->>N: REJECT bad_tx_sig, sender=Alice
    end
    Note over N,H: Các sự kiện đồng thuận hợp lệ vẫn tiếp tục được xử lý
    H->>H: Chốt các khối hợp lệ theo quorum
    N-->>R: Kết thúc mô phỏng
    R-->>T: net, mock.patch được khôi phục
    T->>A: Mỗi node tại t=1 có đúng các mã lỗi mong đợi
    T->>A: fake_block không vào ledger, fake_tx không vào mempool hoặc block
    T->>A: Safety, progress(5), certificates với tập loại trừ V3
```

## T4 — Nhận lần đầu và phát lại giao dịch

Nguồn: [test_t4_replay_tx.py](../Workspace/tests/e2e/test_t4_replay_tx.py).

**Test method:**

- `test_t4_transaction_replay_prevention`

**Thiết lập:** GST=0, delta=1, heights=3, txs_per_account=0, max_txs_per_block=1, t_end=2000; tắt duplicate và throttling.

**Điểm cần đọc đúng:** Giao dịch đi vào qua Net.send, không nạp sẵn mempool. Replay bị chặn tại seen_tx_hashes nên test không yêu cầu log bad_nonce. Không cố định giao dịch phải nằm ở block nào.

[Mermaid](sequence-diagrams/t4-transaction-replay.mmd) · [SVG](sequence-diagrams/t4-transaction-replay.svg) · [PNG](sequence-diagrams/t4-transaction-replay.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT4ReplayTx
    participant R as main.run_sim
    participant N as AdmissionNet
    participant V as V5 nhận lần đầu
    participant H as Các node khác
    participant E as execution
    participant A as Oracle và assertion
    T->>T: Tạo TX Alice nonce=1 và ký bằng identity_keys(cfg)
    T->>T: mock.patch(src.main.Net, AdmissionNet)
    T->>R: run_sim(cfg không có giao dịch ban đầu)
    R->>N: run(t_end)
    N->>N: Assert mọi mempool và seen_tx_hashes đều rỗng
    N->>N: send(0,5,TX), gọi hai lần trước super().run()
    Note over N,H: HEADER height 1 bị giữ tới t=20, height 3 tới t=100
    N-->>V: on_message(TX) → on_tx(tx)
    V->>V: Kiểm field, seen, chữ ký, namespace, nonce đã commit
    V->>V: Thêm seen và mempool, log TX_RECEIVED
    V->>N: broadcast(TX) gossip
    N-->>V: Bản TX trùng
    V->>V: Hash đã nằm trong seen → return
    N-->>H: TX qua gossip
    H->>H: Lần đầu hợp lệ → thêm mempool và TX_RECEIVED
    H->>N: Gossip tiếp, bản trùng được bỏ qua
    N-->>H: HEADER, REQUEST_BODY, BODY và các VOTE
    H->>E: Kiểm và thực thi giao dịch trong block được đề xuất
    E-->>H: Alice/msg mới, nonce Alice=1
    H->>H: Đủ quorum → finalize, loại tx khỏi mempool
    N->>N: Sau một lần _deliver, phát hiện tx đã có trong ledger bất kỳ
    N->>N: replayed_after_commit=True
    N->>N: broadcast(0, TX cũ) đúng một lần
    N-->>V: TX phát lại sau khi đã có commit
    V->>V: seen_tx_hashes nhận ra → không admission lần nữa
    N-->>H: TX phát lại và giao dịch trùng khác
    H->>H: Giữ cơ chế khử trùng lặp
    Note over N,H: Tiếp tục mô phỏng tới khi chốt đủ 3 height
    N-->>R: Kết thúc
    R-->>T: net
    T->>A: replayed_after_commit phải True
    T->>A: Số TX_RECEIVED của Alice nonce=1 đúng bằng n
    T->>A: assert_finalized 3 height, data mong đợi và nonce=1
    T->>A: Mỗi ledger có tx đúng một lần, mọi mempool rỗng
```

## T5 — Mất và trễ tin trước GST

Nguồn: [test_t5_gst_safety.py](../Workspace/tests/e2e/test_t5_gst_safety.py).

**Test method:**

- `test_t5_pre_gst_drops_and_delays_preserve_safety`
- `test_t5_extreme_pre_gst_partition_safety`

**Thiết lập:** Ca thường: seed=42/43/44/99, GST=1500, max_delay=200, drop=0.15, reorder=0.2, delta=20, heights=5. Ca cực đoan: seed=7, GST=2000, max_delay=300, drop=0.40, reorder=0.30, delta=20, heights=3.

**Điểm cần đọc đúng:** Tên ca cực đoan có chữ partition nhưng code dùng xác suất drop/reorder, không tạo phân vùng topology cố định. Cả hai test không assert completion. Nhánh sau GST chỉ áp dụng nếu thời gian mô phỏng đi tới đó; không khẳng định lịch nào cũng đi qua GST.

[Mermaid](sequence-diagrams/t5-pre-gst-safety.mmd) · [SVG](sequence-diagrams/t5-pre-gst-safety.svg) · [PNG](sequence-diagrams/t5-pre-gst-safety.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT5GstSafety
    participant R as main.run_sim
    participant N as Net
    participant S as Node gửi
    participant H as Node nhận
    participant A as Assertion và oracle
    alt Ca thường
        T->>T: Lặp subTest seed 42,43,44,99
        T->>T: load_cfg GST=1500, drop=0.15, heights=5
    else Ca cực đoan
        T->>T: load_cfg seed=7, GST=2000, drop=0.40, heights=3
    end
    T->>R: run_sim(cfg)
    R->>N: Khởi tạo node và run(t_end)
    loop Xử lý sự kiện trước GST
        S->>N: send hoặc broadcast(msg)
        alt Trúng xác suất drop
            N->>N: Log DROP reason=pre_gst, không giao frame
        else Không drop
            N->>N: Chọn trễ trước GST, có thể thêm reorder
            N-->>H: Giao msg theo lịch sự kiện
            H->>H: Xác thực, lọc trùng, lưu phiếu hoặc proposal
        end
        opt Timeout của height/round hiện tại
            N-->>H: on_timeout(key)
            H->>H: NIL vote hoặc chuyển round theo kind
            opt Timeout ROUND
                H->>N: request_sync()
            end
        end
        opt Đủ quorum cho block đã kiểm
            H->>H: finalize(B, certificate)
        end
    end
    opt Mô phỏng còn chạy khi now đạt GST
        S->>N: Truyền thông điệp sau GST
        N->>N: Áp dụng transport sau GST và cận delta toàn tuyến
        N-->>H: Giao tin, xử lý đồng thuận hoặc đồng bộ
        Note over N,H: Admission cục bộ có thể chờ trước SEND đầu tiên
    end
    N-->>R: Kết thúc theo điều kiện runner
    R-->>T: net
    opt Ca thường
        T->>A: Có DROP reason=pre_gst
    end
    T->>A: assert_honest_safety và assert_honest_certificates
    A->>A: Oracle phát lại độc lập các block đã chốt
    opt Ca thường
        T->>A: Mỗi height đã xuất hiện có tối đa một committed hash
    end
    Note over T,A: Không có assertion done hoặc progress đủ heights trong hai test này
```

## T6 — Proposer im lặng và phục hồi round

Nguồn: [test_t6_silent_proposer.py](../Workspace/tests/e2e/test_t6_silent_proposer.py).

**Test method:**

- `test_t6_single_silent_proposer_round_advancement`
- `test_t6_three_silent_validators_liveness_preserved`

**Thiết lập:** Ca một node: V1=Silent(all), seed=42. Ca ba node: V1/V4/V7=Silent(all), seed=10. n=10, f=3, Q=7, mục tiêu 5 height.

**Điểm cần đọc đúng:** TIMEOUT PROPOSE làm cast PREVOTE NIL, không trực tiếp start_round(1). Chuyển round qua PRECOMMIT timeout, ROUND timeout hoặc cơ chế skip. Assertion chính xác round=1/proposer=V2 chỉ nằm ở ca một node.

[Mermaid](sequence-diagrams/t6-silent-proposer.mmd) · [SVG](sequence-diagrams/t6-silent-proposer.svg) · [PNG](sequence-diagrams/t6-silent-proposer.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT6SilentProposer
    participant F as run_with_byzantine
    participant N as Net
    participant B as V1 Silent
    participant H as Honest validators
    participant P as V2 proposer round 1
    participant A as Assertion và oracle
    alt Một node im lặng
        T->>F: behaviors V1=Silent(all), seed=42
    else Ba node im lặng
        T->>F: behaviors V1,V4,V7=Silent(all), seed=10
    end
    F->>F: Chuyển behaviors sang JSON, gọi run_sim
    F->>N: Khởi tạo qua production factory và run(t_end)
    N-->>B: start()
    B->>N: Log BYZ_SILENT, không phát proposal hay vote
    N-->>H: start_height(1), start_round(0)
    H->>N: Lên lịch PROPOSE và ROUND timeout
    N-->>H: on_timeout(PROPOSE,1,0)
    H->>N: Log TIMEOUT kind=PROPOSE
    H->>H: Nếu còn PROPOSE thì cast(PREVOTE,NIL)
    H->>N: Broadcast PREVOTE NIL
    N-->>H: Nhận Q PREVOTE NIL
    H->>H: run() → cast(PRECOMMIT,NIL)
    H->>N: Broadcast PRECOMMIT NIL, lên lịch timeout
    alt PRECOMMIT timeout tới hạn
        N-->>H: on_timeout(PRECOMMIT,1,0)
        H->>H: start_round(1)
    else ROUND timeout tới trước
        N-->>H: on_timeout(ROUND,1,0)
        H->>N: request_sync()
        H->>H: start_round(1)
    end
    Note over H,P: Node cũng có thể theo kịp round qua maybe_skip_round
    P->>P: Proposer(1,1)=V2, propose()
    P->>N: HEADER
    N-->>H: HEADER, trao đổi REQUEST_BODY/BODY
    H->>N: PREVOTE cho block hợp lệ
    N-->>H: Q PREVOTE → LOCK
    H->>N: PRECOMMIT
    N-->>H: Q PRECOMMIT
    H->>H: finalize(), tiếp tục các height
    Note over N,H: Ca ba Silent còn đúng 7 honest, đủ Q nếu chúng phối hợp tiến triển
    N-->>F: Kết thúc, trả net
    F-->>T: net
    opt Ca một Silent
        T->>A: Mỗi honest có TIMEOUT PROPOSE tại (1,0)
        T->>A: Block đầu height=1, round=1, proposer=V2
    end
    T->>A: Safety, progress đủ 5, certificates trên honest
```

## T7a — Proposer đưa hai đề xuất

Nguồn: [test_t7_equivocation.py](../Workspace/tests/e2e/test_t7_equivocation.py).

**Test method:**

- `test_t7_equivocating_proposer_broadcast`
- `test_t7_equivocating_proposer_partitioned`

**Thiết lập:** V1=EquivocateProposer(height=1), seed=42. Ca broadcast không đặt groups; ca chia nhóm dùng [0,2,4,6] và [3,5,7,8].

**Điểm cần đọc đúng:** Chia nhóm ở đây là chọn người nhận proposal, không cắt liên kết mạng. Hai block A rỗng, B chứa một giao dịch hợp lệ. Không cố định block thắng hoặc round chốt. Trong chế độ groups, ByzantineBase không tự on_proposal như nhánh broadcast.

[Mermaid](sequence-diagrams/t7a-proposer-equivocation.mmd) · [SVG](sequence-diagrams/t7a-proposer-equivocation.svg) · [PNG](sequence-diagrams/t7a-proposer-equivocation.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT7Equivocation
    participant F as run_with_byzantine
    participant B as V1 EquivocateProposer
    participant N as Net
    participant L as Honest nhóm trái
    participant H as Honest nhóm phải
    participant A as Assertion và oracle
    T->>F: V1 EquivocateProposer, chọn groups hoặc broadcast
    F->>F: run_sim qua config và factory thật
    N-->>B: START → propose() tại height 1, round 0
    B->>B: first_valid_tx(), build_block rỗng A và một tx B
    B->>B: evidence thêm A/B, log BYZ_EQUIVOCATE_PROPOSAL
    alt Không cấu hình groups
        B->>N: send_proposal(A) → broadcast HEADER A
        B->>N: send_proposal(B) → broadcast HEADER B
        N-->>L: HEADER A và B theo lịch mạng
        N-->>H: HEADER A và B theo lịch mạng
    else Cấu hình groups
        B->>N: HEADER A chỉ tới [0,2,4,6]
        B->>N: HEADER B chỉ tới [3,5,7,8]
        N-->>L: HEADER A
        N-->>H: HEADER B
    end
    L->>N: REQUEST_BODY A
    H->>N: REQUEST_BODY B
    N-->>B: Yêu cầu body theo từng hash
    B->>N: BODY tương ứng từ self.bodies
    N-->>L: on_body → on_proposal
    N-->>H: on_body → on_proposal
    L->>L: Kiểm block, keep_first và lưu blocks
    H->>H: Kiểm block, keep_first và lưu blocks
    opt Node nhận đủ hai proposal cùng slot
        L->>N: Log EQUIVOCATION proposer=V1, giữ proposal đầu
        L->>L: Có thể giữ cả hai block body trong blocks
    end
    L->>N: PREVOTE theo proposal và lock cục bộ
    H->>N: PREVOTE theo proposal và lock cục bộ
    N-->>L: Các phiếu và bằng chứng được giao theo lịch
    N-->>H: Các phiếu và bằng chứng được giao theo lịch
    Note over L,H: Tiến triển qua quorum hoặc timeout/round mới, giữ lock và kiểm POLKA
    L->>L: Chỉ finalize block hợp lệ với Q PRECOMMIT
    H->>H: Chỉ finalize block hợp lệ với Q PRECOMMIT
    F-->>T: net sau khi mô phỏng kết thúc
    T->>A: BYZ_EQUIVOCATE_PROPOSAL của V1 xuất hiện
    opt Ca broadcast
        T->>A: Có EQUIVOCATION proposer=V1
    end
    T->>A: Safety, progress(5), certificates, loại V1
```

## T7b — Tối đa f voter ký hai mặt

Nguồn: [test_t7_equivocation.py](../Workspace/tests/e2e/test_t7_equivocation.py).

**Test method:**

- `test_t7_up_to_f_equivocating_voters`

**Thiết lập:** V3/V5/V7=EquivocateVoter mặc định, seed=42; attack slot mặc định height=1, round=0; targets mặc định=(target,NIL).

**Điểm cần đọc đúng:** Không vẽ mặc định là hai block A/B: targets mặc định là target và NIL. Nếu target đã là NIL thì a==b và hook gọi super().cast(). Nhánh phát hiện equivocation tùy thứ tự giao phiếu; assertion yêu cầu có ít nhất một log cho mỗi Byzantine.

[Mermaid](sequence-diagrams/t7b-voter-equivocation.mmd) · [SVG](sequence-diagrams/t7b-voter-equivocation.svg) · [PNG](sequence-diagrams/t7b-voter-equivocation.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT7Equivocation
    participant F as run_with_byzantine
    participant B as V3,V5,V7 EquivocateVoter
    participant N as Net
    participant H as Honest receiver
    participant A as Assertion và oracle
    T->>F: behaviors V3,V5,V7, seed=42
    F->>F: run_sim và make_node qua config
    N-->>B: Xử lý proposal và phiếu hợp lệ
    B->>B: run() gọi cast(kind,target)
    alt Đúng attack slot, phase, chưa ký và target khác NIL
        B->>B: Tạo hai Vote cùng slot cho target và NIL
        B->>B: signed[key]=target, lưu evidence
        B->>N: Log BYZ_EQUIVOCATE_VOTE
        B->>N: Broadcast vote_target
        B->>N: Broadcast vote_NIL
        N-->>H: Phiếu đến đầu tiên
        H->>H: on_vote(), verify rồi lưu slot[voter]
        N-->>H: Phiếu còn lại cùng voter và slot, khác hash
        H->>N: Log EQUIVOCATION voter tương ứng
        H->>H: Giữ phiếu đầu, không tăng số voter
    else Không đủ điều kiện tạo hai phiếu khác nhau
        B->>B: super().cast(kind,target)
    end
    loop Các round và height tiếp theo
        N-->>H: Giao thông điệp và timeout
        H->>H: Chỉ ký một phiếu mỗi slot, áp dụng lock/POLKA
        H->>H: Đủ Q PRECOMMIT hợp lệ → finalize()
    end
    F-->>T: net
    T->>A: Mỗi V3,V5,V7 có BYZ_EQUIVOCATE_VOTE
    T->>A: Mỗi voter này có ít nhất một EQUIVOCATION
    T->>A: Safety, progress(5), certificates trên honest
    Note over H,A: n=10, Q=7 → hai quorum giao ít nhất 4 người, hơn f=3
```

## T7c — Kết hợp proposer và voter Byzantine

Nguồn: [test_t7_equivocation.py](../Workspace/tests/e2e/test_t7_equivocation.py).

**Test method:**

- `test_t7_coalition_proposer_and_voters`

**Thiết lập:** seed=42; V1=EquivocateProposer(groups=[0,2,3]/[5,6,8],height=1); V4/V7=EquivocateVoter; tổng 3 Byzantine.

**Điểm cần đọc đúng:** Ca này dùng các lớp EquivocateProposer và EquivocateVoter, không dùng lớp ForkCoalition hay Coalition. Test không assert log tấn công riêng, chỉ assert safety/progress/certificates. Nhánh voter tấn công chỉ phát sinh khi cast() thỏa điều kiện.

[Mermaid](sequence-diagrams/t7c-mixed-coalition.mmd) · [SVG](sequence-diagrams/t7c-mixed-coalition.svg) · [PNG](sequence-diagrams/t7c-mixed-coalition.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT7Equivocation
    participant F as run_with_byzantine
    participant P as V1 EquivocateProposer
    participant B as V4,V7 EquivocateVoter
    participant N as Net
    participant L as Honest [0,2,3]
    participant H as Honest [5,6,8]
    participant A as Assertion và oracle
    T->>F: Cấu hình 1 proposer và 2 voter Byzantine
    F->>F: run_sim, factory khởi tạo đúng lớp
    N-->>P: Lượt proposer (height=1,round=0)
    P->>P: Tạo block A rỗng và block B chứa một tx
    P->>N: Gửi HEADER A cho nhóm trái
    P->>N: Gửi HEADER B cho nhóm phải
    N-->>L: Nhận và tải BODY A
    N-->>H: Nhận và tải BODY B
    L->>N: PREVOTE theo kiểm định và lock của mình
    H->>N: PREVOTE theo kiểm định và lock của mình
    opt V4 hoặc V7 gọi cast tại slot tấn công với target khác NIL
        B->>N: Hai phiếu cùng slot cho target và NIL
        N-->>L: Nhận các phiếu, chỉ giữ một phiếu mỗi voter
        N-->>H: Nhận các phiếu, chỉ giữ một phiếu mỗi voter
    end
    Note over L,H: Các nhóm vẫn liên lạc qua Net, không bị network partition
    loop Các sự kiện, timeout và round tiếp theo
        N-->>L: Phiếu, proposal, bằng chứng hoặc timeout
        N-->>H: Phiếu, proposal, bằng chứng hoặc timeout
        L->>L: Kiểm lock/POLKA và quorum trước khi ký/chốt
        H->>H: Kiểm lock/POLKA và quorum trước khi ký/chốt
    end
    F-->>T: net
    T->>A: Safety trên 7 honest
    T->>A: Progress đủ 5 height và certificates hợp lệ
    Note over T,A: Test method không có assertion BYZ_* hoặc EQUIVOCATION riêng
```

## T8a — Hai lần chạy cùng đầu vào

Nguồn: [test_t8_determinism.py](../Workspace/tests/e2e/test_t8_determinism.py).

**Test method:**

- `test_t8_default_config_rerun_twice`
- `test_t8_multiple_arbitrary_seeds`
- `test_t8_chaotic_pre_gst_network_determinism`
- `test_t8_byzantine_adversary_determinism`

**Thiết lập:** Mặc định seed=42; nhiều seed=1/99/1337 với heights=3; mạng nhiễu seed=77,GST=400,max_delay=80,drop=0.1,reorder=0.15,heights=4; Byzantine seed=123,heights=3,V1 EquivocateProposer,V4 Silent.

**Điểm cần đọc đúng:** Mỗi ca chạy hai mạng mới với cùng cấu hình và danh tính cố định. Không yêu cầu các seed khác nhau tạo cùng log. T8 xác nhận các ví dụ cụ thể, không phải chứng minh tất định cho mọi môi trường hay đầu vào.

[Mermaid](sequence-diagrams/t8a-two-runs.mmd) · [SVG](sequence-diagrams/t8a-two-runs.svg) · [PNG](sequence-diagrams/t8a-two-runs.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT8Determinism
    participant F as load_cfg hoặc run_with_byzantine
    participant R as main.run_sim
    participant N1 as Net lần 1
    participant N2 as Net lần 2
    participant V as _assert_complete_deterministic_runs
    participant O as independent_oracle
    T->>F: Chuẩn bị cùng cfg, seed và danh tính
    F-->>T: Cấu hình ca thường, nhiều seed, nhiễu hoặc Byzantine
    T->>R: Lần 1, run_sim(cfg) hoặc helper Byzantine
    R->>N1: Tạo mới PRNG, hàng đợi, node, state
    N1->>N1: run(t_end), lưu logs và kết quả
    R-->>T: net1
    T->>R: Lần 2, cùng đầu vào
    R->>N2: Tạo lại PRNG và node độc lập
    N2->>N2: run(t_end), lưu logs và kết quả
    R-->>T: net2
    T->>V: net1, net2, cfg, tên Byzantine bị loại trừ
    V->>O: digest của expected_data và expected_nonces
    O-->>V: expected_hash độc lập
    V->>V: Ghép log bằng newline, mã hóa UTF-8
    V->>V: Assert bytes log lần 1 bằng lần 2
    loop Mỗi lần chạy
        V->>V: Assert đúng tập tên honest
        loop Từng honest node, kể cả V9
            V->>V: Assert done và ledger dài đúng heights
            V->>V: Assert data, nonce và state hash bằng expected
        end
        V->>O: assert_finalized(nodes, heights, expected_data, expected_nonces)
        O->>O: Tự kiểm parent, tx, chữ ký, state và certificate
        O-->>V: Không có assertion lỗi
    end
    V->>V: So sánh ledger mọi honest với cùng reference chain
    V->>V: So sánh state hash giữa hai lần chạy theo tên node
    V-->>T: Helper thành công
    opt Ca mặc định seed 42
        T->>T: Assert prefix hash chuẩn và ledger từng node hai lần bằng nhau
    end
```

## T8b — Không chấp nhận hai lần cùng bị kẹt

Nguồn: [test_t8_determinism.py](../Workspace/tests/e2e/test_t8_determinism.py).

**Test method:**

- `test_t8_rejects_identically_incomplete_runs`

**Thiết lập:** t_end=0, heights=1, accounts=[Alice], txs_per_account=1.

**Điểm cần đọc đúng:** Test PASS khi helper ném AssertionError chứa did not finish. Không phải hai mô phỏng bị kẹt được xem là chạy đúng.

[Mermaid](sequence-diagrams/t8b-incomplete-negative-control.mmd) · [SVG](sequence-diagrams/t8b-incomplete-negative-control.svg) · [PNG](sequence-diagrams/t8b-incomplete-negative-control.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT8Determinism
    participant R as main.run_sim
    participant N as Hai mạng độc lập
    participant V as _assert_complete_deterministic_runs
    T->>T: load_cfg(t_end=0, heights=1, một giao dịch Alice)
    T->>R: run_sim(cfg) lần 1
    R->>N: Chỉ xử lý sự kiện trong t_end=0
    R-->>T: first chưa hoàn tất
    T->>R: run_sim(cfg) lần 2
    R->>N: Cùng cấu hình và giới hạn thời gian
    R-->>T: second chưa hoàn tất
    T->>T: Assert first.logs == second.logs
    T->>T: Bắt đầu assertRaisesRegex(AssertionError, did not finish)
    T->>V: Kiểm hai kết quả
    V->>V: Bytes log bằng nhau
    V->>V: Kiểm từng honest node.done
    V-->>T: AssertionError did not finish
    T->>T: PASS vì helper đã từ chối hai lần incomplete giống nhau
```

## T8c — Phát hiện lỗi riêng trên V9

Nguồn: [test_t8_determinism.py](../Workspace/tests/e2e/test_t8_determinism.py).

**Test method:**

- `test_t8_checks_every_honest_node_not_just_node_zero`

**Thiết lập:** GST=0, delta=1, heights=1, accounts=[Alice], txs_per_account=1; tắt duplicate/rate_limit/peer_block. Chỉ sửa kết quả lần 2 ở V9.

**Điểm cần đọc đúng:** Năm corruption được áp dụng tách biệt bằng mock.patch.object và khôi phục sau mỗi subtest. Không thay log hoặc V0. Test chứng minh helper không chỉ kiểm node đầu tiên.

[Mermaid](sequence-diagrams/t8c-every-node-negative-control.mmd) · [SVG](sequence-diagrams/t8c-every-node-negative-control.svg) · [PNG](sequence-diagrams/t8c-every-node-negative-control.png)

```mermaid
sequenceDiagram
    autonumber
participant T as TestT8Determinism
    participant R as main.run_sim
    participant V9 as V9 của second
    participant V as _assert_complete_deterministic_runs
    T->>R: first=run_sim(cfg)
    R-->>T: first hoàn tất
    T->>R: second=run_sim(cfg)
    R-->>T: second hoàn tất
    T->>V: Kiểm baseline first và second
    V-->>T: Thành công
    loop Mỗi corruption độc lập
        alt Sửa done
            T->>V9: mock.patch done=False
        else Sửa ledger
            T->>V9: mock.patch ledger=[]
        else Sửa data
            T->>V9: mock.patch state.data thành giá trị wrong
        else Sửa nonces
            T->>V9: mock.patch state.nonces Alice=99
        else Sửa hàm hash
            T->>V9: mock.patch state.hash trả 32 byte x
        end
        T->>T: Bắt đầu assertRaises(AssertionError)
        T->>V: Kiểm lại first và second
        V->>V: Logs vẫn khớp nhưng kiểm từng honest phát hiện sai ở V9
        V-->>T: AssertionError
        T->>V9: Thoát mock.patch, khôi phục dữ liệu hoặc phương thức
    end
    T->>T: PASS khi cả năm corruption đều bị phát hiện
```

## Liên hệ với triển khai

- [main.py](../Workspace/src/main.py): kiểm cấu hình, nạp khóa, tạo node/mạng, admission giao dịch nền và `net.run(t_end)`.
- [node.py](../Workspace/src/node.py): các handler TX/HEADER/BODY/VOTE/SYNC, cơ chế signed/locked/proofs, timeout và finalize.
- [sim.py](../Workspace/src/sim.py): hàng đợi sự kiện, định tuyến, drop/reorder/duplicate và admission/rate limit.
- [byzantine.py](../Workspace/src/byzantine.py): Silent, EquivocateProposer, EquivocateVoter và Replay.
- [c_helpers.py](../Workspace/tests/c_helpers.py): config, RecordingNet, factory wrapper, safety/progress/certificate assertions.
- [independent_oracle.py](../Workspace/tests/independent_oracle.py): mã hóa/hash/xác thực và phát lại giao dịch độc lập với production.

Giao điểm quorum giải thích vì sao không được tùy tiện hạ ngưỡng phiếu. Safety xuyên nhiều round còn dựa vào quy tắc khóa, bằng chứng POLKA và xác thực; chỉ nêu Q lớn hơn n/2 chưa đủ để giải thích toàn bộ giao thức.

T3 unit guards trong `tests/unit/test_t3_signatures.py` được mô tả ở tài liệu kiểm thử; bộ sequence này tập trung T3 E2E hiện tại. Các suite regression, quorum-boundary và catch-up riêng không được gộp vào T1–T8 khi không được các test method ở đây gọi.
