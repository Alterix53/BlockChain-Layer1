# Ảnh sequence diagram T1–T8

14 sơ đồ mô tả 20 test method trong các file T1–T8 chuyên biệt. [Tài liệu chi tiết và cấu hình từng ca](../SEQUENCE_DIAGRAMS_T1_T8.md).

SVG phù hợp phóng to hoặc xuất bản; PNG tiện chèn vào Word/Slides; Mermaid dùng để sửa nội dung. Sơ đồ được xây dựng từ mã nguồn và rút gọn xen kẽ sự kiện, không phải log trace của một lần chạy cụ thể.

| Sơ đồ | Ảnh SVG | Ảnh PNG | Nguồn Mermaid |
|---|---|---|---|
| T1 — Mạng bình thường | [SVG](t1-normal.svg) | [PNG](t1-normal.png) | [Mermaid](t1-normal.mmd) |
| T2a — Nhân bản và đảo thứ tự trên mạng | [SVG](t2a-duplicate-reorder.svg) | [PNG](t2a-duplicate-reorder.png) | [Mermaid](t2a-duplicate-reorder.mmd) |
| T2b — Kiểm tra trực tiếp chống đếm phiếu trùng | [SVG](t2b-rule7.svg) | [PNG](t2b-rule7.png) | [Mermaid](t2b-rule7.mmd) |
| T2c — Byzantine phát lại thông điệp | [SVG](t2c-replay-node.svg) | [PNG](t2c-replay-node.png) | [Mermaid](t2c-replay-node.mmd) |
| T3 — Chèn chữ ký và chứng nhận sai | [SVG](t3-invalid-signatures.svg) | [PNG](t3-invalid-signatures.png) | [Mermaid](t3-invalid-signatures.mmd) |
| T4 — Nhận lần đầu và phát lại giao dịch | [SVG](t4-transaction-replay.svg) | [PNG](t4-transaction-replay.png) | [Mermaid](t4-transaction-replay.mmd) |
| T5 — Mất và trễ tin trước GST | [SVG](t5-pre-gst-safety.svg) | [PNG](t5-pre-gst-safety.png) | [Mermaid](t5-pre-gst-safety.mmd) |
| T6 — Proposer im lặng và phục hồi round | [SVG](t6-silent-proposer.svg) | [PNG](t6-silent-proposer.png) | [Mermaid](t6-silent-proposer.mmd) |
| T7a — Proposer đưa hai đề xuất | [SVG](t7a-proposer-equivocation.svg) | [PNG](t7a-proposer-equivocation.png) | [Mermaid](t7a-proposer-equivocation.mmd) |
| T7b — Tối đa f voter ký hai mặt | [SVG](t7b-voter-equivocation.svg) | [PNG](t7b-voter-equivocation.png) | [Mermaid](t7b-voter-equivocation.mmd) |
| T7c — Kết hợp proposer và voter Byzantine | [SVG](t7c-mixed-coalition.svg) | [PNG](t7c-mixed-coalition.png) | [Mermaid](t7c-mixed-coalition.mmd) |
| T8a — Hai lần chạy cùng đầu vào | [SVG](t8a-two-runs.svg) | [PNG](t8a-two-runs.png) | [Mermaid](t8a-two-runs.mmd) |
| T8b — Không chấp nhận hai lần cùng bị kẹt | [SVG](t8b-incomplete-negative-control.svg) | [PNG](t8b-incomplete-negative-control.png) | [Mermaid](t8b-incomplete-negative-control.mmd) |
| T8c — Phát hiện lỗi riêng trên V9 | [SVG](t8c-every-node-negative-control.svg) | [PNG](t8c-every-node-negative-control.png) | [Mermaid](t8c-every-node-negative-control.mmd) |

Đã đối chiếu đủ 20 tên test method và xác nhận nội dung `.mmd` trùng các khối Mermaid trong tài liệu. 14 sơ đồ đã được Mermaid render thành công. Mỗi ảnh có đánh số bước, các nhánh điều kiện và assertion cuối tương ứng.
