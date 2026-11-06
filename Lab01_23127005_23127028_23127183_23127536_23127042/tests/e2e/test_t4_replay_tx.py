"""Lab §9 T4: first admission, gossip, and replay through the real network."""
import unittest
from dataclasses import replace
from unittest import mock

from src.common import Tx, sign
from src.main import identity_keys, run_sim
from src.sim import Net
from tests.c_helpers import load_cfg, log_events
from tests.independent_oracle import assert_finalized


class TestT4ReplayTx(unittest.TestCase):
    def test_t4_transaction_replay_prevention(self):
        cfg = load_cfg(gst=0, delta=1, heights=3, txs_per_account=0,
                       max_txs_per_block=1, rate_limit=None, peer_block=None,
                       duplicate_probability=0, t_end=2000)
        _, accounts = identity_keys(cfg)
        raw = Tx("Alice", 1, "Alice/msg", "first-network-transaction")
        tx = replace(raw, sig=sign(accounts["Alice"], "TX:" + cfg["chain_id"], raw.body()))

        class AdmissionNet(Net):
            replayed_after_commit = False

            def run(self, t_end):
                assert all(not nd.mempool and not nd.seen_tx_hashes for nd in self.nodes)
                self.send(0, 5, ("TX", tx))
                self.send(0, 5, ("TX", tx))
                super().run(t_end)

            def _transmit(self, src, dst, msg):
                kind, payload = self._unwrap(msg)
                release = 20 if kind == "HEADER" and payload.height == 1 else 100 if kind == "HEADER" and payload.height == 3 else 0
                if self.now < release:
                    self.log(self.nodes[src].name, "DELAY", type=kind, height=payload.height,
                             dst=self.nodes[dst].name, reason="test_admission_window", until=release)
                    self.push(release, "SEND_READY", src, dst, msg)
                    return
                super()._transmit(src, dst, msg)

            def _deliver(self, src, dst, msg):
                super()._deliver(src, dst, msg)
                if not self.replayed_after_commit and any(tx in b.txs for nd in self.nodes for b in nd.ledger):
                    self.replayed_after_commit = True
                    self.broadcast(0, ("TX", tx))

        with mock.patch("src.main.Net", AdmissionNet):
            net = run_sim(cfg)
        self.assertTrue(net.replayed_after_commit, "post-commit replay must actually be sent")
        self.assertEqual(len(log_events(net, "TX_RECEIVED", sender="Alice", nonce=1)), cfg["n"])
        assert_finalized(net.nodes, 3, {"Alice/msg": tx.value}, {"Alice": 1})
        for nd in net.nodes:
            self.assertEqual(sum(t == tx for b in nd.ledger for t in b.txs), 1)
            self.assertFalse(nd.mempool)


if __name__ == "__main__":
    unittest.main()
