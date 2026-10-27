"""Mã hóa tất định, hash, chữ ký (domain separation), và các kiểu dữ liệu."""
import hashlib
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

NIL = b""  # phiếu NIL


# ---------- mã hóa tất định ----------
def encode(o) -> bytes:
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
    return hashlib.sha256(data).digest()


# ---------- khóa và chữ ký ----------
class KeyPair:
    def __init__(self, seed: bytes):
        self.sk = Ed25519PrivateKey.from_private_bytes(H(seed))
        self.pk = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign(kp: KeyPair, domain: str, body) -> bytes:
    return kp.sk.sign(encode(domain) + encode(body))


def verify(pk: bytes, domain: str, body, sig: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(pk).verify(
            sig, encode(domain) + encode(body))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------- kiểu dữ liệu ----------
@dataclass(frozen=True)
class Tx:
    sender: str
    nonce: int
    key: str
    value: str
    sig: bytes = b""

    @property
    def height(self) -> int:
        """Hỗ trợ tương thích với bộ logger mạng của sim.py"""
        return 0

    def body(self):
        return [self.sender, self.nonce, self.key, self.value]


@dataclass(frozen=True)
class Header:
    height: int
    round: int
    pol_round: int     # -1: block mới; >=0: đề xuất lại block đã có polka ở round đó
    parent: bytes
    state_hash: bytes
    tx_root: bytes
    proposer: str
    sig: bytes = b""

    def body(self):
        # Thứ tự phải trùng thứ tự trường (trừ sig) để Header(*body, sig=...) chạy đúng.
        return [self.height, self.round, self.pol_round, self.parent,
                self.state_hash, self.tx_root, self.proposer]


@dataclass(frozen=True)
class Block:
    header: Header
    txs: tuple = ()

    def hash(self) -> bytes:
        # "Block id": chỉ băm phần NỘI DUNG. Không băm round, pol_round, proposer,
        # để cùng một nội dung đề xuất lại ở round khác vẫn ra cùng hash.
        h = self.header
        return H(encode([h.height, h.parent, h.state_hash, h.tx_root]))


@dataclass(frozen=True)
class Vote:
    kind: str          # "PREVOTE" | "PRECOMMIT"
    height: int
    round: int
    block_hash: bytes  # NIL = b""
    voter: str
    sig: bytes = b""

    def body(self):
        return [self.kind, self.height, self.round, self.block_hash, self.voter]


def tx_root(txs) -> bytes:
    return H(encode([[t.body(), t.sig] for t in txs]))


@dataclass(frozen=True)
class CommitCertificate:
    height: int
    round: int
    block_hash: bytes
    signatures: dict  # voter (str) -> signature (bytes)


@dataclass(frozen=True)
class SyncReq:
    requester: str
    from_height: int
    to_height: int
    height: int = 0  # Hỗ trợ log tương thích trong sim.py


@dataclass(frozen=True)
class SyncResp:
    responder: str
    chain_data: tuple  # Tuple chứa các cặp (Block, CommitCertificate)
    height: int = 0
