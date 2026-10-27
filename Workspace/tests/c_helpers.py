"""Hàm dùng chung cho test phần C: mạng giả, dựng node, ký thông điệp/certificate,
kiểm safety, liveness và certificate trên node honest."""
import json
import os
import re
from dataclasses import replace
from unittest import mock

from src.common import (Block, CommitCertificate, Header, KeyPair, Tx, Vote, sign, tx_root,
                        verify)
from src.execution import apply_txs
from src.main import run_sim
from src.node import Node

CHAIN = "lab01"
ACCOUNTS = {"Alice": KeyPair(b"c-test-alice"), "Bob": KeyPair(b"c-test-bob")}
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- mạng giả cho unit test ----------
class RecordingNet:
    """Chỉ GHI lại lời gọi (gửi, log, hẹn giờ), không tự giao thông điệp.
    Test tự đưa thông điệp vào node bằng node.on_message(msg)."""

    def __init__(self):
        self.now = 0
        self.sent = []      # (src, dst hoặc None nếu broadcast, msg)
        self.events = []    # mỗi dòng log là một dict
        self.timeouts = []  # (idx, delay, key)

    def log(self, node, ev, **kw):
        self.events.append(dict(t=self.now, node=node, ev=ev, **kw))

    def broadcast(self, src, msg):
        self.sent.append((src, None, msg))

    def send(self, src, dst, msg):
        self.sent.append((src, dst, msg))

    def set_timeout(self, idx, delay, key):
        self.timeouts.append((idx, delay, key))

    def clear(self):
        self.sent.clear()
        self.events.clear()
        self.timeouts.clear()


def signed_tx(nonce, key=None, value=None, domain="TX:" + CHAIN, sender="Alice"):
    t = Tx(sender, nonce, key or f"{sender}/msg", value or f"v{nonce}")
    return replace(t, sig=sign(ACCOUNTS[sender], domain, t.body()))


def build_node(behaviors, idx, ctx, kp):
    """Node honest, hoặc lớp Byzantine đã configure nếu idx có trong behaviors."""
    cls, params = (behaviors or {}).get(idx, (Node, None))
    nd = cls(idx, ctx, kp)
    if params:
        nd.configure(**params)
    return nd


def make_nodes(n=10, f=3, q=None, behaviors=None, start=True):
    """n node trên RecordingNet. behaviors = {idx: (Lớp, {tham số})}.
    Cấu hình tấn công và Q xong mới START, giống thứ tự factory thật phải làm."""
    net = RecordingNet()
    vals = [f"V{i}" for i in range(n)]
    vkps = [KeyPair(f"c-test-val-{i}".encode()) for i in range(n)]
    ctx = dict(chain_id=CHAIN, vals=vals, f=f, net=net, heights=1,
               vpks={v: k.pk for v, k in zip(vals, vkps)},
               acct_pks={a: k.pk for a, k in ACCOUNTS.items()},
               base_timeout=200, timeout_inc=100, max_txs=10)
    txs = [signed_tx(1), signed_tx(2)]
    nodes = []
    for i in range(n):
        nd = build_node(behaviors, i, ctx, vkps[i])
        if q is not None:
            nd.Q = q
        nd.mempool = list(txs)
        nodes.append(nd)
    if start:
        for nd in nodes:
            nd.start()
        net.clear()  # bỏ các lời gọi lúc khởi động để mỗi test chỉ thấy phần của mình
    return nodes, net


def signed_vote(signer, kind, target, domain=None, **fields):
    """Vote của `signer` ở (height, round) hiện tại; `fields` đổi trường TRƯỚC khi ký."""
    v = replace(Vote(kind, signer.height, signer.round, target, signer.name), **fields)
    return replace(v, sig=sign(signer.kp, domain or "VOTE:" + CHAIN, v.body()))


def signed_header(signer, hd, domain=None):
    return replace(hd, sig=sign(signer.kp, domain or "HEADER:" + CHAIN, hd.body()))


def valid_block(proposer, txs=()):
    txs = tuple(txs)
    s, err = apply_txs(proposer.state, txs, CHAIN, proposer.ctx["acct_pks"])
    assert err is None, err
    # truyền theo TÊN trường: B đã chèn pol_round vào giữa, truyền theo vị trí sẽ lệch
    hd = Header(height=proposer.height, round=proposer.round, pol_round=-1,
                parent=proposer.last_hash(), state_hash=s.hash(), tx_root=tx_root(txs),
                proposer=proposer.name)
    return Block(signed_header(proposer, hd), txs)


def commit_cert(block, signers, round=0, kind="PRECOMMIT", domain=None):
    """CommitCertificate (kiểu của D) cho `block`: mỗi node trong `signers` ký `kind`
    ở (height của block, round) bằng khóa của chính nó."""
    h, bh = block.header.height, block.hash()
    domain = domain or "VOTE:" + CHAIN
    sigs = {nd.name: sign(nd.kp, domain, Vote(kind, h, round, bh, nd.name).body()) for nd in signers}
    return CommitCertificate(height=h, round=round, block_hash=bh, signatures=sigs)


