# Lộ Trình Học Tập & Kiến Trúc Dự Án Blockchain Layer 1 (Lab 01)

Chào mừng bạn đến với tài liệu hướng dẫn toàn diện về dự án **Blockchain Layer 1 Minimal** với thuật toán đồng thuận **Tendermint BFT**.

Tài liệu này được biên soạn bám sát theo yêu cầu đề bài **LAB 01 (Khoa Công nghệ Tri thức - FIT HCMUS)** và bài giảng lý thuyết **Node Architecture, Clients, and State Synchronization**, kết nối trực tiếp lý thuyết hàn lâm với mã nguồn thực tế trong thư mục `Blockchain_lab_1/src/`.

---

## 🗺️ Bản Đồ Lộ Trình Học Tập (Từ Cơ Bản Đến Nâng Cao)

Hệ thống tài liệu được chia thành **5 chuyên đề chuyên sâu** sắp xếp theo tiến trình nhận thức:

```
[Chuyên đề 01: Kiến thức nền tảng Layer 1 & BFT]
                      │
                      ▼
[Chuyên đề 02: Mật mã học, Domain Separation & Mã hóa tất định]
                      │
                      ▼
[Chuyên đề 03: Kiến trúc Node & Mô hình thực thi chuyển trạng thái]
                      │
                      ▼
[Chuyên đề 04: Thuật toán đồng thuận Tendermint BFT & 7 Quy tắc vàng]
                      │
                      ▼
[Chuyên đề 05: Mô phỏng mạng DES & 8 Kịch bản kiểm thử (T1 -> T8)]
```

---

## 📚 Danh Mục Các Tập Tài Liệu

| Bài | Tên tài liệu | Nội dung trọng tâm | File mã nguồn liên quan |
| :--- | :--- | :--- | :--- |
| **01** | [01_Kien_Thuc_Nen_Tang_Layer1.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/01_Kien_Thuc_Nen_Tang_Layer1.md) | Khái niệm Layer 1, State Machine Replication, Giả định mạng bán đồng bộ (Partial Synchrony), Mô hình lỗi Byzantine, Công thức $n = 3f + 1$, Safety vs Liveness, FLP Impossibility. | `config/default.json` |
| **02** | [02_Mat_Ma_Hoc_Va_Tinh_Tat_Dinh.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/02_Mat_Ma_Hoc_Va_Tinh_Tat_Dinh.md) | Khóa Ed25519, Băm SHA-256, Phân tách miền ký (Domain Separation `TX:`, `HEADER:`, `VOTE:`), Mã hóa tất định Canonical Serialization (`encode`), Merkle Root & Merkle Proof. | `src/common.py` |
| **03** | [03_Kien_Truc_Node_Va_Mo_Hinh_Thuc_Thi.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/03_Kien_Truc_Node_Va_Mo_Hinh_Thuc_Thi.md) | 5 tầng kiến trúc Node, Pipeline xử lý khối, Máy trạng thái Key-Value Store, Nonce chống replay, Cơ chế Copy-on-Write, Phân loại Node (Full/Archival/Light), Đồng bộ trạng thái (Sync modes). | `src/execution.py`, `src/common.py` |
| **04** | [04_Thuat_Toan_Dong_Thuan_Tendermint_BFT.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/04_Thuat_Toan_Dong_Thuan_Tendermint_BFT.md) | Vòng đời Height/Round/Step (Propose -> Prevote -> Precommit -> Finalize), Quorum $Q = 2f + 1$, Phân tích chi tiết 7 Quy tắc Ký phiếu và Khóa Block (Locking Rules 1-7), Timeout động, Slashing & Equivocation. | `src/node.py` |
| **05** | [05_Mo_Phong_Mang_Va_Kiem_Thu_He_Thong.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/05_Mo_Phong_Mang_Va_Kiem_Thu_He_Thong.md) | Mô phỏng biến cố rời rạc (Discrete Event Simulation - DES), Virtual Clock, Priority Queue, Tính tất định (Byte-identical logs), Phân tích toàn diện 8 kịch bản kiểm thử T1-T8, Hướng dẫn chạy & debug. | `src/sim.py`, `src/main.py` |

---

## 🎯 Phương Pháp Học Hiệu Quả

1. **Đọc theo tuần tự**: Hãy bắt đầu từ tài liệu **01** để nắm vững tư duy hệ thống và các bất biến toán học (invariants) trước khi đọc code.
2. **Đối chiếu Code thực tế**: Mỗi tài liệu đều trích dẫn các hàm, lớp và cấu trúc dữ liệu cụ thể trong thư mục `Blockchain_lab_1/src/`. Hãy mở song song code để đọc và liên hệ.
3. **Thực nghiệm qua Log**: Chạy mô phỏng bằng lệnh `python -m src.main` và mở file `logs/run.log` để tự mình đối chiếu từng sự kiện mạng (`SEND`, `PROPOSE`, `VOTE`, `FINALIZE`).
