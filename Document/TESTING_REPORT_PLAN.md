# Kế hoạch và kịch bản kiểm thử — Lab 01 Blockchain Layer 1

**Ngày soạn:** 06/11/2026.  
**Đối tượng:** Mô phỏng Tendermint BFT bằng sự kiện rời rạc trong `Workspace/`.  
**Trạng thái:** Dàn ý báo cáo và thiết kế kiểm thử; chưa thực thi test trong lần soạn tài liệu này. Các kết quả PASS/FAIL phải được cập nhật từ lần chạy thực tế.

## 1. Cấu trúc báo cáo đề xuất

Theo README hiện hành, báo cáo bàn giao tối đa 10 trang và không chèn mã nguồn. Có thể phân bổ như sau; nếu testing chỉ là một chương trong báo cáo chung thì rút gọn phần này còn 3–4 trang, giữ bảng T1–T8 và bằng chứng tiêu biểu.

| Phần | Nội dung cần viết | Dung lượng dự kiến |
|---|---|---|
| 1. Thông tin bài làm | Tên lab, thành viên, mã sinh viên, phiên bản mã nguồn được kiểm thử | 0,5 trang |
| 2. Mục tiêu và phạm vi | Safety, liveness, tính đúng của giao dịch, chữ ký, khả năng tái lập | 0,5 trang |
| 3. Môi trường và chiến lược | Python/thư viện thực tế, config, unit/integration/E2E/regression, oracle | 1 trang |
| 4. Thiết kế test | Cách tổ chức suite, dữ liệu chuẩn, tiêu chí PASS/FAIL, ma trận yêu cầu | 1 trang |
| 5. Kịch bản T1–T8 | Điều kiện, các bước, kết quả mong đợi và bằng chứng của từng nhóm | 3 trang |
| 6. Kết quả thực nghiệm | Bảng kết quả, số test thực chạy, log chọn lọc, state/ledger và lỗi | 2 trang |
| 7. Đánh giá và giới hạn | Mức bao phủ, kiểm thử bổ sung, hạn chế, kết luận theo bằng chứng | 1 trang |
| 8. Tài liệu tham khảo | Đề bài, tài liệu implementation, hướng dẫn test | 0,5 trang |

### Đoạn mở đầu có thể dùng trong báo cáo

Hệ thống được kiểm thử theo nhiều mức, từ các thành phần xử lý giao dịch và xác minh chữ ký đến toàn bộ mạng đồng thuận. Mục tiêu là kiểm tra việc từ chối dữ liệu không hợp lệ, duy trì tính nhất quán giữa các validator trung thực, tiếp tục chốt khối khi điều kiện mạng cho phép, và tái lập kết quả với cùng cấu hình đầu vào. Mỗi thí nghiệm được đánh giá bằng các bất biến trên ledger, trạng thái ứng dụng, chứng chỉ chốt khối và nhật ký sự kiện.

## 2. Phạm vi và tiêu chí đánh giá

### 2.1. Các thuộc tính phải kiểm tra

| Thuộc tính | Tiêu chí cụ thể |
|---|---|
| Safety | Tại mỗi height, tập hash block đã chốt trên những node trung thực có block ở height đó có nhiều nhất một phần tử. Quét đến height lớn nhất; không bỏ qua fork chỉ vì một node chưa có block. |
| Liveness/progress | Trong kịch bản có điều kiện phục hồi và thời gian mô phỏng đủ, mọi node trung thực chốt đủ số height mục tiêu. Không yêu cầu node Byzantine hoàn tất. |
| Validity | Mỗi block đã chốt có parent, giao dịch, state hash và chứng chỉ hợp lệ; certificate có ít nhất Q signer khác nhau ký PRECOMMIT đúng height/round/hash. |
| Exactly-once | Giao dịch hợp lệ được nhận và lan truyền; replay không gây thực thi thêm lần nữa. Nonce và dữ liệu cuối phải đúng giá trị dự kiến. |
| Authentication | Sửa nội dung đã ký, sai khóa, sai loại thông điệp hoặc sai chain ID phải bị từ chối. |
| Determinism | Cùng config, seed và identity fixture tạo log mô phỏng UTF-8 giống từng byte, ledger/state giống nhau và mọi honest node đều hoàn tất. |
| Observability | Log chứng minh lỗi/tấn công đã xảy ra và phản ứng tương ứng của hệ thống; log lỗi không thay thế assertion trên state/ledger. |

