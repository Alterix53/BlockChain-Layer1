"""T3 - chữ ký sai / sai domain: thông điệp bị từ chối VÀ có ghi lý do.

Năm đường nhận có chữ ký: vote, header (proposal), tx trong block, certificate khi đồng bộ
(SYNC_RESP của D), tx gossip (TX của D). Mỗi nhóm có một ca đúng (đối chứng) để chắc test đo
đúng phần kiểm chữ ký, không phải vì thông điệp hỏng lung tung. Chữ ký sai giữ đúng 64 byte.
Chạy từ thư mục Workspace:  python -m unittest discover -s tests -p "test_t3.py" -v
"""
import os
import sys
import unittest
from dataclasses import replace
from unittest import mock

_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_TESTS), _TESTS):  # Workspace/ (cho src) và tests/ (cho c_helpers)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.byzantine import flip_byte  # noqa: E402
from src.common import (NIL, Block, CommitCertificate, H, Header, SyncResp, Tx,  # noqa: E402
                        Vote, sign, tx_root)
from src.main import run_sim  # noqa: E402
from src.sim import Net  # noqa: E402
from c_helpers import (ACCOUNTS, CHAIN, assert_honest_certificates, assert_honest_progress,  # noqa: E402
                       assert_honest_safety, commit_cert, events, load_cfg, log_events,
                       make_nodes, signed_header, signed_tx, signed_vote, valid_block)

TARGET = H(b"block-A")


