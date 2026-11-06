# Kiểm duyệt cấu trúc nộp bài - 06/11/2026

## Kết quả

Thư mục nộp bài: `Lab01_23127005_23127028_23127183_23127536_23127042/`.

| Mục bắt buộc | Kết quả kiểm tra |
|---|---|
| Tên thư mục | Đúng mẫu Lab01 + 5 MSSV, lấy từ trang bìa LaTeX có sẵn |
| src/ | 9 module runtime được chuyển nguyên trạng từ Workspace/src |
| tests/ | Giữ toàn bộ suite hiện tại, bao gồm thay đổi chưa commit của người dùng |
| logs/ | Có log simulator mới, console và log từng test |
| config/ | Giữ default.json và identities.json để tái lập |
| README.md | Có thành viên, cấu trúc, cài đặt/chạy, test, cấu hình và tham khảo; bỏ phụ thuộc tài liệu ngoài gói |
| requirements.txt | Giữ cryptography==50.0.2 |
| REPORT.pdf | 9 trang, đã render kiểm tra bố cục cả 9 trang; không chèn source code |

## Xác minh thực thi sau khi di chuyển

Môi trường: Windows, Python bundled 3.12.14, cryptography 50.0.2. Python không có trên PATH của phiên này nên dùng executable bundled để thực thi đúng các module trong README.

- `python -X utf8 -B -m tests -v`: 150 test, 35.265 giây; 150 PASS, 0 failure/error/skip, exit 0.
- Index: `logs/tests/run-4udyr5el/summary.json`, đầy đủ đường dẫn log cho từng test.
- Console: `logs/acceptance-console.txt`.
- `python -X utf8 -B -m src.main --config config/default.json --twice`: exit 0; chốt đủ 5 block, cùng ledger/state của mọi honest node, hai log giống từng byte.
- State: Alice/msg, Bob/msg, Carol/msg đều v5.
- State hash: `0b837be96db72e1f18691d048ad593734a90169c56e518f13441334887b3d307`.
- Console: `logs/simulator-console.txt`; hai log `logs/run.log`, `logs/run.second.log`.

Các lệnh chạy ngay trong thư mục nộp; đường dẫn runtime/config được suy ra từ vị trí file, không cần sửa logic chương trình. Chưa cài lại dependencies trong một môi trường mới; kết quả trên dùng dependency có sẵn và đúng phiên bản requirements.

## Báo cáo

REPORT.pdf mới được tạo từ mô tả implementation, regression/test hiện tại và kết quả chạy sau di chuyển. Gồm thành viên, cấu trúc, mục tiêu, sơ đồ kiến trúc, luồng thông điệp, 7 guards, gossip, đồng thuận, bugs/corrections, T1-T8, coverage bổ sung, tham khảo và danh sách 150 test thực chạy.

Nguồn tái tạo PDF: `Document/Report/build_submission_report.py` (Python reportlab, pypdf, font Arial trên Windows). File này xác định root repository từ vị trí của chính nó; chạy từ root sau khi có index kết quả kiểm thử tương ứng. Ảnh render và text trích xuất QA ở `temp/report-build/`.

Nguồn LaTeX cũ được giữ nguyên để nhóm tiếp tục tham khảo. Nó còn phần cấu trúc chưa hoàn tất, thống kê snapshot cũ và contribution.tex có nội dung SQL Server; không dùng nó làm bản báo cáo nộp cuối trong lần sắp xếp này. Không gán phân công hay đóng góp chưa có bằng chứng cho các thành viên.

## File được giữ lại ở temp/

- ZIP cũ `Blockchain_lab_1.zip` và skeleton `blockchain.py` không thuộc runtime hiện tại.
- Toàn bộ `tmp/`, `output/` cũ và log Workspace cũ.
- Cache bytecode của source/test; cache pytest trong thư mục cha được chuyển sang temp mà không thay ACL.
- Bản README gốc ở root/runtime/tests để truy hồi trước khi sửa.
- Chi tiết các lần chuyển: `temp/reorganization-2026-11-06/MOVES.txt`.

Không xóa vĩnh viễn file, không commit hoặc stage thay đổi. Các cấu hình/tool state ẩn của Git, CodeGraph, IDE/AI và review ở root được giữ ngoài gói nộp. Cây nộp không có cache, ZIP cũ hoặc file trung gian PDF. Các tài liệu lịch sử ở Document/ và PROJECT.md có thể còn nhắc Workspace/; root README giải thích tên cũ.

## Phạm vi kiểm duyệt

Đây là kiểm duyệt cấu trúc, tài liệu đóng gói và chạy lại suite hiện có; không phải audit/chứng minh giao thức đầy đủ. Kết quả n=9/Q=6 và log mutation chứa lỗi cố ý là điều kiện thử nghiệm kỳ vọng, không phải lỗi đóng gói. Không thay assertion để làm test đạt. Gói nộp độc lập với Document/ và temp/; chỉ nộp thư mục có tên Lab01 + 5 MSSV.