Safety và liveness được ghi nhận riêng: một mạng không chốt block nào có thể chưa vi phạm safety nhưng vẫn thất bại về tiến triển. Trước GST không đặt yêu cầu phải tiến triển; sau GST phải xét topology, timeout, throttling và `t_end` của thí nghiệm.

### 2.2. Cấu hình và dữ liệu nền

- Cấu hình nền lấy từ `Workspace/config/default.json`: `n=10`, `f=3`, `heights=5`, `seed=42`, `chain_id=lab01`, `delta=20`, `gst=1000`, `t_end=100000`.
- Quorum với cấu hình này: `Q=2f+1=7`. Runner chuẩn yêu cầu `n=3f+1`, `n>=8` và số Byzantine không vượt `f`.
- Tài khoản nền: Alice, Bob, Carol; mỗi tài khoản có 5 giao dịch, tối đa 10 giao dịch/block.
- Giá trị kỳ vọng khi toàn bộ giao dịch nền đã được thực thi: `Alice/msg`, `Bob/msg`, `Carol/msg` đều bằng `v5`; nonce mỗi tài khoản bằng 5.
- Identity fixture được giữ cố định; seed dùng điều khiển ngẫu nhiên mạng. Không đưa private key vào báo cáo/log minh họa.
- Config mặc định có duplicate/reorder và giới hạn lưu lượng. T1 phải ghi đè các tham số này để tạo mạng không lỗi; không dùng nguyên config demo rồi gọi đó là baseline.
- Mỗi kịch bản lưu đầy đủ config sau khi ghi đè, seed và danh sách node Byzantine. Thay đổi số height hoặc số giao dịch phải cập nhật expected tương ứng.

## 3. Cấu trúc viết test

### 3.1. Tổ chức theo bộ test hiện có

```text
Workspace/tests/
├── unit/                   # Executor, signature/domain, transport, sync handler...
├── integration/            # CLI logging và runner ghi kết quả
├── e2e/                    # T1–T8, catch-up, mạng lỗi, Byzantine, quorum boundary
├── regression/             # Phản ví dụ và lỗi cũ của consensus/network/CLI
├── c_helpers.py            # Fixture, tạo chữ ký, assertion dùng chung
├── independent_oracle.py   # Tính expected và kiểm ledger bằng logic độc lập
├── test_mutation_gate.py   # Bảy nhóm đột biến có chủ đích
└── __main__.py             # Runner lưu log riêng từng test
```

Đây là cấu trúc đã có trong repository; không cần tạo một bộ test trùng lặp. `regression/` phân nhóm theo mục đích chống tái phát lỗi và có thể chứa nhiều mức kiểm thử. Một số file E2E hiện cũng chứa ca kiểm tập trung trên node; mức kiểm thử nên xác định theo phạm vi thực chạy của từng ca.

### 3.2. Quy tắc cho mỗi test case

1. **Arrange:** Tạo fixture mới, config và dữ liệu có expected xác định trước. Không dùng trạng thái của ca khác.
2. **Act:** Đưa dữ liệu qua đúng đường cần kiểm. Test admission/gossip phải đi qua mạng thật; test handler riêng có thể gọi trực tiếp handler.
3. **Assert kích hoạt:** Xác nhận duplicate/drop/replay/equivocation hoặc timeout thực sự xảy ra. Nếu chưa kích hoạt lỗi thì chưa đủ bằng chứng cho mục tiêu kịch bản.
4. **Assert hành vi:** Kiểm nhận/từ chối dữ liệu, số vote, nonce, state, certificate và ledger; tách safety khỏi progress.
5. **Lưu bằng chứng:** Gắn test ID với config, seed, kết quả và file log; giữ traceback khi thất bại.

Đặt tên ca theo hành vi, ví dụ `test_t4_transaction_replay_prevention`; ca mở rộng có thể dùng dạng `test_<condition>_<expected_behavior>`. Một ca chỉ nên có một mục tiêu hành vi chính, dù cần nhiều assertion để chứng minh.

### 3.3. Mẫu mô tả một test case

