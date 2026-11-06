# Lab 01 - Blockchain Layer 1 simulator

## Thành viên

| Họ tên | MSSV |
|---|---|
| Nguyễn Anh Kiệt | 23127005 |
| Phan Thanh Bình | 23127028 |
| Phạm Vũ Ngọc Duy | 23127183 |
| Nguyễn Tấn Phước | 23127536 |
| Nguyễn Đặng Minh Duy | 23127042 |

## Cài đặt và chạy

Yêu cầu Python 3.12+ và pip. Đã kiểm tra bằng Python 3.12.14, cryptography 50.0.2 trên Windows. Chương trình Python không cần biên dịch riêng. Mở PowerShell tại thư mục gốc repository hoặc thư mục nộp bài. Chạy đoạn sau để vào đúng thư mục chương trình (nếu đã ở thư mục nộp thì giữ nguyên):

```powershell
if (-not (Test-Path -LiteralPath "src/main.py")) {
    Set-Location -LiteralPath "Lab01_23127005_23127028_23127183_23127536_23127042"
}
```

Các lệnh bên dưới đều chạy tại thư mục có `src/`, `tests/`, `config/` và `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
python -X utf8 -B -m src.main --config config/default.json --twice
```

Trên Windows có thể dùng `py -3.12` thay `python` nếu có Python Launcher. `--twice` so log từng byte và ledger/state của mọi node trung thực. Log ghi tại `logs/run.log` và `logs/run.second.log`; `--log path` đổi vị trí. Exit 0 khi mọi honest node hoàn tất và hội tụ; exit 1 khi cấu hình sai, fork, state lệch hoặc chưa hoàn tất.

## Chạy kiểm thử

Chạy toàn bộ suite và lưu event log từng test:

```powershell
python -X utf8 -B -m tests -v
```

Runner in đường dẫn `logs/tests/run-<unique>/summary.json`, ánh xạ test ID, kết quả và file log. Chạy không lưu event log:

```powershell
python -X utf8 -B -m unittest discover -s tests -v
```

Chạy một nhóm và thí nghiệm quorum:

```powershell
python -X utf8 -B -m unittest discover -s tests/unit -t . -v
python -X utf8 -B -m tests.e2e.test_quorum_boundary --report
```

Chi tiết nhóm test, oracle độc lập và mutation gate: `tests/README.md` trong thư mục chương trình. Log mutation có thể chứa sự kiện sai được cố ý tạo; PASS nghĩa là assertion đã phát hiện lỗi được tiêm.

## Chạy và lưu các file log

Sau khi cài dependencies và vào đúng thư mục chương trình, chạy trong PowerShell:

```powershell
# Tạo thư mục logs nếu chưa có
New-Item -ItemType Directory -Path logs -Force | Out-Null

# Chạy simulator hai lần; lưu toàn bộ nội dung console
python -X utf8 -B -m src.main --config config/default.json --twice *> logs/simulator-console.txt
$LASTEXITCODE

# Chạy toàn bộ test; lưu toàn bộ nội dung console
python -X utf8 -B -m tests -v *> logs/acceptance-console.txt
$LASTEXITCODE
```

`$LASTEXITCODE` ngay sau mỗi lệnh cho biết mã thoát: 0 là thành công. Vì `*>` chuyển nội dung console vào file nên terminal không hiển thị tiến trình; mở các file `.txt` để xem kết quả. Chạy lại các lệnh trên sẽ ghi đè bốn file đầu ra cố định bên dưới.

| File / thư mục được tạo | Nguồn tạo và ý nghĩa |
|---|---|
| `logs/run.log` | `src/main.py`: nhật ký sự kiện lần mô phỏng thứ nhất. |
| `logs/run.second.log` | `src/main.py` với `--twice`: nhật ký lần thứ hai để so sánh tính tất định. |
| `logs/simulator-console.txt` | PowerShell lưu stdout/stderr của simulator qua `*>`; chứa kết quả hoàn tất, state hash hoặc lỗi. |
| `logs/acceptance-console.txt` | PowerShell lưu stdout/stderr của runner `tests/__main__.py`; chứa danh sách test, tổng kết và đường dẫn event log. |
| `logs/tests/run-<unique>/` | `tests/__main__.py` tạo thư mục mới mỗi lần chạy, chứa event log riêng từng test. |
| `logs/tests/run-<unique>/summary.json` | Index ánh xạ test ID với kết quả và tên file event log tương ứng. |

Đọc nhanh kết quả sau khi chạy:

```powershell
Get-Content -LiteralPath logs/simulator-console.txt
Get-Content -LiteralPath logs/acceptance-console.txt -Tail 12
```

## Cấu trúc và thiết kế

**Trạng thái báo cáo:** `REPORT.pdf` hiện được giữ từ bản export cũ (12 trang), chưa đồng bộ các chỉnh sửa mới trong nguồn LaTeX. Trước khi nộp cho giảng viên, cần xuất lại từ `Document/Report/main.tex` trong repository và kiểm tra tổng PDF không quá 10 trang theo đề bài.

```text
src/              9 module Python của simulator
tests/            unit, integration, e2e, regression, oracle, mutation gate
logs/             log mô phỏng và bằng chứng kết quả kiểm thử
config/           default.json và identities.json
requirements.txt  cryptography==50.0.2
REPORT.pdf        báo cáo thiết kế, kiểm thử và tham khảo
```

`main.py` điều phối CLI; `configuration.py` kiểm cấu hình; `identities.py` nạp khóa; `common.py` mô hình dữ liệu, encoding, hash và chữ ký; `execution.py` thực thi; `node.py` đồng thuận, gossip và catch-up; `sim.py` mạng sự kiện rời rạc; `validation.py` kiểm safety/completion/determinism; `byzantine.py` mô phỏng tấn công.

Cấu hình chuẩn n=3f+1, n>=8; mặc định n=10, f=3, Q=7, seed=42 và 5 height. `links` là full mesh hoặc danh sách liên kết vô hướng liên thông. Sau GST, delta là cận truyền toàn tuyến từ SEND đầu tiên; chờ admission cục bộ được log riêng.

Ed25519, SHA-256 và domain theo chain bảo vệ thông điệp. `tx_root` là hash danh sách giao dịch theo thứ tự, không phải cây Merkle. `config/identities.json` là fixture khóa bí mật của trusted setup mô phỏng, độc lập seed mạng; giữ nguyên để tái lập, không dùng cho tài sản thật và không cấp master secret cho logic Byzantine.

## Kết quả xác minh

Ngày 06/11/2026: 150/150 test PASS, không failure/error/skip; simulator chạy hai lần chốt đủ 5 block và giống log/ledger/state. Bằng chứng: `logs/acceptance-console.txt`, `logs/simulator-console.txt`, `logs/tests/run-4udyr5el/summary.json`. Đây là bằng chứng hồi quy, không phải chứng minh hình thức.

## Tham khảo

- Đề bài Blockchain course, Lab01, Knowledge Engineering Department, 2026, mục 3, 5-10; slide Lab01-presentation được cấp cùng đề.
- Buchman, Kwon, Milosevic, The latest gossip on BFT consensus: https://arxiv.org/abs/1807.04938
- Lamport, Shostak, Pease, The Byzantine Generals Problem: https://doi.org/10.1145/357172.357176
- Ed25519: https://www.rfc-editor.org/rfc/rfc8032
- Cryptography Ed25519 API: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/
- Python unittest: https://docs.python.org/3/library/unittest.html

Xem REPORT.pdf để biết thiết kế và kết quả chi tiết. Gói chạy độc lập, không cần tài liệu ngoài thư mục này.