class TestT3Vote(unittest.TestCase):
    """Đường nhận vote: Node.on_vote."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver, self.sender = self.nodes[0], self.nodes[1]

    def slot(self, kind="PREVOTE"):
        return self.receiver.votes.get((1, 0, kind), {})

    def assert_rejected(self, bad, slot_kind="PREVOTE"):
        self.receiver.on_message(("VOTE", bad))
        rej = events(self.net, "REJECT", node="V0", reason="bad_vote_sig")
        self.assertEqual(len(rej), 1, "phải có đúng 1 dòng REJECT có lý do")
        self.assertEqual(rej[0]["height"], bad.height, "dòng log phải ghi height")
        self.assertNotIn(bad.voter, self.slot(slot_kind), "vote lỗi không được đếm")
        # vote lỗi không được 'chiếm chỗ': vote đúng của cùng người gửi vẫn được đếm sau đó
        good = signed_vote(self.sender, "PREVOTE", TARGET)
        self.receiver.on_message(("VOTE", good))
        self.assertEqual(self.slot().get("V1"), good)

    def test_valid_vote_is_counted(self):  # đối chứng
        v = signed_vote(self.sender, "PREVOTE", TARGET)
        self.receiver.on_message(("VOTE", v))
        self.assertEqual(self.slot(), {"V1": v})
        self.assertEqual(events(self.net, "REJECT"), [])

    def test_corrupted_signature(self):
        v = signed_vote(self.sender, "PREVOTE", TARGET)
        self.assert_rejected(replace(v, sig=flip_byte(v.sig)))

    def test_empty_signature(self):
        v = signed_vote(self.sender, "PREVOTE", TARGET)
        self.assert_rejected(replace(v, sig=b""))

    def test_wrong_domain(self):
        # ký đúng nội dung, đúng khóa, nhưng sai ngữ cảnh (loại thông điệp hoặc chain)
        for domain in ("TX:" + CHAIN, "HEADER:" + CHAIN, "VOTE:other-chain"):
            with self.subTest(domain=domain):
                self.setUp()
                self.assert_rejected(signed_vote(self.sender, "PREVOTE", TARGET, domain=domain))

    def test_field_changed_after_signing(self):
        # sửa bất kỳ trường nào nằm trong body đã ký -> chữ ký cũ không còn khớp
        for field, value in (("height", 2), ("round", 1), ("block_hash", H(b"block-B")),
                             ("kind", "PRECOMMIT"), ("voter", "V2")):
            with self.subTest(field=field):
                self.setUp()
                v = replace(signed_vote(self.sender, "PREVOTE", TARGET), **{field: value})
                self.assert_rejected(v, slot_kind=v.kind)

    def test_unknown_voter(self):
        self.assert_rejected(signed_vote(self.sender, "PREVOTE", TARGET, voter="V99"))


class TestT3Header(unittest.TestCase):
    """Đường nhận proposal: Node.on_proposal kiểm chữ ký header trước mọi thứ khác."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver, self.proposer = self.nodes[0], self.nodes[1]  # V1 là proposer h=1, r=0

    def assert_rejected(self, block, reason="bad_header_sig"):
        self.receiver.on_message(("PROPOSAL", block))
        rej = events(self.net, "REJECT", node="V0", reason=reason)
        self.assertEqual(len(rej), 1)
        self.assertEqual(rej[0]["height"], block.header.height)
        self.assertEqual(self.receiver.proposals, {}, "proposal lỗi không được lưu")
        self.assertNotIn((1, 0, "PREVOTE"), self.receiver.signed, "chưa được prevote gì")

    def test_valid_proposal_is_accepted(self):  # đối chứng
        b = valid_block(self.proposer, [signed_tx(1)])
        self.receiver.on_message(("PROPOSAL", b))
        self.assertEqual(self.receiver.proposals[(1, 0)], b)
        self.assertEqual(self.receiver.signed[(1, 0, "PREVOTE")], b.hash())
        self.assertEqual(events(self.net, "REJECT"), [])

    def test_corrupted_header_signature(self):
        b = valid_block(self.proposer)
        self.assert_rejected(Block(replace(b.header, sig=flip_byte(b.header.sig)), b.txs))

    def test_wrong_domain(self):
        for domain in ("VOTE:" + CHAIN, "TX:" + CHAIN, "HEADER:other-chain"):
            with self.subTest(domain=domain):
                self.setUp()
                b = valid_block(self.proposer)
                self.assert_rejected(Block(signed_header(self.proposer, b.header, domain), b.txs))

    def test_field_changed_after_signing(self):
        b = valid_block(self.proposer)
        hd = replace(b.header, state_hash=flip_byte(b.header.state_hash))  # giữ chữ ký cũ
        self.assert_rejected(Block(hd, b.txs))

    def test_claims_other_proposer(self):
        # V1 ký nhưng ghi proposer="V2": node kiểm bằng khóa công khai của V2 -> sai
        b = valid_block(self.proposer)
        hd = signed_header(self.proposer, replace(b.header, proposer="V2"))
        self.assert_rejected(Block(hd, b.txs))

    def test_correct_signature_but_not_his_turn(self):
        # chữ ký V2 đúng, nhưng h=1, r=0 không phải lượt của V2 -> lý do khác: wrong_proposer
        v2 = self.nodes[2]
        b = valid_block(self.proposer)
        hd = signed_header(v2, replace(b.header, proposer="V2"))
        self.assert_rejected(Block(hd, b.txs), reason="wrong_proposer")