| Trường | Nội dung cần điền |
|---|---|
| ID / tên | Ví dụ T4-01 — Replay giao dịch trước và sau commit |
| Yêu cầu / mục tiêu | Giao dịch được tiếp nhận lần đầu và chỉ thực thi một lần |
| Mức kiểm thử | Unit / integration / E2E; ghi thêm regression nếu phù hợp |
| Tiền điều kiện | Fixture mới, trạng thái ban đầu, tập honest/Byzantine |
| Đầu vào | Config, seed, giao dịch/thông điệp và thời điểm tiêm lỗi |
| Bước thực hiện | Hành động có thứ tự và tái lập được |
| Expected / oracle | Giá trị cụ thể và bất biến cần thỏa |
| Actual / kết quả | Giá trị quan sát, PASS/FAIL/ERROR/SKIP hoặc CHƯA CHẠY |
| Bằng chứng | Test ID đầy đủ, log, summary, config và phiên bản mã nguồn |

## 4. Kịch bản kiểm thử trọng tâm T1–T8

Các mô tả dưới đây bám theo test hiện có. Các yêu cầu tăng cường được ghi rõ để không nhầm với assertion đã được thực thi hoặc đã có sẵn.

### T1 — Mạng bình thường, không lỗi

**Mục tiêu:** Kiểm tra luồng PROPOSE → PREVOTE → PRECOMMIT → FINALIZE và tính đúng của trạng thái cuối.

**Thiết lập:** `seed=42`, `gst=0`, `delta=1`, không Byzantine; drop/duplicate/reorder bằng 0; `rate_limit=None`, `peer_block=None`; 10 node, 5 height và 15 giao dịch nền.

**Các bước:** (1) Khởi tạo mạng sạch. (2) Chạy đến hết hoặc đủ 5 height. (3) Đối chiếu toàn bộ ledger/certificate/state/nonce giữa các node và với expected. (4) Kiểm các sự kiện lỗi và timeout.

**PASS khi:** Mọi node `done=True`, chốt đúng 5 block ở round 0, certificate cũng ở round 0; chuỗi giống nhau; ba giá trị ứng dụng đều `v5`, ba nonce đều 5; không có DROP, DUPLICATE, reorder hoặc TIMEOUT. Hash trạng thái phải khớp nội dung dự kiến, không chỉ khớp nhau giữa các node.

**Bằng chứng:** FINALIZE theo height/round, bảng số block và state/nonce của từng node. File: `e2e/test_t1_normal.py`.

### T2 — Thông điệp lặp và đảo thứ tự

**Mục tiêu:** Kiểm tra vote trùng chỉ được tính một lần và mạng không chốt các block mâu thuẫn.

**Thiết lập:** Nhánh mạng dùng `seed=42`, `gst=5000`, `pre_gst_max_delay=50`, duplicate 0,25, reorder 0,35 và drop 0. Nhánh tập trung tạo hai PREVOTE được cùng voter ký, cùng height/round nhưng khác block hash. Nhánh replay dùng V2 phát lại thông điệp cũ.

**Các bước:** (1) Chạy mạng có duplicate/reorder. (2) Gửi cùng vote A ba lần vào node nhận mới. (3) Gửi vote B mâu thuẫn trong cùng slot. (4) Chạy biến thể Byzantine replay. Mỗi nhánh dùng fixture độc lập.

**PASS khi:** Có DUPLICATE và DELAY với `reason=reorder`; voter chỉ chiếm một entry trong slot; vote B không thay vote A và có EQUIVOCATION. Biến thể replay phải có BYZ_REPLAY. Ledger honest không fork và mọi certificate đã chốt hợp lệ.

**Bằng chứng:** Log duplicate/reorder/equivocation/replay và số entry của voter. File: `e2e/test_t2_duplicate_reorder.py`; đối chiếu thêm `e2e/test_consensus_network.py` cho ca có assertion hoàn tất mạng.

### T3 — Chữ ký hoặc domain không hợp lệ

**Mục tiêu:** Từ chối thông điệp giả mà không làm gián đoạn tiến triển của honest node.

**Thiết lập:** Biến thể chữ ký bị đổi byte/rỗng, payload bị sửa sau ký, signer không biết, sai domain loại thông điệp và sai chain ID. E2E tiêm vote/header/transaction lỗi và certificate giả.

