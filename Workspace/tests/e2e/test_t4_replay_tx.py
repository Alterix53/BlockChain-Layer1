import unittest
from src.common import H, KeyPair, Tx, encode, sign
from src.node import Node
from src.sim import Net
from src.execution import apply_tx


class TestT4ReplayTx(unittest.TestCase):
    """T4 (phần D). Viết lại thành unittest để chạy chung lệnh của nhóm; nội dung giữ nguyên."""

    def test_t4_transaction_replay_prevention(self):
        """
        Kịch bản kiểm thử T4: Replayed/duplicate transaction -> Applied at most once.
        Xác minh:
        1. Mempool khử trùng lặp giao dịch phát lại trong O(1).
        2. Block 1 chỉ nhận TX1, Block 2 chỉ nhận TX2 (không bị chèn lại TX1).
        3. Nonce của tài khoản tăng tuần tự, không bị tăng khống bởi giao dịch replay.
        4. Tầng thực thi (apply_tx) từ chối giao dịch cũ với mã 'bad_nonce'.
        """
        # 1. Cấu hình mạng mô phỏng (max_txs_per_block = 1 để tách riêng Block 1 và Block 2)
        cfg = {
            "n": 8,
            "f": 2,
            "seed": 42,
            "delta": 3,
            "chain_id": "testnet-t4",
            "accounts": ["Alice"],
            "heights": 2,
            "base_timeout": 10,
            "timeout_inc": 2,
            "max_txs_per_block": 1,
            "t_end": 200,
        }

        n, f = cfg["n"], cfg["f"]
        cid = cfg["chain_id"]
        net = Net(cfg)
        vals = [f"V{i}" for i in range(n)]
        vkps = [KeyPair(f"val-t4-{i}".encode()) for i in range(n)]
        alice_kp = KeyPair(b"alice-secret-seed")

        ctx = dict(
            chain_id=cid,
            vals=vals,
            f=f,
            net=net,
            heights=cfg["heights"],
            vpks={v: k.pk for v, k in zip(vals, vkps)},
            acct_pks={"Alice": alice_kp.pk},
            base_timeout=cfg["base_timeout"],
            timeout_inc=cfg["timeout_inc"],
            max_txs=cfg["max_txs_per_block"],
        )

        # 2. Tạo giao dịch hợp lệ TX1 (nonce = 1) và TX2 (nonce = 2)
        tx1_raw = Tx("Alice", 1, "Alice/msg", "hello_first")
        tx1 = Tx(*tx1_raw.body(), sig=sign(alice_kp, "TX:" + cid, tx1_raw.body()))

        tx2_raw = Tx("Alice", 2, "Alice/msg", "hello_second")
        tx2 = Tx(*tx2_raw.body(), sig=sign(alice_kp, "TX:" + cid, tx2_raw.body()))

        # Khởi tạo danh sách validator
        net.nodes = [Node(i, ctx, vkps[i]) for i in range(n)]

        # Nạp TX1 (kèm bản sao trùng lặp) và TX2 vào mempool của các node
        for nd in net.nodes:
            nd.mempool = [tx1, tx1, tx2]  # tx1 xuất hiện lặp lại trong mempool
            nd.seen_tx_hashes.add(H(encode(tx1.body())))
            nd.seen_tx_hashes.add(H(encode(tx2.body())))

        # 3. KẺ TẤN CÔNG LIÊN TỤC PHÁT LẠI TX1 QUA HÀNG ĐỢI MẠNG
        # Các gói tin phát lại được gửi vào các mốc thời gian khác nhau của quá trình đồng thuận
        for i in range(n):
            net.push(2, "MSG", i, ("TX", tx1))
            net.push(6, "MSG", i, ("TX", tx1))
            net.push(10, "MSG", i, ("TX", tx1))

        # Chạy mô phỏng toàn mạng
        net.run(cfg["t_end"])

        # 4. KHẲNG ĐỊNH KẾT QUẢ (ASSERTIONS)
        # a. Toàn bộ các node hoàn thành đầy đủ 2 block
        assert all(nd.done for nd in net.nodes), "Tất cả các node phải hoàn thành 2 block"

        first_node_state_hash = net.nodes[0].state.hash()
        for nd in net.nodes:
            assert len(nd.ledger) == 2, "Hệ thống phải chốt đúng 2 block"

            # Nonce của Alice tăng chính xác lên 2 (TX1 và TX2, không bị tăng khống bởi replay)
            assert nd.state.nonces.get("Alice") == 2

            # Dữ liệu cập nhật đúng theo thứ tự thời gian
            assert nd.state.data.get("Alice/msg") == "hello_second"

            # Tính toàn vẹn và tất định: Mọi node đều có chung state_hash
            assert nd.state.hash() == first_node_state_hash

            # Block 1 chỉ chứa đúng 1 giao dịch TX1
            b1_alice_txs = [t for t in nd.ledger[0].txs if t.sender == "Alice"]
            assert len(b1_alice_txs) == 1
            assert b1_alice_txs[0].nonce == 1

            # Block 2 tuyệt đối KHÔNG chứa TX1 phát lại, chỉ chứa TX2
            b2_replayed = [t for t in nd.ledger[1].txs if t.sender == "Alice" and t.nonce == 1]
            assert len(b2_replayed) == 0, "Block 2 tuyệt đối không được chứa TX1 phát lại"

            b2_alice_txs = [t for t in nd.ledger[1].txs if t.sender == "Alice"]
            assert len(b2_alice_txs) == 1
            assert b2_alice_txs[0].nonce == 2

        # b. Kiểm tra phòng thủ tầng Mempool sau khi chốt:
        # Gửi lại TX1 trực tiếp vào node -> Bị seen_tx_hashes chặn, mempool không nhận
        test_node = net.nodes[0]
        initial_mempool_len = len(test_node.mempool)
        test_node.on_tx(tx1)
        assert len(test_node.mempool) == initial_mempool_len, "Mempool phải từ chối nạp lại TX1"

        # c. Kiểm tra phòng thủ tầng Thực thi (Execution Layer):
        # Cố tình thực thi lại TX1 trên state hiện tại -> Phải bị từ chối với mã lỗi 'bad_nonce'
        err = apply_tx(test_node.state, tx1, cid, {"Alice": alice_kp.pk})
        assert err == "bad_nonce", "Executor phải từ chối phát lại TX1 vì sai số nonce"


if __name__ == "__main__":
    unittest.main()
