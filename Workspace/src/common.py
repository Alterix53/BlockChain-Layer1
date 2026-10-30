"""Mã hóa tất định, hash, chữ ký (domain separation), và các kiểu dữ liệu."""
import hashlib
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

NIL = b""  # Giá trị đại diện cho phiếu trắng (không đồng ý hoặc hết giờ chờ proposal)


# ---------- MÃ HÓA TẤT ĐỊNH (CANONICAL SERIALIZATION) ----------
def encode(o) -> bytes:
    """
    Tuần tự hóa đối tượng Python thành chuỗi byte tất định (Canonical Deterministic Encoding).

    Mục đích:
    Trong hệ thống phân tán, các máy tính khác nhau hoặc các lần chạy khác nhau phải tạo ra
    chuỗi byte giống hệt nhau 100% cho cùng một dữ liệu logic (không phụ thuộc thứ tự dict,
    hệ điều hành, hay cấu trúc bộ nhớ). Điều này là điều kiện tiên quyết để mã hash và chữ ký
    hoàn toàn nhất quán giữa các node.

    Quy tắc gắn tiền tố nhận diện kiểu (Type Prefix Tag):
    - None: b'N'
    - bool: b'B' + b'\x01' (True) hoặc b'\x00' (False)  (kiểm tra trước int vì bool kế thừa int)
    - int: b'I' + 8 byte số nguyên có dấu big-endian (>q)
    - str: b'S' + 4 byte độ dài (>I) + chuỗi mã hóa UTF-8
    - bytes/bytearray: b'Y' + 4 byte độ dài (>I) + nội dung byte thô
    - list/tuple: b'L' + 4 byte số lượng phần tử (>I) + chuỗi byte encode tuần tự từng phần tử
    - dict: b'D' + 4 byte số lượng cặp (>I) + encode tuần tự các cặp (key, value) đã được sắp xếp tăng dần theo key
    """
    if o is None:
        return b"N"
    if isinstance(o, bool):
        return b"B" + (b"\x01" if o else b"\x00")
    if isinstance(o, int):
        return b"I" + struct.pack(">q", o)
    if isinstance(o, str):
        d = o.encode("utf-8")
        return b"S" + struct.pack(">I", len(d)) + d
    if isinstance(o, (bytes, bytearray)):
        return b"Y" + struct.pack(">I", len(o)) + bytes(o)
    if isinstance(o, (list, tuple)):
        return b"L" + struct.pack(">I", len(o)) + b"".join(encode(x) for x in o)
    if isinstance(o, dict):
        items = sorted(o.items())
        return b"D" + struct.pack(">I", len(items)) + b"".join(
            encode(k) + encode(v) for k, v in items)
    raise TypeError(f"cannot encode {type(o)}")


def H(data: bytes) -> bytes:
    """
    Hàm băm mật mã chuẩn SHA-256, trả về chuỗi băm 32 byte cố định.
    Được sử dụng xuyên suốt để tính block_hash, state_hash, tx_root, và sinh khóa.
    """
    return hashlib.sha256(data).digest()


# ---------- KHÓA MẬT MÃ VÀ CHỮ KÝ SỐ (ED25519 & DOMAIN SEPARATION) ----------
class KeyPair:
    """
    Cặp khóa bất đối xứng Ed25519 (Khóa bí mật sk và Khóa công khai pk).
    Khởi tạo tất định từ chuỗi byte `seed` thông qua băm SHA-256 để kiểm thử dễ dàng tái lập.
    """
    def __init__(self, seed: bytes):
        self.sk = Ed25519PrivateKey.from_private_bytes(H(seed))
        self.pk = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign(kp: KeyPair, domain: str, body) -> bytes:
    """
    Ký số Ed25519 với cơ chế phân tách miền (Domain Separation).

    Mục đích của Domain Separation (Mục 5 đề bài):
    Ngăn chặn tấn công phát lại chéo ngữ cảnh (Cross-protocol Replay Attack):
    - Chữ ký trên giao dịch ('TX:chain_id') không thể bị kẻ xấu dùng làm chữ ký header ('HEADER:chain_id').
    - Chữ ký bỏ phiếu ('VOTE:chain_id') không thể dùng cho mạng blockchain khác.
    Dữ liệu ký thực tế = encode(domain) + encode(body).
    """
    return kp.sk.sign(encode(domain) + encode(body))


def verify(pk: bytes, domain: str, body, sig: bytes) -> bool:
    """
    Xác minh chữ ký số Ed25519 của dữ liệu `body` dưới ngữ cảnh `domain` với khóa công khai `pk`.
    Trả về True nếu chữ ký hợp lệ và đúng domain; False nếu chữ ký sai, giả mạo, hoặc sai domain.
    """
    try:
        Ed25519PublicKey.from_public_bytes(pk).verify(
            sig, encode(domain) + encode(body))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------- CÁC CẤU TRÚC DỮ LIỆU CỐT LÕI (IMMUTABLE DATACLASSES) ----------