**Các bước:** (1) Chạy ca đối chứng với chữ ký hợp lệ. (2) Với mỗi fixture mới, thay một điều kiện xác thực. (3) Gửi thông điệp vào handler tương ứng hoặc tiêm vào hàng đợi mạng ở E2E. (4) Kiểm không có tác động hợp lệ từ dữ liệu lỗi. (5) Cho mạng tiếp tục chốt khối.

**PASS khi:** Có lý do phù hợp như `bad_vote_sig`, `bad_header_sig`, `bad_tx_sig` hoặc `REJECT_SYNC reason=invalid_cert_sig`; vote lỗi không được đếm, proposal/transaction lỗi không vào đường xử lý hợp lệ; block/certificate giả không vào ledger. Mọi honest node trong E2E vẫn chốt đủ 5 height, không fork và có certificate hợp lệ.

**Bằng chứng:** REJECT/REJECT_SYNC theo loại lỗi, snapshot vote/mempool/ledger và FINALIZE sau thời điểm tiêm lỗi. Files: `unit/test_t3_signatures.py`, `e2e/test_t3_invalid_signatures.py`.

### T4 — Replay giao dịch và nonce

**Mục tiêu:** Chứng minh giao dịch được nhận lần đầu qua mạng, lan truyền và thực thi đúng một lần dù bị replay.

**Thiết lập:** Mempool và seen set ban đầu rỗng; không bootstrap giao dịch (`txs_per_account=0`); 3 height, tối đa 1 giao dịch/block; Alice ký giao dịch nonce 1, key `Alice/msg`, value `first-network-transaction`.

**Các bước:** (1) Gửi cùng TX hai lần bằng `Net.send`. (2) Cho TX gossip trước khi chốt. (3) Sau khi quan sát commit, broadcast lại TX. (4) Kiểm toàn bộ ledger/state/nonce của mọi node bằng oracle độc lập.

**PASS khi:** Mỗi node tiếp nhận hợp lệ lần đầu đúng một lần; replay sau commit thực sự được gửi; TX xuất hiện đúng một lần trong ledger mỗi node; `Alice/msg` đúng giá trị đầu vào, nonce Alice bằng 1; mempool cuối rỗng và chốt đủ 3 height.

**Bằng chứng:** TX_RECEIVED, thời điểm phát lại, số lần TX xuất hiện và state/nonce cuối. File: `e2e/test_t4_replay_tx.py`. Duplicate có thể bị lọc bởi seen set nên không bắt buộc mọi replay đều sinh `bad_nonce`; kiểm nonce sai riêng ở mức executor.

### T5 — Drop/delay trước GST và phục hồi

**Mục tiêu:** Kiểm safety khi mạng chưa ổn định; đánh giá progress sau GST riêng.

**Thiết lập:** Các seed 42, 43, 44, 99; `gst=1500`, pre-GST delay tối đa 200, drop 0,15, reorder 0,20, `delta=20`, 5 height. Biến thể nặng: seed 7, `gst=2000`, delay 300, drop 0,40, reorder 0,30, 3 height.

**Các bước:** (1) Chạy từng seed bằng mạng mới. (2) Xác nhận mất gói trước GST. (3) Kiểm mọi height đã chốt và certificate. (4) Đánh giá sự kiện sau GST và việc hoàn tất nếu kịch bản có assertion progress.

**PASS về safety khi:** Có lỗi mạng thực sự trong nhánh yêu cầu kích hoạt; không có hai hash đã chốt khác nhau ở cùng height trên honest node; certificate hợp lệ.

**Đánh giá bổ sung:** `e2e/test_t5_gst_safety.py` chủ yếu kiểm safety, không đủ để kết luận mọi node đã phục hồi. Muốn ghi PASS về liveness phải có assertion chốt đủ height và bằng chứng FINALIZE sau phục hồi. Cận sau GST là từ SEND đầu đến RECEIVE cuối của toàn tuyến, không cộng `delta` theo từng hop; thời gian chờ admission trước SEND được đánh giá riêng.

**Bằng chứng:** DROP với `reason=pre_gst`, timestamp quanh GST, FINALIZE và trạng thái hoàn tất. Files: `e2e/test_t5_gst_safety.py`, các ca mạng trong `unit/test_sim.py`, `e2e/test_consensus_network.py`, `regression/test_network.py`.

### T6 — Proposer im lặng

**Mục tiêu:** Kiểm timeout, chuyển round và khả năng tiếp tục chốt block.

