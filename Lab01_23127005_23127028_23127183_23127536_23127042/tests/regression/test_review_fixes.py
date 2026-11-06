"""Counterexamples from the independent f089931 audit; no production expected values."""
import unittest
from dataclasses import replace
from unittest import mock

from src.byzantine import Silent
from src.common import CommitCertificate, Header, SyncReq, SyncResp, sign
from src.main import run_sim
from src.sim import Net
from tests.c_helpers import events, log_events, make_nodes, signed_tx, signed_vote
from tests.independent_oracle import assert_finalized, digest
from tests.regression.fixtures import block_for, fast_cfg


class AuditRegressions(unittest.TestCase):
    def test_current_header_has_capacity_despite_future_round_reservations(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        receiver.ctx['max_pending_headers'] = 2
        future = [block_for(nodes[1], round=r, state_hash=digest([r])) for r in (10, 20)]
        for block in future:
            receiver.on_message(('HEADER', block.header), 1)
        protected = future[0]
        votes = tuple(signed_vote(nd, 'PREVOTE', protected.hash(), round=10) for nd in nodes[1:8])
        receiver.on_message(('POLKA', votes), 1)
        receiver.start_round(1)
        current = block_for(nodes[2], [signed_tx(1)], round=1)
        net.clear()
        receiver.on_message(('HEADER', current.header), 2)
        self.assertTrue(any(msg == ('REQUEST_BODY', current.hash()) for _, _, msg in net.sent))
        self.assertIn(protected.hash(), receiver.pending_headers, 'do not evict a proven block')
        self.assertLessEqual(len(receiver.pending_headers), 2)
        receiver.on_message(('BODY', (current.hash(), current.txs)), 2)
        self.assertIn(current.hash(), receiver.blocks)

    def test_header_flood_cannot_starve_later_honest_proposers(self):
        class Flood(Silent):
            def start(self):
                self.height, self.round = 1, 0
                for i in range(256):
                    hd = Header(1, 0, -1, self.last_hash(), digest([i]), digest([]), self.name)
                    hd = replace(hd, sig=sign(self.kp, 'HEADER:' + self.ctx['chain_id'], hd.body()))
                    self.net.broadcast(self.idx, ('HEADER', hd))
                self.log('FLOOD', height=1, round=0, count=256)

        cfg = fast_cfg(heights=1, delta=0, t_end=5000, txs_per_account=0,
                       byzantine={'1': {'behavior': 'silent'}})
        with mock.patch.dict('src.byzantine.REGISTRY', {'silent': Flood}):
            net = run_sim(cfg)
        self.assertTrue(log_events(net, 'FLOOD', count=256))
        self.assertTrue(log_events(net, 'TIMEOUT', height=1, round=0))
        self.assertTrue(log_events(net, 'PROPOSE', node='V2', round=1))
        assert_finalized(net.nodes, 1, {}, {})
        for nd in net.nodes:
            if not nd.is_byzantine:
                self.assertTrue(nd.done, nd.name)
                self.assertLessEqual(len(nd.pending_headers), 256)

    def test_malformed_sync_over_real_network_is_rejected_and_chain_continues(self):
        good_nodes, _ = make_nodes()
        block = block_for(good_nodes[1])
        malformed = [
            ('SYNC_REQ', SyncReq('V1', '1', 2)),
            ('SYNC_REQ', SyncReq([], 1, 2)),
            ('SYNC_REQ', SyncReq('V1', 1, None)),
            ('SYNC_REQ', None),
            ('SYNC_HEADERS', ((block.header, CommitCertificate(1, 0, block.hash(), None)),)),
            ('SYNC_HEADERS', None),
            ('SYNC_HEADERS', ((None, None),)),
            ('SYNC_HEADERS', (('bad-pair',),)),
            ('SYNC_HEADERS', ((replace(block.header, height=2**80), None),)),
            ('SYNC_RESP', SyncResp('V1', ((block, CommitCertificate(1, 0, block.hash(), None)),))),
            ('SYNC_RESP', None),
        ]
        for message in malformed:
            with self.subTest(message=message):
                class Malformed(Silent):
                    def start(self):
                        self.net.send(self.idx, 0, message)
                with mock.patch.dict('src.byzantine.REGISTRY', {'silent': Malformed}):
                    net = run_sim(fast_cfg(heights=1, delta=0,
                                           byzantine={'1': {'behavior': 'silent'}}))
                rejected = log_events(net, 'REJECT_SYNC', node='V0')
                self.assertTrue(rejected, 'malformed sync must be logged, not crash or silently pass')
                self.assertTrue(all(row.get('reason') for row in rejected))
                assert_finalized(net.nodes, 1)

    def test_late_certificate_finalizes_block_without_separate_body_cache(self):
        nodes, net = make_nodes()
        receiver = nodes[0]
        block = block_for(nodes[1], [signed_tx(1)])
        receiver.on_message(('PROPOSAL', block), 1)
        self.assertIn(block.hash(), receiver.blocks)
        self.assertNotIn(block.hash(), receiver.bodies)
        sigs = {nd.name: signed_vote(nd, 'PRECOMMIT', block.hash()).sig for nd in nodes[2:9]}
        cert = CommitCertificate(1, 0, block.hash(), sigs)
        bad = replace(cert, signatures=dict(sigs, V2=b'x' * 64))
        receiver.on_message(('SYNC_HEADERS', ((block.header, bad),)), 1)
        self.assertEqual(receiver.ledger, [], 'cache does not bypass certificate verification')
        message = ('SYNC_HEADERS', ((block.header, cert),))
        receiver.on_message(message, 1)
        receiver.on_message(message, 1)
        assert_finalized([receiver], 1, {'Alice/msg': 'v1'}, {'Alice': 1})
        self.assertNotIn(block.hash(), receiver.sync_pending)
        self.assertEqual(len(events(net, 'FINALIZE')), 1)

    def test_reserved_relay_then_direct_send_respects_every_actual_window(self):
        self._check_reservations(False)

    def test_reserved_relay_then_another_route_respects_every_actual_window(self):
        self._check_reservations(True)

    def _check_reservations(self, routed_second):
        class Sink:
            done = False
            def __init__(self, i): self.name = f'V{i}'; self.arrivals = []
            def start(self): pass
            def on_timeout(self, _): pass
            def on_message(self, msg, src): self.arrivals.append((msg, net.now))
        net = Net(dict(n=10, seed=1, gst=0, delta=20,
                       links=[[i, i + 1] for i in range(9)],
                       rate_limit={'max_messages': 1, 'window': 10}))
        net.nodes = [Sink(i) for i in range(10)]
        net.send(0, 2, ('ROUTED', None))
        net.send(1 if not routed_second else 2, 0, ('SECOND', None))
        net.run(200)
        self.assertEqual(len(net.nodes[2].arrivals), 1)
        self.assertEqual(len(net.nodes[0].arrivals), 1)
        sends = log_events(net, 'SEND')
        for idx in range(10):
            times = sorted(int(row['t']) for row in sends if row['node'] == f'V{idx}')
            for end in times:
                self.assertLessEqual(sum(end - 10 < t <= end for t in times), 1,
                                     f'V{idx}: actual SEND timestamps {times}')
        for kind, dest in [('ROUTED', 2), ('SECOND', 0)]:
            start = min(int(row['t']) for row in sends if row['type'] == kind)
            self.assertLessEqual(net.nodes[dest].arrivals[0][1] - start, 20)