class TestT3Transaction(unittest.TestCase):
    """Tx sai chữ ký nằm trong block có header hợp lệ: bị bắt ở Node._check -> apply_txs."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver, self.proposer = self.nodes[0], self.nodes[1]

    def block_with(self, txs):
        # header hợp lệ và tx_root khớp body, để lỗi chỉ còn nằm ở chữ ký tx
        hd = Header(height=1, round=0, pol_round=-1, parent=self.proposer.last_hash(),
                    state_hash=self.proposer.state.hash(), tx_root=tx_root(txs), proposer="V1")
        return Block(signed_header(self.proposer, hd), tuple(txs))

    def assert_rejected(self, txs):
        before = self.receiver.state.hash()
        self.receiver.on_message(("PROPOSAL", self.block_with(txs)))
        self.assertEqual(len(events(self.net, "REJECT", node="V0", reason="bad_tx_sig")), 1)
        self.assertEqual(self.receiver.signed[(1, 0, "PREVOTE")], NIL, "phải prevote NIL")
        self.assertEqual(self.receiver.state.hash(), before, "state không được đổi")

    def test_corrupted_tx_signature(self):
        t = signed_tx(1)
        self.assert_rejected([replace(t, sig=flip_byte(t.sig))])

    def test_tx_wrong_domain(self):
        for domain in ("HEADER:" + CHAIN, "VOTE:" + CHAIN, "TX:other-chain"):
            with self.subTest(domain=domain):
                self.setUp()
                self.assert_rejected([signed_tx(1, domain=domain)])


class TestT3CommitCertificate(unittest.TestCase):
    """Đường đồng bộ của D: Node.on_sync_response. Node tụt hậu tin (block, certificate) do
    MỘT peer gửi tới, nên certificate phải tự chứng minh: >= Q chữ ký PRECOMMIT hợp lệ cho
    đúng block đó. Kẻ tấn công: peer Byzantine trả lời đồng bộ (trong test ta ký bằng khóa
    thật của các validator để tạo certificate 'gần đúng', rồi làm sai đúng một chỗ)."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver = self.nodes[0]
        self.block = valid_block(self.nodes[1], [signed_tx(1)])
        self.signers = self.nodes[1:8]  # 7 = Q người ký, không gồm receiver

    def cert(self, block=None, signers=None, **kw):
        return commit_cert(block or self.block, signers or self.signers, **kw)

    @staticmethod
    def with_sigs(cert, **changes):
        """Bản sao certificate với vài chữ ký bị thay (None = bỏ người ký đó)."""
        sigs = dict(cert.signatures)
        for voter, sig in changes.items():
            if sig is None:
                del sigs[voter]
            else:
                sigs[voter] = sig
        return replace(cert, signatures=sigs)

    def deliver(self, block, cert):
        self.receiver.on_message(("SYNC_RESP", SyncResp("V9", ((block, cert),))))

    def assert_rejected(self, block, cert, reason):
        state = self.receiver.state.hash()
        self.deliver(block, cert)
        rej = events(self.net, "REJECT_SYNC", node="V0")
        self.assertEqual([(e["reason"], e["height"]) for e in rej], [(reason, 1)],
                         "phải có đúng 1 dòng REJECT_SYNC ghi lý do và height")
        self.assertEqual(self.receiver.ledger, [], "không được chốt từ certificate lỗi")
        self.assertEqual((self.receiver.height, self.receiver.state.hash()), (1, state))
        # không 'chiếm chỗ': (block, certificate) đúng gửi sau vẫn được nhận
        self.deliver(self.block, self.cert())
        self.assertEqual(self.receiver.ledger, [self.block])

    def test_valid_certificate_is_accepted(self):  # đối chứng
        cert = self.cert()
        self.deliver(self.block, cert)
        self.assertEqual(self.receiver.ledger, [self.block])
        self.assertEqual(self.receiver.certificates[1], cert)
        self.assertEqual(self.receiver.state.hash(), self.block.header.state_hash)
        self.assertEqual(len(events(self.net, "SYNC_CATCHUP_SUCCESS", node="V0", height=1)), 1)
        self.assertEqual(events(self.net, "REJECT_SYNC"), [])

    def test_corrupted_signature(self):
        cert = self.cert()
        bad = self.with_sigs(cert, V4=flip_byte(cert.signatures["V4"]))
        self.assert_rejected(self.block, bad, "invalid_cert_sig")

    def test_wrong_domain(self):
        for domain in ("TX:" + CHAIN, "HEADER:" + CHAIN, "VOTE:other-chain"):
            with self.subTest(domain=domain):
                self.setUp()
                self.assert_rejected(self.block, self.cert(domain=domain), "invalid_cert_sig")

    def test_prevotes_are_not_a_commit(self):
        # Q prevote chỉ là polka; certificate phải là PRECOMMIT
        self.assert_rejected(self.block, self.cert(kind="PREVOTE"), "invalid_cert_sig")

    def test_round_changed_after_signing(self):
        self.assert_rejected(self.block, replace(self.cert(), round=1), "invalid_cert_sig")

    def test_signature_moved_to_other_voter(self):
        # 7 tên đều là validator, nhưng chữ ký của V1 bị gán cho V8
        cert = self.cert()
        bad = self.with_sigs(cert, V1=None, V8=cert.signatures["V1"])
        self.assert_rejected(self.block, bad, "invalid_cert_sig")

    def test_too_few_signers(self):
        self.assert_rejected(self.block, self.cert(signers=self.nodes[1:7]),
                             "insufficient_cert_sigs")

    def test_unknown_signer(self):
        cert = self.cert()
        bad = self.with_sigs(cert, V99=cert.signatures["V1"])
        self.assert_rejected(self.block, bad, "insufficient_cert_sigs")  # D gộp chung một lý do

    def test_certificate_of_another_block(self):
        other = valid_block(self.nodes[1])  # block rỗng, khác hash
        self.assert_rejected(self.block, self.cert(block=other), "cert_mismatch")

    def test_txs_dropped_under_real_certificate(self):
        # giữ header + certificate thật, bỏ tx trong thân: hash block không đổi (chỉ băm header)
        stripped = Block(self.block.header, ())
        self.assert_rejected(stripped, self.cert(), "bad_tx_root")

    def test_txs_reordered_under_real_certificate(self):
        """Hồi quy lỗi cũ của on_sync_response (D), sửa ngày 27/10/2026: trước đây không kiểm
        tx_root. Đảo thứ tự 2 tx của 2 người gửi khác nhau: hash block giữ nguyên, certificate
        vẫn khớp, state cuối giống hệt -> node lưu thân block KHÁC thứ đã được đồng thuận."""
        txs = (signed_tx(1), signed_tx(1, sender="Bob"))
        self.block = valid_block(self.nodes[1], txs)
        self.assert_rejected(Block(self.block.header, txs[::-1]), self.cert(), "bad_tx_root")


