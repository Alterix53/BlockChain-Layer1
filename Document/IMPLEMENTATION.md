# Implementation hiện hành và đối chiếu Lab 01

Lab01.pdf (5 trang) quy định yêu cầu; Lab01-presentation.pdf (21 slide) giải thích
kiến trúc. RPC, receipts/gas, Merkle Patricia Trie, WAL và các vai trò client trong
slide không tự động trở thành yêu cầu lập trình của mô phỏng tối giản.

## Hai công việc độc lập

1. Production: sửa runtime theo đặc tả, kiểm các phản ví dụ đã phát hiện.
2. Testing: kiểm fixture, oracle, đường chạy thật và mutation gate sau production;
   không đổi expected chỉ để khớp lỗi runtime.

## Luồng hiện thực

- `common.py`: Ed25519, SHA-256, encoding nhị phân type/length và domain `TX:`,
  `HEADER:`, `VOTE:` gắn chain ID. `tx_root` là hash phẳng ordered tx, không phải
  cây Merkle; §5 cho phép commitment/encoding tự chọn.
- Block ID băm `[height,parent,state_hash,tx_root]`, giữ nguyên qua reproposal.
  Round, pol_round và proposer được ký trong header nhưng không đổi Block ID.
- `execution.py`: chữ ký, owner namespace, nonce; batch chạy trên bản sao và hủy
  toàn bộ nếu lỗi. Hash gồm data và nonce được sắp xếp.
- `node.py`: PROPOSE → PREVOTE → PRECOMMIT → FINALIZE; một vote/phase/slot.
  Quorum hợp lệ tạo lock kể cả sau timeout, không ký PRECOMMIT lần hai và không
  lùi khóa về round cũ. Đổi block đã khóa chỉ khi có quorum ở round mới hơn.
- Reproposal gửi `POLKA` chứa PREVOTE gốc. Receiver kiểm phase, chữ ký, chain,
  cùng height/round/hash và Q signer khác nhau; pol_round tuyên bố không đủ làm proof.
- HEADER → duyệt → REQUEST_BODY → BODY kiểm root/tx trước khi lưu. BODY không có
  header không được cache. Request có retry; buffer có cận.
- Catch-up: SYNC_REQ → SYNC_HEADERS (header + PRECOMMIT certificate) → REQUEST_BODY
  → BODY → kiểm certificate/parent/execution/root → finalize. Ledger phục vụ body
  đã chốt. Handler SYNC_RESP đầy đủ còn dùng để kiểm chứng bằng chứng/tương thích
  unit fixture; sender production dùng handshake header trước.
- `sim.py`: heap `(time,sequence,...)`, RNG riêng theo seed, deepcopy từng delivery.
  Receiver không sửa được certificate map của sender. Định tuyến qua các hop thật;
  không đọc ledger/state node khác để quyết định đồng thuận.
- `configuration.py`: kiểm BFT config và xác định đường dẫn Workspace.
- `identities.py`: nạp private identity fixture, độc lập seed mạng.
- `validation.py`: kiểm safety, hoàn tất/hội tụ và snapshot để so hai lần chạy.
- `main.py`: điều phối bootstrap qua admission/dedup, chạy mô phỏng và CLI;
  các tên kiểm tra cũ vẫn được import lại để giữ tương thích.

## Mạng và thời gian

Outbound rate dùng chung node. Receiver đặt trước capacity, có thể tạm block peer
admission; chờ được log trước SEND. Trước GST có thể mất/trễ/đảo thứ tự; sau GST
không hủy frame đã truyền vì receive throttling. Sau GST, đường nhiều hop đặt trước
toàn bộ slot truyền; các hop chia cùng một ngân sách sao cho tổng delay <= delta.
Relay dùng slot đã đặt, không đưa frame đang truyền vào hàng đợi không giới hạn.
Do đó cận delta áp toàn tuyến từ SEND đầu tới nhận cuối, không phải delta mỗi hop.
Chờ admission trước SEND được log riêng; phải tính nó khi chọn timeout/t_end.

TX/flow-control chưa gắn block dùng height=0; sync dùng height đầu khoảng;
BODY/REQUEST_BODY tra cùng Block ID. SEND/DROP/DELAY/BLOCK/UNBLOCK/RECEIVE có đủ
timestamp, node ID, type, height. FINALIZE ghi certificate.round.

## Bằng chứng chấp nhận

| Nguồn | Điều phải kiểm |
|---|---|
| Lab §2–3 | Payload không shared mutable; safety mọi height; phục hồi sau GST |
| Lab §5 | Signature/domain; encoding; seed mạng không sinh secret key |
| Lab §6 | Header trước body; topology; ngân sách node; đủ log |
| Lab §6.1 | Một vote/slot; block hợp lệ; lock/proof/unlock; một vote/signer |
| Lab §7 | Owner, nonce và cùng state từ cùng ordered tx |
| Lab §8 | Hai process; danh tính cố định; log bytes và state mọi honest |
| Lab §9 | T1–T8; unit + E2E thật; single entry; mutation bị phát hiện |
| Lab §10 | Folder/ZIP đúng ID; src/tests/logs/config/README/REPORT <=10 trang |
| Slide 5–6, 10, 20 | Tách module; validation trước commit; sync tự kiểm |

reviews/2026-11-04-initial.md và demo lịch sử mô tả snapshot trước đợt sửa. Không dùng số PASS hoặc
đoạn mã cũ ở đó làm expected. Kết quả test phải gắn checkout đã chạy và nêu cả
failed/incomplete, không chỉ số PASS.
