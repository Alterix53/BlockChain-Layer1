"""
Kịch bản T1: Normal Run, No Faults (Mục 9.1 Đề bài & Đặc tả Lab 01)
Điều kiện mạng: Không lỗi, không Byzantine, độ trễ nhỏ sau GST.
Kỳ vọng:
- Toàn bộ validator trung thực chốt đủ 5 block ngay tại Round 0 (không timeout).
- Chuỗi block (ledger) trên mọi node giống hệt nhau.
- State hash cuối cùng khớp nhau tuyệt đối giữa mọi node (với seed 42 là 0b837be96db72e1f...).
- Dữ liệu state cuối cùng phản ánh đầy đủ 15 giao dịch của 3 tài khoản Alice, Bob, Carol.
- Toàn bộ node đều đạt trạng thái done = True.
"""
import unittest
from src.main import run_sim
from tests.c_helpers import (
    assert_honest_certificates,
    assert_honest_progress,
    assert_honest_safety,
    load_cfg,
    log_events,
)


class TestT1Normal(unittest.TestCase):
    def test_t1_normal_execution(self):
        # T1 is the fault-free baseline, independent of the demo config's noise.
        # Delay remains bounded/nonzero; fault and load scenarios have other tests.
        cfg = load_cfg(seed=42, gst=0, delta=1, byzantine={},
                       pre_gst_drop_probability=0, duplicate_probability=0,
                       pre_gst_reorder_probability=0, rate_limit=None, peer_block=None)
        net = run_sim(cfg)

        self.assertTrue(all(not nd.is_byzantine for nd in net.nodes))
        self.assertFalse(log_events(net, "DROP"))
        self.assertFalse(log_events(net, "DUPLICATE"))
        self.assertFalse(log_events(net, "DELAY", reason="reorder"))
        self.assertFalse(log_events(net, "TIMEOUT"))

        # 1. Toàn bộ node trung thực hoàn thành đủ 5 block
        self.assertEqual(len(net.nodes), cfg["n"])
        self.assertTrue(all(nd.done for nd in net.nodes), "Tất cả các node phải hoàn thành")

        # 2. Kiểm tra chuỗi ledger và tính an toàn (Safety)
        assert_honest_safety(net.nodes, set())
        assert_honest_progress(net.nodes, set(), cfg["heights"])
        assert_honest_certificates(net.nodes, set())

        first_chain = [b.hash() for b in net.nodes[0].ledger]
        self.assertEqual(len(first_chain), 5, "Phải chốt đúng 5 block")

        for nd in net.nodes:
            self.assertEqual([b.hash() for b in nd.ledger], first_chain, f"{nd.name} chuỗi không khớp")

        # 3. Mọi block đều được chốt tại Round 0
        for b in net.nodes[0].ledger:
            self.assertEqual(b.header.round, 0, f"Block height {b.header.height} phải chốt ở round 0")

        # Toàn bộ block đều chốt ở round 0 trên mọi node
        for nd in net.nodes:
            self.assertTrue(all(b.header.round == 0 for b in nd.ledger))
            self.assertTrue(all(cert.round == 0 for cert in nd.certificates.values()))

        # 4. Trạng thái ứng dụng và Nonce
        expected_state = {
            "Alice/msg": "v5",
            "Bob/msg": "v5",
            "Carol/msg": "v5",
        }
        expected_nonces = {
            "Alice": 5,
            "Bob": 5,
            "Carol": 5,
        }
        for nd in net.nodes:
            self.assertEqual(nd.state.data, expected_state)
            self.assertEqual(nd.state.nonces, expected_nonces)

        # 5. State hash cuối cùng khớp nhau trên mọi node và khớp giá trị chuẩn seed 42
        state_hash = net.nodes[0].state.hash()
        self.assertTrue(state_hash.hex().startswith("0b837be96db72e1f"),
                        f"State hash {state_hash.hex()} phải bắt đầu bằng 0b837be96db72e1f")
        for nd in net.nodes:
            self.assertEqual(nd.state.hash(), state_hash)


if __name__ == "__main__":
    unittest.main()
