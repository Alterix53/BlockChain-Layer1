"""Test 5 lớp Byzantine (src/byzantine.py).

Mỗi lớp có hai mức:
  - unit: node trên RecordingNet, kiểm attacker định gửi GÌ cho AI, chữ ký có đúng không;
  - mạng thật (run_with_byzantine): node honest có chốt đúng, không fork, chuỗi vẫn chạy,
    và mỗi block đã chốt có CommitCertificate (của D) hợp lệ.
Chạy từ thư mục Workspace:  python -m unittest discover -s tests -p "test_byzantine.py" -v
"""
import os
import sys
import unittest

_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_TESTS), _TESTS):  # Workspace/ (cho src) và tests/ (cho c_helpers)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.byzantine import (REGISTRY, EquivocateProposer, EquivocateVoter,  # noqa: E402
                           InvalidBlock, Replay, Silent, make_node)
from src.common import NIL, H, verify  # noqa: E402
from src.node import Node  # noqa: E402
from c_helpers import (CHAIN, assert_honest_certificates, assert_honest_progress,  # noqa: E402
                       assert_honest_safety, events, log_events, make_nodes, signed_vote,
                       valid_block, run_with_byzantine)

A, B = H(b"block-A"), H(b"block-B")


def sent_by(net, idx):
    return [(dst, msg) for src, dst, msg in net.sent if src == idx]


def start_all(nodes):
    """START mọi node. V1 là proposer h=1, r=0 nên propose() của nó chạy ngay tại đây,
    giống mạng thật: tham số tấn công phải được cấu hình TRƯỚC bước này."""
    for nd in nodes:
        nd.start()


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


# ----------------------------------------------------------------------------- Silent
class TestSilent(unittest.TestCase):
    def test_all_mode_sends_nothing_at_all(self):
        nodes, net = make_nodes(behaviors={1: (Silent, {})}, start=False)
        start_all(nodes)
        silent = nodes[1]  # V1 là proposer h=1, r=0 nhưng không đề xuất
        silent.on_message(("VOTE", signed_vote(nodes[0], "PREVOTE", A)))
        silent.on_message(("PROPOSAL", valid_block(nodes[0])))
        silent.on_timeout(("PROPOSE", 1, 0))
        self.assertEqual(sent_by(net, 1), [])
        self.assertEqual(silent.ledger, [])
        self.assertEqual(len(events(net, "BYZ_SILENT", node="V1")), 1)

    def test_proposer_mode_votes_but_never_proposes(self):
        nodes, net = make_nodes(behaviors={1: (Silent, {"mode": "proposer"})}, start=False)
        start_all(nodes)
        self.assertEqual([m for _, m in sent_by(net, 1) if m[0] == "PROPOSAL"], [])
        self.assertEqual(len(events(net, "BYZ_SKIP_PROPOSE", node="V1")), 1)
        nodes[1].on_timeout(("PROPOSE", 1, 0))  # hết giờ chờ proposal -> prevote NIL như honest
        (dst, (kind, vote)), = sent_by(net, 1)
        self.assertEqual((dst, kind, vote.kind, vote.block_hash), (None, "VOTE", "PREVOTE", NIL))

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


