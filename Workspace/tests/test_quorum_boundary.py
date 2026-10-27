"""Thí nghiệm biên quorum: vì sao cần n >= 3f+1.

Cùng một chiến lược tấn công (ForkCoalition, Byzantine = V1, V7, V8; V1 là proposer h=1, r=0):
  - n=9,  f=3, Q=6 (NGOÀI giả định của đề): hai nhóm honest chốt hai block khác nhau -> fork.
  - n=10, f=3, Q=7 (đúng giả định):           không có fork.
  - n=9,  f=3, Q=7:                            không fork nhưng không ai chốt được (mất liveness).
Hai quorum Q trong n node giao nhau ít nhất 2Q-n node: n9/Q6 -> 3 (có thể toàn Byzantine),
n10/Q7 -> 4 > f (luôn có >= 1 honest, mà honest không ký hai phía).
Kết quả giống nhau dù có chia cắt mạng trước GST (gst=5000) hay không (gst=0): nhóm R không bao
giờ nhận block A nên phiếu A của nhóm L tới R cũng không đủ Q. Thí nghiệm chỉ cần send() của A.
Hai CommitCertificate (của D) của hai nhánh đều hợp lệ: node mới đồng bộ sẽ theo nhánh nào là
tùy peer nào trả lời. Certificate chỉ đáng tin khi n >= 3f+1. Ở n=10, nhóm không chốt được
tự hỏi đồng bộ (SYNC_REQ) sau một round thất bại và bắt kịp bằng certificate của nhóm kia.

Chạy test:     python -m unittest discover -s tests -p "test_quorum_boundary.py" -v
In báo cáo:    python tests/test_quorum_boundary.py --report
"""
import os
import sys
import unittest
from dataclasses import replace
from types import SimpleNamespace

_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_TESTS), _TESTS):  # Workspace/ (cho src) và tests/ (cho c_helpers)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.byzantine import Coalition, ForkCoalition  # noqa: E402
from src.common import KeyPair, SyncResp, Tx, sign  # noqa: E402
from src.node import Node  # noqa: E402
from src.sim import Net  # noqa: E402
from c_helpers import (RecordingNet, assert_honest_certificates,  # noqa: E402
                       assert_honest_progress, assert_honest_safety, cert_sigs_ok, events,
                       honest_finalized, log_events)

BYZ = (1, 7, 8)
LEFT = (0, 2, 3)
RIGHT_N9 = (4, 5, 6)
RIGHT_N10 = (4, 5, 6, 9)


class PartitionNet(Net):
    """TẠM thay cho send(src, dst, msg) (và GST) của phần A. Xóa khi A merge.
    Trước GST: tin giữa hai nhóm honest bị giữ tới sau GST (adversary điều khiển lịch mạng,
    đúng giả định partial synchrony). Tin còn lại và mọi tin sau GST: trễ 1..delta.
    gst=0 nghĩa là không chia cắt gì cả."""

    def __init__(self, cfg, side):
        super().__init__(cfg)
        self.gst, self.side = cfg["gst"], side  # side: idx -> "L" / "R" (Byzantine: không có)

    def _delay(self, src, dst):
        d = self.rng.randint(1, self.delta)
        a, b = self.side.get(src), self.side.get(dst)
        if self.now < self.gst and a and b and a != b:
            return self.gst - self.now + d
        return d

    @staticmethod
    def _height(msg):
        return msg[1].header.height if msg[0] == "PROPOSAL" else msg[1].height

    def broadcast(self, src, msg):
        self.log(self.nodes[src].name, "SEND", type=msg[0], height=self._height(msg))
        for dst in range(len(self.nodes)):
            self.push(self.now + self._delay(src, dst), "MSG", dst, msg)

    def send(self, src, dst, msg):
        self.log(self.nodes[src].name, "SEND", type=msg[0], height=self._height(msg),
                 dst=self.nodes[dst].name)
        self.push(self.now + self._delay(src, dst), "MSG", dst, msg)