class TestT3TxGossip(unittest.TestCase):
    """Đường gossip tx của D: Node.on_tx. Tx lỗi bị loại có ghi lý do (trước 27/10/2026 bị bỏ
    im lặng), không vào mempool, không được phát tiếp, và không 'chiếm chỗ' bản đúng
    (seen_tx_hashes chỉ băm body, không băm chữ ký)."""

    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.receiver = self.nodes[0]
        self.receiver.mempool = []
        self.good = signed_tx(1)

    def assert_dropped(self, bad, reason="bad_tx_sig"):
        self.receiver.on_message(("TX", bad))
        rej = events(self.net, "REJECT", node="V0")
        self.assertEqual([(e["reason"], e["sender"], e["nonce"]) for e in rej],
                         [(reason, bad.sender, bad.nonce)])
        self.assertEqual(self.receiver.mempool, [])
        self.assertEqual(self.net.sent, [], "tx lỗi không được phát tiếp")
        self.receiver.on_message(("TX", self.good))  # bản đúng, cùng body, đến sau
        self.assertEqual(self.receiver.mempool, [self.good],
                         "bản lỗi đến trước không được chặn bản đúng")

    def test_valid_tx_enters_mempool_and_is_gossiped(self):  # đối chứng
        self.receiver.on_message(("TX", self.good))
        self.assertEqual(self.receiver.mempool, [self.good])
        self.assertEqual(self.net.sent, [(0, None, ("TX", self.good))])

    def test_corrupted_signature(self):
        self.assert_dropped(replace(self.good, sig=flip_byte(self.good.sig)))

    def test_wrong_domain(self):
        for domain in ("VOTE:" + CHAIN, "HEADER:" + CHAIN, "TX:other-chain"):
            with self.subTest(domain=domain):
                self.setUp()
                self.assert_dropped(signed_tx(1, domain=domain))

    def test_signed_by_other_account(self):
        # Bob ký đúng body nhưng body ghi sender là Alice
        bob_sig = sign(ACCOUNTS["Bob"], "TX:" + CHAIN, self.good.body())
        self.assert_dropped(replace(self.good, sig=bob_sig))

    def test_unknown_sender_and_foreign_key(self):  # không phải lỗi chữ ký, nhưng vẫn ghi lý do
        for bad, reason in ((replace(self.good, sender="Mallory"), "unknown_sender"),
                            (signed_tx(1, key="Bob/msg"), "not_owner")):
            with self.subTest(reason=reason):
                self.setUp()
                self.assert_dropped(bad, reason)


