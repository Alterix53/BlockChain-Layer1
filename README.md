# Blockchain Layer 1 — Lab 01

Mô phỏng Tendermint BFT bằng sự kiện rời rạc. Nguồn yêu cầu là
[Lab01.pdf](Document/Lab01.pdf) và [slide kiến trúc](Document/Lab01-presentation.pdf).

## Chạy chương trình

Đã kiểm tra với Python 3.12 và `cryptography==50.0.2`.

```powershell
cd Workspace
python -m pip install -r requirements.txt
python -m src.main --config config/default.json --twice
python -m unittest discover -s tests -v
python -X utf8 -B -m tests -v
```

Lệnh cuối chạy suite kèm event log riêng từng test trong
`Workspace/logs/tests/run-<unique>/`; `summary.json` ánh xạ tên test, kết quả và
file log. Đường dẫn được in cuối lần chạy. Xem [hướng dẫn test](Workspace/tests/README.md).
Log sinh ra được Git ignore.

Từ root repo cũng chạy được `python -m Workspace.src.main --twice`.
CLI ghi `Workspace/logs/run.log` và `run.second.log`; đổi bằng `--log`.
Exit code 0 chỉ khi mọi honest đã chốt đủ height và cùng chain/state. Hết `t_end`
mà chưa hoàn tất trả code 1 và `INCOMPLETE`, kể cả hai lần chạy giống nhau.

## Cấu hình và danh tính

- `n=3f+1`, `n>=8`; mặc định `n=10,f=3`. Số Byzantine không được vượt `f`.
- `links` là `"full"` hoặc danh sách liên kết vô hướng liên thông. Net định tuyến
  theo đường ngắn nhất, mọi hop vẫn đi qua delay/drop/rate-limit và được log.
- `rate_limit` dùng ngân sách chung cho node. Peer admission áp backpressure trước
  khi phát SEND; sau GST không hủy frame đã truyền vì peer throttling.
- `delta` là cận toàn tuyến sau GST, từ SEND đầu tiên tới nhận cuối. Đường nhiều hop
  đặt trước capacity và chia cùng một ngân sách delay; không cộng delta cho mỗi hop.
  Chờ admission cục bộ được log riêng bằng DELAY trước SEND đầu tiên.
- `config/identities.json` là fixture **bí mật của trusted setup mô phỏng**, tạo bằng
  nguồn ngẫu nhiên mật mã độc lập seed mạng. Giữ cố định để tái lập chữ ký; không
  cấp file/master secret cho logic Byzantine. Không dùng khóa thử nghiệm cho tài sản thật.
- Tên account phải duy nhất, khác rỗng và không chứa `/`.

Ví dụ proposer im lặng: thêm `"byzantine": {"1": {"behavior": "silent", "mode": "all"}}`
vào config. V1 là proposer height 1, round 0. Các hành vi khác gồm
`equivocate_voter`, `equivocate_proposer`, `invalid_block`, `replay`.
Hash target có thể truyền dạng hex. Thí nghiệm ngoài giả định n=9/Q=6 dùng runner
riêng `tests/test_quorum_boundary.py`, không nới mô hình BFT của runner chuẩn.

## Thiết kế và kiểm định

Xem [implementation hiện hành](Document/IMPLEMENTATION.md) để biết POLKA proof,
header/body handshake, catch-up và phạm vi kiến thức mở rộng của slide.
Số test PASS không thay thế safety, progress, log schema và mutation gate.

## Tổ chức code

`src/main.py` giữ runner/CLI; `configuration.py` kiểm cấu hình, `identities.py` nạp
danh tính, `validation.py` kiểm safety/completion/determinism. Regression mới nằm
trong `tests/regression/`, tách consensus, network và CLI.

File tạm review, output sinh ra và cấu hình IDE/AI cục bộ được ignore; vẫn giữ
`AGENTS.md`, tài liệu, source, test và identity fixture cần cho tái lập. Review lịch sử
nằm tại `Document/reviews/2026-11-04-initial.md`.

## Bàn giao

Đóng gói nội dung Workspace cùng README và REPORT.pdf theo đúng tên
`Lab01_ID1_ID2_ID3_ID4_ID5`. Báo cáo cần thông tin thành viên, tối đa 10 trang,
không chèn source code. ZIP cũ ở root không phải bản phát hành của implementation này.
