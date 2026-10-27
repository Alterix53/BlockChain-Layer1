import json
from pathlib import Path
import unittest

from src.common import KeyPair, Vote, sign
from src.main import run_sim
from src.sim import Net


class DummyNode:
    def __init__(self, name):
        self.name = name
        self.done = False
        self.received = []

    def start(self):
        pass

    def on_message(self, msg, src):
        self.received.append((msg, src, self.net.now))

    def on_timeout(self, _key):
        pass


def make_net(**overrides):
    cfg = {
        "seed": 7,
        "n": 2,
        "delta": 4,
        "gst": 0,
        "pre_gst_max_delay": 10,
        "pre_gst_drop_probability": 0,
        "duplicate_probability": 0,
        "pre_gst_reorder_probability": 0,
        "links": [[0, 1]],
        "link_delays": {"0-1": 2},
        "rate_limit": None,
        "peer_block": None,
    }
    cfg.update(overrides)
    net = Net(cfg)
    net.nodes = [DummyNode("V0"), DummyNode("V1")]
    for node in net.nodes:
        node.net = net
    return net


class NetTests(unittest.TestCase):
    def test_reads_topology_and_per_link_delay(self):
        net = make_net()
        net.send(0, 1, ("TEST", None))
        net.run(5)

        self.assertEqual(net.peers[0], {1})
        self.assertEqual(len(net.nodes[1].received), 1)
        self.assertEqual(net.nodes[1].received[0][:2], (("TEST", None), 0))
        self.assertLessEqual(net.nodes[1].received[0][2], 2)

    def test_drops_messages_before_gst_when_configured(self):
        net = make_net(gst=5, pre_gst_drop_probability=1)
        net.send(0, 1, ("TEST", None))
        net.run(10)

        self.assertEqual(net.nodes[1].received, [])
        self.assertTrue(any("ev=DROP" in line and "reason=pre_gst" in line
                            for line in net.logs))

    def test_post_gst_delivery_obeys_delta_without_pre_gst_drops(self):
        net = make_net(gst=0, delta=4, link_delays={},
                       pre_gst_drop_probability=1)
        net.send(0, 1, ("TEST", None))
        net.run(5)

        self.assertEqual(len(net.nodes[1].received), 1)
        self.assertLessEqual(net.nodes[1].received[0][2], 4)
        self.assertFalse(any("ev=DROP" in line for line in net.logs))

    def test_duplicates_and_reorders_are_logged(self):
        net = make_net(gst=100, pre_gst_max_delay=5,
                       duplicate_probability=1,
                       pre_gst_reorder_probability=1)
        net.send(0, 1, ("TEST", None))
        net.run(20)

        self.assertEqual(len(net.nodes[1].received), 2)
        self.assertTrue(any("ev=DUPLICATE" in line for line in net.logs))
        self.assertTrue(any("reason=reorder" in line for line in net.logs))

    def test_rate_limit_delays_excess_sends(self):
        net = make_net(delta=0, link_delays={"0-1": 0},
                       rate_limit={"max_messages": 1, "window": 10})
        net.send(0, 1, ("FIRST", None))
        net.send(0, 1, ("SECOND", None))
        net.run(20)

        self.assertEqual(len(net.nodes[1].received), 2)
        self.assertEqual([item[2] for item in net.nodes[1].received], [0, 10])
        self.assertTrue(any("reason=rate_limit" in line for line in net.logs))
        self.assertEqual(net.now, 10)

    def test_peer_is_blocked_then_unblocked(self):
        net = make_net(delta=0, link_delays={"0-1": 0},
                       peer_block={"max_messages": 1, "window": 100,
                                   "duration": 5})
        net.send(0, 1, ("FIRST", None))
        net.send(0, 1, ("SECOND", None))
        net.run(10)

        self.assertEqual(len(net.nodes[1].received), 1)
        self.assertFalse(net.blocked_peers)
        self.assertTrue(any("ev=BLOCK" in line for line in net.logs))
        self.assertTrue(any("ev=UNBLOCK" in line for line in net.logs))
        self.assertTrue(any("reason=peer_rate_limit" in line for line in net.logs))


class ConsensusNetworkTests(unittest.TestCase):
    def setUp(self):
        config_path = Path(__file__).parents[1] / "config" / "default.json"
        with config_path.open() as config_file:
            self.base_config = json.load(config_file)
        self.base_config["rate_limit"] = None
        self.base_config["peer_block"] = None

    def assert_no_conflicting_finalization(self, nodes):
        max_height = max((len(node.ledger) for node in nodes), default=0)
        for height in range(max_height):
            hashes = {
                node.ledger[height].hash()
                for node in nodes
                if len(node.ledger) > height
            }
            self.assertLessEqual(
                len(hashes), 1,
                f"conflicting finalized blocks at height {height + 1}",
            )

    def test_t2_duplicate_reordered_votes_count_once_and_keep_safety(self):
        cfg = dict(
            self.base_config,
            gst=100000,
            pre_gst_max_delay=50,
            pre_gst_drop_probability=0,
            duplicate_probability=1,
            pre_gst_reorder_probability=1,
        )
        net = run_sim(cfg)

        self.assertTrue(any("ev=DUPLICATE" in line for line in net.logs))
        self.assertTrue(any("reason=reorder" in line for line in net.logs))
        self.assertTrue(all(node.done for node in net.nodes))
        self.assertTrue(all(len(node.ledger) == cfg["heights"] for node in net.nodes))
        self.assert_no_conflicting_finalization(net.nodes)

        receiver = net.nodes[1]
        voter_key = KeyPair(f"val-{cfg['seed']}-0".encode())
        first_vote = Vote("PREVOTE", cfg["heights"], 0, b"block-a", "V0")
        first_vote = Vote(
            *first_vote.body(),
            sig=sign(voter_key, "VOTE:" + cfg["chain_id"], first_vote.body()),
        )
        conflicting_vote = Vote("PREVOTE", cfg["heights"], 0, b"block-b", "V0")
        conflicting_vote = Vote(
            *conflicting_vote.body(),
            sig=sign(voter_key, "VOTE:" + cfg["chain_id"],
                     conflicting_vote.body()),
        )

        receiver.on_vote(first_vote)
        receiver.on_vote(first_vote)
        receiver.on_vote(conflicting_vote)

        slot = receiver.votes[(cfg["heights"], 0, "PREVOTE")]
        self.assertEqual(len(slot), 1)
        self.assertEqual(slot["V0"].block_hash, b"block-a")
        self.assertTrue(any("ev=EQUIVOCATION" in line for line in net.logs))

    def test_t5_pre_gst_drops_and_delays_preserve_finalization_safety(self):
        for seed in (42, 43, 44):
            with self.subTest(seed=seed):
                cfg = dict(
                    self.base_config,
                    seed=seed,
                    gst=500,
                    pre_gst_max_delay=300,
                    pre_gst_drop_probability=0.05,
                    duplicate_probability=0,
                    pre_gst_reorder_probability=0.2,
                )
                net = run_sim(cfg)

                self.assertTrue(any("reason=pre_gst" in line
                                    and "ev=DROP" in line
                                    for line in net.logs))
                self.assertTrue(any("reason=reorder" in line
                                    and "ev=DELAY" in line
                                    for line in net.logs))
                self.assert_no_conflicting_finalization(net.nodes)


if __name__ == "__main__":
    unittest.main()
