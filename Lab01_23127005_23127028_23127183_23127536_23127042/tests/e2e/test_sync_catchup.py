"""An isolated node catches up over the production network."""
import unittest
from unittest import mock
from src.main import run_sim
from src.sim import Net
from tests.c_helpers import assert_honest_certificates, assert_honest_safety, load_cfg, log_events


class IsolateNet(Net):
    """Drop every physical transmission to/from V9 before GST, including unicasts."""
    ISOLATED, GST = 9, 3000

    def _transmit(self, src, dst, msg):
        if self.now < self.GST and src != dst and self.ISOLATED in (src, dst):
            self.log(self.nodes[src].name, "DROP", dst=self.nodes[dst].name,
                     type=self._unwrap(msg)[0], height=self._message_height(msg),
                     reason="test_isolation")
            return
        super()._transmit(src, dst, msg)


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
                drops = log_events(net, "DROP", reason="test_isolation")
                self.assertTrue(any(r["node"] == "V9" for r in drops))
                self.assertTrue(any(r.get("dst") == "V9" for r in drops))

    def test_normal_run_never_asks(self):
        net = run_sim(load_cfg())
        self.assertEqual(log_events(net, "SYNC_REQUEST"), [])
