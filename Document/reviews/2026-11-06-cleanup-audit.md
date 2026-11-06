# Rà soát hàm và thư viện — 2026-11-06

Phạm vi: 46 file Python trong cây làm việc hiện tại: `blockchain.py`, 9 module `Workspace/src`, và 36 file trong `Workspace/tests`. Đối chiếu thêm requirements, cấu hình, hướng dẫn chạy và tài liệu liên quan. Không coi bản ZIP, checkout tạm trong `.review-tmp`, cache, log và output sinh tự động là mã nguồn đang chạy. Những thay đổi test chưa commit cũng được đưa vào phân tích.

Đã thử CodeGraph trước; công cụ trả được skeleton và một số test nhưng không trả được nguồn các module runtime theo tên/path. Phần còn thiếu được đọc trực tiếp và phân tích AST. Báo cáo chỉ ghi nhận và đề xuất, không sửa mã runtime, test hay requirements.

## 1. Hàm/mã không còn được sử dụng

| Vị trí | Phát hiện | Hướng xử lý |
|---|---|---|
| `blockchain.py:1–24` | Cả lớp `Blockchain` không có nơi import/khởi tạo trong mã Python hiện tại. `new_block`, `new_transaction`, `hash`, `proof_of_work` chỉ là `pass`; `last_block` thuộc cùng skeleton. | Có thể bỏ khỏi bộ mã chạy hoặc chuyển sang tài liệu ví dụ nếu vẫn muốn giữ khung PoW ban đầu. Không nhầm `Blockchain.hash` này với `Block.hash` và `State.hash` đang được dùng. |
| `Workspace/src/byzantine.py:320` | `Replay._seen` chỉ được gán `set()`, không đọc hay cập nhật ở nơi khác. Khử trùng hiện dùng `msg not in self.recorded`. | Bỏ thuộc tính này; chưa cần thay cấu trúc khử trùng vì payload có thể không hash được. |
| `Workspace/src/sim.py:513–516,534–538` | Hai nhánh `if self.now >= self.gst` trong `_receive` không thể chạy tới: trường hợp sau GST đã được xử lý rồi `return` ở dòng 505–508. | Bỏ hai nhánh chết, giữ nhánh DROP trước GST và hành vi giao tin sau GST. |
| `Workspace/src/sim.py:133–146` | `push()` hỗ trợ cả 4 và 5 đối số, nhưng toàn bộ 14 call site tìm được đều truyền 5 đối số. | Có thể đổi thành `push(self, t, kind, src, dst, payload)`, bỏ phân nhánh `*args` tương thích cũ nếu không cần hỗ trợ người gọi ngoài repository. |
| `Workspace/src/validation.py:14` | `if honest_nodes else 0` dư: ngay phía trên đã raise nếu danh sách rỗng. | Dùng trực tiếp `max(len(x.ledger) for x in honest_nodes)`. |

Trong `Workspace/src`, chưa tìm thấy thêm hàm hoàn chỉnh nào đủ bằng chứng để xóa vì không được gọi. Kết luận này dựa trên tham chiếu tĩnh và luồng điều phối hiện có; không phải bằng chứng rằng mọi nhánh đều đã được thực thi.

Các method override như `Silent.start`, `Replay.on_timeout`, `ForkCoalition.on_message`, các method của `LoggedResult`, `setUpClass` và `test_*` được framework hoặc điều phối động gọi. Không được coi là mã chết chỉ vì không thấy một lời gọi trực tiếp mang tên lớp cụ thể. `Tx.height` cũng được đọc gián tiếp qua `getattr` khi ghi log.

## 2. Import thừa và phụ thuộc vòng qua module khác