# ----------------------------------------------------------------------------- EquivocateVoter
class TestEquivocateVoter(unittest.TestCase):
    def test_two_signed_votes_same_slot_to_two_groups(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateVoter, {
            "targets": (A, B), "groups": ([0, 2], [3, 4])})})
        voter = nodes[1]
        voter.cast("PREVOTE", A)
        self.assertEqual(voter.step, "PREVOTE")
        sent = sent_by(net, 1)
        self.assertEqual(sorted(dst for dst, _ in sent), [0, 2, 3, 4])
        for dst, (_, v) in sent:
            self.assertEqual(v.block_hash, A if dst in (0, 2) else B)
            self.assertTrue(verify(voter.kp.pk, "VOTE:" + CHAIN, v.body(), v.sig))
        self.assertEqual({(v.height, v.round, v.kind, v.voter) for v in voter.evidence},
                         {(1, 0, "PREVOTE", "V1")})
        voter.cast("PREVOTE", A)  # gọi lại cùng slot: không phát thêm
        self.assertEqual(len(sent_by(net, 1)), 4)
        voter.cast("PRECOMMIT", A)  # phase sau cũng equivocate
        self.assertEqual(len(sent_by(net, 1)), 8)

    def test_default_targets_broadcast_block_and_nil(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateVoter, {})})
        nodes[1].cast("PREVOTE", A)
        self.assertEqual([(dst, m[1].block_hash) for dst, m in sent_by(net, 1)],
                         [(None, A), (None, NIL)])

    def test_outside_attack_slot_votes_like_honest(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateVoter, {"round": 1})})
        nodes[1].cast("PREVOTE", A)
        self.assertEqual([(dst, m[1].block_hash) for dst, m in sent_by(net, 1)], [(None, A)])

    def test_receiver_counts_first_vote_once_and_logs_equivocation(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateVoter, {"targets": (A, B)})})
        nodes[1].cast("PREVOTE", A)
        va, vb = nodes[1].evidence
        r0, r2 = nodes[0], nodes[2]
        for v in (va, vb, va):        # r0 nhận A trước
            r0.on_message(("VOTE", v))
        for v in (vb, va):            # r2 nhận B trước
            r2.on_message(("VOTE", v))
        self.assertEqual(r0.votes[(1, 0, "PREVOTE")], {"V1": va})
        self.assertEqual(r2.votes[(1, 0, "PREVOTE")], {"V1": vb})  # mỗi receiver giữ vote đến trước
        self.assertEqual(len(events(net, "EQUIVOCATION", node="V0")), 1)
        self.assertEqual(len(events(net, "EQUIVOCATION", node="V2")), 1)

    def test_network_f_equivocating_voters(self):
        byz = (3, 5, 7)
        net = run_checked(self, {i: (EquivocateVoter, {}) for i in byz})
        for i in byz:
            self.assertTrue(log_events(net, "BYZ_EQUIVOCATE_VOTE", node=f"V{i}"))
            self.assertTrue(log_events(net, "EQUIVOCATION", voter=f"V{i}"), "phải có honest phát hiện")


# ----------------------------------------------------------------------------- EquivocateProposer
class TestEquivocateProposer(unittest.TestCase):
    def test_two_valid_blocks_different_hash_to_two_groups(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateProposer, {"groups": ([0, 2], [3, 4])})},
                                start=False)
        prop, receiver = nodes[1], nodes[0]
        before = prop.state.hash()
        start_all(nodes)
        a, b = prop.evidence
        self.assertNotEqual(a.hash(), b.hash())
        self.assertEqual((a.header.height, a.header.round, a.header.parent, a.header.proposer),
                         (b.header.height, b.header.round, b.header.parent, b.header.proposer))
        self.assertEqual(prop.state.hash(), before, "tạo block không được sửa state thật")
        for blk in (a, b):
            self.assertTrue(verify(prop.kp.pk, "HEADER:" + CHAIN, blk.header.body(), blk.header.sig))
            self.assertEqual(receiver._check(blk), (True, ""), "cả hai block đều phải hợp lệ")
        for dst, (_, blk) in sent_by(net, 1):
            self.assertEqual(blk.hash(), a.hash() if dst in (0, 2) else b.hash())

    def test_without_valid_tx_falls_back_to_honest(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateProposer, {})}, start=False)
        nodes[1].mempool = []
        start_all(nodes)
        proposals = [m for _, m in sent_by(net, 1) if m[0] in ("PROPOSAL", "HEADER")]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(len(events(net, "BYZ_SKIP", node="V1", reason="no_valid_tx")), 1)

    def test_groups_need_net_send_from_part_a(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateProposer, {"groups": ([0], [2])})},
                                start=False)
        net.send = None  # giống Net thật hiện tại: chưa có send
        with self.assertRaisesRegex(RuntimeError, "send"):
            nodes[1].start()

    def test_receiver_keeps_first_proposal_and_logs_equivocation(self):
        nodes, net = make_nodes(behaviors={1: (EquivocateProposer, {"groups": ([0], [2])})},
                                start=False)
        start_all(nodes)
        a, b = nodes[1].evidence
        receiver = nodes[3]
        net.clear()
        receiver.on_message(("PROPOSAL", a))
        receiver.on_message(("PROPOSAL", b))
        self.assertIs(receiver.proposals[(1, 0)], a, "prevote theo proposal đến trước")
        self.assertEqual(receiver.signed[(1, 0, "PREVOTE")], a.hash())
        self.assertEqual(len(events(net, "EQUIVOCATION", node="V3", proposer="V1")), 1)
        # nhưng giữ thân CẢ HAI: nếu B đạt Q precommit thì vẫn chốt được (lỗi cũ của node.py)
        self.assertEqual(set(receiver.blocks), {a.hash(), b.hash()})

    def test_bodies_arriving_one_height_early_are_kept(self):
        # chỉ attacker START: receiver còn ở height 0 nên hai block height 1 là "tương lai"
        nodes, net = make_nodes(behaviors={1: (EquivocateProposer, {"groups": ([0], [2])})},
                                start=False)
        nodes[1].start()
        a, b = nodes[1].evidence
        receiver = nodes[3]
        receiver.on_message(("PROPOSAL", a))
        receiver.on_message(("PROPOSAL", b))
        receiver.start()
        self.assertIs(receiver.proposals[(1, 0)], a)
        self.assertEqual(set(receiver.blocks), {a.hash(), b.hash()})

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


