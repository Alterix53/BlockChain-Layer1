"""Một validator: máy trạng thái Tendermint tối giản (propose/prevote/precommit/commit)."""
from collections import Counter

from .common import NIL, Block, Header, Vote, H, sign, tx_root, verify
from .execution import State, apply_tx, apply_txs

GENESIS = H(b"genesis")


class Node:
    def __init__(self, idx, ctx, kp):
        self.idx, self.ctx, self.kp = idx, ctx, kp
        self.name = ctx["vals"][idx]
        self.net = ctx["net"]
        self.Q = 2 * ctx["f"] + 1
        self.state = State()
        self.ledger = []          # block đã chốt
        self.mempool = []
        self.done = False
        self.height = 0
        self.signed = {}          # (h, r, kind) -> block_hash đã ký (luật 1, 2)
        self.locked = None        # (block_hash, round)

    # ----- tiện ích -----
    def log(self, ev, **kw):
        self.net.log(self.name, ev, **kw)

    def last_hash(self):
        return self.ledger[-1].hash() if self.ledger else GENESIS

    def proposer(self, h, r):
        v = self.ctx["vals"]
        return v[(h + r) % len(v)]

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
        if not hasattr(self, "votes"):
            self.votes = {}
        self.scheduled = set()
        self.start_round(0)

    def start_round(self, r):
        self.round, self.step = r, "PROPOSE"
        self.log("ROUND_START", height=self.height, round=r)
        if self.proposer(self.height, r) == self.name:
            self.propose()
        self.set_timeout("PROPOSE")
        self.run()

    def timeout_len(self, r):
        return self.ctx["base_timeout"] + r * self.ctx["timeout_inc"]

    def set_timeout(self, kind):
        key = (kind, self.height, self.round)
        if key in self.scheduled:
            return
        self.scheduled.add(key)
        self.net.set_timeout(self.idx, self.timeout_len(self.round), key)

    # ----- đề xuất block -----
    def propose(self):
        chosen, s = [], self.state.copy()
        for tx in sorted(self.mempool, key=lambda t: (t.sender, t.nonce)):
            if len(chosen) >= self.ctx["max_txs"]:
                break
            trial = s.copy()
            if apply_tx(trial, tx, self.ctx["chain_id"], self.ctx["acct_pks"]) is None:
                s = trial
                chosen.append(tx)
        hd = Header(self.height, self.round, self.last_hash(), s.hash(),
                    tx_root(chosen), self.name)
        hd = Header(*hd.body(), sig=sign(self.kp, "HEADER:" + self.ctx["chain_id"], hd.body()))
        blk = Block(hd, tuple(chosen))
        self.log("PROPOSE", height=self.height, round=self.round, txs=len(chosen))
        self.net.broadcast(self.idx, ("PROPOSAL", blk))

    # ----- nhận thông điệp -----
    def on_message(self, msg):
        if self.done:
            return
        kind, payload = msg
        if kind == "PROPOSAL":
            self.on_proposal(payload)
        elif kind == "VOTE":
            self.on_vote(payload)
        self.run()

    def on_proposal(self, b):
        hd = b.header
        if hd.height < self.height:
            return
        pk = self.ctx["vpks"].get(hd.proposer)
        if pk is None or not verify(pk, "HEADER:" + self.ctx["chain_id"], hd.body(), hd.sig):
            return self.log("REJECT", reason="bad_header_sig", height=hd.height)
        if hd.proposer != self.proposer(hd.height, hd.round):
            return self.log("REJECT", reason="wrong_proposer", height=hd.height)
        if hd.height == self.height:
            self.proposals[(hd.height, hd.round)] = b
            self.blocks[b.hash()] = b
        else:  # proposal của height tương lai: bỏ qua trong bản tối thiểu (TODO: buffer)
            self.future = getattr(self, "future", [])
            self.future.append(b)

    def on_vote(self, v):
        pk = self.ctx["vpks"].get(v.voter)
        if pk is None or not verify(pk, "VOTE:" + self.ctx["chain_id"], v.body(), v.sig):
            return self.log("REJECT", reason="bad_vote_sig", height=v.height)
        if v.height < self.height:
            return
        slot = self.votes.setdefault((v.height, v.round, v.kind), {})
        if v.voter in slot:  # luật 7: chỉ đếm 1 phiếu
            if slot[v.voter].block_hash != v.block_hash:
                self.log("EQUIVOCATION", voter=v.voter, height=v.height, round=v.round)
            return
        slot[v.voter] = v

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
        return True, ""

    # ----- ký phiếu (luật 1, 2, 6) -----
    def cast(self, kind, target):
        key = (self.height, self.round, kind)
        if key in self.signed:
            return
        self.signed[key] = target
        v = Vote(kind, self.height, self.round, target, self.name)
        v = Vote(*v.body(), sig=sign(self.kp, "VOTE:" + self.ctx["chain_id"], v.body()))
        self.step = kind
        self.log("VOTE", kind=kind, height=v.height, round=v.round, block=target.hex()[:8] or "NIL")
        self.net.broadcast(self.idx, ("VOTE", v))

    # ----- các quy tắc chuyển bước -----
    def run(self):
        while not self.done:
            h, r = self.height, self.round
            if self.step == "PROPOSE":
                b = self.proposals.get((h, r))
                if b is not None:
                    bh = b.hash()
                    can = self.check_block(b) and (self.locked is None or self.locked[0] == bh)
                    self.cast("PREVOTE", bh if can else NIL)
                    continue
            if self.step == "PREVOTE":
                pv = self.votes.get((h, r, "PREVOTE"), {})
                done = False
                for t, c in sorted(Counter(v.block_hash for v in pv.values()).items()):
                    if c >= self.Q:
                        if t == NIL:
                            self.cast("PRECOMMIT", NIL); done = True
                        elif t in self.blocks and self.check_block(self.blocks[t]):
                            self.locked = (t, r)  # luật 4
                            self.cast("PRECOMMIT", t); done = True
                        break
                if done:
                    continue
                if len(pv) >= self.Q:
                    self.set_timeout("PREVOTE")
            if self.step == "PRECOMMIT":
                if len(self.votes.get((h, r, "PRECOMMIT"), {})) >= self.Q:
                    self.set_timeout("PRECOMMIT")
            # chốt block: Q precommit cho cùng một block, ở bất kỳ round nào của height này
            for (hh, rr, kind), vs in sorted(self.votes.items()):
                if hh == h and kind == "PRECOMMIT":
                    for t, c in sorted(Counter(v.block_hash for v in vs.values()).items()):
                        if t != NIL and c >= self.Q and t in self.blocks:
                            return self.finalize(self.blocks[t])
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
        self.run()

    def finalize(self, b):
        s, err = apply_txs(self.state, b.txs, self.ctx["chain_id"], self.ctx["acct_pks"])
        assert err is None, err
        self.state = s
        self.ledger.append(b)
        used = {(t.sender, t.nonce) for t in b.txs}
        self.mempool = [t for t in self.mempool if (t.sender, t.nonce) not in used]
        self.log("FINALIZE", height=b.header.height, round=b.header.round,
                 block=b.hash().hex()[:8], state=s.hash().hex()[:8])
        self.votes = {k: v for k, v in self.votes.items() if k[0] > b.header.height}
        self.start_height(b.header.height + 1)
        for fb in getattr(self, "future", []):  # xử lý proposal đến sớm
            if fb.header.height == self.height:
                self.on_proposal(fb)
        self.future = [x for x in getattr(self, "future", []) if x.header.height > self.height]
        self.run()