def run_experiment(n, q, right, f=3, seed=7, gst=5000):
    side = {i: "L" for i in LEFT} | {i: "R" for i in right}
    net = PartitionNet(dict(seed=seed, delta=20, gst=gst), side)
    vals = [f"V{i}" for i in range(n)]
    vkps = [KeyPair(f"val-{seed}-{i}".encode()) for i in range(n)]
    alice = KeyPair(f"acct-{seed}-Alice".encode())
    tx = Tx("Alice", 1, "Alice/msg", "hello")
    tx = replace(tx, sig=sign(alice, "TX:lab01", tx.body()))
    ctx = dict(chain_id="lab01", vals=vals, f=f, net=net, heights=1,
               vpks={v: k.pk for v, k in zip(vals, vkps)}, acct_pks={"Alice": alice.pk},
               base_timeout=200, timeout_inc=100, max_txs=10)
    coalition = Coalition(LEFT, right)
    net.nodes = []
    for i in range(n):
        if i in BYZ:
            nd = ForkCoalition(i, ctx, vkps[i]).configure(coalition=coalition)
        else:
            nd = Node(i, ctx, vkps[i])
        nd.Q = q  # tham số của thí nghiệm, áp cho MỌI node, trước START
        nd.mempool = [tx]
        net.nodes.append(nd)
    assert {nd.Q for nd in net.nodes} == {q}
    net.run(100000)
    return SimpleNamespace(net=net, nodes=net.nodes, coalition=coalition,
                           byz={f"V{i}" for i in BYZ}, ctx=ctx, q=q)


def synced_nodes(ex):
    """Tên các node đã chốt nhờ đồng bộ (SYNC_RESP) chứ không phải nhờ tự gom phiếu."""
    return sorted({r["node"] for r in log_events(ex.net, "SYNC_CATCHUP_SUCCESS")})


def fresh_node_syncs(ex, block, cert):
    """Một node honest MỚI (ledger rỗng) nhận (block, cert) qua đồng bộ của D. Node này chỉ
    nhận, không ký gì, nên dùng tạm vị trí V0 với khóa riêng và mạng ghi log riêng."""
    nd = Node(0, dict(ex.ctx, net=RecordingNet()), KeyPair(b"fresh"))
    nd.Q = ex.q
    nd.start()
    nd.on_message(("SYNC_RESP", SyncResp("peer", ((block, cert),))))
    return nd


class TestQuorumBoundary(unittest.TestCase):
    def test_n9_q6_breaks_safety(self):
        for gst in (5000, 0):
            with self.subTest(gst=gst):
                self.check_n9_fork(run_experiment(n=9, q=6, right=RIGHT_N9, gst=gst))

    def check_n9_fork(self, ex):
        a, b = (blk.hash() for blk in ex.coalition.blocks)
        with self.assertRaisesRegex(AssertionError, "FORK ở height 1"):
            assert_honest_safety(ex.nodes, ex.byz)
        fin = honest_finalized(ex.nodes, ex.byz)[1]
        self.assertEqual(sorted(fin[a]), ["V0", "V2", "V3"])
        self.assertEqual(sorted(fin[b]), ["V4", "V5", "V6"])

        # honest vẫn tuân thủ luật: mỗi phase chỉ ký đúng một target, đúng nhánh của nhóm mình
        for nd in ex.nodes:
            if nd.name not in ex.byz:
                mine = a if nd.idx in LEFT else b
                self.assertEqual(nd.signed, {(1, 0, "PREVOTE"): mine, (1, 0, "PRECOMMIT"): mine})

        # hai certificate (của D): đủ Q chữ ký hợp lệ, cùng slot, giao nhau đúng nhóm Byzantine
        assert_honest_certificates(ex.nodes, ex.byz)
        certs = [ex.nodes[0].certificates[1], ex.nodes[4].certificates[1]]
        for cert, target in zip(certs, (a, b)):
            self.assertEqual((cert.height, cert.round, cert.block_hash), (1, 0, target))
            self.assertEqual(len(cert.signatures), 6)
            self.assertTrue(cert_sigs_ok(cert, ex.ctx["vpks"]))
        self.assertEqual(set(certs[0].signatures) & set(certs[1].signatures), ex.byz)

        # node mới đồng bộ bằng certificate nào cũng được nhận -> chuỗi của nó tùy người trả lời
        for blk, cert in zip(ex.coalition.blocks, certs):
            nd = fresh_node_syncs(ex, blk, cert)
            self.assertEqual(nd.ledger, [blk])
            self.assertEqual(len(events(nd.net, "SYNC_CATCHUP_SUCCESS")), 1)

    def test_n10_q7_same_attack_is_safe(self):
        for gst in (5000, 0):
            with self.subTest(gst=gst):
                ex = run_experiment(n=10, q=7, right=RIGHT_N10, gst=gst)
                a, b = (blk.hash() for blk in ex.coalition.blocks)
                assert_honest_safety(ex.nodes, ex.byz)
                assert_honest_progress(ex.nodes, ex.byz, heights=1)
                assert_honest_certificates(ex.nodes, ex.byz)
                fin = honest_finalized(ex.nodes, ex.byz)[1]
                self.assertEqual(list(fin), [b], "chỉ có block B được chốt, A thì không")
                # R tự chốt (4 + 3 = 7 = Q). L chỉ có 3 + 3 = 6 < Q và không có thân B, nên
                # sau một round thất bại tự hỏi đồng bộ và bắt kịp bằng certificate của R
                self.assertEqual(synced_nodes(ex), ["V0", "V2", "V3"])
                self.assertEqual(sorted({r["node"] for r in log_events(ex.net, "SYNC_REQUEST")}),
                                 ["V0", "V2", "V3"])
                self.assertTrue(any("ev=BYZ_EQUIVOCATE_VOTE" in x for x in ex.net.logs),
                                "tấn công phải thực sự chạy")

    def test_n9_q7_safe_but_no_liveness(self):
        ex = run_experiment(n=9, q=7, right=RIGHT_N9)
        assert_honest_safety(ex.nodes, ex.byz)
        self.assertEqual(honest_finalized(ex.nodes, ex.byz), {},
                         "chỉ 6 honest < 7: không ai chốt được")
        with self.assertRaisesRegex(AssertionError, "chưa chốt đủ"):
            assert_honest_progress(ex.nodes, ex.byz, heights=1)

    def test_experiment_is_deterministic(self):
        one = run_experiment(n=9, q=6, right=RIGHT_N9).net.logs
        two = run_experiment(n=9, q=6, right=RIGHT_N9).net.logs
        self.assertEqual(one, two)