# ----------------------------------------------------------------------------- InvalidBlock
REJECT_MODES = {m: r for m, r in InvalidBlock.EXPECTED_REASON.items() if r is not None}


class TestInvalidBlock(unittest.TestCase):
    def test_each_mode_hits_its_own_guard(self):
        for mode, reason in REJECT_MODES.items():
            with self.subTest(mode=mode):
                nodes, net = make_nodes(behaviors={1: (InvalidBlock, {"mode": mode})}, start=False)
                prop, receiver = nodes[1], nodes[0]
                before = receiver.state.hash()
                start_all(nodes)
                proposals = [m for _, m in sent_by(net, 1) if m[0] in ("PROPOSAL", "HEADER")]
                self.assertTrue(proposals)
                msg = proposals[0]
                net.clear()
                hd = msg[1] if hasattr(msg[1], "body") else msg[1].header
                self.assertTrue(verify(prop.kp.pk, "HEADER:" + CHAIN, hd.body(), hd.sig),
                                "chữ ký header phải đúng: lỗi chỉ nằm ở nội dung")
                receiver.on_message(("PROPOSAL", prop.evidence[-1]))
                self.assertEqual(len(events(net, "REJECT", node="V0", reason=reason)), 1)
                # bad_tx_root/bad_pol_round bị chặn ngay ở cổng on_proposal nên chưa prevote gì;
                # các lỗi còn lại prevote NIL ngay. Hết giờ PROPOSE thì mọi trường hợp đều là NIL.
                receiver.on_timeout(("PROPOSE", 1, 0))
                self.assertEqual(receiver.signed[(1, 0, "PREVOTE")], NIL)
                self.assertEqual(receiver.state.hash(), before)
                self.assertEqual(receiver.ledger, [])

    def test_fake_pol_round_is_not_trusted(self):
        # V2 là proposer ở h=1, r=1. Nó khai "block này đã có polka ở round 0" nhưng không có.
        nodes, net = make_nodes(behaviors={2: (InvalidBlock, {"mode": "fake_pol_round",
                                                              "round": 1})})
        receiver, attacker = nodes[0], nodes[2]
        for nd in (receiver, attacker):
            nd.start_round(1)
        proposals = [x for x in sent_by(net, 2) if x[1][0] in ("PROPOSAL", "HEADER")]
        self.assertTrue(proposals)
        blk = attacker.evidence[-1]
        self.assertEqual((blk.header.round, blk.header.pol_round), (1, 0))
        self.assertEqual(receiver._check(blk), (True, ""), "nội dung block hợp lệ")
        receiver.on_message(("PROPOSAL", blk))
        self.assertNotIn((1, 1, "PREVOTE"), receiver.signed, "chưa tự thấy polka thì phải chờ")
        receiver.on_timeout(("PROPOSE", 1, 1))
        self.assertEqual(receiver.signed[(1, 1, "PREVOTE")], NIL)

        # đối chứng: nếu receiver TỰ thấy Q prevote ở round 0 cho đúng block đó thì tin
        nodes, net = make_nodes(behaviors={2: (InvalidBlock, {"mode": "fake_pol_round",
                                                              "round": 1})})
        receiver, attacker = nodes[0], nodes[2]
        for voter in nodes[3:10]:  # 7 = Q prevote ở round 0
            receiver.on_message(("VOTE", signed_vote(voter, "PREVOTE", blk.hash(), round=0)))
        for nd in (receiver, attacker):
            nd.start_round(1)
        receiver.on_message(("PROPOSAL", blk))
        self.assertEqual(receiver.signed[(1, 1, "PREVOTE")], blk.hash())

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
                net = run_checked(self, {1: (InvalidBlock, {"mode": mode})})
                bad = net.nodes[1].evidence[0].hash()
                for nd in net.nodes[2:]:  # mọi honest
                    self.assertTrue(log_events(net, "REJECT", node=nd.name, reason=reason))
                    self.assertNotIn(bad, [b.hash() for b in nd.ledger])
                    self.assertEqual(nd.signed[(1, 0, "PREVOTE")], NIL)