| Vị trí | Kết luận |
|---|---|
| `Workspace/src/main.py:21` | Import `check_safety` không được dùng trong file và không thấy người gọi nào import nó qua `src.main` trong mã hiện tại. Có thể bỏ import này. Giữ nguyên hàm `validation.check_safety`: `check_completion` vẫn gọi nó. |
| `Workspace/tests/unit/test_executor.py:2–3` | `H` và `apply_txs` được import nhưng không dùng trong file. Có thể bỏ hai tên này khỏi import. |
| `Workspace/tests/e2e/test_consensus_network.py:5`, `test_t4_replay_tx.py:7` | Đang lấy `identity_keys` qua `src.main`. Nên import trực tiếp từ `src.identities`. |
| `Workspace/tests/regression/test_cli.py:12` | Đang lấy `validate_config` qua `src.main`. Nên import trực tiếp từ `src.configuration`. |

Không có vòng import giữa 9 module runtime. Tuy vậy, `identities -> configuration -> byzantine -> node` là chuỗi phụ thuộc rộng chỉ để lấy hằng `WORKSPACE`. Nếu muốn giảm liên kết, có thể chuyển hằng đường dẫn sang một module nhẹ như `paths.py`, rồi để `identities` và `configuration` cùng lấy từ đó. Đây là đề xuất tổ chức, không phải lỗi vòng import.

## 3. Hàm có thể viết gọn và gom logic lặp

| Mức ưu tiên | Vị trí | Đề xuất và điều kiện giữ đúng hành vi |
|---|---|---|
| Cao | `node.py:364` (`on_tx`) và `execution.py:45` (`apply_tx`) | Tách hàm thuần dùng chung kiểm tra định dạng, tài khoản, chữ ký và namespace trong `execution.py`. Giữ quy tắc nonce tại từng nơi: mempool chấp nhận nonce tương lai lớn hơn nonce hiện tại; execution bắt buộc đúng `current + 1`. Không thay toàn bộ `on_tx` bằng `apply_tx`. |
| Cao | `node.py:441,473,541,676,739` | Các đường nhận sync header, sync block, header, proposal và `_check` lặp kiểm tra proposer/chữ ký/header. Có thể tách phần xác thực chung thành hàm trả mã lỗi, truyền dữ liệu đầu vào rõ ràng. Giữ riêng giới hạn height/round, parent, polka, thực thi state và mã lỗi của từng luồng. |
| Vừa | `node.py:155,579` | Lặp cách tính tập block được bảo vệ bởi `sync_pending`, `proofs`, `locked`. Gom thành một helper trả tập hash, dùng cho dọn round và chọn header để loại khỏi bộ đệm. |
| Vừa | `sim.py:187,337` | `_send_routed` và `_reserve_send_time` lặp tạo budget rate limit/peer block, lọc lịch sử và ghi reservation. Tách phần tạo budget dùng chung trước; giữ thuật toán đặt lịch toàn tuyến và đơn hop riêng để không làm sai cận delta sau GST. |
| Vừa | `node.py:280` (`make_block`) | `s` đã là bản sao state; mỗi giao dịch lại tạo `trial = s.copy()`. Hiện `apply_tx` chỉ ghi state sau tất cả guard và không thay đổi state khi trả lỗi, nên có thể áp dụng trực tiếp trên `s`, bỏ bản sao mỗi tx. Điều này phụ thuộc vào việc tiếp tục giữ hợp đồng không sửa state khi từ chối. |
| Vừa | `node.py:805` (`run`) | Tách phần cập nhật lock từ quorum, xử lý bước hiện tại và tìm precommit certificate thành các method trong cùng lớp. Giữ nguyên thứ tự duyệt, điều kiện `continue/return`, ghi log và chống ký hai lần. Đây là phần đồng thuận nên làm sau các dọn dẹp nhỏ. |
| Thấp | `node.py:473` (`on_sync_response`) | Có kiểm tra kiểu certificate và khớp height/hash trước khi gọi `certificate_error`, vốn cũng kiểm tra các điều kiện này. Có thể gom nhưng phải giữ thứ tự từ chối và mã lỗi nếu chúng là hợp đồng test/log. |
| Thấp | `main.py:7–11` | Chuyển cấu hình stdout vào điểm vào CLI để import `run_sim` từ test không tự thay đổi stdout của tiến trình. |