def cert_sigs_ok(cert, vpks, chain=CHAIN):
    """Mọi chữ ký trong certificate là PRECOMMIT hợp lệ của đúng validator cho đúng
    (height, round, block). Kiểm độc lập bằng verify(), không gọi lại code của D."""
    return all(voter in vpks and verify(vpks[voter], "VOTE:" + chain,
                                        Vote("PRECOMMIT", cert.height, cert.round,
                                             cert.block_hash, voter).body(), sig)
               for voter, sig in sorted(cert.signatures.items()))


def events(net, ev, node=None, **fields):
    """Các dòng log (dict) của RecordingNet khớp loại sự kiện, node và trường."""
    return [e for e in net.events if e["ev"] == ev and (node is None or e["node"] == node)
            and all(e.get(k) == v for k, v in fields.items())]


# ---------- chạy trên mạng sim.py thật ----------
def parse_log(line):
    """'t=5 node=V0 ev=REJECT reason=x' -> {'t': '5', 'node': 'V0', ...}"""
    return dict(re.findall(r"(\w+)=(\S+)", line))


def log_events(net, ev, node=None, **fields):
    rows = [parse_log(x) for x in net.logs]
    return [r for r in rows if r.get("ev") == ev and (node is None or r.get("node") == node)
            and all(r.get(k) == str(v) for k, v in fields.items())]


def load_cfg(**overrides):
    with open(os.path.join(WORKSPACE, "config", "default.json")) as fh:
        cfg = json.load(fh)
    cfg.update(overrides)
    return cfg


def run_with_byzantine(behaviors, **cfg_overrides):
    """Chạy run_sim THẬT (mạng sim.py, config mặc định) nhưng thay vài validator bằng lớp
    Byzantine. behaviors = {idx: (Lớp, {tham số})}.
    TẠM: mock.patch thay `Node` trong main.py vì factory theo config là phần của E."""
    def factory(idx, ctx, kp):
        return build_node(behaviors, idx, ctx, kp)

    with mock.patch("src.main.Node", factory):
        return run_sim(load_cfg(**cfg_overrides))


# ---------- kiểm safety / liveness CHỈ trên node honest ----------
def honest_finalized(nodes, byzantine):
    """{height: {block_hash: [tên node honest đã chốt]}}. byzantine: tập tên node Byzantine."""
    out = {}
    for nd in sorted(nodes, key=lambda x: x.idx):
        if nd.name in byzantine:
            continue
        for b in nd.ledger:
            out.setdefault(b.header.height, {}).setdefault(b.hash(), []).append(nd.name)
    return out


def assert_honest_safety(nodes, byzantine):
    """Không có 2 node honest chốt 2 block khác nhau ở cùng height.
    Khác main.check_safety: không lấy min độ dài ledger, nên node rỗng không che được fork."""
    if all(nd.name in byzantine for nd in nodes):
        raise ValueError("không có node honest nào để kiểm")
    for h, blocks in sorted(honest_finalized(nodes, byzantine).items()):
        if len(blocks) > 1:
            detail = {bh.hex()[:16]: names for bh, names in blocks.items()}
            raise AssertionError(f"FORK ở height {h}: {detail}")


def assert_honest_progress(nodes, byzantine, heights):
    """Mọi node honest đều đã chốt đủ `heights` block."""
    lagging = {nd.name: len(nd.ledger) for nd in nodes
               if nd.name not in byzantine and len(nd.ledger) < heights}
    if lagging:
        raise AssertionError(f"node honest chưa chốt đủ {heights} block: {lagging}")


def assert_honest_certificates(nodes, byzantine):
    """Mỗi block node honest đã chốt đều có CommitCertificate (của D) tự kiểm được: đúng
    height và hash block, >= Q người ký, mọi chữ ký PRECOMMIT đều hợp lệ."""
    for nd in nodes:
        if nd.name in byzantine:
            continue
        if sorted(nd.certificates) != list(range(1, len(nd.ledger) + 1)):
            raise AssertionError(f"{nd.name}: certificate {sorted(nd.certificates)} "
                                 f"không khớp ledger dài {len(nd.ledger)}")
        for b in nd.ledger:
            c = nd.certificates[b.header.height]
            if (c.height, c.block_hash) != (b.header.height, b.hash()):
                raise AssertionError(f"{nd.name}: certificate height {c.height} không khớp block")
            if len(c.signatures) < nd.Q:
                raise AssertionError(f"{nd.name}: certificate height {c.height} thiếu chữ ký")
            if not cert_sigs_ok(c, nd.ctx["vpks"], nd.ctx["chain_id"]):
                raise AssertionError(f"{nd.name}: certificate height {c.height} có chữ ký sai")
