"""Một validator: máy trạng thái Tendermint tối giản (propose/prevote/precommit/commit),
kết hợp lõi đồng thuận (phần B) và tầng dữ liệu/đồng bộ (phần D).

Bản này bao gồm đầy đủ:
  * 7 quy tắc vàng Tendermint (Luật 1-7: không ký 2 phiếu, quy tắc khóa block, mở khóa qua polka).
  * Giao thức 2 bước phát tán khối (Mục 6 đề bài: Header trước -> Request Body -> Body).
  * Cơ chế nhảy round (Round skip) khi thấy f+1 validator ở round cao hơn.
  * Đệm thông điệp height tương lai có giới hạn bộ nhớ (chống tấn công cạn kiệt tài nguyên).
  * Đồng bộ bắt kịp trạng thái (Catch-up Sync) bằng CommitCertificate.
"""
from collections import Counter

from .common import (
    NIL,
    Block,
    CommitCertificate,
    Header,
    SyncReq,
    SyncResp,
    Vote,
    H,
    encode,
    sign,
    tx_root,
    verify,
)
from .execution import State, apply_tx, apply_txs, valid_tx_fields

GENESIS = H(b"genesis")
KINDS = ("PREVOTE", "PRECOMMIT")


class Node:
    """
    Đại diện cho một Validator Node chạy giao thức đồng thuận Tendermint BFT.
    """
    is_byzantine = False

    def __init__(self, idx, ctx, kp):
        """
        Khởi tạo trạng thái nội bộ của validator:
        - idx: Chỉ số của node (0, 1, ..., n-1).
        - ctx: Ngữ cảnh mạng (chain_id, danh sách validator vals, f, vpks, timeouts, v.v.).
        - kp: Cặp khóa bí mật/công khai Ed25519 của validator này.
        """
        self.idx, self.ctx, self.kp = idx, ctx, kp
        self.name = ctx["vals"][idx]
        self.net = ctx["net"]
        self.Q = 2 * ctx["f"] + 1                     # Ngưỡng Quorum tối thiểu để đạt đồng thuận (2f + 1)
        self.max_ahead = ctx.get("max_ahead_h", 3)    # Cửa sổ nhận tin: tối đa 3 height phía trước
        self.max_round = ctx.get("max_round", 1000)   # Cửa sổ round phía trước, không phải trần vòng đời
        self.state = State()                          # Máy trạng thái Key-Value của ứng dụng
        self.ledger = []                              # Danh sách các block đã được chốt (Finalized ledger)
        self.certificates = {}                        # Lưu trữ CommitCertificate cho từng height: height -> cert
        self.mempool = []                             # Hàng đợi các giao dịch chờ đưa vào block
        self.seen_tx_hashes = set()                   # Bảng băm khử trùng lặp tx trong O(1) chống replay
        self.done = False                             # Đánh dấu đã hoàn thành toàn bộ heights mục tiêu
        self.height, self.round, self.step = 0, 0, "PROPOSE"
        self.signed = {}                              # (h, r, kind) -> block_hash đã ký (Thực thi Luật 1 & 2)
        self.locked = None                            # (block_hash, round): Block đang bị khóa theo Luật 4 & 5

        # Dữ liệu nội bộ của height hiện tại (được làm mới khi bắt đầu height mới)
        self.proposals, self.blocks, self.checked = {}, {}, {}
        self.scheduled = set()
        self.peer_round = {}                          # voter -> round cao nhất từng thấy ở height này

        # Dữ liệu đệm sống qua nhiều height
        self.votes = {}                               # (h, r, kind) -> {voter: Vote}
        self.future = {}                              # (h, r) -> proposal đầu tiên của height tương lai
        self.future_blocks = {}                       # (h, block_hash) -> thân MỌI proposal hợp lệ đến sớm
        self.bodies = {}                              # block_hash -> tuple of txs (lưu thân block do chính mình đề xuất)
        self.future_headers = []                      # Danh sách (header, source) của height tương lai
        self.pending_headers = {}                     # hash -> header đã duyệt hợp lệ, đang chờ tải body
        self.requested_bodies = set()                 # Tập block_hash đã gửi yêu cầu tải body (tránh hỏi trùng)
        self.proofs = {}                             # (height, round, block_hash) -> PREVOTE certificate
        self.sync_pending = {}                       # block_hash -> verified commit certificate

    # ----- TIỆN ÍCH HỆ THỐNG VÀ VÒNG ĐỜI -----
    def log(self, ev, **kw):
        """Chuyển tiếp bản ghi sự kiện tới bộ mô phỏng mạng để ghi nhật ký."""
        self.net.log(self.name, ev, **kw)

    def last_hash(self):
        """Lấy mã băm của khối gần nhất trong ledger làm parent cho khối mới (hoặc GENESIS nếu là block đầu)."""
        return self.ledger[-1].hash() if self.ledger else GENESIS

    def proposer(self, h, r):
        """Thuật toán chọn Proposer tất định theo cơ chế Round-Robin: (h + r) % n."""
        v = self.ctx["vals"]
        return v[(h + r) % len(v)]

    def in_window(self, h, r):
        """Kiểm tra thông điệp có nằm trong cửa sổ đồng thuận hợp lệ hay không (chống tin rác quá xa)."""
        return (type(h) is int and type(r) is int
                and self.height <= h <= self.height + self.max_ahead
                and 0 <= r <= self.round + self.max_round)

    def start(self):
        """Khởi động validator bắt đầu từ Height 1."""
        self.start_height(1)

    def start_height(self, h):
        """
        Bắt đầu một Height mới:
        1. Kiểm tra nếu đã vượt quá số height mục tiêu -> đánh dấu hoàn thành (self.done = True).
        2. Đặt lại round = 0, giải phóng khóa (self.locked = None).
        3. Nạp lại các proposals, blocks, votes tương lai đã nhận sớm ở height này.
        4. Bắt đầu Round 0 và xử lý các Header tương lai đang chờ.
        """
        if h > self.ctx["heights"]:
            self.done = True
            self.log("DONE", height=h - 1)
            return
        self.height, self.locked = h, None
        self.proposals, self.blocks, self.checked = {}, {}, {}

        # Nạp proposal đến sớm TRƯỚC khi start_round để run() thấy ngay
        for (hh, rr), fb in sorted(self.future.items()):
            if hh == h:
                self.proposals[(hh, rr)] = fb
        for (hh, bh), fb in sorted(self.future_blocks.items()):
            if hh == h:
                self.blocks[bh] = fb
        self.future = {k: v for k, v in self.future.items() if k[0] > h}
        self.future_blocks = {k: v for k, v in self.future_blocks.items() if k[0] > h}

        # Dựng lại peer_round từ phiếu đã đến sớm
        self.peer_round = {}
        for (hh, rr, _), vs in self.votes.items():
            if hh == h:
                for voter in vs:
                    self.peer_round[voter] = max(self.peer_round.get(voter, -1), rr)

        self.pending_headers, self.requested_bodies = {}, set()
        self.scheduled = set()
        self.start_round(max(0, self.skip_target()))

        # Xử lý các Header đã nhận sớm ở height này
        ready = [(hd, src) for hd, src in self.future_headers if hd.height == h]
        self.future_headers = [(hd, src) for hd, src in self.future_headers if hd.height > h]
        for hd, src in ready:
            self.on_header(hd, src)
        if ready:
            self.run()

    def start_round(self, r):
        """
        Bắt đầu một Round đồng thuận mới:
        1. Cập nhật round = r, chuyển bước về 'PROPOSE'.
        2. Nếu mình là Proposer của round này -> tiến hành tạo và phát tán block đề xuất.
        3. Thiết lập các đồng hồ đếm ngược: TimeoutPropose và TimeoutRound (lưới an toàn).
        4. Kích hoạt cỗ máy trạng thái run().
        """
        self.round, self.step = r, "PROPOSE"
        self.log("ROUND_START", height=self.height, round=r)
        if self.proposer(self.height, r) == self.name:
            self.propose()
        self.set_timeout("PROPOSE")
        self.set_timeout("ROUND", 3)   # Lưới an toàn: dù thiếu phiếu cũng không đứng yên mãi
        self.run()

    def timeout_len(self, r):
        """Tính thời lượng timeout tăng dần theo round: base_timeout + r * timeout_inc."""
        return self.ctx["base_timeout"] + r * self.ctx["timeout_inc"]

    def set_timeout(self, kind, mult=1):
        """Đăng ký sự kiện timeout với mạng mô phỏng sim.py."""
        key = (kind, self.height, self.round)
        if key in self.scheduled:
            return
        self.scheduled.add(key)
        self.net.set_timeout(self.idx, mult * self.timeout_len(self.round), key)

    # ----- CƠ CHẾ NHẢY ROUND (ROUND SKIPPING) -----
    def skip_target(self):
        """
        Xác định round lớn nhất mà ít nhất f+1 validator khác nhau đã đạt tới.
        Mục đích: Nếu có >= f+1 node đã sang round cao hơn, node hiện tại không thể đạt
        Quorum ở round cũ nữa, cần nhảy nhanh để duy trì tính Liveness.
        """
        rs = sorted(self.peer_round.values(), reverse=True)
        f = self.ctx["f"]
        return rs[f] if len(rs) > f else -1

    def maybe_skip_round(self):
        """Kiểm tra và thực hiện nhảy round nếu điều kiện skip_target thỏa mãn."""
        t = self.skip_target()
        if t > self.round:
            self.log("ROUND_SKIP", height=self.height, frm=self.round, to=t)
            self.start_round(t)
            return True
        return False

    # ----- KIỂM TRA BẰNG CHỨNG KHÓA (PROOF-OF-LOCK / POLKA) -----
    def polka(self, h, r, bh):
        """Kiểm tra xem block `bh` có đạt được Quorum (>= Q) phiếu PREVOTE ở (h, r) hay không."""
        pv = self.votes.get((h, r, "PREVOTE"), {})
        return ((h, r, bh) in self.proofs
                or sum(1 for v in pv.values() if v.block_hash == bh) >= self.Q)

    def polka_votes(self, h, r, bh):
        proof = self.proofs.get((h, r, bh))
        if proof is not None:
            return proof
        return tuple(v for _, v in sorted(self.votes.get((h, r, "PREVOTE"), {}).items())
                     if v.block_hash == bh)

    def on_polka(self, votes):
        """Accept evidence atomically; an asserted pol_round alone is never trusted."""
        if not isinstance(votes, (tuple, list)) or not votes or len(votes) > len(self.ctx["vals"]):
            return self.log("REJECT", reason="bad_polka", height=self.height)
        first = votes[0]
        if not isinstance(first, Vote) or not self.in_window(first.height, first.round):
            return
        signers = set()
        for vote in votes:
            if (not isinstance(vote, Vote) or not isinstance(vote.voter, str)
                    or not isinstance(vote.block_hash, bytes) or len(vote.block_hash) != 32
                    or vote.kind != "PREVOTE"
                    or (vote.height, vote.round, vote.block_hash)
                    != (first.height, first.round, first.block_hash)
                    or vote.voter in signers or vote.voter not in self.ctx["vpks"]
                    or not verify(self.ctx["vpks"][vote.voter], "VOTE:" + self.ctx["chain_id"],
                                  vote.body(), vote.sig)):
                return self.log("REJECT", reason="bad_polka", height=first.height)
            signers.add(vote.voter)
        if first.block_hash == NIL or len(signers) < self.Q:
            return self.log("REJECT", reason="bad_polka", height=first.height)
        self.proofs[(first.height, first.round, first.block_hash)] = tuple(votes)
        self.log("POLKA", height=first.height, round=first.round,
                 block=first.block_hash.hex()[:8], signers=len(signers))

    def best_polka(self):
        """
        Tìm Polka ở round cao nhất (< round hiện tại) cho một block hợp lệ mà node đã có thân.
        Phục vụ Proposer đề xuất lại block đã đạt Polka theo Quy tắc 5.
        """
        best = None
        for (hh, rr, kind), vs in sorted(self.votes.items()):   # round tăng dần
            if hh != self.height or kind != "PREVOTE" or rr >= self.round:
                continue
            for t, c in sorted(Counter(v.block_hash for v in vs.values()).items()):
                if t != NIL and c >= self.Q and t in self.blocks and self.check_block(self.blocks[t]):
                    best = (t, rr)
        for (hh, rr, bh) in sorted(self.proofs):
            if (hh == self.height and rr < self.round and bh in self.blocks
                    and self.check_block(self.blocks[bh]) and (best is None or rr > best[1])):
                best = (bh, rr)
        return best

    # ----- ĐỀ XUẤT BLOCK (PROPOSAL) -----
    def propose(self):
        """
        Nhiệm vụ của Proposer tại bước PROPOSE:
        1. Kiểm tra nếu có Polka ở round trước: Đề xuất lại khối đó kèm trường `pol_round`.
        2. Nếu không: Đóng gói các giao dịch từ mempool thành một khối mới toanh (`pol_round = -1`).
        3. Ghi log `PROPOSE` và phát tán qua giao thức 2 bước bằng `send_proposal`.
        """
        pol = self.best_polka()
        if pol:
            t, pr = pol
            old = self.blocks[t]
            blk = self.seal(old.txs, old.header.state_hash, pr)   # Giữ nguyên nội dung giao dịch và state_hash
            self.log("REPROPOSE", height=self.height, round=self.round,
                     pol_round=pr, block=t.hex()[:8])
            self.net.broadcast(self.idx, ("POLKA", self.polka_votes(self.height, pr, t)))
        else:
            blk = self.make_block()
        self.log("PROPOSE", height=self.height, round=self.round,
                 pol_round=blk.header.pol_round, txs=len(blk.txs))
        self.send_proposal(blk)

    def make_block(self):
        """Lựa chọn các giao dịch hợp lệ từ mempool và đóng gói thành khối mới."""
        chosen, s = [], self.state.copy()
        for tx in sorted(self.mempool, key=lambda t: (t.sender, t.nonce)):
            if len(chosen) >= self.ctx["max_txs"]:
                break
            trial = s.copy()
            if apply_tx(trial, tx, self.ctx["chain_id"], self.ctx["acct_pks"]) is None:
                s = trial
                chosen.append(tx)
        return self.seal(chosen, s.hash(), -1)

    def seal(self, txs, state_hash, pol_round):
        """Tạo đối tượng Header và Block hoàn chỉnh kèm chữ ký số Ed25519 của proposer."""
        hd = Header(self.height, self.round, pol_round, self.last_hash(),
                    state_hash, tx_root(txs), self.name)
        hd = Header(*hd.body(), sig=sign(self.kp, "HEADER:" + self.ctx["chain_id"], hd.body()))
        return Block(hd, tuple(txs))

    def send_proposal(self, blk):
        """
        Giao thức 2 bước phát tán khối (Mục 6 đề bài):
        1. Proposer giữ phần thân (txs) cục bộ tại bộ nhớ `self.bodies`.
        2. Proposer tự nạp proposal của chính mình vào bộ đệm cục bộ.
        3. Chỉ phát tán duy nhất `Header` qua mạng: `broadcast("HEADER", blk.header)`.
           Bên nhận sau khi thẩm định Header sẽ gửi yêu cầu xin tải Body sau.
        """
        self.bodies[blk.hash()] = blk.txs
        self.on_proposal(blk)  # Proposer tự thẩm định và nạp khối của chính mình
        self.net.broadcast(self.idx, ("HEADER", blk.header))

    # ----- BỎ PHIẾU (VOTING HOOKS) -----
    def make_vote(self, kind, target):
        """Tạo đối tượng phiếu bầu Vote hợp lệ kèm chữ ký số dưới miền 'VOTE:chain_id'."""
        v = Vote(kind, self.height, self.round, target, self.name)
        return Vote(*v.body(), sig=sign(self.kp, "VOTE:" + self.ctx["chain_id"], v.body()))

    def send_vote(self, v):
        """Phát tán phiếu bầu tới toàn thể các validator qua mạng mô phỏng."""
        self.net.broadcast(self.idx, ("VOTE", v))

    # ----- BỘ TIẾP NHẬN VÀ ĐIỀU PHỐI THÔNG ĐIỆP -----
    def on_message(self, msg, src=None):
        """
        Hàm tiếp nhận thông điệp tổng từ mạng mô phỏng sim.py:
        Điều phối tới các hàm xử lý chuyên trách theo loại gói tin:
        - SYNC_REQ: Yêu cầu đồng bộ từ peer bị tụt lại.
        - REQUEST_BODY: Yêu cầu tải thân block.
        - HEADER: Tiêu đề khối đề xuất.
        - BODY: Thân khối đề xuất.
        - VOTE: Phiếu bầu PREVOTE / PRECOMMIT.
        - TX: Giao dịch lan truyền trong mạng.
        - SYNC_RESP: Phản hồi dữ liệu khối đồng bộ.
        """
        kind, payload = msg
        # Kể cả node đã hoàn thành vẫn phải tiếp tục phục vụ đồng bộ cho peer đến muộn
        if kind == "SYNC_REQ":
            return self.on_sync_request(payload)
        if kind == "REQUEST_BODY":
            return self.on_request_body(payload, src)
        if self.done:
            return
        if kind == "PROPOSAL":
            self.on_proposal(payload)
        elif kind == "HEADER":
            self.on_header(payload, src)
        elif kind == "BODY":
            self.on_body(payload)
        elif kind == "VOTE":
            self.on_vote(payload)
        elif kind == "POLKA":
            self.on_polka(payload)
        elif kind == "TX":
            self.on_tx(payload)
        elif kind == "SYNC_RESP":
            self.on_sync_response(payload)
        elif kind == "SYNC_HEADERS":
            self.on_sync_headers(payload, src)

        # Kiểm tra nhảy round và chạy tiếp cỗ máy trạng thái
        if not self.maybe_skip_round():
            self.run()

    # ----- XỬ LÝ GIAO DỊCH VÀ ĐỒNG BỘ CATCH-UP (PHẦN D) -----
    def on_tx(self, tx, gossip=True):
        """
        Xử lý giao dịch lan truyền (Tx Gossip):
        1. Khử trùng lặp tx trong O(1) qua `seen_tx_hashes`.
        2. Thẩm định tính hợp lệ: Người gửi tồn tại, chữ ký số đúng domain, đúng namespace `sender/`.
           Nếu vi phạm -> ghi log `REJECT` kèm lý do (Kịch bản T3).
        3. Thêm vào mempool và phát tán tiếp cho các node khác.
        """
        if not valid_tx_fields(tx):
            return self.log("REJECT", reason="bad_tx_format", height=self.height)
        tx_hash = H(encode(tx.body()))
        if tx_hash in self.seen_tx_hashes:
            return

        pk = self.ctx["acct_pks"].get(tx.sender)
        if pk is None:
            return self.log("REJECT", reason="unknown_sender", sender=tx.sender, nonce=tx.nonce)
        if not verify(pk, "TX:" + self.ctx["chain_id"], tx.body(), tx.sig):
            return self.log("REJECT", reason="bad_tx_sig", sender=tx.sender, nonce=tx.nonce)
        if "/" in tx.sender or tx.key.partition("/")[0] != tx.sender:
            return self.log("REJECT", reason="not_owner", sender=tx.sender, nonce=tx.nonce)
        if tx.nonce <= self.state.nonces.get(tx.sender, 0):
            return self.log("REJECT", reason="bad_nonce", sender=tx.sender, nonce=tx.nonce)

        self.seen_tx_hashes.add(tx_hash)
        self.mempool.append(tx)
        self.log("TX_RECEIVED", sender=tx.sender, nonce=tx.nonce)
        if gossip:
            self.net.broadcast(self.idx, ("TX", tx))

    def request_sync(self):
        """
        Chủ động phát yêu cầu đồng bộ khối (Sync Request) khi phát hiện cả một round trôi qua
        mà không chốt được block (có thể mạng đã chốt ở height này mà mình bị lỡ gói tin).
        """
        req = SyncReq(requester=self.name, from_height=self.height,
                      to_height=self.height + self.max_ahead)
        self.log("SYNC_REQUEST", height=req.from_height, to=req.to_height)
        self.net.broadcast(self.idx, ("SYNC_REQ", req))

    def on_sync_request(self, req):
        """
        Xử lý khi nhận được yêu cầu đồng bộ từ peer khác:
        Trích xuất các khối đã finalize kèm CommitCertificate trong ledger và gửi phản hồi `SYNC_RESP`.
        """
        vals = self.ctx["vals"]
        if req.requester not in vals or req.requester == self.name:
            return
        lo = max(1, req.from_height)
        hi = min(req.to_height, len(self.ledger), lo + self.max_ahead)
        chain_data = tuple((self.ledger[h - 1].header, self.certificates[h])
                           for h in range(lo, hi + 1) if h in self.certificates)
        if chain_data:
            self.send_to(vals.index(req.requester), ("SYNC_HEADERS", chain_data))

    def certificate_error(self, cert, h, bh):
        if cert.height != h or cert.block_hash != bh or type(cert.round) is not int or cert.round < 0:
            return "cert_mismatch"
        if not set(cert.signatures) <= set(self.ctx["vals"]):
            return "unknown_signer"
        if len(cert.signatures) < self.Q:
            return "insufficient_cert_sigs"
        for voter, sig in sorted(cert.signatures.items()):
            body = Vote("PRECOMMIT", h, cert.round, bh, voter).body()
            if not verify(self.ctx["vpks"][voter], "VOTE:" + self.ctx["chain_id"], body, sig):
                return "invalid_cert_sig"
        return None

    def on_sync_headers(self, items, src):
        """Authenticate finalized headers before requesting any transaction bodies."""
        for hd, cert in items[:self.max_ahead + 1]:
            if not self.height <= hd.height <= self.height + self.max_ahead:
                continue
            bh = Block(hd).hash()
            error = self.certificate_error(cert, hd.height, bh)
            if error:
                self.log("REJECT_SYNC", reason=error, height=hd.height)
                continue
            pk = self.ctx["vpks"].get(hd.proposer)
            if (pk is None or hd.proposer != self.proposer(hd.height, hd.round)
                    or not (-1 <= hd.pol_round < hd.round)
                    or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig)):
                self.log("REJECT_SYNC", reason="invalid_header", height=hd.height)
                continue
            self.sync_pending[bh] = cert
            self.on_header(hd, src)
            if hd.height == self.height and bh in self.bodies:
                self.on_body((bh, self.bodies[bh]))

    def send_to(self, dst, msg):
        """Gửi thông điệp unicast tới node `dst` thông qua bộ mô phỏng mạng `sim.py`."""
        self.net.send(self.idx, dst, msg)

    def on_sync_response(self, resp):
        """
        Xử lý gói tin phản hồi đồng bộ khối kèm bằng chứng mật mã (CommitCertificate):
        Thực hiện chuỗi kiểm tra an ninh nghiêm ngặt:
        1. Block và Cert phải khớp chiều cao và mã băm.
        2. Thân block phải khớp với Merkle root `tx_root` trong Header.
        3. Header phải hợp lệ và có chữ ký đúng của proposer.
        4. Cert phải chứa >= 2f + 1 chữ ký PRECOMMIT hợp lệ từ các validator chính thống.
        5. Mã băm khối cha (parent) phải khớp với đỉnh ledger hiện tại của node.
        6. Thực thi các giao dịch phải ra state_hash khớp hoàn toàn với cam kết trong Header.
        -> Nếu hợp lệ: finalize khối và bắt kịp mạng!
        """
        for blk, cert in resp.chain_data:
            h = blk.header.height
            if h != self.height:
                continue

            if cert.height != h or cert.block_hash != blk.hash():
                return self.log("REJECT_SYNC", reason="cert_mismatch", height=h)
            if blk.header.tx_root != tx_root(blk.txs):
                return self.log("REJECT_SYNC", reason="bad_tx_root", height=h)
            hd = blk.header
            pk = self.ctx["vpks"].get(hd.proposer)
            if (pk is None or hd.proposer != self.proposer(hd.height, hd.round)
                    or not (-1 <= hd.pol_round < hd.round)
                    or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig)):
                return self.log("REJECT_SYNC", reason="invalid_header", height=h)

            if not set(cert.signatures) <= set(self.ctx["vals"]):
                return self.log("REJECT_SYNC", reason="unknown_signer", height=h)
            if len(cert.signatures) < self.Q:
                return self.log("REJECT_SYNC", reason="insufficient_cert_sigs", height=h)
            for voter, sig in sorted(cert.signatures.items()):
                body = Vote("PRECOMMIT", h, cert.round, cert.block_hash, voter).body()
                if not verify(self.ctx["vpks"][voter], "VOTE:" + self.ctx["chain_id"], body, sig):
                    return self.log("REJECT_SYNC", reason="invalid_cert_sig", height=h)

            if blk.header.parent != self.last_hash():
                return self.log("REJECT_SYNC", reason="bad_parent_hash", height=h)

            new_s, err = apply_txs(self.state, blk.txs, self.ctx["chain_id"], self.ctx["acct_pks"])
            if err or new_s.hash() != blk.header.state_hash:
                return self.log("REJECT_SYNC", reason="bad_state_execution", height=h)

            self.log("SYNC_CATCHUP_SUCCESS", height=h, block=blk.hash().hex()[:8])
            self.finalize(blk, cert)

    # ----- THẨM ĐỊNH HEADER & BODY (GIAO THỨC 2 BƯỚC) -----
    def keep_first(self, book, b):
        """
        Quy tắc lưu trữ ưu tiên thông điệp đến trước:
        Nếu cùng một (height, round) mà nhận được 2 đề xuất khác nhau -> Phát hiện và log EQUIVOCATION.
        """
        key = (b.header.height, b.header.round)
        old = book.get(key)
        if old is None:
            book[key] = b
            return True
        if old.hash() != b.hash():
            self.log("EQUIVOCATION", proposer=b.header.proposer,
                     height=key[0], round=key[1])
        return False

    def on_header(self, hd, src):
        """
        Xử lý khi nhận được Header đề xuất từ proposer (Bước 1 của giao thức 2 bước):
        1. Kiểm tra tính hợp lệ sơ bộ: pol_round, chữ ký proposer, đúng lượt proposer, parent hash.
        2. Nếu hợp lệ: lưu vào `pending_headers`.
        3. Gửi thông điệp `REQUEST_BODY` ngược lại cho proposer `src` để xin tải danh sách txs.
        """
        if (not isinstance(hd, Header) or not isinstance(hd.proposer, str)
                or any(type(value) is not int or not -(2**63) <= value < 2**63
                       for value in (hd.height, hd.round, hd.pol_round))
                or any(not isinstance(value, bytes) or len(value) != 32
                       for value in (hd.parent, hd.state_hash, hd.tx_root))):
            return self.log("REJECT", reason="bad_header_format", height=self.height)
        certified = self.sync_pending.get(Block(hd).hash())
        if not self.in_window(hd.height, hd.round) and not (
                certified is not None and self.height <= hd.height <= self.height + self.max_ahead):
            return
        if not (-1 <= hd.pol_round < hd.round):
            return self.log("REJECT", reason="bad_pol_round", height=hd.height)
        pk = self.ctx["vpks"].get(hd.proposer)
        if pk is None or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig):
            return self.log("REJECT", reason="bad_header_sig", height=hd.height)
        if hd.proposer != self.proposer(hd.height, hd.round):
            return self.log("REJECT", reason="wrong_proposer", height=hd.height)
        block_hash = Block(hd).hash()
        if hd.height > self.height:
            if (len(self.future_headers) < self.ctx.get("max_future_headers", 256)
                    and not any(Block(old).hash() == block_hash for old, _ in self.future_headers)):
                self.future_headers.append((hd, src))
            return
        if hd.parent != self.last_hash():
            return self.log("REJECT", reason="bad_parent", height=hd.height)
        if block_hash not in self.pending_headers and len(self.pending_headers) >= self.ctx.get("max_pending_headers", 256):
            return self.log("REJECT", reason="header_buffer_full", height=hd.height)
        self.pending_headers[block_hash] = hd
        if block_hash in self.blocks:
            blk = Block(hd, self.blocks[block_hash].txs)
            self.on_proposal(blk)
            if self.height == hd.height:
                self.run()
            return
        if block_hash in self.bodies:
            blk = Block(hd, self.bodies[block_hash])
            if hd.tx_root == tx_root(blk.txs):
                self.on_proposal(blk)
                if self.height == hd.height:
                    self.run()
                return
            del self.bodies[block_hash]
        if (block_hash, hd.round) in self.requested_bodies:
            return
        if src is None:
            return self.log("REJECT", reason="missing_header_source", height=hd.height)
        self.requested_bodies.add((block_hash, hd.round))
        self.log("REQUEST_BODY", height=hd.height,
                 block=block_hash.hex()[:8], peer=self.ctx["vals"][src])
        self.send_to(src, ("REQUEST_BODY", block_hash))
        self.net.set_timeout(self.idx, self.timeout_len(self.round),
                             ("BODY_RETRY", hd.height, hd.round, block_hash, src))

    def on_request_body(self, block_hash, src):
        """Proposer phản hồi gói tin BODY chứa danh sách txs khi peer gửi REQUEST_BODY."""
        if src is None:
            return
        txs = self.bodies.get(block_hash)
        if txs is None:
            txs = next((b.txs for b in self.ledger if b.hash() == block_hash), None)
        if txs is None:
            return self.log("REJECT", reason="body_not_found",
                            block=block_hash.hex()[:8])
        self.send_to(src, ("BODY", (block_hash, txs)))

    def on_body(self, payload):
        """
        Xử lý khi nhận được Body (danh sách txs) từ proposer (Bước 2 của giao thức 2 bước):
        1. Ghép nối Header đang chờ trong `pending_headers` với danh sách txs thành đối tượng Block.
        2. Thẩm định mã băm Merkle `tx_root` và mã băm khối `block_hash`.
        3. Chuyển tiếp vào hàm `on_proposal` để xử lý bỏ phiếu.
        """
        if (not isinstance(payload, (tuple, list)) or len(payload) != 2
                or not isinstance(payload[0], bytes) or len(payload[0]) != 32
                or not isinstance(payload[1], (tuple, list))):
            return self.log("REJECT", reason="bad_body_format", height=self.height)
        block_hash, txs = payload
        hd = self.pending_headers.get(block_hash)
        if hd is None:
            return self.log("REJECT", reason="body_without_header",
                            block=block_hash.hex()[:8])
        block = Block(hd, tuple(txs))
        if not all(valid_tx_fields(tx) for tx in block.txs):
            return self.log("REJECT", reason="bad_tx_format", height=hd.height)
        if hd.tx_root != tx_root(block.txs):
            return self.log("REJECT", reason="bad_tx_root",
                            height=hd.height)
        if block.hash() != block_hash:
            return self.log("REJECT", reason="body_header_mismatch",
                            height=hd.height)
        if block_hash in self.sync_pending:
            cert = self.sync_pending.pop(block_hash)
            self.on_sync_response(SyncResp("peer", ((block, cert),)))
            return
        self.on_proposal(block)
        if block_hash in self.blocks:
            self.bodies[block_hash] = block.txs
        if self.height == hd.height:
            self.run()

    def on_proposal(self, b):
        """Thẩm định khối đề xuất hoàn chỉnh và lưu trữ vào bộ nhớ proposals/blocks."""
        hd = b.header
        if not self.in_window(hd.height, hd.round):
            return
        pk = self.ctx["vpks"].get(hd.proposer)
        if pk is None or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig):
            return self.log("REJECT", reason="bad_header_sig", height=hd.height)
        if hd.proposer != self.proposer(hd.height, hd.round):
            return self.log("REJECT", reason="wrong_proposer", height=hd.height)
        if not (-1 <= hd.pol_round < hd.round):
            return self.log("REJECT", reason="bad_pol_round", height=hd.height)
        if hd.tx_root != tx_root(b.txs):
            return self.log("REJECT", reason="bad_tx_root", height=hd.height)
        if hd.height == self.height:
            if not self.check_block(b):
                self.bodies.pop(b.hash(), None)
                if hd.round == self.round and self.step == "PROPOSE":
                    self.cast("PREVOTE", NIL)
                return
            self.keep_first(self.proposals, b)
            self.blocks.setdefault(b.hash(), b)
        else:
            self.keep_first(self.future, b)
            self.future_blocks.setdefault((hd.height, b.hash()), b)

    def on_vote(self, v):
        """
        Xử lý khi nhận phiếu bầu Vote từ một validator:
        1. Xác minh loại phiếu và chữ ký Ed25519 của voter dưới miền 'VOTE:chain_id' (Kịch bản T3).
        2. Quy tắc 7 (Chống đếm phiếu 2 lần):
           - Nếu voter đã có phiếu trong slot (h, r, kind) với cùng block_hash -> bỏ qua.
           - Nếu voter gửi 2 phiếu khác nhau cho cùng một slot -> Phát hiện và ghi log EQUIVOCATION!
        3. Cập nhật bảng đếm phiếu `self.votes`.
        """
        if (not isinstance(v, Vote) or not isinstance(v.voter, str)
                or not isinstance(v.block_hash, bytes) or len(v.block_hash) not in (0, 32)):
            return self.log("REJECT", reason="bad_vote_format", height=self.height)
        if v.kind not in KINDS or not self.in_window(v.height, v.round):
            return
        pk = self.ctx["vpks"].get(v.voter)
        if pk is None or not verify(pk, "VOTE:" + self.ctx["chain_id"], v.body(), v.sig):
            return self.log("REJECT", reason="bad_vote_sig", height=v.height)
        slot = self.votes.setdefault((v.height, v.round, v.kind), {})
        if v.voter in slot:
            if slot[v.voter].block_hash != v.block_hash:
                self.log("EQUIVOCATION", voter=v.voter, height=v.height, round=v.round)
            return
        slot[v.voter] = v
        if v.height == self.height:
            self.peer_round[v.voter] = max(self.peer_round.get(v.voter, -1), v.round)

    # ----- THẨM ĐỊNH VÀ BỎ PHIẾU (7 QUY TẮC VÀNG TENDERMINT) -----
    def check_block(self, b):
        """Thực thi Quy tắc 3: Kiểm tra tính hợp lệ toàn diện của block trước khi prevote/precommit."""
        h = b.hash()
        if h not in self.checked:
            ok, why = self._check(b)
            self.checked[h] = ok
            if not ok:
                self.log("REJECT", reason=why, height=b.header.height)
        return self.checked[h]

    def _check(self, b):
        """Kiểm tra chi tiết: height, parent hash, Merkle root, thực thi state, state_hash, chữ ký proposer."""
        hd = b.header
        if hd.height != self.height:
            return False, "wrong_height"
        if hd.parent != self.last_hash():
            return False, "bad_parent"
        if hd.tx_root != tx_root(b.txs):
            return False, "bad_tx_root"
        s, err = apply_txs(self.state, b.txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        if err:
            return False, err
        if s.hash() != hd.state_hash:
            return False, "bad_state_hash"
        pk = self.ctx["vpks"].get(hd.proposer)
        if pk is None or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig):
            return False, "bad_header_sig"
        if hd.proposer != self.proposer(hd.height, hd.round):
            return False, "wrong_proposer"
        return True, ""

    def prevote_target(self, b):
        """
        Quy tắc quyết định mục tiêu bỏ phiếu PREVOTE (Thực thi Quy tắc 3, 4, 5):
        - Nếu block không hợp lệ -> bầu NIL.
        - Nếu node đang bị khóa vào chính block này (self.locked == bh) -> tiếp tục bầu bh.
        - Nếu là block mới (pol_round < 0): Chỉ được bầu bh nếu node chưa bị khóa (self.locked is None);
          nếu đã bị khóa vào block khác thì bắt buộc phải bầu NIL để bảo vệ tính Safety.
        - Nếu là block đề xuất lại có Polka: Node phải tự kiểm tra thấy >= Q prevote ở pol_round.
          Thực thi Quy tắc 5 (Mở khóa): Chỉ đổi sang bầu block mới nếu pol_round > round bị khóa cũ!
        """
        hd, bh = b.header, b.hash()
        if not self.check_block(b):
            return NIL
        if self.locked is not None and self.locked[0] == bh:
            return bh                                    # Đúng block đang khóa
        if hd.pol_round < 0:                             # Block mới
            return bh if self.locked is None else NIL
        # Đề xuất lại: phải TỰ thấy polka ở pol_round (không tin lời proposer nói miệng)
        if not self.polka(hd.height, hd.pol_round, bh):
            return None
        # Quy tắc 5: Đang khóa block khác thì chỉ đổi khi polka ở round SAU round khóa cũ
        if self.locked is None or self.locked[1] < hd.pol_round:
            return bh
        return NIL

    def cast(self, kind, target):
        """
        Thực thi Quy tắc 1, 2, 6: Ký và phát hành phiếu bầu.
        - Đảm bảo mỗi validator chỉ ký TỐI ĐA 1 phiếu PREVOTE và 1 phiếu PRECOMMIT trong một (height, round).
        - Ghi nhận vào `self.signed` để ngăn chặn việc ký lại hoặc bị lợi dụng ký 2 mặt.
        - Ghi log `VOTE`, gửi qua mạng và thiết lập timeout tương ứng.
        """
        key = (self.height, self.round, kind)
        if key in self.signed:
            return
        self.signed[key] = target
        v = self.make_vote(kind, target)
        self.step = kind
        self.log("VOTE", kind=kind, height=v.height, round=v.round, block=target.hex()[:8] or "NIL")
        self.on_vote(v)  # Tự ghi nhận phiếu của chính mình
        self.send_vote(v)
        if kind in ("PREVOTE", "PRECOMMIT"):
            self.set_timeout(kind)

    # ----- CỖ MÁY TRẠNG THÁI CHÍNH (TENDERMINT ENGINE) -----
    def run(self):
        """
        Trái tim điều phối chuyển bước của thuật toán Tendermint:
        1. Bước PROPOSE: Chờ nhận đề xuất -> Gọi `prevote_target` -> Ký phiếu PREVOTE -> Chuyển sang PREVOTE.
        2. Bước PREVOTE:
           - Gom phiếu PREVOTE từ các peer.
           - Nếu thấy >= Q phiếu PREVOTE cho block bh: Thực thi Quy tắc 4 (Khóa block: `self.locked = (bh, r)`),
             ghi log `LOCK`, ký phiếu `PRECOMMIT bh` và chuyển sang PRECOMMIT.
           - Nếu thấy >= Q phiếu PREVOTE NIL: Ký phiếu `PRECOMMIT NIL` và chuyển sang PRECOMMIT.
        3. Bước PRECOMMIT: Chờ thu thập đủ phiếu PRECOMMIT.
        4. CHỐT BLOCK (FINALIZE):
           - Nếu thấy >= Q phiếu PRECOMMIT cho cùng một block bh != NIL:
             Gom các chữ ký tạo thành `CommitCertificate` hợp lệ -> Gọi `finalize(block, cert)`.
        """
        while not self.done:
            h, r = self.height, self.round
            # A quorum can arrive after PREVOTE timed out. Record it without
            # signing a second PRECOMMIT or regressing a newer lock.
            candidates = set(self.proofs)
            for (hh, rr, kind), vs in self.votes.items():
                if hh == h and rr <= r and kind == "PREVOTE":
                    candidates.update((hh, rr, target) for target, count in
                                      Counter(v.block_hash for v in vs.values()).items()
                                      if target != NIL and count >= self.Q)
            for hh, rr, target in sorted(candidates):
                if (hh == h and rr <= r and target in self.blocks
                        and (self.locked is None or rr > self.locked[1])
                        and self.check_block(self.blocks[target])):
                    self.locked = (target, rr)
                    self.log("LOCK", height=h, round=rr, block=target.hex()[:8])
            if self.step == "PROPOSE":
                b = self.proposals.get((h, r))
                if b is not None:
                    t = self.prevote_target(b)
                    if t is not None:
                        self.cast("PREVOTE", t)
                        continue
            if self.step == "PREVOTE":
                pv = self.votes.get((h, r, "PREVOTE"), {})
                done = False
                for t, c in sorted(Counter(v.block_hash for v in pv.values()).items()):
                    if c >= self.Q:
                        if t == NIL:
                            self.cast("PRECOMMIT", NIL)
                            done = True
                        elif t in self.blocks and self.check_block(self.blocks[t]):
                            self.cast("PRECOMMIT", t)
                            done = True
                        break
                if done:
                    continue
                if len(pv) >= self.Q:
                    self.set_timeout("PREVOTE")
            if self.step == "PRECOMMIT":
                if len(self.votes.get((h, r, "PRECOMMIT"), {})) >= self.Q:
                    self.set_timeout("PRECOMMIT")

            # Chốt block: gom đủ Q precommit -> Tạo CommitCertificate rồi finalize
            for (hh, rr, kind), vs in sorted(self.votes.items()):
                if hh == h and kind == "PRECOMMIT":
                    for t, c in sorted(Counter(v.block_hash for v in vs.values()).items()):
                        if (t != NIL and c >= self.Q and t in self.blocks
                                and self.check_block(self.blocks[t])):
                            sigs = {v.voter: v.sig for v in vs.values() if v.block_hash == t}
                            cert = CommitCertificate(height=hh, round=rr, block_hash=t, signatures=sigs)
                            return self.finalize(self.blocks[t], cert)
            return

    def on_timeout(self, key):
        """
        Xử lý sự kiện hết giờ (Timeout Trigger) để đảm bảo tính Liveness:
        - Timeout PROPOSE: Hết giờ chờ đề xuất -> Tự động bầu `PREVOTE NIL`.
        - Timeout PREVOTE: Hết giờ chờ prevote -> Tự động bầu `PRECOMMIT NIL`.
        - Timeout PRECOMMIT: Hết giờ chờ precommit -> Tăng round (`start_round(r + 1)`).
        - Timeout ROUND: Hết giờ cả round -> Chủ động gọi `request_sync()` rồi tăng round.
        """
        if key[0] == "BODY_RETRY":
            _, h, r, bh, src = key
            if not self.done and h == self.height and bh not in self.blocks and bh in self.pending_headers:
                self.send_to(src, ("REQUEST_BODY", bh))
                self.net.set_timeout(self.idx, self.timeout_len(self.round), key)
            return
        kind, h, r = key
        if self.done or h != self.height or r != self.round:
            return
        self.log("TIMEOUT", kind=kind, height=h, round=r)
        if kind == "PROPOSE" and self.step == "PROPOSE":
            self.cast("PREVOTE", NIL)
        elif kind == "PREVOTE" and self.step == "PREVOTE":
            self.cast("PRECOMMIT", NIL)
        elif kind == "PRECOMMIT":
            return self.start_round(r + 1)
        elif kind == "ROUND":
            self.request_sync()
            return self.start_round(r + 1)
        self.run()

    def finalize(self, b, cert=None):
        """
        Chốt khối vĩnh viễn (Finality Commitment):
        1. Thực thi dứt điểm các giao dịch trong block lên `self.state`.
        2. Thêm khối vào `self.ledger`.
        3. Lưu `CommitCertificate` làm bằng chứng đồng thuận.
        4. Dọn dẹp mempool (loại bỏ các tx đã được đưa vào block).
        5. Ghi log `FINALIZE` với block_hash và state_hash tương ứng.
        6. Giải phóng bộ nhớ của các round cũ và chuyển sang Height kế tiếp (`start_height(h + 1)`).
        """
        s, err = apply_txs(self.state, b.txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        if err is not None or s.hash() != b.header.state_hash:
            raise ValueError(f"invalid finalized execution: {err or 'bad_state_hash'}")
        self.state = s
        self.ledger.append(b)
        if cert is not None:
            self.certificates[b.header.height] = cert

        # Dọn dẹp mempool & ghi nhận tx_hash
        used = {(t.sender, t.nonce) for t in b.txs}
        self.mempool = [t for t in self.mempool if (t.sender, t.nonce) not in used]
        for t in b.txs:
            self.seen_tx_hashes.add(H(encode(t.body())))

        h = b.header.height
        self.log("FINALIZE", height=h, round=cert.round if cert is not None else b.header.round,
                 block=b.hash().hex()[:8], state=s.hash().hex()[:8])
        self.votes = {k: v for k, v in self.votes.items() if k[0] > h}
        self.future = {k: v for k, v in self.future.items() if k[0] > h}
        self.future_blocks = {k: v for k, v in self.future_blocks.items() if k[0] > h}
        # Old alternative proposals are no longer needed. Finalized bodies are
        # served from ledger, and future complete blocks have their own buffer.
        self.bodies.clear()
        self.proofs = {key: proof for key, proof in self.proofs.items() if key[0] > h}
        self.sync_pending = {bh: c for bh, c in self.sync_pending.items() if c.height > h}
        self.start_height(h + 1)
