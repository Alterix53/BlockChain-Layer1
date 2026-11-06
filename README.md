<div align="center">

# Lab 01 · Blockchain Layer 1

Mô phỏng blockchain BFT trên mạng không tin cậy, với giao dịch có chữ ký và trạng thái tất định.

**Python 3.12+ · Ed25519 · SHA-256 · Tendermint-style BFT**

[Phần nộp bài](Lab01_23127005_23127028_23127183_23127536_23127042/) · [Hướng dẫn chi tiết](Lab01_23127005_23127028_23127183_23127536_23127042/README.md) · [Báo cáo PDF](Lab01_23127005_23127028_23127183_23127536_23127042/REPORT.pdf) · [Tài liệu](Document/)

</div>

---

## Tổng quan

Các validator trao đổi thông điệp qua mạng mô phỏng để thống nhất chuỗi block và trạng thái key–value. Hệ thống hỗ trợ trễ, mất gói, nhân bản, đảo thứ tự thông điệp và các hành vi Byzantine.

- **Đồng thuận:** Propose → Prevote → Precommit → Finalize, với cơ chế khóa block và bằng chứng POL.
- **Xác thực:** chữ ký Ed25519, domain separation theo loại thông điệp và chain, cam kết SHA-256.
- **Truyền tải:** gossip giao dịch, gửi header trước body, giới hạn tốc độ và đồng bộ catch-up.
- **Tái lập:** cùng cấu hình, seed và identity cho log giống từng byte và cùng trạng thái cuối.

Cấu hình mặc định: **10 validator · f = 3 · quorum = 7 · seed = 42 · 5 block**.

## Chạy nhanh

Yêu cầu Python 3.12+ và pip. Từ **gốc repository**, chạy:

```powershell
cd Lab01_23127005_23127028_23127183_23127536_23127042
python -m pip install -r requirements.txt
python -X utf8 -B -m src.main --config config/default.json --twice
```

`--twice` chạy mô phỏng hai lần, so sánh log từng byte và ledger/state của các node trung thực. Log được ghi vào `logs/run.log` và `logs/run.second.log`; exit code `0` cho biết kiểm tra hoàn tất thành công. Trên Windows có Python Launcher, có thể thay `python` bằng `py -3.12`.

## Kiểm thử

Các lệnh sau chạy từ **thư mục nộp bài** vừa mở ở trên:

```powershell
# Toàn bộ bộ kiểm thử, có log riêng cho từng test
python -X utf8 -B -m tests -v

# Riêng nhóm E2E
python -X utf8 -B -m unittest discover -s tests/e2e -t . -v
```

Runner `python -m tests` tạo thư mục `logs/tests/run-<unique>/`; `summary.json` ánh xạ tên test tới kết quả và file log. Xem [hướng dẫn kiểm thử](Lab01_23127005_23127028_23127183_23127536_23127042/tests/README.md) và [cách chạy riêng T1–T8](Document/Report/E2E_RESULTS.md).

### Kết quả đã xác minh · 06/11/2026

| Phạm vi | Kết quả | Thời gian | Bằng chứng |
| :--- | :---: | ---: | :--- |
| Toàn bộ bộ kiểm thử — lần kiểm tra cuối | **150/150 PASS** | 28,722 giây | [Console](Document/reviews/2026-11-06-final-validation-console.txt) |
| Toàn bộ nhóm E2E | **37/37 PASS** | 20,718 giây | [Console](Lab01_23127005_23127028_23127183_23127536_23127042/logs/e2e-console.txt) |
| Riêng tám kịch bản T1–T8 | **20/20 PASS** | 9,820 giây | [Console](Lab01_23127005_23127028_23127183_23127536_23127042/logs/t1-t8-console.txt) |

Không có failure, error hoặc skip trong các lần chạy trên. T1–T8 là **tám nhóm kịch bản**, gồm tổng cộng 20 test method; các biến thể subtest không được tính riêng. Thời gian do `unittest` đo cho từng lần chạy, không phải thời gian mô phỏng. Đây là bằng chứng hồi quy, không phải chứng minh hình thức của giao thức.

## Cấu trúc repository

```text
.
├── Lab01_23127005_23127028_23127183_23127536_23127042/
│   ├── src/               Mã nguồn mô phỏng
│   ├── tests/             Unit, integration, E2E và regression
│   ├── config/            Cấu hình và identity cố định
│   ├── logs/              Log mô phỏng và bằng chứng test
│   ├── requirements.txt   cryptography==50.0.2
│   ├── README.md          Hướng dẫn chạy chi tiết
│   └── REPORT.pdf         Bản PDF hiện có
├── Document/              Đề bài, thiết kế, sơ đồ và nguồn LaTeX
└── README.md              Giới thiệu repository
```

> **Trạng thái báo cáo:** `REPORT.pdf` hiện là bản export cũ gồm 12 trang. Cần xuất lại từ [nguồn LaTeX](Document/Report/main.tex), đồng bộ nội dung mới và bảo đảm tổng PDF không quá 10 trang trước khi nộp cho giảng viên.

## Thành viên

| MSSV | Họ và tên |
| :---: | :--- |
| 23127005 | Nguyễn Anh Kiệt |
| 23127028 | Phan Thanh Bình |
| 23127183 | Phạm Vũ Ngọc Duy |
| 23127536 | Nguyễn Tấn Phước |
| 23127042 | Nguyễn Đặng Minh Duy |

## Tài liệu và tham khảo

- [Đề bài Lab 01](Document/Lab01.pdf) · [Slide môn học](Document/Lab01-presentation.pdf)
- [Thiết kế và hiện thực](Document/IMPLEMENTATION.md) · [Sơ đồ lớp](Document/CLASS_DIAGRAMS.md) · [Luồng T1–T8](Document/SEQUENCE_DIAGRAMS_T1_T8.md)
- [The latest gossip on BFT consensus](https://arxiv.org/abs/1807.04938)
- [The Byzantine Generals Problem](https://doi.org/10.1145/357172.357176)
- [Ed25519 — RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) · [PyCA Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) · [Python unittest](https://docs.python.org/3/library/unittest.html)
