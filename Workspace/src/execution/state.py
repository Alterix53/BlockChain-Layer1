from __future__ import annotations
import copy
from typing import Optional
from src.common import canonical_encode, H


class State:
    """
    Quản lý trạng thái Key-Value và bảng số thứ tự nonce của các tài khoản.
    Đảm bảo tính tất định (determinism) khi tính toán state_hash.
    """
    def __init__(self, data: Optional[dict[str, str]] = None, nonces: Optional[dict[str, int]] = None) -> None:
        self.data: dict[str, str] = dict(data) if data is not None else {}
        self.nonces: dict[str, int] = dict(nonces) if nonces is not None else {}

    def get(self, key: str) -> Optional[str]:
        """Truy vấn giá trị theo key từ bảng dữ liệu."""
        return self.data.get(key)

    def get_nonce(self, sender: str) -> int:
        """Lấy nonce hiện tại của tài khoản gửi (mặc định bằng 0 nếu chưa có giao dịch)."""
        return self.nonces.get(sender, 0)

    def copy(self) -> State:
        """
        Tạo bản sao sâu (deep copy) của State phục vụ kiểm tra dry-run 
        hoặc thực thi khối mà không ảnh hưởng trực tiếp tới trạng thái gốc.
        """
        return State(data=self.data.copy(), nonces=self.nonces.copy())

    def compute_state_hash(self) -> bytes:
        """
        Tính toán chuỗi hash đại diện cho trạng thái hiện tại.
        
        Quy tắc tất định:
        - Luôn sắp xếp khóa của data và nonces theo thứ tự từ điển (lexicographical order).
        - Đóng gói thành danh sách các cặp [key, value] và tuần tự hóa qua canonical_encode.
        - Băm bằng hàm băm mật mã H() dùng chung (SHA-256).
        """
        sorted_data_keys = sorted(self.data.keys())
        canonical_data = [[k, self.data[k]] for k in sorted_data_keys]

        sorted_nonce_keys = sorted(self.nonces.keys())
        canonical_nonces = [[k, self.nonces[k]] for k in sorted_nonce_keys]

        state_payload = {
            "data": canonical_data,
            "nonces": canonical_nonces,
        }
        encoded_bytes = canonical_encode(state_payload)
        return H(encoded_bytes)