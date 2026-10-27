"""Mạng mô phỏng tối thiểu: đồng hồ ảo + hàng đợi sự kiện + PRNG có seed."""
import heapq
import random


class Net:
    def __init__(self, cfg):
        self.rng = random.Random(cfg["seed"])
        self.delta = cfg["delta"]
        self.q, self.seq, self.now = [], 0, 0
        self.nodes, self.logs = [], []

    def log(self, node, ev, **kw):
        extra = " ".join(f"{k}={v}" for k, v in kw.items())
        self.logs.append(f"t={self.now} node={node} ev={ev} {extra}".rstrip())

    def push(self, t, kind, dst, payload):
        self.seq += 1
        heapq.heappush(self.q, (t, self.seq, kind, dst, payload))

    def broadcast(self, src, msg):
        name = self.nodes[src].name
        h = msg[1].header.height if msg[0] == "PROPOSAL" else getattr(msg[1], "height", 0)
        self.log(name, "SEND", type=msg[0], height=h)
        for dst in range(len(self.nodes)):
            # TODO: chỗ này sẽ thêm drop / duplicate / reorder / GST / rate limit
            self.push(self.now + self.rng.randint(1, self.delta), "MSG", dst, msg)

    def set_timeout(self, idx, delay, key):
        self.push(self.now + delay, "TIMEOUT", idx, key)

    def run(self, t_end):
        for i in range(len(self.nodes)):
            self.push(0, "START", i, None)
        while self.q:
            t, _, kind, dst, payload = heapq.heappop(self.q)
            if t > t_end:
                break
            self.now = t
            n = self.nodes[dst]
            if kind == "START":
                n.start()
            elif kind == "MSG":
                n.on_message(payload)
            else:
                n.on_timeout(payload)
            if all(x.done for x in self.nodes):
                break