"""Chạy một kịch bản: python -m src.main [--config config/default.json] [--twice]"""
import argparse
import json
import os
import sys

# Đảm bảo in ký tự tiếng Việt an toàn trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .byzantine import ByzantineBase, make_node
from .common import H, KeyPair, Tx, sign
from .node import Node
from .sim import Net


def run_sim(cfg):
    """
    Khởi tạo và thực thi một kịch bản mô phỏng hoàn chỉnh từ tệp cấu hình JSON.

    Công việc thực hiện:
    1. Kiểm tra bất biến số học hệ thống BFT: n = 3f + 1 và n >= 8 (Mục 3 & 6 đề bài).
    2. Khởi tạo mạng mô phỏng Net(cfg) với hạt giống ngẫu nhiên (seed).
    3. Tạo danh sách n validator và sinh các cặp khóa Ed25519 tất định từ seed.
    4. Sinh các cặp khóa tài khoản người dùng và tạo danh sách các giao dịch Tx ban đầu hợp lệ.
    5. Khởi tạo danh sách các node: hỗ trợ nạp cấu hình Byzantine qua factory `make_node` nếu có.
    6. Nạp danh sách giao dịch ban đầu vào mempool của các node.
    7. Chạy vòng lặp mô phỏng sự kiện rời rạc cho đến khi đạt thời gian `t_end`.
    """
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

    # Hỗ trợ nạp cấu hình Byzantine từ tệp JSON nếu có
    byz_cfg = {int(k): v for k, v in cfg.get("byzantine", {}).items()}
    net.nodes = []
    for i in range(n):
        if i in byz_cfg:
            b_info = dict(byz_cfg[i])
            behavior = b_info.pop("behavior", "honest")
            node = make_node(behavior, i, ctx, vkps[i], **b_info)
        else:
            node = Node(i, ctx, vkps[i])
        net.nodes.append(node)

    for nd in net.nodes:
        nd.mempool = list(txs)
    net.run(cfg["t_end"])
    return net


def check_safety(nodes):
    """
    Kiểm tra bất biến an toàn (Safety Invariant):
    Tuyệt đối không bao giờ được phép có 2 khối khác nhau (mã băm khác nhau)
    được chốt tại cùng một chiều cao height giữa các validator trung thực.
    Loại trừ các node Byzantine cố ý làm sai ledger.
    """
    honest_nodes = [x for x in nodes if not isinstance(x, ByzantineBase)] or nodes
    max_height = max(len(x.ledger) for x in honest_nodes) if honest_nodes else 0
    for h in range(max_height):
        # Lấy hash của block tại height h của mọi honest node đã chốt height này
        hashes = {x.ledger[h].hash() for x in honest_nodes if len(x.ledger) > h}
        assert len(hashes) <= 1, f"FORK phát hiện ở height {h + 1}: {hashes}!"
    return max_height


def main():
    """
    Điểm vào chính khi chạy từ dòng lệnh:
    Cung cấp các cờ:
    - `--config`: Đường dẫn tới file JSON cấu hình mạng (mặc định 'config/default.json').
    - `--twice`: Thực thi 2 lần liên tiếp để kiểm chứng tính tất định 100% (Kịch bản T8).
    """
    ap = argparse.ArgumentParser(description="Mô phỏng mạng Blockchain Layer 1 với Tendermint BFT")
    ap.add_argument("--config", default="config/default.json", help="Đường dẫn file cấu hình JSON")
    ap.add_argument("--twice", action="store_true", help="Chạy 2 lần so sánh byte log và state hash (T8)")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    net = run_sim(cfg)
    m = check_safety(net.nodes)
    os.makedirs("logs", exist_ok=True)
    open("logs/run.log", "w", encoding="utf-8").write("\n".join(net.logs) + "\n")
    print(f"OK: {m} block được chốt, mọi node cùng chuỗi.")
    print("state hash cuối:", net.nodes[0].state.hash().hex()[:16])
    print("state:", net.nodes[0].state.data)
    if a.twice:
        net2 = run_sim(cfg)
        same = net.logs == net2.logs and net.nodes[0].state.hash() == net2.nodes[0].state.hash()
        print("Tất định (2 lần chạy giống hệt):", same)
        assert same, "Lỗi tính tất định: Nhật ký hoặc state hash giữa 2 lần chạy không khớp!"


if __name__ == "__main__":
    main()
