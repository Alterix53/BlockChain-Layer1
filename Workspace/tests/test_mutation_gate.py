"""Small in-memory mutation gate. Each mutant must fail its behavioral assertion."""
import unittest
from unittest import mock

from src import execution
from src.node import Node
from tests.e2e import test_t4_replay_tx as replay_cases
from tests.regression import test_consensus as consensus_cases
from tests.regression import test_network as network_cases


class MutationGate(unittest.TestCase):
    def killed(self, case, method, patcher):
        # Unexpected fixture errors are deliberately NOT accepted as a kill.
        with patcher:
            with self.assertRaises(AssertionError, msg=method + " did not detect the mutant"):
                getattr(case(method), method)()

    def test_gossip_disabled_is_detected(self):
        self.killed(replay_cases.TestT4ReplayTx, "test_t4_transaction_replay_prevention",
                    mock.patch.object(Node, "on_tx", lambda self, tx, gossip=True: None))

    def test_production_factory_bypassed_is_detected(self):
        def ignore_behavior(behavior, idx, ctx, kp, **params):
            return Node(idx, ctx, kp)
        self.killed(network_cases.NetworkContracts, "test_json_factory_silent_proposer",
                    mock.patch("src.main.make_node", ignore_behavior))

    def test_invalid_signature_acceptance_is_detected(self):
        self.killed(consensus_cases.ConsensusContracts, "test_invalid_vote_signature",
                    mock.patch("src.node.verify", return_value=True))

    def test_wrong_domain_acceptance_is_detected(self):
        self.killed(consensus_cases.ConsensusContracts, "test_wrong_vote_domain",
                    mock.patch("src.node.verify", return_value=True))

    def test_nonce_guard_bypass_is_detected(self):
        original = execution.apply_tx
        def allow_replay(state, tx, chain, keys):
            state.nonces[tx.sender] = tx.nonce - 1
            return original(state, tx, chain, keys)
        self.killed(consensus_cases.ConsensusContracts, "test_nonce_replay_cannot_execute_twice",
                    mock.patch("src.execution.apply_tx", allow_replay))

    def test_double_counting_is_detected(self):
        original = Node.on_vote
        def count_duplicate(node, vote):
            slot = node.votes.get((vote.height, vote.round, vote.kind), {})
            duplicate = vote.voter in slot
            original(node, vote)
            if duplicate:
                slot["duplicate-" + str(len(slot))] = vote
        self.killed(consensus_cases.ConsensusContracts, "test_duplicate_votes_do_not_supply_quorum",
                    mock.patch.object(Node, "on_vote", count_duplicate))

    def test_state_root_guard_bypass_is_detected(self):
        original = Node._check
        def ignore_state_root(node, block):
            ok, why = original(node, block)
            return (True, "") if why == "bad_state_hash" else (ok, why)
        self.killed(consensus_cases.ConsensusContracts, "test_state_commitment_is_checked_before_prevote",
                    mock.patch.object(Node, "_check", ignore_state_root))


if __name__ == "__main__":
    unittest.main()
