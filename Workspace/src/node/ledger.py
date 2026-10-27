from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List
from src.common import crypto, Block, Vote

@dataclass
class CommitCertificate:
    """
    Bằng chứng mật mã chứng minh block đã đạt tính đồng thuận tối hậu (finality).
    Chứa tối thiểu 2f + 1 chữ ký PRECOMMIT từ các validator khác nhau.
    """
    height: int
    round: int
    block_hash: bytes
    signatures: Dict[str, bytes]  # validator_id (pubkey) -> signature bytes


class Ledger:
    """
    Quản lý chuỗi khối bất biến và bằng chứng CommitCertificate tương ứng.
    """
    def __init__(self) -> None:
        self.blocks: Dict[int, Block] = {}
        self.certificates: Dict[int, CommitCertificate] = {}
        self.latest_height: int = 0

    def verify_commit_certificate(
        self,
        block: Block,
        cert: CommitCertificate,
        validator_keys: List[str],
        chain_id: str,
    ) -> Tuple[bool, str]:
        """
        Xác thực tính hợp lệ của CommitCertificate:
        1. Khớp nối chiều cao khối và giá trị băm của block.
        2. Đạt ngưỡng túc số quorum >= 2f + 1 (với f = (n - 1) // 3).
        3. Tất cả validator ký phải thuộc danh sách validator hợp lệ và không trùng lặp.
        4. Xác thực chữ ký số của từng validator với domain 'VOTE:chain_id'.
        """
        # 1. So khớp thông tin block
        if cert.height != block.header.height:
            return False, "CERT_HEIGHT_MISMATCH"
        if cert.block_hash != block.hash():
            return False, "CERT_BLOCK_HASH_MISMATCH"

        # 2. Tính toán túc số quorum
        n = len(validator_keys)
        f = (n - 1) // 3
        quorum = 2 * f + 1

        valid_signer_keys = set(validator_keys)
        unique_signers = set(cert.signatures.keys())

        # Kiểm tra chỉ chứa các validator thuộc danh sách cho phép
        if not unique_signers.issubset(valid_signer_keys):
            return False, "UNKNOWN_VALIDATOR_SIGNATURE"

        if len(unique_signers) < quorum:
            return False, f"INSUFFICIENT_SIGNATURES: got {len(unique_signers)}, required {quorum}"

        # 3. Xác thực chữ ký từng validator
        domain = f"VOTE:{chain_id}"
        vote_message = Vote(
            height=cert.height,
            round=cert.round,
            phase="PRECOMMIT",
            block_hash=cert.block_hash
        ).payload_bytes()

        for val_pubkey, sig in cert.signatures.items():
            if not crypto.verify(pubkey=val_pubkey, message=vote_message, signature=sig, domain=domain):
                return False, f"INVALID_VOTE_SIGNATURE from {val_pubkey}"

        return True, "OK"

    def commit_block(
        self,
        block: Block,
        cert: CommitCertificate,
        validator_keys: List[str],
        chain_id: str,
    ) -> bool:
        """
        Kiểm tra và lưu trữ block cùng certificate vào ledger.
        """
        is_valid, reason = self.verify_commit_certificate(block, cert, validator_keys, chain_id)
        if not is_valid:
            return False

        h = block.header.height
        self.blocks[h] = block
        self.certificates[h] = cert
        if h > self.latest_height:
            self.latest_height = h

        return True

    def get_block(self, height: int) -> Optional[Block]:
        """Truy xuất block theo height."""
        return self.blocks.get(height)

    def get_certificate(self, height: int) -> Optional[CommitCertificate]:
        """Truy xuất certificate theo height phục vụ phản hồi sync cho peer."""
        return self.certificates.get(height)