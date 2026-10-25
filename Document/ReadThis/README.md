# Tài Liệu Học Tập & Kiến Trúc Dự Án Blockchain Layer 1 (Lab 01)

Thư mục này chứa toàn bộ hệ thống tài liệu hướng dẫn học tập từ cơ bản đến nâng cao, bám sát đề bài **LAB 01 (Khoa Công nghệ Tri thức - FIT HCMUS)** và slide bài giảng **Node Architecture, Clients, and State Synchronization**.

---

## 📑 Danh Mục Bài Học

1. 🗺️ **[00_Tong_Quan_Lo_Trinh_Hoc.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/00_Tong_Quan_Lo_Trinh_Hoc.md)**: Tổng quan lộ trình học, sơ đồ tư duy toàn dự án và phương pháp tiếp cận.
2. 🏛️ **[01_Kien_Thuc_Nen_Tang_Layer1.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/01_Kien_Thuc_Nen_Tang_Layer1.md)**: Layer 1 Blockchain, State Machine Replication, Giả định mạng Partial Synchrony, Mô hình lỗi Byzantine BFT, Chứng minh toán học công thức $n = 3f + 1$, Safety vs Liveness, Định lý FLP.
3. 🔐 **[02_Mat_Ma_Hoc_Va_Tinh_Tat_Dinh.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/02_Mat_Ma_Hoc_Va_Tinh_Tat_Dinh.md)**: Chữ ký Ed25519, Băm SHA-256, Phân tách miền ký (Domain Separation `TX:`, `HEADER:`, `VOTE:`), Mã hóa tất định Canonical Serialization (`encode`), Cây Merkle và Merkle Proof.
4. ⚙️ **[03_Kien_Truc_Node_Va_Mo_Hinh_Thuc_Thi.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/03_Kien_Truc_Node_Va_Mo_Hinh_Thuc_Thi.md)**: 5 tầng kiến trúc Node, Pipeline xử lý khối, Máy trạng thái Key-Value Store, Cơ chế kiểm tra quyền sở hữu & Nonce, Kỹ thuật Copy-on-Write, Phân loại Node Roles và Chế độ đồng bộ (Sync modes).
5. 🤝 **[04_Thuat_Toan_Dong_Thuan_Tendermint_BFT.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/04_Thuat_Toan_Dong_Thuan_Tendermint_BFT.md)**: Cơ chế đồng thuận Tendermint Core (Height, Round, Step), Quorum $Q = 2f + 1$, Phân tích chuyên sâu 7 Quy tắc Ký phiếu và Khóa Block (Locking Rules 1-7) đối chiếu code `node.py`, Timeout thích ứng, Chống gian lận Equivocation & Slashing.
6. 🧪 **[05_Mo_Phong_Mang_Va_Kiem_Thu_He_Thong.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/05_Mo_Phong_Mang_Va_Kiem_Thu_He_Thong.md)**: Bộ mô phỏng mạng Discrete Event Simulator (DES) với Virtual Clock và Priority Queue, Tính tất định tuyệt đối, Phân tích 8 kịch bản kiểm thử T1-T8, Hướng dẫn chạy và phân tích file log.
7. 🚀 **[06_RPC_Stack_Indexing_Va_Kien_Truc_Client.md](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/ReadThis/06_RPC_Stack_Indexing_Va_Kien_Truc_Client.md)**: Tầng RPC & WebSocket Gateway, Pipeline Lập chỉ mục Indexing (ETL / Subgraphs), An ninh API Edge, So sánh Geth vs Erigon vs Nethermind, Design Trade-offs, End-to-End Dataflow & SLOs.

---

## 📄 Tài Liệu Đính Kèm Của Môn Học
- **[Lab01.pdf](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/Lab01.pdf)**: Đề bài chi tiết và yêu cầu nộp bài Lab 01.
- **[Lab01-presentation.pdf](file:///e:/DISK_D/MDUY/Nam4/4.1%20Blockchain/Lab1/Document/Lab01-presentation.pdf)**: Slide bài giảng lý thuyết về Kiến trúc Node, Clients và Đồng bộ trạng thái.
