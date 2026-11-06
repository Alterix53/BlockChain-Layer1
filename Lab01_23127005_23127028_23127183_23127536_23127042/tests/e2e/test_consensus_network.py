"""Consensus over duplicate, reordered and delayed messages."""
import json
import unittest
from src.common import H, Vote, sign
from src.main import identity_keys, run_sim
from tests.c_helpers import WORKSPACE
from pathlib import Path


class ConsensusNetworkTests(unittest.TestCase):
    def setUp(self):
        config_path = Path(WORKSPACE) / "config" / "default.json"
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
        voter_key = identity_keys(cfg)[0][0]
        round = receiver.round
        first_vote = Vote("PREVOTE", cfg["heights"], round, H(b"block-a"), "V0")
        first_vote = Vote(
            *first_vote.body(),
            sig=sign(voter_key, "VOTE:" + cfg["chain_id"], first_vote.body()),
        )
        conflicting_vote = Vote("PREVOTE", cfg["heights"], round, H(b"block-b"), "V0")
        conflicting_vote = Vote(
            *conflicting_vote.body(),
            sig=sign(voter_key, "VOTE:" + cfg["chain_id"],
                     conflicting_vote.body()),
        )

        receiver.on_vote(first_vote)
        receiver.on_vote(first_vote)
        receiver.on_vote(conflicting_vote)

        slot = receiver.votes[(cfg["heights"], round, "PREVOTE")]
        self.assertEqual(len(slot), 1)
        self.assertEqual(slot["V0"].block_hash, H(b"block-a"))
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
