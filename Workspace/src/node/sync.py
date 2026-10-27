from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
from src.common.types import Block
from src.execution.executor import apply_txs
from src.execution.state import State
from src.node.ledger import Ledger, CommitCertificate


@dataclass
class SyncRequest:
    """Thông điệp yêu cầu đồng bộ block từ độ cao from_height đến to_height."""
    from_height: int
    to_height: int


@dataclass
class SyncResponse:
    """Thông điệp phản hồi chứa chuỗi các cặp (Block, CommitCertificate)."""
    chain_data: List[Tuple[Block, CommitCertificate]]


class StateSync:
    """
    Xử lý bắt kịp mạng khi node bị trễ chiều cao so với các peer.
    """
    def __init__(self, ledger: Ledger, state: State, chain_id: str, validator_keys: List[str]) -> None:
        self.ledger: Ledger = ledger
        self.state: State = state
        self.chain_id: str = chain_id
        self.validator_keys: List[str] = validator_keys

    def create_sync_request(self, peer_height: int) -> SyncRequest:
        """Tạo yêu cầu lấy dải block còn thiếu từ local_height + 1 đến peer_height."""
        start_height = self.ledger.latest_height + 1
        return SyncRequest(from_height=start_height, to_height=peer_height)

    def handle_sync_request(self, request: SyncRequest) -> SyncResponse:
        """Đóng gói dữ liệu block và certificate phản hồi cho peer khác khi được yêu cầu."""
        chain_data: List[Tuple[Block, CommitCertificate]] = []
        for h in range(request.from_height, request.to_height + 1):
            block = self.ledger.get_block(h)
            cert = self.ledger.get_certificate(h)
            if block is not None and cert is not None:
                chain_data.append((block, cert))
            else:
                break
        return SyncResponse(chain_data=chain_data)

    def process_sync_response(self, response: SyncResponse) -> Tuple[bool, str]:
        """
        Quy trình thẩm định độc lập (Zero Trust) từng block nhận được từ peer:
        - Bước 1: Xác thực CommitCertificate (đạt quorum >= 2f + 1 chữ ký hợp lệ).
        - Bước 2: Kiểm tra liên kết chuỗi (block.header.parent_hash khớp với hash của block h - 1).
        - Bước 3: Tái thực thi danh sách txs qua apply_txs() trên state cục bộ.
        - Bước 4: So khớp computed_state_hash với block.header.state_hash.
        - Bước 5: Cập nhật ledger và lưu state mới.
        """
        for block, cert in response.chain_data:
            h = block.header.height

            # Đảm bảo khối tiếp nối liên tục chiều cao hiện tại
            if h != self.ledger.latest_height + 1:
                return False, f"UNEXPECTED_HEIGHT: expected {self.ledger.latest_height + 1}, got {h}"

            # 1. Thẩm định Commit Certificate
            is_cert_valid, reason = self.ledger.verify_commit_certificate(
                block=block,
                cert=cert,
                validator_keys=self.validator_keys,
                chain_id=self.chain_id
            )
            if not is_cert_valid:
                return False, f"INVALID_CERT_AT_HEIGHT_{h}: {reason}"

            # 2. Kiểm tra liên kết băm cha-con
            if h > 1:
                prev_block = self.ledger.get_block(h - 1)
                if prev_block is None or block.header.parent_hash != prev_block.hash():
                    return False, f"BROKEN_PARENT_HASH_AT_HEIGHT_{h}"

            # 3 & 4. Thực thi lại giao dịch và kiểm tra state hash
            new_state, computed_state_hash = apply_txs(self.state, block.body.txs, self.chain_id)
            if computed_state_hash != block.header.state_hash:
                return False, f"STATE_HASH_MISMATCH_AT_HEIGHT_{h}: computed {computed_state_hash.hex()} vs block {block.header.state_hash.hex()}"

            # 5. Lưu vào ledger và ghi nhận state mới
            self.ledger.commit_block(block, cert, self.validator_keys, self.chain_id)
            self.state = new_state

        return True, "SYNC_COMPLETED"