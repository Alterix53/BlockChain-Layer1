# Kết quả chạy riêng E2E — 06/11/2026

Chạy trong thư mục nộp `Lab01_23127005_23127028_23127183_23127536_23127042/`, dùng Python bundled 3.12.14 và dependency hiện có. Không thay mã nguồn hay assertion.

| Phạm vi | Test đạt | Failure/error/skip | Thời gian unittest | Exit code | Index trong thư mục nộp |
|---|---:|---|---:|---:|---|
| Riêng tám kịch bản T1–T8 | 20/20 | 0/0/0 | 9.820 giây | 0 | `logs/t1-t8/run-8rks9po9/summary.json` |
| Toàn bộ `tests/e2e` | 37/37 | 0/0/0 | 20.718 giây | 0 | `logs/e2e/run-_0c6h6zv/summary.json` |

T1–T8 là tám nhóm kịch bản, không phải tám test method. Số test method T1 đến T8 lần lượt là 1, 3, 1, 1, 2, 2, 4, 6; tất cả PASS. Các biến thể subtest không tính riêng. Nhóm E2E đầy đủ còn kiểm tra Byzantine, mạng lỗi, catch-up và ranh giới quorum; fork trong thử nghiệm ngoài giả định BFT và đối chứng âm là kết quả kỳ vọng của các assertion tương ứng.

Thời gian lấy từ dòng `Ran ... tests in ...s` trong `logs/t1-t8-console.txt` và `logs/e2e-console.txt`. Mỗi console ghi `OK`, đường dẫn run tương ứng và exit code 0. Đã đối chiếu index và kết thúc từng log: đủ 20 và 37 log, tất cả ghi `# outcome=passed`.

## Tái lập trong PowerShell từ thư mục nộp

Riêng T1–T8, có lưu log từng test:

```powershell
$scenarioModules = Get-ChildItem tests/e2e/test_t[1-8]_*.py | Sort-Object Name | ForEach-Object { 'tests.e2e.' + $_.BaseName }
python -X utf8 -B -m tests -v --log-dir logs/t1-t8 @scenarioModules
```

Toàn bộ nhóm E2E, có lưu log từng test:

```powershell
$e2eModules = Get-ChildItem tests/e2e/test_*.py | Sort-Object Name | ForEach-Object { 'tests.e2e.' + $_.BaseName }
python -X utf8 -B -m tests -v --log-dir logs/e2e @e2eModules
```

Mỗi lần chạy tạo một thư mục run mới. Các con số trên thuộc hai run đã nêu; thời gian là thời gian thực thi test trên máy, không phải thời gian mô phỏng và không thay thế kết quả toàn suite 150 test trước đó.
