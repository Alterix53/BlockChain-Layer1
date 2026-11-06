"""Honest safety, progress and certificates under Byzantine attacks."""
import unittest
from src.byzantine import EquivocateProposer, EquivocateVoter, InvalidBlock, Replay, Silent
from src.common import NIL
from tests.c_helpers import assert_honest_certificates, assert_honest_progress, assert_honest_safety, log_events, make_nodes, run_with_byzantine


REJECT_MODES = {m: r for m, r in InvalidBlock.EXPECTED_REASON.items() if r is not None}


def run_checked(test, behaviors, heights=5, **cfg):
    """Chạy mạng thật rồi kiểm safety + liveness + certificate trên node honest."""
    net = run_with_byzantine(behaviors, **cfg)
    byz = {f"V{i}" for i in behaviors}
    assert_honest_safety(net.nodes, byz)
    assert_honest_progress(net.nodes, byz, heights)
    assert_honest_certificates(net.nodes, byz)
    for nd in net.nodes:  # không chốt trùng: mỗi height xuất hiện đúng một lần
        if nd.name not in byz:
            test.assertEqual([b.header.height for b in nd.ledger], list(range(1, heights + 1)))
    return net


class TestSilent(unittest.TestCase):
    def test_network_silent_proposer_round_timeout_chain_continues(self):
        # đây cũng là kịch bản T6 của B: proposer h=1, r=0 im lặng
        net = run_checked(self, {1: (Silent, {})})
        for nd in net.nodes:
            if nd.name != "V1":
                self.assertTrue(log_events(net, "TIMEOUT", node=nd.name, kind="PROPOSE",
                                           height=1, round=0))
                first = nd.ledger[0].header
                self.assertEqual((first.round, first.proposer), (1, "V2"))

    def test_network_three_silent(self):
        run_checked(self, {i: (Silent, {}) for i in (1, 4, 7)})


class TestEquivocateVoter(unittest.TestCase):
    def test_network_f_equivocating_voters(self):
        byz = (3, 5, 7)
        net = run_checked(self, {i: (EquivocateVoter, {}) for i in byz})
        for i in byz:
            self.assertTrue(log_events(net, "BYZ_EQUIVOCATE_VOTE", node=f"V{i}"))
            self.assertTrue(log_events(net, "EQUIVOCATION", voter=f"V{i}"), "phải có honest phát hiện")


class TestEquivocateProposer(unittest.TestCase):
    def test_network_equivocating_proposer(self):
        """Mạng thật: không fork, có honest phát hiện, KHÔNG node honest nào kẹt. Trước khi sửa
        node.py, các ca này làm node honest kẹt mãi vì thiếu thân block thắng: h1 seed 2, 3
        (nhận block thua trước), h2 seed 1, 14 (nhận cả hai khi còn ở height 1)."""
        for h, seed in ((1, 1), (1, 2), (1, 3), (1, 42), (2, 1), (2, 14)):
            with self.subTest(height=h, seed=seed):
                byz = f"V{h % 10}"  # proposer của (h, round 0)
                net = run_checked(self, {h % 10: (EquivocateProposer, {"height": h})}, seed=seed)
                self.assertTrue(log_events(net, "BYZ_EQUIVOCATE_PROPOSAL", node=byz))
                self.assertTrue(log_events(net, "EQUIVOCATION", proposer=byz),
                                "phải có honest phát hiện proposer gửi 2 block")


class TestInvalidBlock(unittest.TestCase):
    def test_network_fake_pol_round(self):
        # V1 im lặng để round 0 thất bại; V2 tấn công ở round 1; round 2 (V3 honest) chốt
        behaviors = {1: (Silent, {}), 2: (InvalidBlock, {"mode": "fake_pol_round", "round": 1})}
        net = run_checked(self, behaviors)
        self.assertTrue(log_events(net, "BYZ_INVALID_BLOCK", node="V2", mode="fake_pol_round"))
        for nd in net.nodes[3:]:
            self.assertEqual(nd.signed[(1, 1, "PREVOTE")], NIL)
            self.assertEqual(nd.ledger[0].header.round, 2)

    def test_network_every_honest_rejects_and_chain_continues(self):
        for mode, reason in REJECT_MODES.items():
            with self.subTest(mode=mode):
                net = run_checked(self, {1: (InvalidBlock, {"mode": mode})},
                                  gst=0, delta=1, rate_limit=None, peer_block=None,
                                  duplicate_probability=0, pre_gst_reorder_probability=0)
                bad = net.nodes[1].evidence[0].hash()
                for nd in net.nodes[2:]:  # mọi honest
                    self.assertTrue(log_events(net, "REJECT", node=nd.name, reason=reason))
                    self.assertNotIn(bad, [b.hash() for b in nd.ledger])
                    self.assertEqual(nd.signed[(1, 0, "PREVOTE")], NIL)


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.nodes, self.net = make_nodes(behaviors={2: (Replay, {"delay": 7, "limit": 2})})
        self.replayer, self.sender, self.receiver = self.nodes[2], self.nodes[1], self.nodes[0]

    def test_network_replay_same_height_and_old_height(self):
        # delay 3: bản sao tới khi cả mạng còn ở height đó (thông điệp trùng)
        # delay 100: tới khi mạng đã sang height sau (thông điệp cũ)
        for delay in (3, 100):
            with self.subTest(delay=delay):
                net = run_checked(self, {4: (Replay, {"delay": delay, "limit": 20})})
                self.assertEqual(len(log_events(net, "BYZ_REPLAY", node="V4")), 20)
