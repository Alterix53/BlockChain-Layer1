"""
Kịch bản T6: Proposer Silent / Crashed (Mục 9.6 Đề bài & Đặc tả Lab 01)
Điều kiện mạng:
- Proposer tại round 0 (V1) bị sập nguồn hoặc cố tình im lặng (Silent Byzantine).
Kỳ vọng:
- Đồng hồ timeout PROPOSE kích hoạt trên các node trung thực: ev=TIMEOUT kind=PROPOSE height=1 round=0.
- Các validator honest tuân thủ luật đồng thuận: Ký và phát PREVOTE NIL -> PRECOMMIT NIL.
- Vòng đồng thuận chuyển tiếp sang Round 1 (start_round(1)).
- Proposer của Round 1 (V2) là node trung thực, đề xuất khối hợp lệ.
- Khối đầu tiên được chốt thành công tại Round 1 với Proposer là V2:
  header.round == 1 và header.proposer == "V2".
- Chuỗi tiếp tục tiến lên các height tiếp theo, đảm bảo tính Liveness.
- Hỗ trợ tối đa f validator im lặng đồng thời mà hệ thống vẫn chốt đủ số block mục tiêu.
"""
import unittest
from src.byzantine import Silent
from tests.c_helpers import (
    assert_honest_certificates,
    assert_honest_progress,
    assert_honest_safety,
    log_events,
    run_with_byzantine,
)


class TestT6SilentProposer(unittest.TestCase):
    def test_t6_single_silent_proposer_round_advancement(self):
        # V1 là proposer tại height 1, round 0: cố tình im lặng hoàn toàn
        behaviors = {1: (Silent, {"mode": "all"})}
        net = run_with_byzantine(behaviors, seed=42)

        byz_indices = {1}
        honest_nodes = [nd for nd in net.nodes if nd.idx not in byz_indices]

        # 1. Kiểm tra sự kiện TIMEOUT PROPOSE tại height 1 round 0
        for nd in honest_nodes:
            timeouts = log_events(net, "TIMEOUT", node=nd.name, kind="PROPOSE",
                                  height=1, round=0)
            self.assertTrue(len(timeouts) >= 1, f"{nd.name} phải kích hoạt timeout PROPOSE ở round 0")

        # 2. Khối đầu tiên tại height 1 phải được chốt tại round 1 bởi V2
        for nd in honest_nodes:
            self.assertTrue(len(nd.ledger) >= 1, f"{nd.name} phải chốt được block")
            first_block = nd.ledger[0]
            self.assertEqual(first_block.header.height, 1)
            self.assertEqual(first_block.header.round, 1, "Block 1 phải được chốt tại round 1")
            self.assertEqual(first_block.header.proposer, "V2", "Proposer round 1 phải là V2")

        byz_names = {f"V{i}" for i in byz_indices}
        # 3. Tính Safety và Liveness: chuỗi vẫn tiến đủ 5 block trên mọi node honest
        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)

    def test_t6_three_silent_validators_liveness_preserved(self):
        # f = 3 node im lặng hoàn toàn (V1, V4, V7)
        byz_indices = {1, 4, 7}
        byz_names = {f"V{i}" for i in byz_indices}
        behaviors = {i: (Silent, {"mode": "all"}) for i in byz_indices}
        net = run_with_byzantine(behaviors, seed=10)

        # Toàn bộ 7 node honest còn lại (đủ Quorum Q = 7) vẫn tiến lên và chốt đủ 5 block
        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)


if __name__ == "__main__":
    unittest.main()