# ----------------------------------------------------------------------------- Replay
class TestReplay(unittest.TestCase):
    def setUp(self):
        self.nodes, self.net = make_nodes(behaviors={2: (Replay, {"delay": 7, "limit": 2})})
        self.replayer, self.sender, self.receiver = self.nodes[2], self.nodes[1], self.nodes[0]

    def test_records_and_replays_identical_message(self):
        original = ("VOTE", signed_vote(self.sender, "PREVOTE", A))
        self.replayer.on_message(original)
        idx, delay, key = self.net.timeouts[-1]
        self.assertEqual((idx, delay, key), (2, 7, ("BYZ_REPLAY", 0)))
        self.replayer.on_timeout(key)  # RecordingNet không tự kích hoạt hẹn giờ
        (dst, msg), = sent_by(self.net, 2)
        self.assertIs(msg, original, "phải gửi lại nguyên đối tượng, không sửa, không ký lại")
        self.receiver.on_message(original)
        self.receiver.on_message(msg)
        self.assertEqual(len(self.receiver.votes[(1, 0, "PREVOTE")]), 1, "bản phát lại không được đếm thêm")

    def test_bounded_and_no_rerecord(self):
        votes = [("VOTE", signed_vote(self.nodes[i], "PREVOTE", A)) for i in (0, 1, 3)]
        self.replayer.on_message(votes[0])
        self.replayer.on_message(votes[0])  # cùng thông điệp quay lại: không ghi lần 2
        for v in votes[1:]:
            self.replayer.on_message(v)
        self.assertEqual(self.replayer.recorded, votes[:2], "tối đa limit=2 thông điệp")

    def test_only_attack_height_and_other_timeouts_still_work(self):
        old = ("VOTE", signed_vote(self.sender, "PREVOTE", A, height=2))
        self.replayer.on_message(old)
        self.assertEqual(self.replayer.recorded, [])
        self.replayer.on_timeout(("PROPOSE", 1, 0))  # timeout đồng thuận vẫn chạy như honest
        self.assertEqual(self.replayer.signed[(1, 0, "PREVOTE")], NIL)

    def test_network_replay_same_height_and_old_height(self):
        # delay 3: bản sao tới khi cả mạng còn ở height đó (thông điệp trùng)
        # delay 100: tới khi mạng đã sang height sau (thông điệp cũ)
        for delay in (3, 100):
            with self.subTest(delay=delay):
                net = run_checked(self, {4: (Replay, {"delay": delay, "limit": 20})})
                self.assertEqual(len(log_events(net, "BYZ_REPLAY", node="V4")), 20)


