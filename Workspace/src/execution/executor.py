from __future__ import annotations
from typing import Tuple, List
from src.common import crypto, Tx
from src.execution.state import State

def validate_tx(tx: Tx, state: State, chain_id: str) -> Tuple[bool, str]:
    """
    Kiểm tra 3 điều kiện hợp lệ cốt lõi của một giao dịch:
    1. Xác thực chữ ký mật mã với Domain Separation TX:chain_id.
    2. Kiểm tra quyền sở hữu Namespace: key phải bắt đầu bằng '{sender}/'.
    3. Kiểm tra Nonce tuần tự: tx.nonce == current_nonce + 1 (chống replay và gap).
    """
    # 1. Kiểm tra chữ ký & domain separation
    domain = f"TX:{chain_id}"
    message_bytes = tx.payload_bytes()
    if not crypto.verify(pubkey=tx.sender, message=message_bytes, signature=tx.signature, domain=domain):
        return False, "INVALID_SIGNATURE_OR_DOMAIN"

    # 2. Kiểm tra phân quyền Namespace
    expected_prefix = f"{tx.sender}/"
    if not tx.key.startswith(expected_prefix):
        return False, "UNAUTHORIZED_NAMESPACE"

    # 3. Kiểm tra Nonce chống Replay
    current_nonce = state.get_nonce(tx.sender)
    expected_nonce = current_nonce + 1

    if tx.nonce < expected_nonce:
        return False, "NONCE_REPLAY"
    if tx.nonce > expected_nonce:
        return False, "NONCE_GAP"

    return True, "OK"


def apply_txs(state: State, txs: List[Tx], chain_id: str) -> Tuple[State, bytes]:
    """
    Áp dụng tuần tự danh sách các giao dịch lên bản sao của State.
    Chỉ các giao dịch hợp lệ mới được ghi nhận vào dữ liệu và cập nhật nonce.
    Trả về đối tượng State mới cùng state_hash tính toán được.
    """
    new_state = state.copy()
    for tx in txs:
        is_valid, _ = validate_tx(tx, new_state, chain_id)
        if is_valid:
            new_state.data[tx.key] = tx.value
            new_state.nonces[tx.sender] = tx.nonce

    new_state_hash = new_state.compute_state_hash()
    return new_state, new_state_hash