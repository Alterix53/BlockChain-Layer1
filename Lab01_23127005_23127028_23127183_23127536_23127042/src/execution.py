"""State key-value + thực thi giao dịch tất định."""
from .common import H, Tx, encode, verify


def valid_tx_fields(tx):
    return (isinstance(tx, Tx) and isinstance(tx.sender, str)
            and isinstance(tx.key, str) and isinstance(tx.value, str)
            and isinstance(tx.sig, bytes) and type(tx.nonce) is int
            and 0 < tx.nonce < 2**63)


class State:
    """
    Máy trạng thái ứng dụng Key-Value (Application State Machine).

    Cấu trúc:
    - data: Bảng lưu trữ dữ liệu ứng dụng (khóa -> giá trị), ví dụ: 'Alice/msg' -> 'v1'.
    - nonces: Bảng theo dõi số thứ tự giao dịch cuối cùng đã thực thi của từng tài khoản,
              đảm bảo nguyên tắc chống tấn công phát lại (Replay Protection).
    """
    def __init__(self):
        self.data = {}    # key -> value
        self.nonces = {}  # account -> nonce cuối đã dùng

    def copy(self):
        """
        Tạo bản sao độc lập của trạng thái (Cơ chế Copy-on-Write).
        Mục đích: Cho phép node thử nghiệm thực thi danh sách giao dịch mà không làm
        ảnh hưởng đến trạng thái chính thức nếu khối bị từ chối hoặc chưa được chốt.
        """
        s = State()
        s.data, s.nonces = dict(self.data), dict(self.nonces)
        return s

    def hash(self) -> bytes:
        """
        Tính toán mã băm cam kết trạng thái (State Root Hash).
        Mục đích: Đại diện cho toàn bộ trạng thái hiện tại dưới dạng băm 32 byte.
        Tất cả các cặp (key, value) trong data và nonces đều được sắp xếp theo thứ tự từ điển (sorted)
        trước khi encode và băm SHA-256, đảm bảo hai node có cùng dữ liệu thì luôn ra cùng một state hash.
        """
        return H(encode([sorted(self.data.items()), sorted(self.nonces.items())]))


def apply_tx(state: State, tx, chain_id: str, acct_pks: dict):
    """
    Áp dụng một giao dịch đơn lẻ lên trạng thái (sửa đổi trực tiếp tại chỗ).

    Các bước kiểm tra an toàn (Guards):
    1. Kiểm tra tài khoản tồn tại: Người gửi tx.sender phải có khóa công khai trong acct_pks.
       -> Lỗi nếu không tồn tại: 'unknown_sender'
    2. Xác minh chữ ký mật mã: Chữ ký tx.sig phải hợp lệ dưới miền 'TX:chain_id'.
       -> Lỗi nếu chữ ký giả mạo hoặc sai domain: 'bad_tx_sig' (Kịch bản T3)
    3. Phân quyền sở hữu dữ liệu (Namespace Isolation): Tài khoản chỉ được ghi vào các key
       bắt đầu bằng chính tên của mình ('sender/...').
       -> Lỗi nếu ghi đè dữ liệu của người khác: 'not_owner'
    4. Kiểm tra Nonce tuần tự (Replay Protection): Nonce của giao dịch bắt buộc phải bằng
       nonce hiện tại của tài khoản + 1 (không được trùng, không được nhảy cóc).
       -> Lỗi nếu trùng hoặc sai thứ tự: 'bad_nonce' (Kịch bản T4)

    Kết quả:
    - Nếu hợp lệ: Cập nhật state.data và state.nonces, trả về None.
    - Nếu vi phạm: Trả về chuỗi mã lỗi tương ứng.
    """
    if not valid_tx_fields(tx):
        return "bad_tx_format"
    pk = acct_pks.get(tx.sender)
    if pk is None:
        return "unknown_sender"
    if not verify(pk, "TX:" + chain_id, tx.body(), tx.sig):
        return "bad_tx_sig"
    if "/" in tx.sender or tx.key.partition("/")[0] != tx.sender:
        return "not_owner"
    if tx.nonce != state.nonces.get(tx.sender, 0) + 1:
        return "bad_nonce"

    # Cập nhật trạng thái
    state.data[tx.key] = tx.value
    state.nonces[tx.sender] = tx.nonce
    return None


def apply_txs(state: State, txs, chain_id: str, acct_pks: dict):
    """
    Thực thi nguyên tử (Atomic Execution) toàn bộ danh sách giao dịch trong một khối.

    Quy trình:
    1. Tạo một bản sao trạng thái tạm thời `s = state.copy()`.
    2. Tuần tự thực thi từng tx trong danh sách bằng `apply_tx`.
    3. Nếu có bất kỳ giao dịch nào bị lỗi: Hủy toàn bộ thay đổi và trả về (None, err).
    4. Nếu tất cả giao dịch đều hợp lệ: Trả về (s, None) - trạng thái mới hoàn chỉnh.
    """
    s = state.copy()
    for tx in txs:
        err = apply_tx(s, tx, chain_id, acct_pks)
        if err:
            return None, err
    return s, None
