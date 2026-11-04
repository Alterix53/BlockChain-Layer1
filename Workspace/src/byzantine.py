"""Validator Byzantine (phần C): lớp con của Node, cố tình làm sai để thử node trung thực.

Năm hành vi theo mục 3 của đề: im lặng, phiếu mâu thuẫn, đề xuất mâu thuẫn, block sai,
phát lại thông điệp cũ. ForkCoalition phối hợp cả nhóm Byzantine cho thí nghiệm ngoài
giả định (n=9, Q=6).

Byzantine chỉ ký bằng khóa của chính nó và chỉ tác động lên node khác qua self.net;
không đọc hay sửa state/votes/ledger của node khác. Chỉ ghi đè hook/phương thức của Node,
không cần sửa node.py.
"""
from dataclasses import replace

from .common import NIL, Block, sign, tx_root
from .execution import apply_txs
from .node import Node


def flip_byte(data: bytes) -> bytes:
    """
    Đảo 1 bit ở byte đầu tiên của chuỗi dữ liệu byte, giữ nguyên độ dài.
    Mục đích: Tạo ra dữ liệu 'gần đúng' nhưng sai mật mã (chữ ký hỏng, hash sai)
    để kiểm thử các guard thẩm định của node trung thực (Kịch bản T3).
    """
    return bytes([data[0] ^ 1]) + data[1:]


def short(h: bytes) -> str:
    """Rút gọn chuỗi byte thành 8 ký tự hex (hoặc 'NIL' nếu rỗng) để in log ngắn gọn."""
    return h.hex()[:8] or "NIL"


