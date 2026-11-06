"""Independent NetworkContracts regression cases."""
import unittest
from unittest import mock
from src.byzantine import Silent
from src.common import CommitCertificate, SyncResp
from src.main import run_sim
from src.sim import Net
from tests.c_helpers import log_events, make_nodes
from tests.independent_oracle import assert_finalized
from tests.regression.fixtures import block_for, fast_cfg


class NetworkContracts(unittest.TestCase):
    def test_selective_pre_gst_vote_loss_recovers_with_polka_evidence(self):
        cfg = fast_cfg(heights=1, gst=10, pre_gst_max_delay=1, accounts=["Alice"], txs_per_account=1,
                       byzantine={"1": {"behavior": "equivocate_proposer", "groups": [[0, 2, 3, 4, 5, 6, 7], [8, 9]]},
                                  "8": {"behavior": "silent"}, "9": {"behavior": "silent"}})

        class SelectiveNet(Net):
            def _transmit(self, src, dst, msg):
                kind, payload = self._unwrap(msg)
                # The cleanup on main uses HEADER/REQUEST_BODY/BODY for proposals.
                # Deliver the adversary's proposal, then withhold its consensus votes.
                withheld = src == 1 and kind not in ("PROPOSAL", "HEADER", "BODY")
                lost = (self.now < self.gst and kind == "VOTE" and payload.kind == "PREVOTE"
                        and payload.round == 0 and dst != 0)
                if withheld or lost:
                    self.log(self.nodes[src].name, "DROP", dst=self.nodes[dst].name,
                             type=kind, height=self._message_height(msg),
                             reason="byzantine_withholds" if withheld else "selected_pre_gst_loss")
                    return
                super()._transmit(src, dst, msg)

        with mock.patch("src.main.Net", SelectiveNet):
            net = run_sim(cfg)
        self.assertTrue(log_events(net, "DROP", reason="selected_pre_gst_loss"))
        self.assertTrue(log_events(net, "REPROPOSE", node="V0"))
        self.assertTrue(log_events(net, "POLKA"), "proof must reach receivers")
        assert_finalized(net.nodes, 1, {}, {})

    def test_json_factory_silent_proposer(self):
        cfg = fast_cfg(byzantine={"1": {"behavior": "silent", "mode": "all"}})
        net = run_sim(cfg)
        self.assertIsInstance(net.nodes[1], Silent)
        self.assertTrue(log_events(net, "BYZ_SILENT", node="V1"))
        self.assertTrue(log_events(net, "TIMEOUT", kind="PROPOSE", height=1, round=0))
        assert_finalized(net.nodes, 2)

    def test_connected_sparse_topology_converges(self):
        net = run_sim(fast_cfg(links=[[i, (i + 1) % 10] for i in range(10)],
                               accounts=["Alice"], txs_per_account=2))
        assert_finalized(net.nodes, 2, {"Alice/msg": "v2"}, {"Alice": 2})

    def test_sparse_delivery_obeys_global_post_gst_delta(self):
        class Receiver:
            done = False
            def __init__(self, idx): self.name = "V" + str(idx); self.arrivals = []
            def start(self): pass
            def on_timeout(self, key): pass
            def on_message(self, msg, src): self.arrivals.append(net.now)

        net = Net(dict(n=10, seed=1, gst=0, delta=1,
                       links=[[i, (i + 1) % 10] for i in range(10)]))
        net.nodes = [Receiver(i) for i in range(10)]
        net.send(0, 5, ("TEST", None))
        net.run(100)
        self.assertEqual(len(net.nodes[5].arrivals), 1)
        self.assertLessEqual(net.nodes[5].arrivals[0], net.delta,
                             "Lab §3 bounds correct-node delivery, not just each routed hop")

    def test_sparse_route_reserves_pressure_before_origin_send(self):
        class Receiver:
            done = False
            def __init__(self, idx): self.name = "V" + str(idx); self.arrivals = {}
            def start(self): pass
            def on_timeout(self, key): pass
            def on_message(self, msg, src): self.arrivals[msg[1]] = net.now

        class TimedNet(Net):
            def __init__(self, cfg): super().__init__(cfg); self.started = {}
            def _transmit(self, src, dst, msg):
                kind, sequence = self._unwrap(msg)
                if src == 0 and kind == "TEST": self.started.setdefault(sequence, self.now)
                super()._transmit(src, dst, msg)

        net = TimedNet(dict(n=10, seed=1, gst=0, delta=3,
                            links=[[i, (i + 1) % 10] for i in range(10)],
                            rate_limit={"max_messages": 1, "window": 10}))
        net.nodes = [Receiver(i) for i in range(10)]
        for i in range(3): net.send(1, 2, ("PRESSURE", i))
        for i in range(3): net.send(0, 5, ("TEST", i))
        net.run(200)
        self.assertEqual(set(net.nodes[5].arrivals), {0, 1, 2})
        for sequence, arrival in net.nodes[5].arrivals.items():
            self.assertLessEqual(arrival - net.started[sequence], net.delta)

    def test_network_delivery_owns_certificate_dictionary(self):
        nodes, _ = make_nodes()
        block = block_for(nodes[1])
        cert = CommitCertificate(1, 0, block.hash(), {"V0": b"original"})

        class Receiver:
            done = False
            def __init__(self, idx): self.name = "V" + str(idx); self.idx = idx; self.received = []
            def start(self): pass
            def on_timeout(self, key): pass
            def on_message(self, msg, src):
                self.received.append(msg)
                if self.idx == 0: msg[1].chain_data[0][1].signatures.clear()

        net = Net(dict(n=3, seed=1, delta=0, gst=0))
        net.nodes = [Receiver(i) for i in range(3)]
        net.broadcast(0, ("SYNC_RESP", SyncResp("V0", ((block, cert),))))
        cert.signatures["Mallory"] = b"after-send"
        net.run(1)
        for receiver in net.nodes[1:]:
            self.assertEqual(receiver.received[0][1].chain_data[0][1].signatures, {"V0": b"original"})
        self.assertEqual(cert.signatures, {"V0": b"original", "Mallory": b"after-send"})

    def test_outbound_budget_is_shared_across_destinations(self):
        class Receiver:
            done = False
            def __init__(self, idx): self.name = "V" + str(idx); self.arrivals = []
            def start(self): pass
            def on_timeout(self, key): pass
            def on_message(self, msg, src): self.arrivals.append(net.now)

        net = Net(dict(n=3, seed=1, gst=0, delta=0,
                       rate_limit={"max_messages": 1, "window": 10}))
        net.nodes = [Receiver(i) for i in range(3)]
        net.send(0, 1, ("TEST", None))
        net.send(0, 2, ("TEST", None))
        net.run(20)
        self.assertEqual(net.nodes[1].arrivals, [0])
        self.assertEqual(net.nodes[2].arrivals, [10])

    def test_bootstrap_deduplicates_without_initial_gossip(self):
        cfg = fast_cfg(t_end=0, accounts=["Alice"], txs_per_account=2)
        net = run_sim(cfg)
        for nd in net.nodes:
            self.assertEqual(len(nd.mempool), 2)
            self.assertEqual(len(nd.seen_tx_hashes), 2)
            tx = nd.mempool[0]
            nd.on_tx(tx)
            self.assertEqual(len(nd.mempool), 2)
        self.assertFalse(log_events(net, "SEND", type="TX"))

    def test_network_events_have_required_fields_and_body_height(self):
        net = run_sim(fast_cfg())
        assert_finalized(net.nodes, 2)
        rows = [row for ev in ("SEND", "RECEIVE", "DELAY", "DROP", "BLOCK", "UNBLOCK")
                for row in log_events(net, ev)]
        self.assertTrue(any(row["type"] == "BODY" for row in rows))
        for row in rows:
            self.assertTrue({"t", "node", "ev", "type", "height"} <= set(row), row)
            self.assertGreaterEqual(int(row["t"]), 0)
            self.assertGreaterEqual(int(row["height"]), 0)
            if row["type"] in ("HEADER", "BODY", "REQUEST_BODY", "VOTE"):
                self.assertIn(int(row["height"]), (1, 2))
