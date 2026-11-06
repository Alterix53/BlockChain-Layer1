"""T3: reject invalid signed messages while the real chain progresses."""
import unittest
from dataclasses import replace
from unittest import mock
from src.byzantine import flip_byte
from src.common import Block, CommitCertificate, H, Header, SyncResp, Tx, Vote, sign, tx_root
from src.main import run_sim
from src.sim import Net
from tests.c_helpers import assert_honest_certificates, assert_honest_progress, assert_honest_safety, load_cfg, log_events


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
        hd = Header(height=1, round=2, pol_round=-1, parent=H(b"genesis"), state_hash=H(b"s"),
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
        own = sign(v3.kp, "VOTE:" + cid, Vote("PRECOMMIT", 1, 2, bh, v3.name).body())
        names = [v3.name] + [nd.name for nd in self.nodes if nd is not v3][:v3.Q - 1]
        cert = CommitCertificate(height=1, round=2, block_hash=bh,
                                 signatures={name: own for name in names})
        self.fake_tx = Tx("Alice", 1, "Alice/msg", "stolen", sig=flip_byte(own))
        self.bad += [("SYNC_RESP", SyncResp(v3.name, ((self.fake_block, cert),))),
                     ("TX", self.fake_tx)]
        for msg in self.bad:
            for dst in range(len(self.nodes)):
                self.push(1, "MSG", 3, dst, msg)
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
