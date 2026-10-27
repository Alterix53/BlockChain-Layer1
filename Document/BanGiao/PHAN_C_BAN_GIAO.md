# Bàn giao phần C (Byzantine) — sau khi tích hợp B và D

Ngày 27/10/2026. Dựa trên `main` sau khi đã merge B (commit `4b44ed4`) và D (PR #2, `c9e6848`).
- Đợt 1 (PR #3, nhánh `feature/part-C`): phần C, cùng các lỗi B2, B3, D2, D3 ở mục 2 và mục 3.
- Đợt 2 (nhánh `fix/part-D-sync`): C làm nốt các việc còn lại của D (mục 3b). **@D xem kỹ mục 3b.**

## 1. Phần C có gì

| File | Nội dung |
|---|---|
| `Workspace/src/byzantine.py` | 5 hành vi Byzantine, mỗi hành vi là lớp con của `Node`: `Silent`, `EquivocateVoter`, `EquivocateProposer`, `InvalidBlock` (7 kiểu block sai), `Replay`. Thêm `ForkCoalition` cho thí nghiệm n=9, cùng `REGISTRY` và `make_node(...)` để E dùng làm factory. |
| `Workspace/tests/test_byzantine.py` | T7. Mỗi hành vi có test riêng lẻ (unit) và test chạy trên mạng `sim.py` thật. Các test mạng đều kiểm safety, liveness và certificate trên node honest. |
| `Workspace/tests/test_t3.py` | T3: chữ ký sai hoặc sai domain thì bị loại **và có ghi lý do**, trên cả 5 đường nhận: vote, header, tx trong block, certificate khi đồng bộ (D), tx gossip (D). Có thêm 1 test chạy đầu-cuối. |
| `Workspace/tests/test_quorum_boundary.py` | Thí nghiệm ngoài giả định: n=9, Q=6 thì fork; đối chứng n=10, Q=7 thì không fork; n=9, Q=7 thì không fork nhưng mất liveness. |
| `Workspace/tests/c_helpers.py` | Hàm dùng chung: mạng giả, dựng node, ký vote/header/certificate, kiểm safety, liveness và certificate. |

Chạy (từ thư mục `Workspace`):

```bash
python -m unittest discover -s tests -v            # 80 test (gồm cả test của D), kết quả: OK
python tests/test_quorum_boundary.py --report      # in kết quả thí nghiệm n=9 / n=10
python -m src.main --twice                         # vẫn tất định, state hash 0b837be9...
```

Từ đợt 2, `unittest discover` chạy luôn test của D trong `tests/unit` và `tests/e2e` (mục 3b).

## 2. Vấn đề gặp phải sau khi pull B

| # | Vấn đề | Đã xử lý |
|---|---|---|
| B1 | `Header` thêm `pol_round` vào **giữa** các trường, nên mọi chỗ tạo `Header(...)` theo vị trí bị lệch. 36 test của C vỡ ngay sau khi pull. | Phía C: mọi chỗ tạo header đều dùng tên trường (`Header(height=..., pol_round=..., ...)`), và dùng lại `seal()` của B. **Khuyên cả nhóm cũng tạo `Header`/`Vote` bằng tên trường.** |
| B2 | **Lỗi liveness** trong `on_proposal`: chỉ lưu thân của proposal **đến trước**. Nếu proposer Byzantine gửi 2 block và block đến sau đạt Q precommit, node không có thân để `finalize` và **kẹt mãi** ở height đó. Ví dụ seed 2: V7 và V9 có 0 block trong khi node khác đủ 5. | **Đã sửa trong `node.py`**: vẫn prevote theo proposal đến trước, nhưng giữ thân của mọi proposal hợp lệ (`self.blocks.setdefault(...)`). |
| B3 | Cùng lỗi đó ở **height tương lai**: `self.future` chỉ giữ 1 block cho mỗi (h, r). Node nhận cả 2 block của height h+1 khi còn ở height h thì vẫn kẹt (h=2: seed 1 và seed 14). | **Đã sửa**: thêm `self.future_blocks[(h, hash)]` giữ mọi thân đến sớm, `start_height` nạp lại. Đã chạy 150 lần (height 1–5 × 30 seed): không kẹt, không fork. |

## 3. Vấn đề gặp phải sau khi pull D

| # | Vấn đề | Đã xử lý |
|---|---|---|
| D1 | `CertRecorder` (bản tạm của C để chụp certificate) vỡ vì `finalize(b, cert)` đổi chữ ký hàm. | Phía C: bỏ bản tạm, dùng `node.certificates` thật của D. |
| D2 | `on_tx` bỏ tx sai chữ ký, sai domain, sai chủ **im lặng**, trong khi T3 yêu cầu ghi lý do. | **Đã sửa trong `node.py`**: log `REJECT reason=unknown_sender / bad_tx_sig / not_owner` kèm `sender`, `nonce`. |
| D3 | `on_sync_response` **không kiểm `tx_root(blk.txs) == header.tx_root`**. `Block.hash()` chỉ băm header, nên peer Byzantine có thể đảo thứ tự hoặc thay tx mà certificate vẫn khớp và state cuối vẫn giống. Kết quả: node lưu thân block khác với thứ đã được đồng thuận. | **Đã sửa**: log `REJECT_SYNC reason=bad_tx_root` trước khi kiểm chữ ký. |
| D4 | Certificate có người ký không phải validator thì bị log `insufficient_cert_sigs`, gộp chung với lý do "thiếu chữ ký". | **Đã tách (đợt 2)**: `REJECT_SYNC reason=unknown_signer`. |

Các chỗ C đã sửa trong `node.py` đều có test giữ lại (nếu ai hoàn tác, test sẽ đỏ). **B và D nhớ pull trước khi sửa tiếp `node.py`** để tránh xung đột.

## 3b. Đợt 2: C làm nốt phần đồng bộ của D — @D check lại giúp

| # | Trước đây | Bây giờ (trong `node.py`) | Test |
|---|---|---|---|
| D5 | **Không node nào gửi `SYNC_REQ`**, nên node bị tụt lại (mất tin, bị cô lập, thiếu thân block) kẹt mãi. | `request_sync()`: khi **hết cả một round** (timeout `ROUND`) mà chưa chốt được, node broadcast `SYNC_REQ(from=height hiện tại, to=height + max_ahead)` và log `SYNC_REQUEST`. Hỏi thừa vô hại: ai chưa có thì không trả lời, trả lời sai thì bị `REJECT_SYNC`. Lần chạy bình thường **không** phát sinh tin nào (log `main` giống hệt trước). | `tests/e2e/test_sync_catchup.py`: V9 bị cô lập tới GST=3000 (lỡ cả 5 height) hoặc GST=300 (kẹt ở height cuối), cả hai đều tự bắt kịp, cùng chuỗi. |
| D6 | Node đã chốt xong (`done`) bỏ qua mọi tin, kể cả `SYNC_REQ`, nên node tụt ở height cuối không có ai trả lời. | `on_message` xử lý `SYNC_REQ` **trước** khi xét `done`. | `test_done_node_still_serves` |
| D7 | `on_sync_request` lặp `range(from_height, to_height)` theo số do **người lạ** gửi: `to_height=10**12` treo node (DoS). Người hỏi không phải validator vẫn được xử lý. | Chặn khoảng: từ `max(1, from)`, tối đa `max_ahead + 1` block, chỉ height đã có certificate. Bỏ qua người hỏi lạ và chính mình. | `test_requested_range_is_bounded` |
| D8 | `on_sync_request` tìm người hỏi bằng `self.net.nodes` và gọi thẳng `net.push` (bỏ qua mạng). | Tìm bằng `ctx["vals"].index(...)`. Gửi qua `send_to(dst, msg)`: Net có `send` (của A) thì dùng; chưa có thì giữ cách cũ `net.push`. | (dùng chung các test trên) |
| D9 | Chốt qua đồng bộ tự làm lại một phần `finalize` nhưng **thiếu dọn mempool, votes, future**: tx đã chốt vẫn nằm trong mempool. | Kiểm xong thì gọi luôn `self.finalize(blk, cert)` (log thêm `SYNC_CATCHUP_SUCCESS` như cũ). Kiểm chữ ký certificate viết gọn lại (`Vote(...).body()` thay cho cắt ghép list). | `test_synced_block_is_cleaned_like_finalize` |
| D10 | Thư mục `src/node/` và `src/execution/` không được import ở đâu, dùng API không tồn tại, và bị `node.py`/`execution.py` che. | **Đã xóa** (vẫn xem lại được trong lịch sử git, commit `a32524b`). | — |
| D11 | Test của D viết kiểu `pytest`, nên lệnh `unittest` chung không chạy tới. | Bọc vào lớp `unittest.TestCase` (nội dung kiểm tra giữ nguyên), thêm `__init__.py` cho `tests/unit`, `tests/e2e`. `pytest` vẫn chạy được. | 7 test của D chạy chung: tổng 80 test OK |

Thí nghiệm n=10 của C nhờ vậy cũng tự chạy trọn: nhóm L (thiếu thân block B) tự hỏi đồng bộ sau một round thất bại và bắt kịp bằng certificate của nhóm R. Trước đây test phải tự đưa certificate vào bằng tay.

**@D check giúp mấy điểm:** (1) kích hoạt theo timeout `ROUND` có hợp ý D không, hay D muốn thêm cách khác (ví dụ thấy f+1 validator ở height cao hơn thì hỏi ngay); (2) giới hạn `max_ahead + 1` block mỗi lần trả lời; (3) D có cần gì trong 2 thư mục đã xóa không.

## 4. Việc còn lại cho A (mạng) — bàn giao

C đã viết sẵn những phần cần mạng, nhưng một số chỗ đang dùng bản TẠM, chờ A:

1. **`Net.send(src, dst, msg)`**: gửi cho đúng một node, đi qua cùng pipeline với `broadcast` (độ trễ, log `SEND`, sau này thêm drop/dup/reorder).
   - `ByzantineBase.send_to` gọi đúng hàm này. Khi Net chưa có, tấn công kiểu "gửi riêng hai nhóm" (`groups=...`) báo `RuntimeError("... chờ phần A")`.
2. **GST / chia cắt mạng (partition)**: trước GST, adversary được giữ tin giữa hai nhóm; sau GST, mọi tin tới trong `delta`.
   - `tests/test_quorum_boundary.py::PartitionNet` là bản **tạm** làm đúng việc này. Khi A merge, thay bằng Net của A và xóa `PartitionNet`.
3. **Mọi loại tin phải đi qua Net**: `Node.send_to` (dùng cho `SYNC_RESP`) đã tự gọi `net.send` khi Net có hàm này. Khi A xong `send`, chỉ cần xóa nhánh `net.push` dự phòng trong `Node.send_to` (đánh dấu `TODO(A)`).
4. **Log `SEND` cho mọi loại tin** (`TX`, `SYNC_REQ`, `SYNC_RESP`), không chỉ `PROPOSAL`/`VOTE`. `sim.py` hiện dùng `getattr(msg[1], "height", 0)`, nên giữ cách này hoặc cho mỗi kiểu tin có `height`.
5. Nếu A làm giao thức `HEADER -> REQUEST_BODY -> BODY`: phía C chỉ phải sửa `ByzantineBase.send_proposal` (đã đánh dấu `TODO(A)`).

Sau khi A merge, C sẽ (hoặc A làm giúp):
- Đổi `test_groups_need_net_send_from_part_a` trong `test_byzantine.py`: Net thật đã có `send` thì tấn công theo nhóm chạy được trên mạng thật.
- Chạy lại `test_quorum_boundary.py` với Net của A (gst=5000 và gst=0), kết quả phải giữ nguyên.

## 5. Việc cho D và E

**D**
- Các việc trước đây ghi cho D (kích hoạt `SYNC_REQ`, dọn 2 thư mục thừa, chạy test chung) **C đã làm ở đợt 2**, xem mục 3b. D chỉ cần review và góp ý.

**E (tích hợp / test)**
- Factory theo config: dùng `src/byzantine.py::make_node(behavior, idx, ctx, kp, **params)`, **cấu hình trước khi START** (proposer gọi `propose()` ngay trong `start()`). Ví dụ cho `main.py`:
  ```python
  from .byzantine import make_node
  byz = {int(k): v for k, v in cfg.get("byzantine", {}).items()}   # {"1": {"behavior": "silent"}}
  net.nodes = [make_node(byz.get(i, {}).get("behavior", "honest"), i, ctx, vkps[i],
                         **{k: v for k, v in byz.get(i, {}).items() if k != "behavior"})
               for i in range(n)]
  ```
  Khi có factory này thì xóa `mock.patch` trong `tests/c_helpers.py::run_with_byzantine` (đang đánh dấu TẠM).
- **`main.check_safety` sai**: lấy `min(len(ledger))`, nên chỉ cần 1 node chưa chốt gì (ví dụ node `Silent`) là bỏ qua toàn bộ kiểm tra, fork cũng không phát hiện được. Nên kiểm theo từng height trên các node honest, như `c_helpers.assert_honest_safety` (đã có test cho chính hàm này: `TestSafetyChecker`).
- Node `Silent(mode="all")` không bao giờ `done`. Mô phỏng vẫn dừng nhờ `t_end`, nhưng điều kiện dừng "mọi node done" (nếu E thêm) phải bỏ qua node Byzantine.
- Trình chạy test chung: hiện mọi test đều là `unittest`, chạy bằng `python -m unittest discover -s tests`. Nếu E muốn dùng `pytest` thì vẫn chạy được, không phải sửa test.

**B**
- Sau sửa B2/B3, một proposer Byzantine có thể gửi nhiều block khác nhau cho cùng (h, r) và mọi thân hợp lệ đều được giữ, nên bộ nhớ tăng theo số block nó ký. Trong mô phỏng không đáng kể. Nếu muốn chặt hơn: chỉ giữ thân block khi đã thấy vote cho hash đó, hoặc giới hạn số thân mỗi (h, r) và dựa vào đồng bộ của D để lấy phần thiếu.

## 6. Tóm tắt ai làm gì

| Ai | Việc | Mức độ |
|---|---|---|
| A | `send(src, dst, msg)`, GST/partition, drop/dup/reorder; xóa nhánh `net.push` dự phòng trong `Node.send_to` | Cần cho tấn công theo nhóm trên mạng thật và cho T6 |
| D | Review mục 3b (đồng bộ tự kích hoạt, giới hạn khoảng, 2 thư mục đã xóa, test chuyển sang `unittest`) | Góp ý, không còn việc bắt buộc |
| E | Factory `make_node` theo config; sửa `check_safety` | Cần để chạy T7 bằng config |
| B, D | Pull bản sửa `node.py` (đợt 1 và đợt 2) trước khi sửa tiếp | Tránh xung đột |
| C | Sau khi A merge: bỏ `PartitionNet`, cập nhật test `groups` | Nhỏ |