**Thiết lập:** Nhánh 1: V1 im lặng toàn bộ, seed 42. Nhánh 2: V1, V4, V7 im lặng, seed 10; còn 7 honest node, vừa đủ quorum.

**Các bước:** (1) Khởi tạo hành vi Silent qua factory của chương trình. (2) Chạy đến timeout round 0. (3) Theo dõi proposer/round ở height 1. (4) Kiểm ledger/certificate và hoàn tất của toàn bộ honest node.

**PASS khi:** Nhánh 1 có TIMEOUT loại PROPOSE tại height 1, round 0 trên mọi honest node; block đầu chốt ở round 1 với proposer V2. Cả hai nhánh đều chốt đủ 5 height trên mọi honest node, không fork và certificate hợp lệ.

**Bằng chứng:** TIMEOUT, FINALIZE và thông tin proposer/round của block đầu. File: `e2e/test_t6_silent_proposer.py`.

### T7 — Byzantine equivocation

**Mục tiêu:** Kiểm phản ứng khi validator ký hoặc đề xuất dữ liệu mâu thuẫn, với số Byzantine không vượt `f=3`.

**Thiết lập:** Bốn biến thể: V1 phát hai proposal; V1 gửi proposal khác nhau cho hai nhóm; V3/V5/V7 bỏ phiếu mâu thuẫn; liên minh V1 equivocate proposer cùng V4/V7 equivocate voter. Dùng seed 42, mục tiêu 5 height.

**Các bước:** (1) Cấu hình từng biến thể riêng. (2) Chạy qua Byzantine factory thật. (3) Kiểm BYZ_EQUIVOCATE_PROPOSAL/BYZ_EQUIVOCATE_VOTE và EQUIVOCATION ở các ca có assertion tương ứng. (4) Đối chiếu toàn bộ ledger, certificate và tiến triển của honest node.

**PASS khi:** Hành vi tấn công theo ca đã được kích hoạt; không có hai block mâu thuẫn được honest node chốt tại cùng height; mọi honest node chốt đủ 5 height và certificate hợp lệ. Không yêu cầu Byzantine có ledger đúng.

**Giải thích:** Với `n=10`, `Q=7`, hai quorum giao nhau ít nhất 4 validator, trong đó có ít nhất một honest khi Byzantine tối đa 3. Lập luận safety qua nhiều round còn cần quy tắc lock và bằng chứng POLKA; chỉ kiểm một vote mỗi slot chưa đủ. Kết quả của các ca hữu hạn là bằng chứng thực nghiệm, không phải chứng minh cho mọi chiến lược Byzantine.

**Bằng chứng:** Log hành vi Byzantine, EQUIVOCATION, FINALIZE và tập signer certificate. File: `e2e/test_t7_equivocation.py`.

### T8 — Tính tất định và khả năng tái lập

**Mục tiêu:** Chạy lại cùng đầu vào phải cho cùng kết quả hoàn chỉnh.

**Thiết lập:** Hai lần chạy độc lập trạng thái với cùng config/seed/identity fixture. Các biến thể hiện có: seed 42; seed 1/99/1337; mạng hỗn loạn seed 77; Byzantine seed 123. Số height dùng theo từng ca.

**Các bước:** (1) Tạo hai mạng mới. (2) Chạy với đầu vào như nhau. (3) So sánh log mô phỏng đã serialize UTF-8 theo byte. (4) Kiểm đúng tập honest node, `done`, số height, ledger, state data, nonce và state hash bằng oracle độc lập. (5) Chạy đối chứng âm: hai lần đều dừng sớm; chỉ V9 sai trong khi log và V0 giữ nguyên.

**PASS khi:** Hai lần đều hoàn tất đúng trên mọi honest node, log giống từng byte và ledger/state đúng expected. Đối chứng âm phải bị assertion phát hiện. Hai lần chạy cùng bị kẹt không được tính là thành công tất định.

**Bằng chứng:** Kết quả so sánh log, bảng trạng thái tất cả honest node, kết quả đối chứng âm. File: `e2e/test_t8_determinism.py`. Bổ sung bằng chứng CLI ở hai process độc lập từ `regression/test_cli.py`; không đồng nhất hai simulation trong một process với hai process riêng. Khi so byte dùng log mô phỏng gốc, không dùng wrapper log chứa metadata riêng từng test/network.

## 5. Nhóm kiểm thử bổ sung cần đưa vào ma trận