Các helper mới nên đặt ở tầng sở hữu dữ liệu (`execution` cho giao dịch, tầng kiểm tra header cho xác thực header), nhận tham số cụ thể và trả kết quả. Tránh gom vào một `utils.py` lớn rồi import ngược `Node` hoặc `main`.

Không gom `tests/independent_oracle.py` vào hàm hash/encode/verify/execution của production. Sự độc lập này có chủ đích để test phát hiện trường hợp mọi node cùng tạo kết quả sai. Cũng không đồng nhất bộ kiểm safety nhận tập tên Byzantine của test với bộ kiểm runtime mà không xem khác biệt giao diện.

## 4. Tổng hợp thư viện cần dùng

| Nhóm | Thư viện | Vai trò |
|---|---|---|
| Package ngoài, cần cài | `cryptography==50.0.2` | Ed25519 private/public keys, ký, xác minh, xuất khóa raw, `InvalidSignature`; được production và oracle sử dụng. Đã có trong `Workspace/requirements.txt`. |
| Standard library, runtime | `hashlib`, `struct`, `dataclasses` | SHA-256, mã hóa byte tất định, mô hình dữ liệu và `replace`. |
| Standard library, runtime | `collections`, `heapq`, `random`, `copy` | Đếm phiếu, BFS, hàng đợi sự kiện, RNG có seed và sao chép payload độc lập. |
| Standard library, runtime | `argparse`, `json`, `pathlib`, `sys` | CLI, đọc cấu hình/identity, đường dẫn và mã thoát. |
| Standard library, test/runner | `unittest` (gồm `mock`), `contextlib`, `io`, `os`, `re`, `subprocess`, `tempfile`, `types` | Chạy test, quan sát log, patch có kiểm soát, test CLI và file tạm. Các test còn dùng lại một số standard library kể trên. |

Các module standard library không cần đưa vào requirements. Chưa thấy thiếu package ngoài nào qua toàn bộ import Python đã rà soát.

## 5. Thư viện không cần thiết

- Không có package dư trong `requirements.txt`: file chỉ khai báo `cryptography`, và package này đang được dùng.
- `pytest` không được import bởi mã Python hiện tại và không cần cho lệnh acceptance `unittest`. `tests/conftest.py` là hỗ trợ bổ sung cho cách chạy pytest; không thuộc luồng unittest. Chỉ cần pytest nếu vẫn muốn duy trì cách chạy tùy chọn đó.
- `Document/DEMO_TOAN_BO_QUA_TRINH.md:181,195` còn hướng dẫn `python -m pytest`. Nên thống nhất các ví dụ này sang unittest, hoặc ghi rõ pytest là công cụ tùy chọn cần cài thêm. `PROJECT.md:25` cũng còn dùng cách gọi “100% pytest green”.
- Không cần thêm package mới chỉ để thực hiện những refactor trong báo cáo.

## 6. Kiểm chứng và thứ tự đề xuất

Đã parse AST toàn bộ 46 file Python, đối chiếu khai báo/tham chiếu/import và dựng đồ thị import runtime. Đã chạy toàn bộ suite hiện tại bằng Python bundled 3.12.14 với `cryptography 50.0.2`:

```text
python -X utf8 -B -m unittest discover -s tests
Ran 150 tests in 29.003s
OK
```

Python trên PATH không có; hai bản Python uv tìm được chưa có cryptography. Kết quả thành công trên là từ runtime bundled có sẵn, không cài thêm package. Test xanh là baseline cho code hiện tại, chưa xác nhận các refactor chưa thực hiện.

Thứ tự hợp lý: bỏ skeleton/thuộc tính/import/nhánh chết; sửa import test về module sở hữu; rút gọn `push`, điều kiện dư và bản sao state; sau đó mới gom xác thực giao dịch/header và tách máy trạng thái. Chạy lại suite sau mỗi nhóm thay đổi, giữ oracle độc lập và mutation gate hiện có.