@dataclass(frozen=True)
class Tx:
    """
    Giao dịch (Transaction) do tài khoản phát hành nhằm cập nhật trạng thái.
    - sender: Địa chỉ/Tên tài khoản người gửi (ví dụ: 'Alice').
    - nonce: Số thứ tự giao dịch của tài khoản (1, 2, 3...) chống replay.
    - key: Khóa trạng thái cần cập nhật (phải thuộc namespace 'sender/...').
    - value: Giá trị mới muốn ghi vào state.
    - sig: Chữ ký số Ed25519 của người gửi dưới miền 'TX:chain_id'.
    """
    sender: str
    nonce: int
    key: str
    value: str
    sig: bytes = b""

    @property
    def height(self) -> int:
        """Thuộc tính phụ trợ để bộ logger mạng sim.py trích xuất height đồng nhất."""
        return 0

    def body(self):
        """Trả về nội dung nghiệp vụ được ký (loại trừ chữ ký sig)."""
        return [self.sender, self.nonce, self.key, self.value]


@dataclass(frozen=True)
class Header:
    """
    Tiêu đề khối (Block Header) chứa siêu dữ liệu và các cam kết mật mã:
    - height: Chiều cao của khối trong blockchain (1, 2, 3...).
    - round: Vòng đồng thuận Tendermint chốt được khối này.
    - pol_round: Vòng đạt Proof-of-Lock (Polka round):
      + Giá trị -1: Đây là khối mới tinh đề xuất ở vòng hiện tại.
      + Giá trị >= 0: Khối cũ đã đạt Polka ở vòng `pol_round` được đề xuất lại (Quy tắc 5).
    - parent: Mã băm của khối cha liền trước (h - 1).
    - state_hash: Mã băm của cây trạng thái máy ảo sau khi thực thi danh sách txs.
    - tx_root: Cam kết mật mã (Merkle root) của tập giao dịch trong khối.
    - proposer: Validator đề xuất khối.
    - sig: Chữ ký số của proposer dưới miền 'HEADER:chain_id'.
    """
    height: int
    round: int
    pol_round: int     # -1: block mới; >=0: đề xuất lại block đã có polka ở round đó
    parent: bytes
    state_hash: bytes
    tx_root: bytes
    proposer: str
    sig: bytes = b""

    def body(self):
        """Nội dung tiêu đề được ký (loại trừ chữ ký sig). Thứ tự phải khớp với dataclass."""
        return [self.height, self.round, self.pol_round, self.parent,
                self.state_hash, self.tx_root, self.proposer]


@dataclass(frozen=True)
class Block:
    """
    Khối hoàn chỉnh (Block) bao gồm Header và tập các giao dịch (txs).
    """
    header: Header
    txs: tuple = ()

    def hash(self) -> bytes:
        """
        Định danh khối (Block ID):
        Chỉ băm phần NỘI DUNG CỐT LÕI [height, parent, state_hash, tx_root].
        Không băm `round`, `pol_round`, `proposer` để đảm bảo: Nếu cùng một nội dung khối
        được đề xuất lại ở các round sau do mạng trễ, mã băm block_hash vẫn giữ nguyên.
        """
        h = self.header
        return H(encode([h.height, h.parent, h.state_hash, h.tx_root]))


@dataclass(frozen=True)
class Vote:
    """
    Phiếu bầu đồng thuận của validator trong thuật toán Tendermint:
    - kind: Loại phiếu ('PREVOTE' hoặc 'PRECOMMIT').
    - height: Chiều cao khối đang bầu.
    - round: Vòng bầu cử đang diễn ra.
    - block_hash: Mã băm của block ủng hộ (hoặc NIL = b"" nếu từ chối / timeout).
    - voter: Tên của validator bỏ phiếu.
    - sig: Chữ ký số của voter dưới miền 'VOTE:chain_id'.
    """
    kind: str          # "PREVOTE" | "PRECOMMIT"
    height: int
    round: int
    block_hash: bytes  # NIL = b""
    voter: str
    sig: bytes = b""

    def body(self):
        """Nội dung phiếu được ký (loại trừ trường chữ ký sig)."""
        return [self.kind, self.height, self.round, self.block_hash, self.voter]


def tx_root(txs) -> bytes:
    """
    Tính cam kết mật mã của danh sách giao dịch trong block (Transaction Merkle Root).
    Băm mảng các phần tử [tx.body(), tx.sig] đã tuần tự hóa.
    Nếu tập txs rỗng, vẫn sinh ra mã băm tất định 32 byte của danh sách rỗng.
    """
    return H(encode([[t.body(), t.sig] for t in txs]))


@dataclass(frozen=True)
class CommitCertificate:
    """
    Chứng chỉ cam kết chốt khối (Commit Certificate / Finality Proof):
    Chứa tập hợp tối thiểu 2f + 1 chữ ký PRECOMMIT hợp lệ từ các validator khác nhau
    cho cùng một (height, round, block_hash).
    Chứng chỉ này là bằng chứng không thể chối cãi để các node đồng bộ bắt kịp (Catch-up sync).
    """
    height: int
    round: int
    block_hash: bytes
    signatures: dict  # voter (str) -> signature (bytes)


@dataclass(frozen=True)
class SyncReq:
    """
    Thông điệp yêu cầu đồng bộ khối (Catch-up Sync Request):
    Node bị tụt lại phát yêu cầu xin dữ liệu khối từ `from_height` đến `to_height`.
    """
    requester: str
    from_height: int
    to_height: int
    height: int = 0  # Hỗ trợ log tương thích trong sim.py


@dataclass(frozen=True)
class SyncResp:
    """
    Thông điệp phản hồi dữ liệu đồng bộ (Catch-up Sync Response):
    Gửi kèm chuỗi các bộ đôi (Block, CommitCertificate) để bên nhận kiểm tra và nạp vào ledger.
    """
    responder: str
    chain_data: tuple  # Tuple chứa các cặp (Block, CommitCertificate)
    height: int = 0