Các nhóm này đã có phạm vi tương ứng trong suite hiện hành; cần đối chiếu tên method và kết quả chạy trước khi khẳng định mức bao phủ cụ thể trong báo cáo cuối.

| Nhóm | Kịch bản cần mô tả / đánh giá | Nơi đối chiếu |
|---|---|---|
| Execution | Nonce cũ/nhảy cóc, chữ ký sai, ghi ngoài namespace, batch lỗi không đổi state gốc | `unit/test_executor.py` |
| Lock/POLKA | Proof thiếu hoặc giả không mở khóa; bằng chứng quorum hợp lệ hỗ trợ tiến triển; không ký hai lần cùng slot | `regression/test_consensus.py` |
| Header/body | Body thiếu/sai root/không khớp header; retry; buffer không bị proposal tương lai làm nghẽn | `regression/test_consensus.py`, `regression/test_review_fixes.py` |
| Catch-up | Node chậm nhận header/certificate/body rồi tự xác minh; duplicate sync không execute lại | `unit/test_sync_request.py`, `e2e/test_sync_catchup.py` |
| Network | Routing nhiều hop, giới hạn toàn node, cận toàn tuyến sau GST, payload không shared mutable | `unit/test_sim.py`, `regression/test_network.py` |
| Config/CLI | Cấu hình sai bị từ chối; hết `t_end` chưa hoàn tất trả code 1/INCOMPLETE; chạy hai process | `regression/test_cli.py` |
| Test logging | Không làm thay đổi logger gốc; lưu lỗi/subtest/setup error; giữ log subprocess | `unit/test_event_logging.py`, `integration/test_event_logging_cli.py` |
| Quorum boundary | Thử nghiệm ngoài giả định BFT bằng runner riêng; không dùng để kết luận runner chuẩn sai | `e2e/test_quorum_boundary.py` |
| Mutation gate | Assertion phải bắt được việc vô hiệu hóa các kiểm tra quan trọng | `test_mutation_gate.py` |

Mutation gate hiện có bảy nhóm: tắt admission/gossip TX; bỏ qua Byzantine factory; chấp nhận chữ ký sai; chấp nhận domain sai; bỏ nonce guard; đếm vote trùng; bỏ state-root check. PASS của mutation test nghĩa là assertion dự kiến phát hiện mutant; lỗi fixture hoặc exception không liên quan không được coi là phát hiện thành công.

Oracle độc lập kiểm encoding, hash, chữ ký, thực thi, parent link và finality để hạn chế việc các node cùng tạo một kết quả sai nhưng vẫn khớp nhau. Không lấy trực tiếp output production làm toàn bộ expected.

## 6. Quy trình thực thi và thu thập bằng chứng

Thực hiện từ thư mục `Workspace`. README ghi nhận Python 3.12 và dependency `cryptography==50.0.2`; báo cáo cuối phải điền phiên bản thực tế của máy chạy.

```powershell
python --version
python -m pip show cryptography
git rev-parse HEAD
git status --short

# Toàn bộ suite, lưu log riêng từng test và summary.json
python -X utf8 -B -m tests -v

# Chạy từng nhóm khi cần phân tích
python -X utf8 -B -m unittest discover -s tests/unit -t . -v
python -X utf8 -B -m unittest discover -s tests/integration -t . -v
python -X utf8 -B -m unittest discover -s tests/e2e -t . -v
python -X utf8 -B -m unittest discover -s tests/regression -t . -v

# Chạy một kịch bản với log riêng
python -X utf8 -B -m tests -v tests.e2e.test_t1_normal
```

Runner có log tạo `Workspace/logs/tests/run-<unique>/`; lấy đường dẫn chính xác từ output. `summary.json` ánh xạ test ID, status và file log. Lưu thêm config thực dùng và thông tin commit/working tree; commit hash đơn lẻ không mô tả được thay đổi chưa commit.

Không cộng số test của các lệnh chạy lặp thành tổng số test độc lập. Ghi rõ số test method, số biến thể/subtest và số lần chạy nếu thống kê cả ba.

### Bộ bằng chứng tối thiểu

