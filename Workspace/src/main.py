"""Chạy một kịch bản: python -m src.main [--config config/default.json] [--twice]"""
import argparse
import json
import sys

# Đảm bảo in ký tự tiếng Việt an toàn trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .byzantine import make_node
from .common import Tx, sign
from .node import Node
from .sim import Net
from pathlib import Path

from .configuration import WORKSPACE, validate_config
from .identities import identity_keys
from .validation import check_completion, check_safety, snapshot


def run_sim(cfg):
    """
    Khởi tạo và thực thi một kịch bản mô phỏng hoàn chỉnh từ tệp cấu hình JSON.

    Công việc thực hiện:
    1. Kiểm tra bất biến số học hệ thống BFT: n = 3f + 1 và n >= 8 (Mục 3 & 6 đề bài).
    2. Khởi tạo mạng mô phỏng Net(cfg) với hạt giống ngẫu nhiên (seed).
    3. Nạp private identity fixture Ed25519 cố định, độc lập seed mạng.
    4. Sinh các cặp khóa tài khoản người dùng và tạo danh sách các giao dịch Tx ban đầu hợp lệ.
    5. Khởi tạo danh sách các node: hỗ trợ nạp cấu hình Byzantine qua factory `make_node` nếu có.
    6. Nạp danh sách giao dịch ban đầu vào mempool của các node.
    7. Chạy vòng lặp mô phỏng sự kiện rời rạc cho đến khi đạt thời gian `t_end`.
    """
    byz_cfg = validate_config(cfg)
    n, f = cfg["n"], cfg["f"]
    cid = cfg["chain_id"]
    net = Net(cfg)
    vals = [f"V{i}" for i in range(n)]
    vkps, akps = identity_keys(cfg)
    ctx = dict(chain_id=cid, vals=vals, f=f, net=net, heights=cfg["heights"],
               vpks={v: k.pk for v, k in zip(vals, vkps)},
               acct_pks={a: k.pk for a, k in akps.items()},
               base_timeout=cfg["base_timeout"], timeout_inc=cfg["timeout_inc"],
               max_txs=cfg["max_txs_per_block"])
    for key in ("max_ahead_h", "max_round", "max_future_headers", "max_pending_headers"):
        if key in cfg:
            ctx[key] = cfg[key]
    txs = []
    for a in cfg["accounts"]:
        for k in range(1, cfg["txs_per_account"] + 1):
            t = Tx(a, k, f"{a}/msg", f"v{k}")
            txs.append(Tx(*t.body(), sig=sign(akps[a], "TX:" + cid, t.body())))

    # Hỗ trợ nạp cấu hình Byzantine từ tệp JSON nếu có
    net.nodes = []
    for i in range(n):
        if i in byz_cfg:
            b_info = dict(byz_cfg[i])
            behavior = b_info.pop("behavior", "honest")
            node = make_node(behavior, i, ctx, vkps[i], **b_info)
            if behavior in ("equivocate_proposer", "invalid_block") and node.proposer(
                    node.attack_height, node.attack_round) != node.name:
                raise ValueError(f"{node.name} không phải proposer tại slot tấn công đã cấu hình")
        else:
            node = Node(i, ctx, vkps[i])
        net.nodes.append(node)

    for nd in net.nodes:
        for tx in txs:
            nd.on_tx(tx, gossip=False)
    net.run(cfg["t_end"])
    return net


def main():
    """
    Điểm vào chính khi chạy từ dòng lệnh:
    Cung cấp các cờ:
    - `--config`: Đường dẫn tới file JSON cấu hình mạng (mặc định 'config/default.json').
    - `--twice`: Thực thi 2 lần liên tiếp để kiểm chứng tính tất định 100% (Kịch bản T8).
    """
    ap = argparse.ArgumentParser(description="Mô phỏng mạng Blockchain Layer 1 với Tendermint BFT")
    ap.add_argument("--config", default=str(WORKSPACE / "config/default.json"), help="Đường dẫn file cấu hình JSON")
    ap.add_argument("--log", default=str(WORKSPACE / "logs/run.log"))
    ap.add_argument("--twice", action="store_true", help="Chạy 2 lần so sánh byte log và state hash (T8)")
    a = ap.parse_args()
    try:
        with open(a.config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        net = run_sim(cfg)
        log = Path(a.log)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(("\n".join(net.logs) + "\n").encode("utf-8"))
        node = check_completion(net.nodes, cfg["heights"])
        if a.twice:
            net2 = run_sim(cfg)
            check_completion(net2.nodes, cfg["heights"])
            second_log = log.with_name(log.stem + ".second" + log.suffix)
            second_log.write_bytes(("\n".join(net2.logs) + "\n").encode("utf-8"))
            if log.read_bytes() != second_log.read_bytes() or snapshot(net.nodes) != snapshot(net2.nodes):
                raise RuntimeError("hai lần chạy khác log/ledger/state của node trung thực")
            print("Tất định (2 lần chạy giống hệt): True")
        print(f"OK: {cfg['heights']} block được chốt, mọi node trung thực cùng chuỗi/state.")
        print("state hash cuối:", node.state.hash().hex())
        print("state:", node.state.data)
        return 0
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
