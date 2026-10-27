"""Mạng mô phỏng: đồng hồ ảo, hàng đợi sự kiện và lỗi mạng có seed."""
import heapq
import random

from .common import H, encode


class Net:
    def __init__(self, cfg):
        self.rng = random.Random(cfg["seed"])
        self.n = cfg["n"]
        self.delta = cfg["delta"]
        self.gst = cfg.get("gst", 0)
        self.pre_gst_max_delay = cfg.get("pre_gst_max_delay", max(100, self.delta))
        self.pre_gst_drop_probability = cfg.get("pre_gst_drop_probability", 0.0)
        self.duplicate_probability = cfg.get("duplicate_probability", 0.0)
        self.pre_gst_reorder_probability = cfg.get("pre_gst_reorder_probability", 0.0)
        self.rate_limit = cfg.get("rate_limit")
        self.peer_block = cfg.get("peer_block")

        if self.delta < 0 or self.gst < 0 or self.pre_gst_max_delay < 0:
            raise ValueError("delta, gst và pre_gst_max_delay phải >= 0")
        for name, probability in (
            ("pre_gst_drop_probability", self.pre_gst_drop_probability),
            ("duplicate_probability", self.duplicate_probability),
            ("pre_gst_reorder_probability", self.pre_gst_reorder_probability),
        ):
            if not 0 <= probability <= 1:
                raise ValueError(f"{name} phải nằm trong [0, 1]")

        self.peers = [set() for _ in range(self.n)]
        links = cfg.get("links", "full")
        if links == "full":
            for src in range(self.n):
                self.peers[src] = set(range(self.n)) - {src}
        elif isinstance(links, list):
            for link in links:
                if not isinstance(link, (list, tuple)) or len(link) != 2:
                    raise ValueError(f"link phải có dạng [src, dst]: {link}")
                src, dst = link
                if not (isinstance(src, int) and isinstance(dst, int)
                        and 0 <= src < self.n and 0 <= dst < self.n):
                    raise ValueError(f"link có node ngoài phạm vi: {link}")
                if src == dst:
                    raise ValueError(f"không thể tạo link từ node đến chính nó: {link}")
                self.peers[src].add(dst)
                self.peers[dst].add(src)
        else:
            raise ValueError("links phải là 'full' hoặc danh sách các cặp node")

        self.link_delays = {}
        for pair, bound in cfg.get("link_delays", {}).items():
            try:
                src, dst = (int(value) for value in pair.split("-"))
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"link_delays key phải có dạng 'src-dst': {pair}") from exc
            if not (0 <= src < self.n and 0 <= dst < self.n):
                raise ValueError(f"link_delays có node ngoài phạm vi: {pair}")
            if dst not in self.peers[src]:
                raise ValueError(f"link_delays tham chiếu đến link không tồn tại: {pair}")
            if bound < 0 or bound > self.delta:
                raise ValueError(f"độ trễ của {pair} phải nằm trong [0, delta]")
            self.link_delays[frozenset((src, dst))] = bound

        if self.rate_limit is not None:
            if (self.rate_limit.get("max_messages", 0) <= 0
                    or self.rate_limit.get("window", 0) <= 0):
                raise ValueError("rate_limit cần max_messages và window > 0")
        if self.peer_block is not None:
            if (self.peer_block.get("max_messages", 0) <= 0
                    or self.peer_block.get("window", 0) <= 0
                    or self.peer_block.get("duration", 0) <= 0):
                raise ValueError("peer_block cần max_messages, window, duration > 0")

        self.q, self.seq, self.now = [], 0, 0
        self.nodes, self.logs = [], []
        self.block_heights = {}
        self.send_times = {}
        self.receive_times = {}
        self.blocked_peers = {}

    def log(self, node, ev, **kw):
        extra = " ".join(f"{k}={v}" for k, v in kw.items())
        self.logs.append(f"t={self.now} node={node} ev={ev} {extra}".rstrip())

    def _node_name(self, idx):
        if idx is None:
            return "NET"
        if idx < len(self.nodes):
            return self.nodes[idx].name
        return f"V{idx}"

    def push(self, t, kind, src, dst, payload):
        self.seq += 1
        heapq.heappush(self.q, (t, self.seq, kind, src, dst, payload))

    def _message_height(self, msg):
        kind, payload = msg
        if kind == "PROPOSAL":
            header = payload.header
        elif kind == "HEADER":
            header = payload
        elif kind == "VOTE":
            return payload.height
        elif kind == "BODY":
            block_hash, _ = payload
            return self.block_heights.get(block_hash)
        elif kind == "REQUEST_BODY":
            return self.block_heights.get(payload)
        else:
            return None

        block_hash = H(encode(header.body()))
        self.block_heights[block_hash] = header.height
        return header.height

    def broadcast(self, src, msg):
        height = self._message_height(msg)
        for dst in sorted(self.peers[src]):
            self.send(src, dst, msg)
        self.push(self.now, "MSG", src, src, msg)
        self.log(self._node_name(src), "LOCAL_DELIVERY", type=msg[0],
                 height=height)

    def send(self, src, dst, msg):
        if not (0 <= src < self.n and 0 <= dst < self.n):
            raise ValueError(f"node gửi/nhận ngoài phạm vi: {src}, {dst}")
        if src != dst and dst not in self.peers[src]:
            raise ValueError(f"không có kết nối giữa node {src} và {dst}")
        height = self._message_height(msg)
        if src == dst:
            self.log(self._node_name(src), "SEND", dst=self._node_name(dst),
                     type=msg[0], height=height, local=True)
            self.push(self.now, "MSG", src, dst, msg)
            return

        send_at = self._reserve_send_time(src, dst)
        if send_at > self.now:
            self.log(self._node_name(src), "DELAY", dst=self._node_name(dst),
                     type=msg[0], height=height, reason="rate_limit",
                     until=send_at)
            self.push(send_at, "SEND_READY", src, dst, msg)
            return
        self._transmit(src, dst, msg)

    def _reserve_send_time(self, src, dst):
        if self.rate_limit is None:
            return self.now

        limit = self.rate_limit["max_messages"]
        window = self.rate_limit["window"]
        key = (src, dst)
        times = [t for t in self.send_times.get(key, [])
                 if t > self.now - window]
        candidate = self.now
        while True:
            active = sorted(t for t in times if candidate - window < t <= candidate)
            if len(active) < limit:
                break
            candidate = active[0] + window
        times.append(candidate)
        self.send_times[key] = sorted(times)
        return candidate

    def _transmit(self, src, dst, msg):
        height = self._message_height(msg)
        self.log(self._node_name(src), "SEND", dst=self._node_name(dst),
                 type=msg[0], height=height)

        before_gst = self.now < self.gst
        if before_gst and self.rng.random() < self.pre_gst_drop_probability:
            self.log(self._node_name(src), "DROP", dst=self._node_name(dst),
                     type=msg[0], height=height, reason="pre_gst")
            return

        copies = 2 if self.rng.random() < self.duplicate_probability else 1
        if copies > 1:
            self.log(self._node_name(src), "DUPLICATE", dst=self._node_name(dst),
                     type=msg[0], height=height, copies=copies)
        for _ in range(copies):
            delay, reordered = self._delivery_delay(src, dst, before_gst)
            if delay:
                self.log(self._node_name(src), "DELAY", dst=self._node_name(dst),
                         type=msg[0], height=height, delay=delay,
                         reason="reorder" if reordered else "network")
            self.push(self.now + delay, "MSG", src, dst, msg)

    def _delivery_delay(self, src, dst, before_gst):
        if before_gst:
            delay = self.rng.randint(0, self.pre_gst_max_delay)
            reordered = (
                self.rng.random() < self.pre_gst_reorder_probability
                and self.pre_gst_max_delay > 0
            )
            if reordered:
                delay += self.rng.randint(1, self.pre_gst_max_delay)
            return delay, reordered

        bound = self.link_delays.get(frozenset((src, dst)), self.delta)
        return self.rng.randint(0, bound), False

    def _receive(self, src, dst, msg):
        if src == dst:
            self.nodes[dst].on_message(msg, src)
            return

        height = self._message_height(msg)
        src_name = self._node_name(src)
        dst_name = self._node_name(dst)
        blocked_until = self.blocked_peers.get((dst, src))
        if blocked_until is not None and self.now < blocked_until:
            self.log(dst_name, "DROP", src=src_name, type=msg[0],
                     height=height, reason="peer_blocked")
            return

        if self.peer_block is not None:
            key = (dst, src)
            window = self.peer_block["window"]
            times = [t for t in self.receive_times.get(key, [])
                     if t > self.now - window]
            if len(times) >= self.peer_block["max_messages"]:
                until = self.now + self.peer_block["duration"]
                self.blocked_peers[key] = until
                self.log(dst_name, "BLOCK", src=src_name, until=until,
                         reason="peer_rate_limit")
                self.log(dst_name, "DROP", src=src_name, type=msg[0],
                         height=height, reason="peer_rate_limit")
                self.push(until, "UNBLOCK", dst, src, until)
                self.receive_times[key] = times
                return
            times.append(self.now)
            self.receive_times[key] = times

        self.nodes[dst].on_message(msg, src)

    def set_timeout(self, idx, delay, key):
        self.push(self.now + delay, "TIMEOUT", None, idx, key)

    def run(self, t_end):
        for i in range(len(self.nodes)):
            self.push(0, "START", None, i, None)
        while self.q:
            t, _, kind, src, dst, payload = heapq.heappop(self.q)
            if t > t_end:
                break
            self.now = t
            if kind == "START":
                self.nodes[dst].start()
            elif kind == "MSG":
                self._receive(src, dst, payload)
            elif kind == "SEND_READY":
                self._transmit(src, dst, payload)
            elif kind == "UNBLOCK":
                if self.blocked_peers.get((src, dst)) == payload:
                    del self.blocked_peers[(src, dst)]
                    self.log(self._node_name(src), "UNBLOCK",
                             src=self._node_name(dst))
            else:
                self.nodes[dst].on_timeout(payload)
            if self.nodes and all(node.done for node in self.nodes):
                break