# ----------------------------------------------------------------------------- nhảy round (B)
class TestRoundSkipAttack(unittest.TestCase):
    """Byzantine gửi phiếu ở round rất cao để kéo node honest nhảy round theo.
    Node chỉ nhảy khi f+1 validator KHÁC NHAU ở round cao hơn: trong f+1 người chắc chắn
    có ít nhất 1 honest, nên f Byzantine một mình không kéo được."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver = self.nodes[0]

    def high_round_votes(self, voters, r=50):
        for i in voters:
            v = signed_vote(self.nodes[i], "PREVOTE", A, round=r)
            self.receiver.on_message(("VOTE", v))

    def test_f_byzantine_cannot_force_round_skip(self):
        self.high_round_votes((7, 8, 9))                    # f = 3
        self.high_round_votes((7, 8, 9), r=60)              # gửi thêm cũng chỉ là 3 người
        self.assertEqual(self.receiver.round, 0)
        self.assertEqual(events(self.net, "ROUND_SKIP"), [])

    def test_f_plus_one_validators_trigger_skip(self):  # đối chứng
        self.high_round_votes((6, 7, 8, 9))                 # f + 1 = 4
        self.assertEqual(self.receiver.round, 50)
        self.assertEqual(len(events(self.net, "ROUND_SKIP", node="V0", to=50)), 1)

    def test_far_future_or_absurd_messages_are_not_stored(self):
        # chống làm đầy bộ nhớ: height quá xa, round âm hoặc quá trần bị bỏ
        for fields in ({"height": 1 + 4}, {"round": -1}, {"round": 10**6}):
            v = signed_vote(self.nodes[7], "PREVOTE", A, **fields)
            self.receiver.on_message(("VOTE", v))
            self.assertNotIn((v.height, v.round, "PREVOTE"), self.receiver.votes, fields)
        self.assertEqual(self.receiver.round, 0)


# ----------------------------------------------------------------------------- cấu hình
class TestConfigure(unittest.TestCase):
    def test_bad_parameters_are_rejected(self):
        nodes, _ = make_nodes(start=False)
        ctx, kp = nodes[0].ctx, nodes[0].kp
        bad = [
            (EquivocateVoter, {"groups": ([0, 1], [1, 2])}, ValueError),   # giao nhau
            (EquivocateVoter, {"groups": ([0], [99])}, ValueError),        # ngoài [0, n)
            (EquivocateVoter, {"targets": (A, A)}, ValueError),
            (EquivocateVoter, {"phases": ("FOO",)}, ValueError),
            (InvalidBlock, {"mode": "no_such_mode"}, ValueError),
            (Silent, {"mode": "loud"}, ValueError),
            (Replay, {"delay": -1}, ValueError),
            (Silent, {"typo_param": 1}, TypeError),                        # tên tham số sai
        ]
        for cls, params, err in bad:
            with self.subTest(cls=cls.__name__, params=params):
                with self.assertRaises(err):
                    cls(5, ctx, kp).configure(**params)

    def test_registry_and_factory(self):
        nodes, _ = make_nodes(start=False)
        ctx, kp = nodes[0].ctx, nodes[0].kp
        for name, cls in REGISTRY.items():
            self.assertTrue(issubclass(cls, Node), name)
        nd = make_node("invalid_block", 5, ctx, kp, mode="bad_parent")
        self.assertEqual((type(nd), nd.mode), (InvalidBlock, "bad_parent"))
        with self.assertRaises(ValueError):
            make_node("no_such_behavior", 5, ctx, kp)
        with self.assertRaises(ValueError):
            make_node("honest", 5, ctx, kp, mode="x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
