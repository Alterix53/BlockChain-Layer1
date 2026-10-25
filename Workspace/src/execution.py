"""State key-value + thực thi giao dịch tất định."""
from .common import H, encode, verify


class State:
    def __init__(self):
        self.data = {}    # key -> value
        self.nonces = {}  # account -> nonce cuối đã dùng

    def copy(self):
        s = State()
        s.data, s.nonces = dict(self.data), dict(self.nonces)
        return s

    def hash(self) -> bytes:
        return H(encode([sorted(self.data.items()), sorted(self.nonces.items())]))


def apply_tx(state: State, tx, chain_id: str, acct_pks: dict):
    """Áp dụng một tx lên state (sửa tại chỗ). Trả về None nếu OK, hoặc chuỗi lý do lỗi."""
    pk = acct_pks.get(tx.sender)
    if pk is None:
        return "unknown_sender"
    if not verify(pk, "TX:" + chain_id, tx.body(), tx.sig):
        return "bad_tx_sig"
    if not tx.key.startswith(tx.sender + "/"):
        return "not_owner"
    if tx.nonce != state.nonces.get(tx.sender, 0) + 1:
        return "bad_nonce"
    state.data[tx.key] = tx.value
    state.nonces[tx.sender] = tx.nonce
    return None


def apply_txs(state: State, txs, chain_id: str, acct_pks: dict):
    """Trả về (state_mới, None) hoặc (None, lý do). Không sửa state gốc."""
    s = state.copy()
    for tx in txs:
        err = apply_tx(s, tx, chain_id, acct_pks)
        if err:
            return None, err
    return s, None