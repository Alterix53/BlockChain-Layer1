"""Sync request, response bounds and finalized-state cleanup."""
import unittest
from dataclasses import replace
from src.common import SyncReq, SyncResp
from tests.c_helpers import commit_cert, events, make_nodes, signed_header, signed_tx, valid_block


class TestSyncRequestUnit(unittest.TestCase):
    def setUp(self):
        self.nodes, self.net = make_nodes()
        self.asker, self.server = self.nodes[0], self.nodes[1]

    def give_ledger(self, node, n_blocks):
        """Cho `node` chốt n_blocks block (mỗi block có certificate 7 chữ ký)."""
        node.ctx["heights"] = n_blocks
        for i in range(n_blocks):
            blk = valid_block(node, [signed_tx(i + 1)])
            proposer = self.nodes[(blk.header.height + blk.header.round) % len(self.nodes)]
            hd = replace(blk.header, proposer=proposer.name)
            blk = replace(blk, header=signed_header(proposer, hd))
            node.finalize(blk, commit_cert(blk, self.nodes[2:9]))
        self.net.clear()

    def responses(self):
        return [(dst, msg[1]) for src, dst, msg in self.net.sent if msg[0] == "SYNC_HEADERS"]

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
        self.assertEqual((dst, [hd.height for hd, _ in resp]), (0, [1]))

    def test_requested_range_is_bounded(self):
        self.give_ledger(self.server, 6)
        # khoảng khổng lồ / âm: không lặp theo to_height, tối đa max_ahead + 1 block
        self.server.on_message(("SYNC_REQ", SyncReq("V0", -5, 10**12)))
        (_, resp), = self.responses()
        self.assertEqual([hd.height for hd, _ in resp],
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
