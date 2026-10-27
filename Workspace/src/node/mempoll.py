from __future__ import annotations
from typing import List, Set
from src.common import H, Tx
from src.execution.executor import validate_tx
from src.execution.state import State


class Mempool:
    """
    Hàng đợi giao dịch cục bộ của validator:
    - Lưu trữ danh sách giao dịch hợp lệ chờ Proposer đóng block.
    - Khử trùng lặp trong O(1) qua cấu trúc set lưu tx_hash.
    - Tự động giải phóng các giao dịch đã commit (eviction).
    """
    def __init__(self, capacity: int = 1000) -> None:
        self.capacity: int = capacity
        self.pending_txs: List[Tx] = []
        self.seen_tx_hashes: Set[bytes] = set()

    def add_tx(self, tx: Tx, current_state: State, chain_id: str) -> bool:
        """
        Thêm giao dịch vào mempool:
        - Trả về False nếu hash đã tồn tại hoặc mempool đã đạt giới hạn dung lượng.
        - Trả về False nếu giao dịch không thỏa mãn validate_tx với state hiện tại.
        """
        tx_hash = H(tx.payload_bytes())
        if tx_hash in self.seen_tx_hashes:
            return False

        if len(self.pending_txs) >= self.capacity:
            return False

        is_valid, _ = validate_tx(tx, current_state, chain_id)
        if not is_valid:
            return False

        self.seen_tx_hashes.add(tx_hash)
        self.pending_txs.append(tx)
        return True

    def get_proposal_txs(self, limit: int) -> List[Tx]:
        """Lấy danh sách tối đa 'limit' giao dịch từ đầu hàng đợi để Proposer đề xuất block."""
        return self.pending_txs[:limit]

    def evict_txs(self, committed_txs: List[Tx]) -> None:
        """
        Loại bỏ các giao dịch đã được chốt (committed) vào ledger ra khỏi hàng đợi mempool.
        """
        committed_hashes = {H(tx.payload_bytes()) for tx in committed_txs}
        self.pending_txs = [
            tx for tx in self.pending_txs 
            if H(tx.payload_bytes()) not in committed_hashes
        ]