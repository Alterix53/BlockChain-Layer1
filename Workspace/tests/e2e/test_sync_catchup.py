"""Đồng bộ bắt kịp (phần D): node tụt lại tự hỏi SYNC_REQ và chốt bằng (block, certificate).

Kích hoạt: hết cả một round mà không chốt được (timeout ROUND) thì hỏi các peer từ height hiện
tại. Node đã chốt xong (done) vẫn trả lời. Phía trả lời chặn khoảng height do người hỏi gửi.
Chạy từ thư mục Workspace:  python -m unittest discover -s tests -p "test_sync_catchup.py" -v
"""
import os
import sys
import unittest
from unittest import mock

_TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.dirname(_TESTS), _TESTS):  # Workspace/ (cho src) và tests/ (cho c_helpers)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.common import SyncReq, SyncResp  # noqa: E402
from src.main import run_sim  # noqa: E402
from src.sim import Net  # noqa: E402
from c_helpers import (assert_honest_certificates, assert_honest_safety, commit_cert,  # noqa: E402
                       events, load_cfg, log_events, make_nodes, signed_tx, valid_block)


class IsolateNet(Net):
    """Mạng sim.py thật, nhưng trước GST mọi tin tới/từ V9 bị giữ lại tới sau GST (V9 bị cô
    lập). Không có send(): phía trả lời đồng bộ đi theo nhánh cũ của D (net.push)."""
    ISOLATED, GST = 9, 3000

    def _delay(self, src, dst):
        d = self.rng.randint(1, self.delta)
        if self.now < self.GST and src != dst and self.ISOLATED in (src, dst):
            return self.GST - self.now + d
        return d

    def broadcast(self, src, msg):
        h = msg[1].header.height if msg[0] == "PROPOSAL" else getattr(msg[1], "height", 0)
        self.log(self.nodes[src].name, "SEND", type=msg[0], height=h)
        for dst in range(len(self.nodes)):
            self.push(self.now + self._delay(src, dst), "MSG", dst, msg)


class TestSyncCatchUpNetwork(unittest.TestCase):
    def test_isolated_node_catches_up(self):
        # gst=3000: V9 lỡ cả 5 height; gst=300: V9 tự chốt 1..4 từ tin đến muộn nhưng tin
        # height 5 tới lúc nó còn ở height 1 nên bị bỏ (quá xa) -> chỉ đồng bộ mới cứu được
        for gst in (3000, 300):
            with self.subTest(gst=gst), mock.patch.object(IsolateNet, "GST", gst), \
                    mock.patch("src.main.Net", IsolateNet):
                net = run_sim(load_cfg())
                chain = [b.hash() for b in net.nodes[0].ledger]
                self.assertEqual(len(chain), 5)
                for nd in net.nodes:
                    self.assertEqual([b.hash() for b in nd.ledger], chain, nd.name)
                assert_honest_safety(net.nodes, set())
                assert_honest_certificates(net.nodes, set())
                self.assertTrue(log_events(net, "SYNC_REQUEST", node="V9"))
                self.assertTrue(log_events(net, "SYNC_CATCHUP_SUCCESS", node="V9"))
                asked = {r["node"] for r in log_events(net, "SYNC_REQUEST")}
                self.assertEqual(asked, {"V9"}, "node không bị tụt thì không phải hỏi")

    def test_normal_run_never_asks(self):
        net = run_sim(load_cfg())
        self.assertEqual(log_events(net, "SYNC_REQUEST"), [])


class TestSyncRequestUnit(unittest.TestCase):
    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.asker, self.server = self.nodes[0], self.nodes[1]

    def give_ledger(self, node, n_blocks):
        """Cho `node` chốt n_blocks block (mỗi block có certificate 7 chữ ký)."""
        node.ctx["heights"] = n_blocks
        for i in range(n_blocks):
            blk = valid_block(node, [signed_tx(i + 1)])
            node.finalize(blk, commit_cert(blk, self.nodes[2:9]))
        self.net.clear()

    def responses(self):
        return [(dst, msg[1]) for src, dst, msg in self.net.sent if msg[0] == "SYNC_RESP"]

    def test_round_timeout_asks_for_sync(self):
        self.asker.on_timeout(("ROUND", 1, 0))
        reqs = [msg[1] for src, dst, msg in self.net.sent if msg[0] == "SYNC_REQ"]
        self.assertEqual(reqs, [SyncReq("V0", 1, 1 + self.asker.max_ahead)])
        self.assertEqual(len(events(self.net, "SYNC_REQUEST", node="V0", height=1)), 1)
        self.assertEqual(self.asker.round, 1, "vẫn sang round sau như cũ")

    def test_done_node_still_serves(self):
        self.give_ledger(self.server, 1)
        self.assertTrue(self.server.done)
        self.server.on_message(("SYNC_REQ", SyncReq("V0", 1, 1)))
        (dst, resp), = self.responses()
        self.assertEqual((dst, [b.header.height for b, _ in resp.chain_data]), (0, [1]))

    def test_requested_range_is_bounded(self):
        self.give_ledger(self.server, 6)
        # khoảng khổng lồ / âm: không lặp theo to_height, tối đa max_ahead + 1 block
        self.server.on_message(("SYNC_REQ", SyncReq("V0", -5, 10**12)))
        (_, resp), = self.responses()
        self.assertEqual([b.header.height for b, _ in resp.chain_data],
                         list(range(1, self.server.max_ahead + 2)))
        # người hỏi không phải validator, hoặc chính mình: không trả lời
        self.net.clear()
        for who in ("Mallory", "V1"):
            self.server.on_message(("SYNC_REQ", SyncReq(who, 1, 3)))
        self.assertEqual(self.responses(), [])

    def test_synced_block_is_cleaned_like_finalize(self):
        # chốt qua đồng bộ phải dọn mempool như chốt thường (trước đây tx đã chốt còn nằm lại)
        self.give_ledger(self.server, 1)
        blk, cert = self.server.ledger[0], self.server.certificates[1]
        self.asker.on_message(("SYNC_RESP", SyncResp(self.server.name, ((blk, cert),))))
        self.assertEqual(self.asker.ledger, [blk])
        self.assertNotIn(blk.txs[0], self.asker.mempool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
