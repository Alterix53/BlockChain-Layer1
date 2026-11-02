"""
Kịch bản T2: Duplicate / Reordered Messages (Mục 9.2 Đề bài & Đặc tả Lab 01)
Điều kiện mạng:
- DES kích hoạt duplicate_probability và pre_gst_reorder_probability.
- Byzantine Replay node thu thập và phát lại các gói tin cũ.
Kỳ vọng:
- Tầng mạng DES ghi nhận các sự kiện ev=DUPLICATE và ev=DELAY reason=reorder.
- Tầng đồng thuận tuân thủ Quy tắc 7 Tendermint:
  * Không đếm 2 lần cho cùng một lá phiếu trùng lặp.
  * Nếu một voter gửi 2 phiếu khác nhau, ghi nhận log ev=EQUIVOCATION và giữ phiếu đầu tiên.
- Tầng mempool khử trùng lặp giao dịch phát lại bằng seen_tx_hashes.
- Tuyệt đối không bao giờ xảy ra phân nhánh (No Fork), bảo toàn tính Safety.
"""
import unittest
from src.byzantine import Replay
from src.common import KeyPair, Vote, sign
from src.main import run_sim
from tests.c_helpers import (
    assert_honest_certificates,
    assert_honest_safety,
    events,
    load_cfg,
    log_events,
    make_nodes,
    run_with_byzantine,
)


class TestT2DuplicateReorder(unittest.TestCase):
    def test_t2_network_duplicate_and_reorder_safety(self):
        # 1. Cấu hình mạng với tỉ lệ nhân bản và đảo thứ tự gói tin cao
        cfg = load_cfg(
            seed=42,
            gst=5000,
            pre_gst_max_delay=50,
            pre_gst_drop_probability=0.0,
            duplicate_probability=0.25,
            pre_gst_reorder_probability=0.35,
        )
        net = run_sim(cfg)

        # 2. Xác nhận tầng mạng DES đã thực sự nhân bản và xáo trộn gói tin
        dups = log_events(net, "DUPLICATE")
        reorders = [r for r in log_events(net, "DELAY") if r.get("reason") == "reorder"]
        self.assertTrue(len(dups) > 0, "Mạng phải ghi nhận sự kiện DUPLICATE")
        self.assertTrue(len(reorders) > 0, "Mạng phải ghi nhận sự kiện DELAY reason=reorder")

        # 3. Tính an toàn được bảo toàn: Không có Fork
        assert_honest_safety(net.nodes, set())
        assert_honest_certificates(net.nodes, set())

        first_chain = [b.hash() for b in net.nodes[0].ledger]
        for nd in net.nodes:
            self.assertEqual([b.hash() for b in nd.ledger], first_chain)

    def test_t2_rule7_anti_double_voting_and_equivocation(self):
        # Kiểm tra chi tiết Quy tắc 7 trên node nhận ở height 1 round 0
        nodes, net = make_nodes()
        receiver = nodes[0]

        voter_kp = KeyPair(b"test-voter-key-seed")
        cid = receiver.ctx["chain_id"]
        h, r = 1, 0

        vote_a = Vote("PREVOTE", h, r, b"block_hash_A_32bytes_sample12345", "V_TEST")
        vote_a = Vote(*vote_a.body(), sig=sign(voter_kp, "VOTE:" + cid, vote_a.body()))

        vote_b = Vote("PREVOTE", h, r, b"block_hash_B_32bytes_sample12345", "V_TEST")
        vote_b = Vote(*vote_b.body(), sig=sign(voter_kp, "VOTE:" + cid, vote_b.body()))

        # Nạp khóa của V_TEST vào context để pass chữ ký
        receiver.ctx["vpks"]["V_TEST"] = voter_kp.pk

        # Gửi vote_a lần 1
        receiver.on_vote(vote_a)
        # Gửi lặp lại vote_a lần 2 và lần 3 (Duplicate)
        receiver.on_vote(vote_a)
        receiver.on_vote(vote_a)

        slot = receiver.votes.get((h, r, "PREVOTE"), {})
        self.assertIn("V_TEST", slot)
        self.assertEqual(slot["V_TEST"].block_hash, vote_a.block_hash)
        self.assertEqual(len([v for v in slot.values() if v.voter == "V_TEST"]), 1,
                         "Voter chỉ được tính tối đa 1 phiếu duy nhất")

        # Gửi vote_b mâu thuẫn (Equivocation)
        receiver.on_vote(vote_b)
        # Phiếu bầu đầu tiên (vote_a) phải được giữ nguyên
        self.assertEqual(slot["V_TEST"].block_hash, vote_a.block_hash)
        # Hệ thống phải phát hiện và ghi log EQUIVOCATION
        equiv_logs = events(net, "EQUIVOCATION", voter="V_TEST")
        self.assertTrue(len(equiv_logs) >= 1, "Phải ghi nhận log EQUIVOCATION khi phát hiện 2 phiếu khác nhau")

    def test_t2_byzantine_replay_attack_node(self):
        # Kích hoạt node Byzantine Replay phát lại thông điệp cũ sau một khoảng delay
        behaviors = {2: (Replay, {"delay": 20, "limit": 10})}
        net = run_with_byzantine(behaviors, seed=42)

        # Kiểm tra node Byzantine đã phát lại thông điệp
        replays = log_events(net, "BYZ_REPLAY")
        self.assertTrue(len(replays) > 0, "Node Replay phải phát lại thông điệp")

        # Tất cả các node honest vẫn đạt được đồng thuận an toàn, không fork
        honest_nodes = [nd for nd in net.nodes if not getattr(nd, "is_byzantine", False)]
        assert_honest_safety(net.nodes, {2})
        assert_honest_certificates(net.nodes, {2})


if __name__ == "__main__":
    unittest.main()
