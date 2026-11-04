# Lab 01 runtime

Python 3.12+, cài `python -m pip install -r requirements.txt`.

```powershell
python -m src.main --config config/default.json --twice
python -m unittest discover -s tests -v
```

Exit 0 chỉ khi mọi honest hoàn thành và cùng chain/state; exit 1 khi cấu hình sai,
fork, state lệch hoặc incomplete. `--log path` đổi nhật ký. `--twice` ghi hai file log
và so bytes cùng ledger/state mọi honest. Private fixture `config/identities.json`
độc lập seed mạng; giữ cố định để tái lập, không cấp master secret cho Byzantine.
Không dùng khóa fixture cho tài sản thật.

Nguồn chuẩn: `../Document/Lab01.pdf`. Thiết kế: `../Document/IMPLEMENTATION.md`.
Khi nộp bổ sung REPORT.pdf và đổi tên folder/ZIP theo ID thành viên như §10.
