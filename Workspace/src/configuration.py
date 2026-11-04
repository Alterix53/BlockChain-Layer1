"""Scenario validation and workspace-relative configuration paths."""
from pathlib import Path

from .byzantine import REGISTRY

WORKSPACE = Path(__file__).resolve().parents[1]


def validate_config(cfg):
    for key in ("n", "f", "heights", "seed", "max_txs_per_block", "txs_per_account", "t_end"):
        if type(cfg.get(key)) is not int:
            raise ValueError(f"{key} phải là số nguyên")
    n, f = cfg["n"], cfg["f"]
    if f < 0 or n != 3 * f + 1 or n < 8:
        raise ValueError("cần n = 3f+1 và n >= 8")
    if cfg["heights"] < 1 or cfg["max_txs_per_block"] < 1 or cfg["txs_per_account"] < 0 or cfg["t_end"] < 0:
        raise ValueError("heights/max_txs phải > 0; số tx và t_end phải >= 0")
    if not isinstance(cfg.get("chain_id"), str) or not cfg["chain_id"]:
        raise ValueError("chain_id phải khác rỗng")
    accounts = cfg.get("accounts")
    if (not isinstance(accounts, list) or not accounts
            or any(not isinstance(a, str) or not a or "/" in a for a in accounts)
            or len(set(accounts)) != len(accounts)):
        raise ValueError("accounts phải duy nhất, khác rỗng và không chứa '/' trong tên")
    if cfg.get("base_timeout", 0) <= 0 or cfg.get("timeout_inc", -1) < 0:
        raise ValueError("base_timeout phải > 0 và timeout_inc >= 0")
    for key in ("max_ahead_h", "max_round", "max_future_headers", "max_pending_headers"):
        if key in cfg and (type(cfg[key]) is not int or cfg[key] < 1):
            raise ValueError(f"{key} phải là số nguyên dương")
    raw = cfg.get("byzantine", {})
    if not isinstance(raw, dict):
        raise ValueError("byzantine phải là object ánh xạ index sang cấu hình")
    out = {}
    for key, entry in raw.items():
        try:
            idx = int(key)
        except (ValueError, TypeError):
            raise ValueError(f"index Byzantine không hợp lệ: {key!r}") from None
        if not 0 <= idx < n or idx in out or not isinstance(entry, dict):
            raise ValueError(f"cấu hình Byzantine không hợp lệ: {key!r}")
        if (not isinstance(entry.get("behavior", "honest"), str)
                or entry.get("behavior", "honest") not in REGISTRY):
            raise ValueError(f"hành vi không hỗ trợ: {entry.get('behavior')!r}")
        out[idx] = entry
    if sum(e.get("behavior", "honest") != "honest" for e in out.values()) > f:
        raise ValueError("số Byzantine vượt f trong mô hình chuẩn")
    return out