1. Thời điểm chạy, môi trường, mã nguồn và config/seed.
2. Output runner và `summary.json`, gồm cả failure/error/skip.
3. Log cho thấy fault được kích hoạt và phản ứng của hệ thống.
4. Assertion hoặc bảng ledger/state/nonce/certificate trên mọi honest node.
5. Với lỗi: traceback, test ID, actual so với expected và cách tái lập.

Nếu rút log để đưa vào báo cáo, ghi rõ đó là trích đoạn và giữ file đầy đủ trong bộ bàn giao. Không tự tạo dòng log rồi trình bày như kết quả quan sát.

## 7. Mẫu bảng kết quả để hoàn thiện sau khi chạy

| Kịch bản | Đã kích hoạt điều kiện? | Safety/validity | Progress/đúng state | Kết quả thực chạy | Bằng chứng |
|---|---|---|---|---|---|
| T1 — Bình thường | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |
| T2 — Duplicate/reorder | Chưa ghi nhận | Chưa đo | Ghi theo ca có assertion | CHƯA CHẠY | — |
| T3 — Chữ ký/domain sai | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |
| T4 — Replay giao dịch | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |
| T5 — Drop/delay trước GST | Chưa ghi nhận | Chưa đo | Đánh giá phục hồi riêng | CHƯA CHẠY | — |
| T6 — Proposer im lặng | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |
| T7 — Equivocation | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |
| T8 — Tái lập | Chưa ghi nhận | Chưa đo | Chưa đo | CHƯA CHẠY | — |

Mỗi nhóm T1–T8 có thể gồm nhiều ca; báo cáo nhóm chỉ ghi PASS khi tất cả ca thuộc phạm vi công bố đều đạt. SKIP hoặc chưa chạy không được tính là PASS. Trường hợp safety đạt nhưng progress không đạt phải mô tả cả hai.

### Mẫu đoạn viết kết quả

> Bộ kiểm thử được thực thi trên [môi trường], với mã nguồn [commit và trạng thái working tree], cấu hình [đường dẫn/config] vào [thời điểm]. Runner ghi nhận [N] test, gồm [P] đạt, [F] thất bại, [E] lỗi và [S] bỏ qua. Trong kịch bản [ID], log [file] ghi nhận [sự kiện lỗi/tấn công]; các assertion xác nhận [ledger/state/certificate/progress quan sát được]. Những ca chưa thực thi hoặc chưa có bằng chứng được liệt kê riêng.

## 8. Điều kiện kết luận báo cáo

- Suite thuộc phạm vi công bố phải chạy xong, không có failure/error; mọi skip được giải thích.
- Mỗi kịch bản lỗi có bằng chứng đã kích hoạt đúng điều kiện thử.
- Safety được kiểm trên mọi honest node và mọi height có block, kể cả khi độ dài ledger khác nhau.
- Progress được kiểm riêng trong các kịch bản yêu cầu phục hồi; không suy ra từ việc không có fork.
- Expected state/nonce và certificate được kiểm, không chỉ đếm số block hay so hash giữa các node.
- T8 kiểm mọi honest node, log bytes và tính hoàn tất; có đối chứng âm và bằng chứng hai process nếu công bố khả năng tái lập ở mức đó.
- Mutation gate vẫn hiệu quả; không sửa expected chỉ để khớp kết quả đang lỗi.

Chỉ kết luận hệ thống đáp ứng các kịch bản và giả định đã kiểm thử. Các seed hữu hạn và bảy nhóm mutation không bao phủ mọi lịch sự kiện hay mọi chiến lược Byzantine. Thời gian mô phỏng ảo không được trình bày thành hiệu năng mạng thực hoặc TPS triển khai thực tế.

## 9. Nguồn đối chiếu trong repository

- `Document/Lab01.pdf`: yêu cầu bài lab; đối chiếu trực tiếp khi hoàn thiện báo cáo nộp.
- `README.md`: cách chạy, mô hình BFT và quy cách bàn giao.
- `Document/IMPLEMENTATION.md`: implementation hiện hành và giới hạn phạm vi.
- `Workspace/tests/README.md`: acceptance gate, oracle, fault schedule, mutation và logging.
- `Workspace/config/default.json`: cấu hình nền.
- `Workspace/tests/unit/`, `integration/`, `e2e/`, `regression/`: hành vi/assertion thực tế.

Không dùng trạng thái milestone lịch sử trong `PROJECT.md`, ZIP cũ hoặc số PASS trong review cũ làm kết quả của lần chạy hiện tại.
