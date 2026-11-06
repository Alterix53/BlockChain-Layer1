"""Independent ConsensusContracts regression cases."""
import unittest
from dataclasses import replace
from src import execution
from src.common import CommitCertificate, NIL
from tests.c_helpers import CHAIN, events, make_nodes, signed_tx, signed_vote
from tests.independent_oracle import assert_finalized, digest
from tests.regression.fixtures import block_for


class ConsensusContracts(unittest.TestCase):
    def test_late_quorum_locks_without_second_precommit(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1])
        receiver.on_message(("PROPOSAL", block))
        receiver.on_timeout(("PREVOTE", 1, 0))
        before = dict(receiver.signed)
        for voter in nodes[1:8]:
            receiver.on_message(("VOTE", signed_vote(voter, "PREVOTE", block.hash())))
        self.assertEqual(receiver.locked, (block.hash(), 0))
        self.assertEqual(receiver.signed, before)
        self.assertEqual(receiver.signed[(1, 0, "PRECOMMIT")], NIL)
        self.assertEqual(len(events(net, "VOTE", node="V0", kind="PRECOMMIT")), 1)

    def test_round_1001_is_current_and_accepts_authenticated_votes(self):
        nodes, _ = make_nodes()
        receiver = nodes[0]
        receiver.start_round(1000)
        receiver.on_timeout(("ROUND", 1, 1000))
        self.assertEqual(receiver.round, 1001)
        block = block_for(nodes[2], round=1001)
        receiver.on_message(("PROPOSAL", block))
        for voter in nodes[1:8]:
            receiver.on_message(("VOTE", signed_vote(voter, "PREVOTE", block.hash(), round=1001)))
        self.assertEqual(receiver.signed[(1, 1001, "PREVOTE")], block.hash())
        self.assertEqual(receiver.locked, (block.hash(), 1001))

    def test_body_poison_is_not_cached_and_valid_body_recovers(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1], [signed_tx(1)])
        receiver.on_message(("BODY", (block.hash(), ())), 2)
        self.assertNotIn(block.hash(), receiver.bodies)
        receiver.on_message(("HEADER", block.header), 1)
        self.assertTrue(any(msg == ("REQUEST_BODY", block.hash()) for _, _, msg in net.sent))
        receiver.on_message(("BODY", (block.hash(), ())), 2)
        self.assertNotIn(block.hash(), receiver.bodies)
        receiver.on_message(("BODY", (block.hash(), block.txs)), 1)
        self.assertEqual(receiver.blocks[block.hash()], block)
        self.assertEqual(receiver.signed[(1, 0, "PREVOTE")], block.hash())

    def test_missing_body_is_requested_again(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1])
        receiver.on_message(("HEADER", block.header), 1)
        retry = next(key for idx, _, key in net.timeouts if idx == 0 and key[0] == "BODY_RETRY")
        count = sum(msg[0] == "REQUEST_BODY" for _, _, msg in net.sent)
        receiver.on_timeout(retry)
        self.assertEqual(sum(msg[0] == "REQUEST_BODY" for _, _, msg in net.sent), count + 1)
        receiver.on_message(("BODY", (block.hash(), block.txs)), 1)
        receiver.on_timeout(retry)
        self.assertEqual(sum(msg[0] == "REQUEST_BODY" for _, _, msg in net.sent), count + 1)

    def test_polka_invalid_or_duplicate_signers_are_rejected_atomically(self):
        for fault in ("duplicate", "signature", "domain", "target", "few"):
            with self.subTest(fault=fault):
                nodes, net = make_nodes()
                receiver = nodes[0]
                target = digest(["proof-target"])
                votes = [signed_vote(nd, "PREVOTE", target) for nd in nodes[1:8]]
                if fault == "duplicate":
                    votes[-1] = votes[0]
                elif fault == "signature":
                    votes[-1] = replace(votes[-1], sig=b"x" * 64)
                elif fault == "domain":
                    votes[-1] = signed_vote(nodes[7], "PREVOTE", target, domain="TX:" + CHAIN)
                elif fault == "target":
                    votes[-1] = signed_vote(nodes[7], "PREVOTE", digest(["other"]))
                else:
                    votes.pop()
                receiver.on_message(("POLKA", tuple(votes)))
                self.assertFalse(receiver.polka(1, 0, target))
                self.assertEqual(receiver.proofs, {})
                self.assertEqual(receiver.votes.get((1, 0, "PREVOTE"), {}), {})
                self.assertTrue(events(net, "REJECT", reason="bad_polka"))
                good = tuple(signed_vote(nd, "PREVOTE", target) for nd in nodes[1:8])
                receiver.on_message(("POLKA", good))
                self.assertTrue(receiver.polka(1, 0, target))

    def test_duplicate_votes_do_not_supply_quorum(self):
        nodes, _ = make_nodes()
        receiver = nodes[0]
        target = digest(["one-voter"])
        vote = signed_vote(nodes[1], "PREVOTE", target)
        for _ in range(8):
            receiver.on_message(("VOTE", vote))
        self.assertEqual(len(receiver.votes[(1, 0, "PREVOTE")]), 1)
        self.assertFalse(receiver.polka(1, 0, target))
        self.assertIsNone(receiver.locked)

    def _reject_vote(self, domain=None, corrupt=False):
        nodes, _ = make_nodes()
        receiver = nodes[0]
        vote = signed_vote(nodes[1], "PREVOTE", digest(["signed"]), domain=domain)
        if corrupt:
            vote = replace(vote, sig=b"x" * 64)
        receiver.on_message(("VOTE", vote))
        self.assertNotIn("V1", receiver.votes.get((1, 0, "PREVOTE"), {}))

    def test_invalid_vote_signature(self):
        self._reject_vote(corrupt=True)

    def test_wrong_vote_domain(self):
        self._reject_vote(domain="TX:" + CHAIN)

    def test_state_commitment_is_checked_before_prevote(self):
        nodes, _ = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1], [signed_tx(1)], state_hash=b"x" * 32)
        receiver.on_message(("PROPOSAL", block))
        self.assertEqual(receiver.signed[(1, 0, "PREVOTE")], NIL)
        self.assertEqual(receiver.state.data, {})
        self.assertEqual(receiver.ledger, [])
        self.assertNotIn((1, 0), receiver.proposals)
        self.assertNotIn(block.hash(), receiver.blocks)
        self.assertNotIn(block.hash(), receiver.bodies)

    def test_nonce_replay_cannot_execute_twice(self):
        from tests.c_helpers import ACCOUNTS
        state = execution.State()
        tx = signed_tx(1)
        keys = {name: key.pk for name, key in ACCOUNTS.items()}
        self.assertIsNone(execution.apply_tx(state, tx, CHAIN, keys))
        before = (dict(state.data), dict(state.nonces))
        self.assertEqual(execution.apply_tx(state, tx, CHAIN, keys), "bad_nonce")
        self.assertEqual((state.data, state.nonces), before)

    def test_sync_authenticates_header_and_certificate_before_fetching_body(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1], [signed_tx(1)])
        sigs = {nd.name: signed_vote(nd, "PRECOMMIT", block.hash()).sig for nd in nodes[2:9]}
        cert = CommitCertificate(1, 0, block.hash(), sigs)
        bad = replace(cert, signatures=dict(sigs, V2=b"x" * 64))
        receiver.on_message(("SYNC_HEADERS", ((block.header, bad),)), 1)
        self.assertEqual(receiver.ledger, [])
        self.assertFalse(any(msg[0] == "REQUEST_BODY" for _, _, msg in net.sent))
        receiver.on_message(("SYNC_HEADERS", ((block.header, cert),)), 1)
        self.assertTrue(any(msg == ("REQUEST_BODY", block.hash()) for _, _, msg in net.sent))
        self.assertEqual(receiver.ledger, [], "header/certificate alone must not execute transactions")
        receiver.on_message(("BODY", (block.hash(), block.txs)), 1)
        assert_finalized([receiver], 1, {"Alice/msg": "v1"}, {"Alice": 1})