class TestSafetyChecker(unittest.TestCase):
    """Kiểm chính hàm kiểm safety bằng ledger giả (không phải fork của mạng thật)."""

    @staticmethod
    def fake(idx, *hashes):
        blocks = [SimpleNamespace(header=SimpleNamespace(height=h + 1), hash=lambda x=x: x)
                  for h, x in enumerate(hashes)]
        return SimpleNamespace(idx=idx, name=f"V{idx}", ledger=blocks)

    def test_same_chain_ok(self):
        assert_honest_safety([self.fake(0, b"A"), self.fake(1, b"A")], set())

    def test_fork_detected_even_with_empty_ledger(self):
        # main.check_safety lấy min độ dài ledger = 0 nên bỏ sót ca này
        nodes = [self.fake(0, b"A"), self.fake(1, b"B"), self.fake(2)]
        with self.assertRaisesRegex(AssertionError, "FORK"):
            assert_honest_safety(nodes, set())

    def test_byzantine_ledger_ignored(self):
        assert_honest_safety([self.fake(0, b"A"), self.fake(1, b"B")], {"V1"})

    def test_progress_detects_stalled_honest(self):
        with self.assertRaisesRegex(AssertionError, "chưa chốt đủ"):
            assert_honest_progress([self.fake(0, b"A"), self.fake(1)], set(), heights=1)


def report():
    for title, n, q, right in (("Ngoài giả định", 9, 6, RIGHT_N9),
                               ("Đối chứng", 10, 7, RIGHT_N10),
                               ("Giữ Q=7 ở n=9", 9, 7, RIGHT_N9)):
        ex = run_experiment(n=n, q=q, right=right)
        print(f"\n=== {title}: n={n} f=3 Q={q}  Byzantine={sorted(ex.byz)}  "
              f"L={[f'V{i}' for i in LEFT]}  R={[f'V{i}' for i in right]}")
        print(f"    giao tối thiểu 2 quorum = 2Q-n = {2 * q - n}")
        fin = honest_finalized(ex.nodes, ex.byz)
        for h, blocks in sorted(fin.items()):
            for bh, names in blocks.items():
                print(f"    height {h}: block {bh.hex()[:16]} chốt bởi {names}")
        fork = any(len(m) > 1 for m in fin.values())
        if synced_nodes(ex):
            print(f"    chốt nhờ tự hỏi đồng bộ (không đủ phiếu/thân block): {synced_nodes(ex)}")
        stuck = [nd.name for nd in ex.nodes if nd.name not in ex.byz and not nd.ledger]
        if stuck:
            print(f"    honest chưa chốt (liveness, không phải fork): {stuck}")
        print("    => FORK: safety bị phá" if fork else
              "    => an toàn: không có 2 block ở cùng height")
        if fork:
            certs = [ex.nodes[0].certificates[1], ex.nodes[4].certificates[1]]
            for blk, cert in zip(ex.coalition.blocks, certs):
                synced = fresh_node_syncs(ex, blk, cert).ledger == [blk]
                print(f"    certificate {cert.block_hash.hex()[:16]}: {sorted(cert.signatures)} "
                      f"chữ ký hợp lệ={cert_sigs_ok(cert, ex.ctx['vpks'])}  "
                      f"node mới đồng bộ nhận={synced}")
            inter = set(certs[0].signatures) & set(certs[1].signatures)
            print(f"    giao điểm hai certificate = {sorted(inter)}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        unittest.main(verbosity=2)