class InjectNet(Net):
    """Mạng sim.py thật; trước khi chạy cài sẵn các thông điệp lỗi vào hàng đợi lúc t=1,
    gửi tới mọi node. Người tấn công là V3, chỉ dùng khóa của chính V3: vote/header sai chữ
    ký hoặc sai domain, một SYNC_RESP với certificate giả (chỉ chữ ký của V3 là thật, được
    chép sang tên người khác), và một tx giả chữ ký của Alice."""

    def run(self, t_end):
        v3 = self.nodes[3]
        cid = v3.ctx["chain_id"]
        base = Vote("PREVOTE", 1, 0, H(b"fake"), v3.name)
        good_sig = sign(v3.kp, "VOTE:" + cid, base.body())
        hd = Header(height=1, round=0, pol_round=-1, parent=H(b"genesis"), state_hash=H(b"s"),
                    tx_root=H(b"t"), proposer=v3.name)
        self.bad = [
            ("VOTE", replace(base, sig=flip_byte(good_sig))),
            ("VOTE", replace(base, sig=sign(v3.kp, "TX:" + cid, base.body()))),
            ("VOTE", replace(base, sig=sign(v3.kp, "VOTE:other-chain", base.body()))),
            ("PROPOSAL", Block(replace(hd, sig=sign(v3.kp, "VOTE:" + cid, hd.body())), ())),
        ]
        fake = replace(hd, tx_root=tx_root(()))  # thân khớp header: lỗi chỉ nằm ở certificate
        self.fake_block = Block(replace(fake, sig=sign(v3.kp, "HEADER:" + cid, fake.body())), ())
        bh = self.fake_block.hash()
        own = sign(v3.kp, "VOTE:" + cid, Vote("PRECOMMIT", 1, 0, bh, v3.name).body())
        names = [v3.name] + [nd.name for nd in self.nodes if nd is not v3][:v3.Q - 1]
        cert = CommitCertificate(height=1, round=0, block_hash=bh,
                                 signatures={name: own for name in names})
        self.fake_tx = Tx("Alice", 1, "Alice/msg", "stolen", sig=flip_byte(own))
        self.bad += [("SYNC_RESP", SyncResp(v3.name, ((self.fake_block, cert),))),
                     ("TX", self.fake_tx)]
        for msg in self.bad:
            for dst in range(len(self.nodes)):
                self.push(1, "MSG", dst, msg)
        super().run(t_end)


class TestT3EndToEnd(unittest.TestCase):
    """Chạy mô phỏng thật: thông điệp lỗi bị mọi node loại, có log, chuỗi vẫn chạy tiếp."""

    def test_rejected_and_logged_and_chain_continues(self):
        with mock.patch("src.main.Net", InjectNet):
            net = run_sim(load_cfg())
        for nd in net.nodes:
            rej = log_events(net, "REJECT", node=nd.name, t=1)
            tx_rej = [r for r in rej if "sender" in r]  # REJECT của tx ghi sender, không ghi height
            self.assertEqual([(r["reason"], r["sender"]) for r in tx_rej],
                             [("bad_tx_sig", "Alice")])
            msg_rej = [r for r in rej if "sender" not in r]
            reasons = sorted(r["reason"] for r in msg_rej)
            self.assertEqual(reasons, ["bad_header_sig"] + ["bad_vote_sig"] * 3, nd.name)
            self.assertTrue(all(r["height"] == "1" for r in msg_rej))
            sync = log_events(net, "REJECT_SYNC", node=nd.name, t=1)
            self.assertEqual([(r["reason"], r["height"]) for r in sync],
                             [("invalid_cert_sig", "1")], nd.name)
            self.assertNotIn(net.fake_block.hash(), [b.hash() for b in nd.ledger])
            self.assertNotIn(net.fake_tx, nd.mempool + [t for b in nd.ledger for t in b.txs])
        assert_honest_safety(net.nodes, {"V3"})
        assert_honest_progress(net.nodes, {"V3"}, heights=5)
        assert_honest_certificates(net.nodes, {"V3"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
