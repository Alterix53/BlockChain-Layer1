"""Một validator: máy trạng thái Tendermint tối giản (propose/prevote/precommit/commit),
kết hợp lõi đồng thuận (phần B) và tầng dữ liệu/đồng bộ (phần D).

Bản này thêm so với xương sống:
  * Luật 5 đầy đủ (proposal mang pol_round, mở khóa khi tự thấy polka ở round sau).
  * Proposer đề xuất lại block đã có polka.
  * Nhảy round khi thấy f+1 validator ở round cao hơn (+ timeout cả round làm lưới an toàn).
  * Buffer proposal/vote của height tương lai, có giới hạn bộ nhớ.
  * Các hook nhỏ (send_proposal, make_vote, send_vote) để người khác ghi đè.
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
from .execution import State, apply_tx, apply_txs

GENESIS = H(b"genesis")
KINDS = ("PREVOTE", "PRECOMMIT")


class Node:
    def __init__(self, idx, ctx, kp):
        self.idx, self.ctx, self.kp = idx, ctx, kp
        self.name = ctx["vals"][idx]
        self.net = ctx["net"]
        self.Q = 2 * ctx["f"] + 1
        self.max_ahead = ctx.get("max_ahead_h", 3)    # chỉ nhận tin tối đa 3 height phía trước
        self.max_round = ctx.get("max_round", 1000)   # trần tuyệt đối cho round
        self.state = State()
        self.ledger = []              # Danh sách block đã chốt
        self.certificates = {}        # height -> CommitCertificate (Phần D)
        self.mempool = []             # Hàng đợi giao dịch chờ
        self.seen_tx_hashes = set()   # Khử trùng lặp mempool trong O(1) (Phần D)
        self.done = False
        self.height, self.round, self.step = 0, 0, "PROPOSE"
        self.signed = {}              # (h, r, kind) -> block_hash đã ký (luật 1, 2)
        self.locked = None            # (block_hash, round)

        # Dữ liệu của height hiện tại (reset ở start_height)
        self.proposals, self.blocks, self.checked = {}, {}, {}
        self.scheduled = set()
        self.peer_round = {}          # voter -> round cao nhất từng thấy ở height này

        # Dữ liệu sống qua nhiều height
        self.votes = {}               # (h, r, kind) -> {voter: Vote}
        self.future = {}              # (h, r) -> proposal đầu tiên của height tương lai
        self.future_blocks = {}       # (h, block_hash) -> thân MỌI proposal hợp lệ đến sớm
        self.bodies = {}             # block hash -> tuple of txs (locally proposed blocks)
        self.future_headers = []     # (header, source), bounded by max_ahead
        self.pending_headers = {}    # hash -> accepted header at current height
        self.requested_bodies = set()

    # ----- tiện ích -----
    def log(self, ev, **kw):
        self.net.log(self.name, ev, **kw)

    def last_hash(self):
        return self.ledger[-1].hash() if self.ledger else GENESIS

    def proposer(self, h, r):
        v = self.ctx["vals"]
        return v[(h + r) % len(v)]

    def in_window(self, h, r):
        return self.height <= h <= self.height + self.max_ahead and 0 <= r <= self.max_round

    # ----- vòng đời -----
    def start(self):
        self.start_height(1)

    def start_height(self, h):
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
        # Process future headers after height transition, without bypassing the network.
        ready = [(hd, src) for hd, src in self.future_headers if hd.height == h]
        self.future_headers = [(hd, src) for hd, src in self.future_headers if hd.height > h]
        for hd, src in ready:
            self.on_header(hd, src)
        if ready:
            self.run()

    def start_round(self, r):
        self.round, self.step = r, "PROPOSE"
        self.log("ROUND_START", height=self.height, round=r)
        if self.proposer(self.height, r) == self.name:
            self.propose()
        self.set_timeout("PROPOSE")
        self.set_timeout("ROUND", 3)   # lưới an toàn: dù thiếu phiếu cũng không đứng yên mãi
        self.run()

    def timeout_len(self, r):
        return self.ctx["base_timeout"] + r * self.ctx["timeout_inc"]

    def set_timeout(self, kind, mult=1):
        key = (kind, self.height, self.round)
        if key in self.scheduled:
            return
        self.scheduled.add(key)
        self.net.set_timeout(self.idx, mult * self.timeout_len(self.round), key)

    # ----- nhảy round -----
    def skip_target(self):
        """Round lớn nhất mà ít nhất f+1 validator khác nhau đã đạt (-1 nếu chưa đủ)."""
        rs = sorted(self.peer_round.values(), reverse=True)
        f = self.ctx["f"]
        return rs[f] if len(rs) > f else -1

    def maybe_skip_round(self):
        t = self.skip_target()
        if t > self.round:
            self.log("ROUND_SKIP", height=self.height, frm=self.round, to=t)
            self.start_round(t)
            return True
        return False

    # ----- polka -----
    def polka(self, h, r, bh):
        """Có >= Q prevote cho bh ở (h, r) không?"""
        pv = self.votes.get((h, r, "PREVOTE"), {})
        return sum(1 for v in pv.values() if v.block_hash == bh) >= self.Q

    def best_polka(self):
        """Polka ở round cao nhất (< round hiện tại) cho block mà ta có thân và hợp lệ."""
        best = None
        for (hh, rr, kind), vs in sorted(self.votes.items()):   # round tăng dần
            if hh != self.height or kind != "PREVOTE" or rr >= self.round:
                continue
            for t, c in sorted(Counter(v.block_hash for v in vs.values()).items()):
                if t != NIL and c >= self.Q and t in self.blocks and self.check_block(self.blocks[t]):
                    best = (t, rr)
        return best

    # ----- đề xuất block -----
    def propose(self):
        pol = self.best_polka()
        if pol:
            t, pr = pol
            old = self.blocks[t]
            blk = self.seal(old.txs, old.header.state_hash, pr)   # giữ nguyên nội dung
            self.log("REPROPOSE", height=self.height, round=self.round,
                     pol_round=pr, block=t.hex()[:8])
        else:
            blk = self.make_block()
        self.log("PROPOSE", height=self.height, round=self.round,
                 pol_round=blk.header.pol_round, txs=len(blk.txs))
        self.send_proposal(blk)

    def make_block(self):
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
        hd = Header(self.height, self.round, pol_round, self.last_hash(),
                    state_hash, tx_root(txs), self.name)
        hd = Header(*hd.body(), sig=sign(self.kp, "HEADER:" + self.ctx["chain_id"], hd.body()))
        return Block(hd, tuple(txs))

    # ----- hook gửi tin (người khác ghi đè để tạo node lỗi) -----
    def send_proposal(self, blk):
        """Keep body locally; broadcast only the signed header.

        The receiver decides whether to request the matching body.
        Keep this hook overrideable for Byzantine-node tests.
        """
        self.bodies[blk.hash()] = blk.txs
        self.on_proposal(blk)  # proposer must validate its own block locally
        self.net.broadcast(self.idx, ("HEADER", blk.header))

    def make_vote(self, kind, target):
        v = Vote(kind, self.height, self.round, target, self.name)
        return Vote(*v.body(), sig=sign(self.kp, "VOTE:" + self.ctx["chain_id"], v.body()))

    def send_vote(self, v):
        self.net.broadcast(self.idx, ("VOTE", v))

    # ----- nhận thông điệp -----
    def on_message(self, msg, src=None):
        kind, payload = msg
        # Even finalized nodes must serve lagging peers.
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
        elif kind == "TX":
            self.on_tx(payload)
        elif kind == "SYNC_RESP":
            self.on_sync_response(payload)

        if not self.maybe_skip_round():
            self.run()

    # ----- Phần D: Mempool Gossip & Catch-up Sync -----
    def on_tx(self, tx):
        tx_hash = H(encode(tx.body()))
        if tx_hash in self.seen_tx_hashes:
            return

        # T3: tx lỗi bị loại VÀ ghi lý do (cùng tên lý do với execution.apply_tx).
        # Chỉ đánh dấu "đã thấy" SAU khi kiểm xong: seen_tx_hashes băm body không băm chữ ký,
        # nên bản sai chữ ký đến trước không được chặn bản đúng đến sau.
        pk = self.ctx["acct_pks"].get(tx.sender)
        if pk is None:
            return self.log("REJECT", reason="unknown_sender", sender=tx.sender, nonce=tx.nonce)
        if not verify(pk, "TX:" + self.ctx["chain_id"], tx.body(), tx.sig):
            return self.log("REJECT", reason="bad_tx_sig", sender=tx.sender, nonce=tx.nonce)
        if not tx.key.startswith(tx.sender + "/"):
            return self.log("REJECT", reason="not_owner", sender=tx.sender, nonce=tx.nonce)

        self.seen_tx_hashes.add(tx_hash)
        self.mempool.append(tx)
        self.log("TX_RECEIVED", sender=tx.sender, nonce=tx.nonce)
        self.net.broadcast(self.idx, ("TX", tx))

    def request_sync(self):
        """Hỏi các peer (block, certificate) từ height hiện tại. Gọi khi cả một round trôi qua
        mà không chốt được: có thể mạng đã chốt height này mà mình thiếu phiếu hoặc thân block.
        Hỏi thừa cũng vô hại: ai chưa có thì không trả lời, trả lời sai thì bị REJECT_SYNC."""
        req = SyncReq(requester=self.name, from_height=self.height,
                      to_height=self.height + self.max_ahead)
        self.log("SYNC_REQUEST", height=req.from_height, to=req.to_height)
        self.net.broadcast(self.idx, ("SYNC_REQ", req))

    def on_sync_request(self, req):
        vals = self.ctx["vals"]
        if req.requester not in vals or req.requester == self.name:
            return
        # chặn khoảng do người lạ gửi: không lặp theo to_height tùy ý (tránh DoS), tối đa
        # max_ahead + 1 block mỗi lần, và chỉ những height đã có certificate
        lo = max(1, req.from_height)
        hi = min(req.to_height, len(self.ledger), lo + self.max_ahead)
        chain_data = tuple((self.ledger[h - 1], self.certificates[h])
                           for h in range(lo, hi + 1) if h in self.certificates)
        if chain_data:
            self.send_to(vals.index(req.requester), ("SYNC_RESP", SyncResp(self.name, chain_data)))

    def send_to(self, dst, msg):
        """All node-to-node traffic must pass through the network simulator."""
        self.net.send(self.idx, dst, msg)

    def on_sync_response(self, resp):
        for blk, cert in resp.chain_data:
            h = blk.header.height
            if h != self.height:
                continue

            if cert.height != h or cert.block_hash != blk.hash():
                return self.log("REJECT_SYNC", reason="cert_mismatch", height=h)
            # Block.hash() chỉ băm header (tx_root), không băm txs: phải tự kiểm thân khớp
            # header, nếu không peer có thể đảo/thay txs mà certificate vẫn khớp
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
            # chốt qua đúng đường của finalize: dọn mempool, votes, future rồi sang height sau
            self.finalize(blk, cert)

    # ----- thẩm định thông điệp -----
    def keep_first(self, book, b):
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
        if not self.in_window(hd.height, hd.round):
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
        self.pending_headers.setdefault(block_hash, hd)
        if block_hash in self.requested_bodies:
            return
        if src is None:
            return self.log("REJECT", reason="missing_header_source", height=hd.height)
        self.requested_bodies.add(block_hash)
        self.log("REQUEST_BODY", height=hd.height,
                 block=block_hash.hex()[:8], peer=self.ctx["vals"][src])
        self.send_to(src, ("REQUEST_BODY", block_hash))

    def on_request_body(self, block_hash, src):
        if src is None:
            return
        txs = self.bodies.get(block_hash)
        if txs is None:
            return self.log("REJECT", reason="body_not_found",
                            block=block_hash.hex()[:8])
        self.send_to(src, ("BODY", (block_hash, txs)))

    def on_body(self, payload):
        block_hash, txs = payload
        hd = self.pending_headers.get(block_hash)
        if hd is None:
            return self.log("REJECT", reason="body_without_header",
                            block=block_hash.hex()[:8])
        block = Block(hd, tuple(txs))
        if block.hash() != block_hash or hd.tx_root != tx_root(block.txs):
            return self.log("REJECT", reason="body_header_mismatch",
                            height=hd.height)
        self.on_proposal(block)
        if self.height == hd.height:
            self.run()

    def on_proposal(self, b):
        hd = b.header
        if not self.in_window(hd.height, hd.round):      # cũ quá, hoặc xa quá
            return
        pk = self.ctx["vpks"].get(hd.proposer)
        if pk is None or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig):
            return self.log("REJECT", reason="bad_header_sig", height=hd.height)
        if hd.proposer != self.proposer(hd.height, hd.round):
            return self.log("REJECT", reason="wrong_proposer", height=hd.height)
        if not (-1 <= hd.pol_round < hd.round):
            return self.log("REJECT", reason="bad_pol_round", height=hd.height)
        if hd.tx_root != tx_root(b.txs):                 # chặn từ cổng: body không khớp header
            return self.log("REJECT", reason="bad_tx_root", height=hd.height)
        if hd.height == self.height:
            # prevote theo proposal đến TRƯỚC, nhưng giữ thân của MỌI proposal hợp lệ: nếu
            # proposer gửi 2 block và block đến sau đạt Q precommit thì vẫn có thân để chốt
            self.keep_first(self.proposals, b)
            self.blocks.setdefault(b.hash(), b)
        else:
            self.keep_first(self.future, b)
            self.future_blocks.setdefault((hd.height, b.hash()), b)

    def on_vote(self, v):
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

    # ----- kiểm tra block (luật 3) -----
    def check_block(self, b):
        h = b.hash()
        if h not in self.checked:
            ok, why = self._check(b)
            self.checked[h] = ok
            if not ok:
                self.log("REJECT", reason=why, height=b.header.height)
        return self.checked[h]

    def _check(self, b):
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

    # ----- luật prevote (luật 3, 4, 5) -----
    def prevote_target(self, b):
        """Trả về hash block, NIL, hoặc None (= chưa đủ bằng chứng, chờ thêm)."""
        hd, bh = b.header, b.hash()
        if not self.check_block(b):
            return NIL
        if self.locked is not None and self.locked[0] == bh:
            return bh                                    # đúng block đang khóa
        if hd.pol_round < 0:                             # block mới
            return bh if self.locked is None else NIL
        # đề xuất lại: phải TỰ thấy polka ở pol_round (không tin lời proposer)
        if not self.polka(hd.height, hd.pol_round, bh):
            return None
        # luật 5: đang khóa block khác thì chỉ đổi khi polka ở round SAU round khóa
        if self.locked is None or self.locked[1] < hd.pol_round:
            return bh
        return NIL

    # ----- ký phiếu (luật 1, 2, 6) -----
    def cast(self, kind, target):
        key = (self.height, self.round, kind)
        if key in self.signed:
            return
        self.signed[key] = target
        v = self.make_vote(kind, target)
        self.step = kind
        self.log("VOTE", kind=kind, height=v.height, round=v.round, block=target.hex()[:8] or "NIL")
        # Count our own signed vote even if broadcast() excludes the sender.
        self.on_vote(v)
        self.send_vote(v)
        if kind in ("PREVOTE", "PRECOMMIT"):
            self.set_timeout(kind)

    # ----- các quy tắc chuyển bước -----
    def run(self):
        while not self.done:
            h, r = self.height, self.round
            if self.step == "PROPOSE":
                b = self.proposals.get((h, r))
                if b is not None:
                    t = self.prevote_target(b)
                    if t is not None:
                        self.cast("PREVOTE", t)
                        continue
                    # t is None: chờ polka; timeout PROPOSE sẽ ép NIL nếu không đến
            if self.step == "PREVOTE":
                pv = self.votes.get((h, r, "PREVOTE"), {})
                done = False
                for t, c in sorted(Counter(v.block_hash for v in pv.values()).items()):
                    if c >= self.Q:
                        if t == NIL:
                            self.cast("PRECOMMIT", NIL)
                            done = True
                        elif t in self.blocks and self.check_block(self.blocks[t]):
                            self.locked = (t, r)
                            self.log("LOCK", height=h, round=r, block=t.hex()[:8])
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
        elif kind == "ROUND":   # cả round trôi qua không chốt được: hỏi đồng bộ rồi sang round sau
            self.request_sync()
            return self.start_round(r + 1)
        self.run()

    def finalize(self, b, cert=None):
        s, err = apply_txs(self.state, b.txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        assert err is None, err
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
        self.log("FINALIZE", height=h, round=b.header.round,
                 block=b.hash().hex()[:8], state=s.hash().hex()[:8])
        self.votes = {k: v for k, v in self.votes.items() if k[0] > h}
        self.future = {k: v for k, v in self.future.items() if k[0] > h}
        self.future_blocks = {k: v for k, v in self.future_blocks.items() if k[0] > h}
        self.bodies = {bh: txs for bh, txs in self.bodies.items()
                       if bh != b.hash()}  # discard finalized proposal body
        self.start_height(h + 1)