class ByzantineBase(Node):
    """
    Lớp cơ sở cho mọi Validator Byzantine (kế thừa từ Node).

    Vai trò:
    - Quản lý các tham số tấn công: attack_height, attack_round, groups chia rẽ mạng.
    - Cung cấp các công cụ ký lại thông điệp (sign_header), tạo khối hợp lệ (build_block).
    - Mở rộng hook `send_vote` và `send_proposal` để gửi riêng rẽ cho từng nhóm node (dsts).
    """
    is_byzantine = True

    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.attack_height, self.attack_round = 1, 0
        self.groups = None  # None: gửi cho mọi node; (left, right): chia rẽ gửi riêng cho 2 nhóm
        self.evidence = []  # Lưu vết các thông điệp tấn công đã ký để phục vụ đối chiếu kiểm thử

    def configure(self, height=1, round=0, groups=None):
        """
        Cấu hình thời điểm và mục tiêu tấn công trước khi bắt đầu mô phỏng:
        - height, round: Mốc thời gian thực hiện hành vi gian lận.
        - groups: Cặp danh sách index validator (nhóm trái, nhóm phải) để gửi tin mâu thuẫn.
        """
        if height < 1 or round < 0:
            raise ValueError("cần height >= 1 và round >= 0")
        self.attack_height, self.attack_round = height, round
        self.groups = None if groups is None else self._check_groups(groups)
        return self

    def _check_groups(self, groups):
        """Kiểm tra tính hợp lệ của hai nhóm phân vùng mạng (phải khác rỗng và không giao nhau)."""
        n = len(self.ctx["vals"])
        left, right = (tuple(sorted(set(g))) for g in groups)
        if not left or not right or set(left) & set(right):
            raise ValueError("hai nhóm phải khác rỗng và không giao nhau")
        if any(type(i) is not int or not 0 <= i < n for i in left + right):
            raise ValueError("nhóm chỉ chứa index validator trong [0, n)")
        return left, right

    def active(self):
        """Kiểm tra xem node hiện tại có đang ở đúng mốc height và round tấn công hay không."""
        return (self.height, self.round) == (self.attack_height, self.attack_round)

    def sign_header(self, hd):
        """Ký lại tiêu đề khối Header bằng khóa bí mật của chính node sau khi đã sửa đổi nội dung."""
        return replace(hd, sig=sign(self.kp, "HEADER:" + self.ctx["chain_id"], hd.body()))

    def build_block(self, txs):
        """Tạo một khối Block hợp lệ trên trạng thái hiện tại của node nhưng không biến đổi state gốc."""
        txs = tuple(txs)
        s, err = apply_txs(self.state, txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        if err:
            raise ValueError(err)
        return self.seal(txs, s.hash(), -1)

    def first_valid_tx(self):
        """Tìm giao dịch đầu tiên trong mempool có thể áp dụng thành công lên state hiện tại."""
        for tx in sorted(self.mempool, key=lambda t: (t.sender, t.nonce)):
            if apply_txs(self.state, (tx,), self.ctx["chain_id"], self.ctx["acct_pks"])[1] is None:
                return tx
        return None

    def send_to(self, dst, msg=None):
        """Gửi thông điệp tới một danh sách node đích cụ thể hoặc một node đơn lẻ.
        Tương thích cả hai chữ ký:
        - send_to(dst, msg) chuẩn từ Node (dst là int hoặc list/tuple các int)
        - send_to(msg, dsts) cũ trong ByzantineBase (msg là tuple thông điệp, dsts là list/tuple int)
        """
        if not callable(getattr(self.net, "send", None)):
            raise RuntimeError("Net chưa có send(src, dst, msg): chờ phần A")
        if isinstance(dst, (tuple, list)) and len(dst) >= 2 and isinstance(dst[0], str) and isinstance(msg, (tuple, list, set)):
            actual_msg, actual_dsts = dst, msg
        elif isinstance(dst, (list, tuple, set)):
            actual_msg, actual_dsts = msg, dst
        else:
            actual_msg, actual_dsts = msg, [dst]

        for d in sorted(actual_dsts):
            self.net.send(self.idx, d, actual_msg)

    def send_to_many(self, msg, dsts):
        """Phương thức bổ trợ gửi cùng một thông điệp tới nhiều node đích."""
        self.send_to(dsts, msg)

    def send_vote(self, vote, dsts=None):
        """Phát tán phiếu bầu: nếu dsts=None thì broadcast, ngược lại gửi riêng theo nhóm."""
        if dsts is None:
            return super().send_vote(vote)
        self.send_to(dsts, ("VOTE", vote))

    def send_proposal(self, block, dsts=None):
        """Phát tán đề xuất khối: nếu dsts=None thì broadcast, ngược lại gửi riêng theo nhóm."""
        if dsts is None:
            return super().send_proposal(block)
        self.send_to(dsts, ("PROPOSAL", block))


class Silent(ByzantineBase):
    """
    Hành vi Byzantine: Im lặng / Crashed (Mục 3 đề bài & Kịch bản T6).

    Chế độ hoạt động:
    - mode="all": Node hoàn toàn im lặng, không gửi bất kỳ thông điệp nào (mô phỏng node chết hẳn).
    - mode="proposer": Node vẫn tham gia bỏ phiếu bình thường như node honest, nhưng khi đến lượt
      làm Proposer thì cố tình KHÔNG đề xuất block.
      -> Mục đích: Kích hoạt đồng hồ TimeoutPropose của các node honest để kiểm tra cơ chế tăng Round (Liveness).
    """
    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.mode = "all"

    def configure(self, mode="all", **base):
        if mode not in ("all", "proposer"):
            raise ValueError("mode phải là 'all' hoặc 'proposer'")
        self.mode = mode
        return super().configure(**base)

    def start(self):
        self.log("BYZ_SILENT", mode=self.mode)
        if self.mode == "proposer":
            super().start()

    def propose(self):
        """Bỏ qua việc đề xuất khối khi tới lượt."""
        self.log("BYZ_SKIP_PROPOSE", height=self.height, round=self.round)

    def on_message(self, msg, src=None):
        """Chỉ tiếp nhận và phản hồi thông điệp nếu đang ở chế độ 'proposer'."""
        if self.mode == "proposer":
            super().on_message(msg, src)

    def on_timeout(self, key):
        """Chỉ xử lý timeout nếu ở chế độ 'proposer'."""
        if self.mode == "proposer":
            super().on_timeout(key)


class EquivocateVoter(ByzantineBase):
    """
    Hành vi Byzantine: Bỏ phiếu hai mặt (Equivocation Voter - Kịch bản T7).

    Chiến thuật tấn công:
    Tại slot tấn công (attack_height, attack_round), với mỗi giai đoạn (PREVOTE hoặc PRECOMMIT),
    node ký HAI phiếu bầu có nội dung mâu thuẫn nhau:
    - Nhóm trái nhận phiếu bầu cho Block A.
    - Nhóm phải nhận phiếu bầu cho Block B (hoặc NIL).
    -> Mục tiêu: Cố gắng làm hai nhóm honest đạt 2 Quorum khác nhau để gây rẽ nhánh chuỗi (Fork).
    Nhờ định lý giao điểm Quorum (Q1 ∩ Q2 >= f + 1), hệ thống honest vẫn luôn an toàn (Safety).
    """
    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.targets = None
        self.phases = ("PREVOTE", "PRECOMMIT")

    def configure(self, targets=None, phases=("PREVOTE", "PRECOMMIT"), **base):
        if targets is not None:
            targets = tuple(bytes.fromhex(t) if isinstance(t, str) else t for t in targets)
            if len(targets) != 2 or targets[0] == targets[1]:
                raise ValueError("targets phải là 2 hash khác nhau")
            if any(not isinstance(t, bytes) or len(t) not in (0, 32) for t in targets):
                raise ValueError("targets phải là NIL hoặc hash 32 byte (hex trong JSON)")
        if not phases or set(phases) - {"PREVOTE", "PRECOMMIT"}:
            raise ValueError("phases chỉ gồm PREVOTE/PRECOMMIT")
        self.targets, self.phases = targets, tuple(phases)
        return super().configure(**base)

    def cast(self, kind, target):
        key = (self.height, self.round, kind)
        a, b = self.targets or (target, NIL)
        if not self.active() or kind not in self.phases or key in self.signed or a == b:
            return super().cast(kind, target)
        self.signed[key] = a
        self.step = kind
        votes = (self.make_vote(kind, a), self.make_vote(kind, b))
        self.evidence.extend(votes)
        self.log("BYZ_EQUIVOCATE_VOTE", kind=kind, height=self.height, round=self.round,
                 a=short(a), b=short(b))
        for v, dsts in zip(votes, self.groups or (None, None)):
            self.send_vote(v, dsts)


class EquivocateProposer(ByzantineBase):
    """
    Hành vi Byzantine: Đề xuất hai mặt (Equivocation Proposer - Kịch bản T7).

    Chiến thuật tấn công:
    Khi tới lượt làm Proposer tại slot tấn công:
    - Ký và đề xuất Block A (rỗng) gửi cho nhóm trái.
    - Ký và đề xuất Block B (chứa 1 tx hợp lệ) gửi cho nhóm phải.
    Hai block này đều có chữ ký hợp lệ nhưng mang nội dung và mã băm khác nhau.
    -> Kiểm tra: Các node honest giữ đề xuất đến trước và phát hiện log EQUIVOCATION khi thấy block thứ hai.
    """
    def propose(self):
        if not self.active():
            return super().propose()
        tx = self.first_valid_tx()
        if tx is None:
            self.log("BYZ_SKIP", reason="no_valid_tx", height=self.height, round=self.round)
            return super().propose()
        a, b = self.build_block(()), self.build_block((tx,))
        self.evidence.extend((a, b))
        self.log("BYZ_EQUIVOCATE_PROPOSAL", height=self.height, round=self.round,
                 a=short(a.hash()), b=short(b.hash()))
        for blk, dsts in zip((a, b), self.groups or (None, None)):
            self.send_proposal(blk, dsts)


class InvalidBlock(ByzantineBase):
    """
    Hành vi Byzantine: Đề xuất khối sai quy cách (Invalid Block Proposer - Kịch bản T3).

    Chiến thuật tấn công:
    Proposer ký tiêu đề khối Header ĐÚNG bằng khóa bí mật của mình, nhưng cố tình làm sai
    đúng một trường thông tin để kiểm tra các chốt chặn (Guards) của node honest:
    - 'bad_parent': Parent hash sai, không nối tiếp ledger cũ.
    - 'bad_tx_root': Merkle root trong header không khớp với băm danh sách giao dịch.
    - 'bad_state_hash': Cam kết state_hash sai so với kết quả thực thi thực tế.
    - 'bad_tx_sig': Đưa giao dịch có chữ ký bị lỗi/giả mạo vào block.
    - 'replayed_tx': Đưa cùng một giao dịch 2 lần vào block (lần 2 vi phạm nonce).
    - 'bad_pol_round': Khai man pol_round >= round hiện tại (sai quy tắc đồng thuận).
    - 'fake_pol_round': Khai man có Polka ở round trước nhưng thực tế không có.
    """
    EXPECTED_REASON = {
        "bad_parent": "bad_parent",
        "bad_tx_root": "bad_tx_root",
        "bad_state_hash": "bad_state_hash",
        "bad_tx_sig": "bad_tx_sig",
        "replayed_tx": "bad_nonce",
        "bad_pol_round": "bad_pol_round",
        "fake_pol_round": None,
    }

    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.mode = "bad_state_hash"

    def configure(self, mode="bad_state_hash", **base):
        if mode not in self.EXPECTED_REASON:
            raise ValueError(f"mode không hỗ trợ: {mode}")
        self.mode = mode
        super().configure(**base)
        if mode == "fake_pol_round" and self.attack_round < 1:
            raise ValueError("fake_pol_round cần round >= 1 (pol_round = round - 1)")
        return self

    def on_request_body(self, block_hash, src):
        # An attacker must serve its intentionally invalid evidence, independently
        # of the honest Node cache which correctly removes invalid bodies.
        if src is not None:
            for block in self.evidence:
                if isinstance(block, Block) and block.hash() == block_hash:
                    self.send_to(src, ("BODY", (block_hash, block.txs)))
                    return
        super().on_request_body(block_hash, src)

    def propose(self):
        if not self.active():
            return super().propose()
        tx = self.first_valid_tx()
        if tx is None and self.mode in ("bad_tx_sig", "replayed_tx"):
            self.log("BYZ_SKIP", reason="no_valid_tx", height=self.height, round=self.round)
            return super().propose()
        good = self.build_block(() if tx is None else (tx,))
        hd, txs = good.header, good.txs
        if self.mode == "bad_parent":
            hd = replace(hd, parent=flip_byte(hd.parent))
        elif self.mode == "bad_tx_root":
            hd = replace(hd, tx_root=flip_byte(hd.tx_root))
        elif self.mode == "bad_state_hash":
            hd = replace(hd, state_hash=flip_byte(hd.state_hash))
        elif self.mode == "bad_tx_sig":
            txs = (replace(txs[0], sig=flip_byte(txs[0].sig)),)
            hd = replace(hd, tx_root=tx_root(txs))
        elif self.mode == "replayed_tx":
            txs = (txs[0], txs[0])
            hd = replace(hd, tx_root=tx_root(txs))
        elif self.mode == "bad_pol_round":
            hd = replace(hd, pol_round=self.round)
        else:  # fake_pol_round
            hd = replace(hd, pol_round=self.round - 1)
        bad = Block(self.sign_header(hd), txs)
        self.evidence.append(bad)
        self.log("BYZ_INVALID_BLOCK", mode=self.mode, height=self.height, round=self.round,
                 block=short(bad.hash()))
        self.send_proposal(bad)


class Replay(ByzantineBase):
    """
    Hành vi Byzantine: Phát lại thông điệp cũ (Replay Attack - Mục 3 đề bài & Kịch bản T2).

    Chiến thuật tấn công:
    - Lắng nghe và ghi lại các thông điệp mạng (`VOTE`, `PROPOSAL`) hợp lệ ở height tấn công.
    - Sau một khoảng thời gian ảo `delay`, phát lại NGUYÊN VẸN thông điệp đó ra mạng.
    -> Kiểm tra: Các node honest tuân thủ Quy tắc 7 và bộ đệm mempool/seen_tx_hashes sẽ nhận diện
       thông điệp trùng lặp và bỏ qua an toàn, không đếm 2 lần và không gây rối loạn đồng thuận.
    """
    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.kinds, self.delay, self.limit = ("VOTE", "PROPOSAL", "HEADER", "TX"), 100, 20
        self.recorded = []
        self._seen = set()

    def configure(self, kinds=("VOTE", "PROPOSAL", "HEADER", "TX"), delay=100, limit=20, **base):
        if set(kinds) - {"VOTE", "PROPOSAL", "HEADER", "BODY", "TX"} or delay < 0 or limit < 0:
            raise ValueError("kinds chỉ gồm VOTE/PROPOSAL/HEADER/BODY/TX; delay, limit >= 0")
        self.kinds, self.delay, self.limit = tuple(kinds), delay, limit
        return super().configure(**base)

    @staticmethod
    def msg_height(msg):
        return msg[1].header.height if msg[0] == "PROPOSAL" else getattr(msg[1], "height", 0)

    def on_message(self, msg, src=None):
        if (msg[0] in self.kinds and (self.msg_height(msg) or self.height) == self.attack_height
                and len(self.recorded) < self.limit and msg not in self.recorded):
            self.recorded.append(msg)
            self.net.set_timeout(self.idx, self.delay, ("BYZ_REPLAY", len(self.recorded) - 1))
        super().on_message(msg, src)

    def on_timeout(self, key):
        if key[0] != "BYZ_REPLAY":
            return super().on_timeout(key)
        msg = self.recorded[key[1]]
        self.evidence.append(msg)
        self.log("BYZ_REPLAY", type=msg[0], height=self.msg_height(msg))
        self.net.broadcast(self.idx, msg)


class Coalition:
    """Kế hoạch phối hợp tác chiến của liên minh Byzantine."""
    def __init__(self, left, right):
        self.left, self.right = tuple(sorted(left)), tuple(sorted(right))
        self.blocks = None


class ForkCoalition(ByzantineBase):
    """
    Liên minh Byzantine tấn công phá vỡ Safety (Thí nghiệm ranh giới Quorum):
    Được thiết kế cho thí nghiệm ngoài giả định (n=9, f=3 nhưng Q=6 < 2f+1=7):
    Cả nhóm Byzantine cùng phối hợp ký hai mặt cho cả 2 khối ở 2 phân vùng mạng để ép xảy ra FORK.
    """
    def configure(self, coalition, **base):
        base.setdefault("groups", (coalition.left, coalition.right))
        super().configure(**base)
        if self.attack_height != 1:
            raise ValueError("ForkCoalition chỉ hỗ trợ height 1")
        self.coalition = coalition
        return self

    def start(self):
        self.height, self.round = self.attack_height, self.attack_round
        self.log("BYZ_COALITION_START", height=self.height, round=self.round)
        if self.proposer(self.height, self.round) == self.name:
            tx = self.first_valid_tx()
            if tx is None:
                raise ValueError("ForkCoalition cần 1 tx hợp lệ trong mempool")
            a, b = self.build_block(()), self.build_block((tx,))
            self.coalition.blocks = (a, b)
            self.evidence.extend((a, b))
            self.log("BYZ_EQUIVOCATE_PROPOSAL", height=self.height, round=self.round,
                     a=short(a.hash()), b=short(b.hash()))
            for blk, dsts in zip((a, b), self.groups):
                self.send_proposal(blk, dsts)
        self.net.set_timeout(self.idx, 1, ("BYZ_COALITION_VOTE",))

    def on_timeout(self, key):
        if key != ("BYZ_COALITION_VOTE",):
            return
        if self.coalition.blocks is None:
            raise RuntimeError("không có proposer của nhóm ở slot tấn công")
        a, b = self.coalition.blocks
        for kind in ("PREVOTE", "PRECOMMIT"):
            for blk, dsts in zip((a, b), self.groups):
                v = self.make_vote(kind, blk.hash())
                self.evidence.append(v)
                self.send_vote(v, dsts)
        self.log("BYZ_EQUIVOCATE_VOTE", kind="PREVOTE+PRECOMMIT", height=self.height,
                 round=self.round, a=short(a.hash()), b=short(b.hash()))

    def on_message(self, msg, src=None):
        return


# Bảng tra cứu ánh xạ tên hành vi sang lớp đối tượng tương ứng
REGISTRY = {
    "honest": Node,
    "silent": Silent,
    "equivocate_voter": EquivocateVoter,
    "equivocate_proposer": EquivocateProposer,
    "invalid_block": InvalidBlock,
    "replay": Replay,
    "fork_coalition": ForkCoalition,
}


def make_node(behavior, idx, ctx, kp, **params):
    """
    Factory Pattern: Khởi tạo validator node theo tên hành vi cấu hình trong JSON.
    Cho phép cấu hình linh hoạt các kịch bản thử nghiệm Byzantine trước khi khởi động mạng.
    """
    if behavior not in REGISTRY:
        raise ValueError(f"hành vi không tồn tại: {behavior!r}; có: {sorted(REGISTRY)}")
    node = REGISTRY[behavior](idx, ctx, kp)
    if params:
        if not isinstance(node, ByzantineBase):
            raise ValueError("node honest không nhận tham số tấn công")
        node.configure(**params)
    return node
