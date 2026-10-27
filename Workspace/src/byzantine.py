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
    """Đổi 1 bit ở byte đầu, giữ nguyên độ dài (dữ liệu 'gần đúng' nhưng sai)."""
    return bytes([data[0] ^ 1]) + data[1:]


def short(h: bytes) -> str:
    return h.hex()[:8] or "NIL"


class ByzantineBase(Node):
    """Phần dùng chung: tham số tấn công + các hàm tạo/gửi thông điệp.

    Dùng lại hook của Node (B): make_vote, seal, send_vote, send_proposal. Ở đây chỉ mở
    rộng send_vote/send_proposal thêm tham số dsts để gửi riêng từng nhóm; dsts=None thì
    gọi đúng bản của Node. Khi A đổi sang HEADER/BODY chỉ phải sửa ở đây.
    """

    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.attack_height, self.attack_round = 1, 0
        self.groups = None  # None: gửi cho mọi node; (trái, phải): gửi riêng hai nhóm
        self.evidence = []  # mọi thông điệp tấn công đã ký, để test/báo cáo kiểm lại

    # ----- cấu hình: factory gọi TRƯỚC START (start_round gọi propose() ngay) -----
    def configure(self, height=1, round=0, groups=None):
        if height < 1 or round < 0:
            raise ValueError("cần height >= 1 và round >= 0")
        self.attack_height, self.attack_round = height, round
        self.groups = None if groups is None else self._check_groups(groups)
        return self

    def _check_groups(self, groups):
        n = len(self.ctx["vals"])
        left, right = (tuple(sorted(set(g))) for g in groups)
        if not left or not right or set(left) & set(right):
            raise ValueError("hai nhóm phải khác rỗng và không giao nhau")
        if any(type(i) is not int or not 0 <= i < n for i in left + right):
            raise ValueError("nhóm chỉ chứa index validator trong [0, n)")
        return left, right

    def active(self):
        return (self.height, self.round) == (self.attack_height, self.attack_round)

    # ----- tạo thông điệp, ký bằng khóa của chính mình -----
    # make_vote(kind, target) dùng nguyên của Node.
    def sign_header(self, hd):
        """Ký lại header sau khi đã sửa một trường (bản sao mới, không sửa tại chỗ)."""
        return replace(hd, sig=sign(self.kp, "HEADER:" + self.ctx["chain_id"], hd.body()))

    def build_block(self, txs):
        """Block HỢP LỆ (pol_round=-1) trên state hiện tại của chính node; state gốc không đổi."""
        txs = tuple(txs)
        s, err = apply_txs(self.state, txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        if err:
            raise ValueError(err)
        return self.seal(txs, s.hash(), -1)

    def first_valid_tx(self):
        """Tx đầu tiên trong mempool áp dụng được lên state hiện tại; None nếu không có."""
        for tx in sorted(self.mempool, key=lambda t: (t.sender, t.nonce)):
            if apply_txs(self.state, (tx,), self.ctx["chain_id"], self.ctx["acct_pks"])[1] is None:
                return tx
        return None

    # ----- gửi: luôn đi qua mạng -----
    def send_to(self, msg, dsts):
        """Gửi riêng từng đích. Cần Net.send của A (cùng pipeline với broadcast)."""
        if not callable(getattr(self.net, "send", None)):
            raise RuntimeError("Net chưa có send(src, dst, msg): chờ phần A")
        for dst in sorted(dsts):
            self.net.send(self.idx, dst, msg)

    def send_vote(self, vote, dsts=None):
        if dsts is None:
            return super().send_vote(vote)
        self.send_to(("VOTE", vote), dsts)

    def send_proposal(self, block, dsts=None):
        # TODO(A): khi có giao thức HEADER -> REQUEST_BODY -> BODY thì chỉ sửa ở đây
        if dsts is None:
            return super().send_proposal(block)
        self.send_to(("PROPOSAL", block), dsts)


class Silent(ByzantineBase):
    """Im lặng.
    mode="all": không gửi gì, không phản ứng gì (node chết ngay từ đầu).
    mode="proposer": vẫn bỏ phiếu như honest nhưng không bao giờ đề xuất block.

    Không làm bằng cách cho cast() thành pass: Node.run() gọi cast() rồi `continue`,
    nếu self.step không đổi thì vòng while lặp vô hạn.
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
        self.log("BYZ_SKIP_PROPOSE", height=self.height, round=self.round)

    def on_message(self, msg):
        if self.mode == "proposer":
            super().on_message(msg)

    def on_timeout(self, key):
        if self.mode == "proposer":
            super().on_timeout(key)


class EquivocateVoter(ByzantineBase):
    """Tại slot tấn công, với mỗi phase trong `phases`: ký HAI vote khác target cho cùng
    (height, round, phase). Ngoài slot tấn công thì bỏ phiếu như honest.

    targets=None: nhóm trái nhận target mà FSM honest chọn, nhóm phải nhận NIL.
    groups=None: phát cả hai vote cho mọi node (receiver nào nhận đủ cả hai sẽ log
    EQUIVOCATION và chỉ đếm vote đến trước).
    """

    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.targets = None
        self.phases = ("PREVOTE", "PRECOMMIT")

    def configure(self, targets=None, phases=("PREVOTE", "PRECOMMIT"), **base):
        if targets is not None:
            targets = tuple(targets)
            if len(targets) != 2 or targets[0] == targets[1]:
                raise ValueError("targets phải là 2 hash khác nhau")
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
        self.step = kind  # bắt buộc, nếu không Node.run() lặp mãi ở bước cũ
        votes = (self.make_vote(kind, a), self.make_vote(kind, b))
        self.evidence.extend(votes)
        self.log("BYZ_EQUIVOCATE_VOTE", kind=kind, height=self.height, round=self.round,
                 a=short(a), b=short(b))
        for v, dsts in zip(votes, self.groups or (None, None)):
            self.send_vote(v, dsts)


class EquivocateProposer(ByzantineBase):
    """Khi tới lượt đề xuất ở slot tấn công: ký HAI block hợp lệ khác nhau cho cùng
    (height, round): A rỗng, B chứa 1 tx hợp lệ. Hai block rỗng sẽ trùng hash vì
    Block.hash() chỉ băm nội dung (height, parent, state_hash, tx_root), không băm chữ ký.

    groups=None: phát A rồi B cho mọi node (độ trễ ngẫu nhiên quyết định ai thấy cái nào
    trước); groups=(L, R): A cho L, B cho R.
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
    """Khi tới lượt đề xuất ở slot tấn công: gửi block có chữ ký header ĐÚNG nhưng nội dung
    sai đúng MỘT chỗ (mode), để kiểm từng guard trong Node.on_proposal / Node._check."""
    # mode -> lý do node honest phải ghi khi từ chối (None: không REJECT, chỉ không prevote)
    EXPECTED_REASON = {
        "bad_parent": "bad_parent",
        "bad_tx_root": "bad_tx_root",        # bị chặn ngay ở cổng on_proposal
        "bad_state_hash": "bad_state_hash",
        "bad_tx_sig": "bad_tx_sig",
        "replayed_tx": "bad_nonce",          # cùng 1 tx 2 lần trong block: lần 2 sai nonce
        "bad_pol_round": "bad_pol_round",    # pol_round >= round: không thể có polka ở đó
        "fake_pol_round": None,              # khai có polka ở round trước nhưng thật ra không có
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
            hd = replace(hd, tx_root=tx_root(txs))  # root khớp body để lỗi rơi đúng vào tx
        elif self.mode == "replayed_tx":
            txs = (txs[0], txs[0])
            hd = replace(hd, tx_root=tx_root(txs))
        elif self.mode == "bad_pol_round":
            hd = replace(hd, pol_round=self.round)
        else:  # fake_pol_round: block hợp lệ, chỉ khai man bằng chứng polka
            hd = replace(hd, pol_round=self.round - 1)
        bad = Block(self.sign_header(hd), txs)  # ký lại: chữ ký header vẫn hợp lệ
        self.evidence.append(bad)
        self.log("BYZ_INVALID_BLOCK", mode=self.mode, height=self.height, round=self.round,
                 block=short(bad.hash()))
        self.send_proposal(bad)


class Replay(ByzantineBase):
    """Ghi lại thông điệp nhận được thuộc height tấn công rồi phát lại NGUYÊN VẸN (cùng
    chữ ký) sau `delay` đơn vị thời gian ảo, tối đa `limit` thông điệp. Ngoài ra vẫn xử lý
    như honest. Mỗi thông điệp chỉ ghi một lần nên tin phát lại quay về không bị phát tiếp."""

    def __init__(self, idx, ctx, kp):
        super().__init__(idx, ctx, kp)
        self.kinds, self.delay, self.limit = ("VOTE", "PROPOSAL"), 100, 20
        self.recorded = []
        self._seen = set()  # chỉ để hỏi "đã ghi chưa", không duyệt nên không ảnh hưởng tất định

    def configure(self, kinds=("VOTE", "PROPOSAL"), delay=100, limit=20, **base):
        if set(kinds) - {"VOTE", "PROPOSAL"} or delay < 0 or limit < 0:
            raise ValueError("kinds chỉ gồm VOTE/PROPOSAL; delay, limit >= 0")
        self.kinds, self.delay, self.limit = tuple(kinds), delay, limit
        return super().configure(**base)

    @staticmethod
    def msg_height(msg):
        return msg[1].header.height if msg[0] == "PROPOSAL" else msg[1].height

    def on_message(self, msg):
        if (msg[0] in self.kinds and self.msg_height(msg) == self.attack_height
                and len(self.recorded) < self.limit and msg not in self._seen):
            self._seen.add(msg)
            self.recorded.append(msg)
            self.net.set_timeout(self.idx, self.delay, ("BYZ_REPLAY", len(self.recorded) - 1))
        super().on_message(msg)

    def on_timeout(self, key):
        if key[0] != "BYZ_REPLAY":
            return super().on_timeout(key)
        msg = self.recorded[key[1]]
        self.evidence.append(msg)
        self.log("BYZ_REPLAY", type=msg[0], height=self.msg_height(msg))
        self.net.broadcast(self.idx, msg)


class Coalition:
    """Kế hoạch chung của nhóm Byzantine (adversary được phép phối hợp với nhau)."""

    def __init__(self, left, right):
        self.left, self.right = tuple(sorted(left)), tuple(sorted(right))
        self.blocks = None  # (A, B) do thành viên là proposer tạo


class ForkCoalition(ByzantineBase):
    """Thí nghiệm ngoài giả định: cả nhóm Byzantine ký HAI phía ở slot tấn công.
    Proposer của nhóm gửi block A cho nhóm trái, B cho nhóm phải; mọi thành viên ký
    PREVOTE và PRECOMMIT cho A gửi trái, cho B gửi phải. Không chạy FSM honest, nên
    chỉ hỗ trợ height 1 (không theo dõi ledger)."""

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
        # đợi 1 đơn vị: mọi START ở t=0 đã chạy xong nên proposer chắc chắn đã tạo A, B
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

    def on_message(self, msg):
        return


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
    """Factory gợi ý cho E: tạo node theo tên hành vi, cấu hình xong rồi mới START."""
    if behavior not in REGISTRY:
        raise ValueError(f"hành vi không tồn tại: {behavior!r}; có: {sorted(REGISTRY)}")
    node = REGISTRY[behavior](idx, ctx, kp)
    if params:
        if not isinstance(node, ByzantineBase):
            raise ValueError("node honest không nhận tham số tấn công")
        node.configure(**params)
    return node
