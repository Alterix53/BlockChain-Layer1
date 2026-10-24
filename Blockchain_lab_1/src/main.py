"""Chạy một kịch bản: python -m src.main [--config config/default.json] [--twice]"""
import argparse
import json
import os

from .common import H, KeyPair, Tx, sign
from .node import Node
from .sim import Net


def run_sim(cfg):
    n, f = cfg["n"], cfg["f"]
    assert n == 3 * f + 1 and n >= 8, "cần n = 3f+1 và n >= 8"
    cid = cfg["chain_id"]
    net = Net(cfg)
    vals = [f"V{i}" for i in range(n)]
    vkps = [KeyPair(f"val-{cfg['seed']}-{i}".encode()) for i in range(n)]
    akps = {a: KeyPair(f"acct-{cfg['seed']}-{a}".encode()) for a in cfg["accounts"]}
    ctx = dict(chain_id=cid, vals=vals, f=f, net=net, heights=cfg["heights"],
               vpks={v: k.pk for v, k in zip(vals, vkps)},
               acct_pks={a: k.pk for a, k in akps.items()},
               base_timeout=cfg["base_timeout"], timeout_inc=cfg["timeout_inc"],
               max_txs=cfg["max_txs_per_block"])
    txs = []
    for a in cfg["accounts"]:
        for k in range(1, cfg["txs_per_account"] + 1):
            t = Tx(a, k, f"{a}/msg", f"v{k}")
            txs.append(Tx(*t.body(), sig=sign(akps[a], "TX:" + cid, t.body())))
    net.nodes = [Node(i, ctx, vkps[i]) for i in range(n)]
    for nd in net.nodes:
        nd.mempool = list(txs)  # TODO: gossip tx thay vì phát sẵn cho mọi node
    net.run(cfg["t_end"])
    return net


def check_safety(nodes):
    m = min(len(x.ledger) for x in nodes)
    for h in range(m):
        assert len({x.ledger[h].hash() for x in nodes}) == 1, f"FORK ở height {h+1}!"
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default.json")
    ap.add_argument("--twice", action="store_true", help="chạy 2 lần, so sánh log (T8)")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    net = run_sim(cfg)
    m = check_safety(net.nodes)
    os.makedirs("logs", exist_ok=True)
    open("logs/run.log", "w").write("\n".join(net.logs) + "\n")
    print(f"OK: {m} block được chốt, mọi node cùng chuỗi.")
    print("state hash cuối:", net.nodes[0].state.hash().hex()[:16])
    print("state:", net.nodes[0].state.data)
    if a.twice:
        net2 = run_sim(cfg)
        same = net.logs == net2.logs and net.nodes[0].state.hash() == net2.nodes[0].state.hash()
        print("Tất định (2 lần chạy giống hệt):", same)
        assert same


if __name__ == "__main__":
    main()