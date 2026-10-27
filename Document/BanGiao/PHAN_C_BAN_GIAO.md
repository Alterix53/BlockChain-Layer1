# Bàn giao phần C (Byzantine) — sau khi tích hợp B và D

Ngày 27/10/2026. Nhánh `feature/part-C`. Dựa trên `main` sau khi đã merge B (commit `4b44ed4`) và D (PR #2, `c9e6848`).

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
python -m unittest discover -s tests -v            # 67 test, kết quả: OK
python tests/test_quorum_boundary.py --report      # in kết quả thí nghiệm n=9 / n=10
python -m src.main --twice                         # vẫn tất định, state hash 0b837be9...
```

Lưu ý: `unittest discover` **không** chạy 7 test của D trong `tests/unit`, `tests/e2e`, vì các test này viết theo kiểu pytest. Xem mục 5.

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
| D4 | Certificate có người ký không phải validator thì bị log `insufficient_cert_sigs`, gộp chung với lý do "thiếu chữ ký". | Chưa đổi (vẫn đúng hành vi, chỉ lý do chưa tách). D có thể tách thành `unknown_signer` nếu muốn; khi đó sửa 1 dòng trong `test_t3.py::test_unknown_signer`. |

Các chỗ C đã sửa trong `node.py` đều có test giữ lại (nếu ai hoàn tác, test sẽ đỏ). **B và D nhớ pull trước khi sửa tiếp `node.py`** để tránh xung đột.

## 4. Việc còn lại cho A (mạng) — bàn giao

C đã viết sẵn những phần cần mạng, nhưng một số chỗ đang dùng bản TẠM, chờ A:

1. **`Net.send(src, dst, msg)`**: gửi cho đúng một node, đi qua cùng pipeline với `broadcast` (độ trễ, log `SEND`, sau này thêm drop/dup/reorder).
   - `ByzantineBase.send_to` gọi đúng hàm này. Khi Net chưa có, tấn công kiểu "gửi riêng hai nhóm" (`groups=...`) báo `RuntimeError("... chờ phần A")`.
2. **GST / chia cắt mạng (partition)**: trước GST, adversary được giữ tin giữa hai nhóm; sau GST, mọi tin tới trong `delta`.
   - `tests/test_quorum_boundary.py::PartitionNet` là bản **tạm** làm đúng việc này. Khi A merge, thay bằng Net của A và xóa `PartitionNet`.
3. **Mọi loại tin phải đi qua Net**: `Node.on_sync_request` (D) đang gọi thẳng `self.net.push(...)` và `self.net.nodes`, bỏ qua độ trễ/drop của A. Khi có `send`, đổi thành `self.net.send(self.idx, dst_idx, ("SYNC_RESP", resp))`.
4. **Log `SEND` cho mọi loại tin** (`TX`, `SYNC_REQ`, `SYNC_RESP`), không chỉ `PROPOSAL`/`VOTE`. `sim.py` hiện dùng `getattr(msg[1], "height", 0)`, nên giữ cách này hoặc cho mỗi kiểu tin có `height`.
5. Nếu A làm giao thức `HEADER -> REQUEST_BODY -> BODY`: phía C chỉ phải sửa `ByzantineBase.send_proposal` (đã đánh dấu `TODO(A)`).

Sau khi A merge, C sẽ (hoặc A làm giúp):
- Đổi `test_groups_need_net_send_from_part_a` trong `test_byzantine.py`: Net thật đã có `send` thì tấn công theo nhóm chạy được trên mạng thật.
- Chạy lại `test_quorum_boundary.py` với Net của A (gst=5000 và gst=0), kết quả phải giữ nguyên.

## 5. Việc cho D và E

**D**
- **Chưa node nào gửi `SYNC_REQ`**: đồng bộ chỉ có phía trả lời, chưa có phía hỏi. Cần cơ chế kích hoạt, ví dụ thấy f+1 validator ở height cao hơn thì hỏi. Test n=10 của C đã cho thấy đồng bộ bằng certificate giúp nhóm bị tụt bắt kịp, nếu có ai hỏi.
- Thư mục `src/node/` (`ledger.py`, `mempoll.py`, `sync.py`) và `src/execution/` (`executor.py`, `state.py`) **không được import ở đâu**. Chúng dùng API không tồn tại (`src.common.types`, `crypto`, `payload_bytes`) và bị `node.py`/`execution.py` che (không có `__init__.py`). Nếu ai lỡ thêm `__init__.py` vào `src/node/` thì `from .node import Node` sẽ hỏng toàn bộ. Đề nghị xóa, hoặc đổi tên thành ghi chú.
- Test của D (`tests/unit`, `tests/e2e`) cần `pytest`, nên `unittest discover` không chạy chúng. C đã chạy tay: 7/7 đạt.

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
- Chọn một trình chạy test chung. `pytest` chạy được cả test `unittest` của C lẫn test của D; còn nếu giữ `unittest` thì D cần đổi test sang lớp `unittest.TestCase`.

**B**
- Sau sửa B2/B3, một proposer Byzantine có thể gửi nhiều block khác nhau cho cùng (h, r) và mọi thân hợp lệ đều được giữ, nên bộ nhớ tăng theo số block nó ký. Trong mô phỏng không đáng kể. Nếu muốn chặt hơn: chỉ giữ thân block khi đã thấy vote cho hash đó, hoặc giới hạn số thân mỗi (h, r) và dựa vào đồng bộ của D để lấy phần thiếu.

## 6. Tóm tắt ai làm gì

| Ai | Việc | Mức độ |
|---|---|---|
| A | `send(src, dst, msg)`, GST/partition, drop/dup/reorder; chuyển `on_sync_request` sang `send` | Cần cho tấn công theo nhóm trên mạng thật và cho T6 |
| D | Kích hoạt `SYNC_REQ`; dọn `src/node/`, `src/execution/` | Đồng bộ hiện chưa tự chạy |
| E | Factory `make_node` theo config; sửa `check_safety`; chọn trình chạy test | Cần để chạy T7 bằng config |
| B, D | Pull bản sửa `node.py` (B2, B3, D2, D3) trước khi sửa tiếp | Tránh xung đột |
| C | Sau khi A merge: bỏ `PartitionNet`, cập nhật test `groups` | Nhỏ |
