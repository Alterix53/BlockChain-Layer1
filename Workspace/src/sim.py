"""Mạng mô phỏng: đồng hồ ảo, hàng đợi sự kiện và lỗi mạng có seed."""
import heapq
import random

from .common import H, encode


class Net:
    def __init__(self, cfg):
        """
        Khởi tạo bộ mô phỏng mạng biến cố rời rạc (Discrete Event Simulation - DES).

        Công việc thực hiện:
        1. Khởi tạo bộ sinh số giả ngẫu nhiên (PRNG) với seed cố định để đảm bảo tính tất định (T8).
        2. Thiết lập các thông số mạng cơ bản: số validator (n), cận trễ tối đa sau GST (delta).
        3. Cấu hình mô hình mạng bán đồng bộ (Partial Synchrony):
           - gst: Thời điểm ổn định mạng toàn cục (Global Stabilization Time).
           - pre_gst_max_delay: Độ trễ tối đa trước GST (mô phỏng mạng bị trễ nặng).
           - pre_gst_drop_probability: Xác suất rớt gói tin trước GST (Kịch bản T5).
           - duplicate_probability: Xác suất nhân bản gói tin (Kịch bản T2).
           - pre_gst_reorder_probability: Xác suất đảo thứ tự gói tin trước GST (Kịch bản T2).
        4. Thiết lập topo mạng (Topology & Peers):
           - Mặc định là 'full' (kết nối đầy đủ giữa mọi cặp node).
           - Hoặc danh sách liên kết tùy biến [src, dst].
           - Bảng link_delays quy định độ trễ riêng cho từng cặp liên kết.
        5. Cấu hình kiểm soát lưu lượng và phòng vệ DoS (Mục 6 đề bài):
           - rate_limit: Giới hạn tốc độ gửi tin đi của từng node (Outbound Rate Limit).
           - peer_block: Tạm thời chặn các peer gửi tin dồn dập (Inbound Peer Throttling).
        6. Khởi tạo hàng đợi biến cố ưu tiên (heapq), đồng hồ ảo (now = 0), và lịch sử log.
        """
        self.rng = random.Random(cfg["seed"])
        self.n = cfg.get("n", 10)
        self.delta = cfg.get("delta", 20)
        self.gst = cfg.get("gst", 0)
        self.pre_gst_max_delay = cfg.get("pre_gst_max_delay", max(100, self.delta))
        self.pre_gst_drop_probability = cfg.get("pre_gst_drop_probability", 0.0)
        self.duplicate_probability = cfg.get("duplicate_probability", 0.0)
        self.pre_gst_reorder_probability = cfg.get("pre_gst_reorder_probability", 0.0)
        self.rate_limit = cfg.get("rate_limit")
        self.peer_block = cfg.get("peer_block")

        # Kiểm tra tính hợp lệ của các giá trị cấu hình
        if self.delta < 0 or self.gst < 0 or self.pre_gst_max_delay < 0:
            raise ValueError("delta, gst và pre_gst_max_delay phải >= 0")
        for name, probability in (
            ("pre_gst_drop_probability", self.pre_gst_drop_probability),
            ("duplicate_probability", self.duplicate_probability),
            ("pre_gst_reorder_probability", self.pre_gst_reorder_probability),
        ):
            if not 0 <= probability <= 1:
                raise ValueError(f"{name} phải nằm trong [0, 1]")

        # Xây dựng danh sách liên kết (peers) của từng node theo cấu hình topo
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

        # Cấu hình độ trễ cố định cho từng đường truyền (nếu có)
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

        # Kiểm tra tính hợp lệ của cấu hình Rate Limit & Peer Block
        if self.rate_limit is not None:
            if (self.rate_limit.get("max_messages", 0) <= 0
                    or self.rate_limit.get("window", 0) <= 0):
                raise ValueError("rate_limit cần max_messages và window > 0")
        if self.peer_block is not None:
            if (self.peer_block.get("max_messages", 0) <= 0
                    or self.peer_block.get("window", 0) <= 0
                    or self.peer_block.get("duration", 0) <= 0):
                raise ValueError("peer_block cần max_messages, window, duration > 0")

        # Các cấu trúc dữ liệu mô phỏng biến cố rời rạc (DES)
        self.q, self.seq, self.now = [], 0, 0     # Hàng đợi ưu tiên, biến đánh số thứ tự tie-break, đồng hồ ảo
        self.nodes, self.logs = [], []            # Danh sách các validator node và nhật ký sự kiện
        self.block_heights = {}                   # Bộ đệm ánh xạ block_hash -> height phục vụ ghi log
        self.send_times = {}                      # Lưu lịch sử mốc thời gian gửi tin (phục vụ Outbound Rate Limit)
        self.receive_times = {}                   # Lưu lịch sử mốc thời gian nhận tin (phục vụ Inbound Peer Throttling)
        self.blocked_peers = {}                   # Bảng theo dõi các peer đang bị tạm khóa: (dst, src) -> unblock_time

    def log(self, node, ev, **kw):
        """
        Ghi nhận một sự kiện mạng vào danh sách logs theo định dạng chuẩn đề bài:
        `t={now} node={node} ev={ev} {các_tham_số_bổ_sung}`.
        Dùng làm bằng chứng đối chiếu kiểm thử và tính tất định (T8).
        """
        extra = " ".join(f"{k}={v}" for k, v in kw.items())
        self.logs.append(f"t={self.now} node={node} ev={ev} {extra}".rstrip())

    def _node_name(self, idx):
        """
        Chuyển đổi chỉ số node (int) sang tên hiển thị (str, ví dụ 'V0', 'V1', hoặc 'NET').
        Giúp định dạng bản ghi log nhất quán và dễ đọc.
        """
        if idx is None:
            return "NET"
        if idx < len(self.nodes):
            return self.nodes[idx].name
        return f"V{idx}"

    def push(self, t, kind, *args):
        """
        Đẩy một biến cố mới vào hàng đợi ưu tiên (Priority Queue - heapq).

        Hỗ trợ cả 2 chữ ký tương thích ngược:
        - 5 tham số: push(t, kind, src, dst, payload)
        - 4 tham số: push(t, kind, dst, payload) -> mặc định src = None
        """
        if len(args) == 3:
            src, dst, payload = args
        elif len(args) == 2:
            src, (dst, payload) = None, args
        else:
            raise TypeError(f"push() nhận 4 hoặc 5 tham số (t, kind, [src], dst, payload), nhận {2 + len(args)}")
        self.seq += 1
        heapq.heappush(self.q, (t, self.seq, kind, src, dst, payload))

    def _message_height(self, msg):
        """
        Trích xuất thuộc tính `height` (chiều cao block) từ thông điệp mạng.
        Hỗ trợ nhiều loại tin: PROPOSAL, HEADER, VOTE, BODY, REQUEST_BODY.
        Mục đích: Đính kèm `height` vào các bản ghi log mạng (SEND, DROP, DELAY, ...) theo chuẩn Mục 6.
        """
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

        # Lưu lại height tương ứng với block_hash để tra cứu khi nhận gói BODY/REQUEST_BODY
        block_hash = H(encode(header.body()))
        self.block_heights[block_hash] = header.height
        return header.height

    def broadcast(self, src, msg):
        """
        Phát tán thông điệp từ node `src` tới tất cả các node lân cận trong topo (`self.peers[src]`).

        Công việc thực hiện:
        1. Gọi hàm `send(src, dst, msg)` tới từng peer theo thứ tự tăng dần.
        2. Tự động chuyển phát cục bộ (Local Delivery) cho chính node `src` tại `self.now`
           (vì node không gửi tin cho chính mình qua mạng ngoài).
        3. Ghi log sự kiện `LOCAL_DELIVERY`.
        """
        height = self._message_height(msg)
        for dst in sorted(self.peers[src]):
            self.send(src, dst, msg)
        self.push(self.now, "MSG", src, src, msg)
        self.log(self._node_name(src), "LOCAL_DELIVERY", type=msg[0],
                 height=height)

    def send(self, src, dst, msg):
        """
        Gửi thông điệp đơn điểm (Unicast) từ node `src` tới node `dst`.

        Công việc thực hiện:
        1. Kiểm tra tính hợp lệ của đường truyền: src và dst phải nằm trong phạm vi và có kết nối topo.
        2. Nếu gửi cho chính mình (src == dst): chuyển phát nội bộ ngay lập tức.
        3. Áp dụng giới hạn tốc độ gửi (Outbound Rate Limit) qua `_reserve_send_time`:
           - Nếu vi phạm hạn mức: hoãn gửi, ghi log `DELAY reason=rate_limit`,
             và đẩy sự kiện `SEND_READY` vào hàng đợi để chờ đến lượt gửi trong tương lai.
           - Nếu chưa vượt hạn mức: chuyển tiếp ngay tới `_transmit` để truyền tin qua mạng.
        """
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

        # Kiểm tra Outbound Rate Limiting
        send_at = self._reserve_send_time(src, dst)
        if send_at > self.now:
            self.log(self._node_name(src), "DELAY", dst=self._node_name(dst),
                     type=msg[0], height=height, reason="rate_limit",
                     until=send_at)
            self.push(send_at, "SEND_READY", src, dst, msg)
            return
        self._transmit(src, dst, msg)

    def _reserve_send_time(self, src, dst):
        """
        Thuật toán cửa sổ trượt (Sliding Window) để quản lý giới hạn tốc độ gửi (Outbound Rate Limit).

        Công việc thực hiện:
        1. Nếu không cấu hình rate_limit -> cho phép gửi ngay lập tức (`self.now`).
        2. Lấy danh sách các mốc thời gian đã gửi gần nhất trong khoảng cửa sổ `[now - window, now]`.
        3. Tìm thời điểm sớm nhất `candidate` sao cho trong cửa sổ `[candidate - window, candidate]`
           tổng số gói gửi không vượt quá `max_messages`.
        4. Ghi nhận `candidate` vào lịch sử gửi và trả về thời điểm được phép gửi tin.
        """
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
        """
        Mô phỏng quá trình truyền dẫn vật lý của gói tin qua môi trường mạng không tin cậy.

        Công việc thực hiện:
        1. Ghi log sự kiện `SEND`.
        2. Mô phỏng rớt gói tin trước GST (Mô hình Bán đồng bộ - Kịch bản T5):
           - Nếu `now < gst` và ngẫu nhiên < `pre_gst_drop_probability`:
             hủy gói tin, ghi log `DROP reason=pre_gst`, kết thúc.
        3. Mô phỏng nhân bản gói tin (Packet Duplication - Kịch bản T2):
           - Nếu ngẫu nhiên < `duplicate_probability`: tạo 2 bản sao (`copies = 2`), ghi log `DUPLICATE`.
        4. Tính toán độ trễ mạng ngẫu nhiên (`_delivery_delay`) cho từng bản sao.
        5. Ghi log `DELAY` (nếu có độ trễ) và đưa sự kiện `MSG` vào hàng đợi với mốc đến: `self.now + delay`.
        """
        height = self._message_height(msg)
        self.log(self._node_name(src), "SEND", dst=self._node_name(dst),
                 type=msg[0], height=height)

        # Mô phỏng lỗi rơi gói trước mốc GST (Global Stabilization Time)
        before_gst = self.now < self.gst
        if before_gst and self.rng.random() < self.pre_gst_drop_probability:
            self.log(self._node_name(src), "DROP", dst=self._node_name(dst),
                     type=msg[0], height=height, reason="pre_gst")
            return

        # Mô phỏng lỗi nhân bản gói tin
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
        """
        Tính toán độ trễ lan truyền gói tin trên đường truyền từ `src` tới `dst`.

        Công việc thực hiện:
        1. Trước GST (mạng chưa ổn định):
           - Sinh độ trễ ngẫu nhiên lớn trong khoảng `[0, pre_gst_max_delay]`.
           - Mô phỏng đảo thứ tự gói tin (Reordering): nếu ngẫu nhiên < `pre_gst_reorder_probability`,
             cộng thêm độ trễ phụ để gói tin đến sau các gói phát hành muộn hơn.
        2. Sau GST (mạng đã ổn định):
           - Độ trễ tuân thủ nghiêm ngặt cận trên: sinh ngẫu nhiên trong khoảng `[0, bound]`,
             với `bound` lấy từ `link_delays` (nếu cấu hình) hoặc giá trị mặc định `delta`.
        """
        if before_gst:
            delay = self.rng.randint(0, self.pre_gst_max_delay)
            reordered = (
                self.rng.random() < self.pre_gst_reorder_probability
                and self.pre_gst_max_delay > 0
            )
            if reordered:
                delay += self.rng.randint(1, self.pre_gst_max_delay)
            return delay, reordered

        # Sau GST: độ trễ luôn <= delta
        bound = self.link_delays.get(frozenset((src, dst)), self.delta)
        return self.rng.randint(0, bound), False

    def _receive(self, src, dst, msg):
        """
        Xử lý sự kiện nhận gói tin tại node đích `dst`.

        Công việc thực hiện:
        1. Nếu là tin nội bộ (src == dst): chuyển thẳng vào hàm `on_message` của node nhận.
        2. Kiểm tra trạng thái tạm khóa (Peer Blocking):
           - Nếu node `src` đang trong thời gian bị `dst` khóa (`now < blocked_until`):
             hủy gói tin, ghi log `DROP reason=peer_blocked`.
        3. Áp dụng phòng vệ Inbound Rate Limit (Chống DoS / Spam từ peer quá mức):
           - Nếu số lượng gói `src` gửi tới `dst` trong khoảng `window` đạt ngưỡng `max_messages`:
             kích hoạt khóa peer `src` trong khoảng thời gian `duration`.
             Ghi log `BLOCK` và `DROP reason=peer_rate_limit`.
             Lên lịch sự kiện `UNBLOCK` tại mốc `self.now + duration`.
        4. Nếu mọi kiểm tra đều đạt: chuyển giao gói tin tới `node.on_message(msg, src)` để xử lý đồng thuận.
        """
        if src == dst:
            self.nodes[dst].on_message(msg, src)
            return

        height = self._message_height(msg)
        src_name = self._node_name(src)
        dst_name = self._node_name(dst)

        # Kiểm tra xem peer gửi có đang bị chặn hay không
        blocked_until = self.blocked_peers.get((dst, src))
        if blocked_until is not None and self.now < blocked_until:
            self.log(dst_name, "DROP", src=src_name, type=msg[0],
                     height=height, reason="peer_blocked")
            return

        # Kiểm tra tần suất nhận tin từ peer (Inbound Peer Throttling)
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

        # Chuyển giao thông điệp vào tầng ứng dụng của validator
        self.nodes[dst].on_message(msg, src)

    def set_timeout(self, idx, delay, key):
        """
        Đặt bộ đếm thời gian (Timeout Timer) cho validator `idx`.
        Đẩy sự kiện 'TIMEOUT' vào hàng đợi với mốc kích hoạt là `self.now + delay`.
        Phục vụ cơ chế timeout của Tendermint (TimeoutPropose, TimeoutPrevote, TimeoutPrecommit).
        """
        self.push(self.now + delay, "TIMEOUT", None, idx, key)

    def run(self, t_end):
        """
        Vòng lặp sự kiện chính của bộ mô phỏng biến cố rời rạc (DES Dispatcher Loop).

        Công việc thực hiện:
        1. Khởi động mạng: Đẩy sự kiện 'START' tại t=0 cho toàn bộ n validator.
        2. Vòng lặp điều phối:
           - Rút sự kiện có mốc thời gian sớm nhất từ hàng đợi `heapq.heappop`.
           - Nếu thời gian sự kiện vượt quá giới hạn mô phỏng `t_end` -> dừng.
           - Cập nhật đồng hồ ảo nhảy cóc tức thì: `self.now = t`.
           - Phân phối xử lý theo loại sự kiện:
             + 'START': Gọi `node.start()` để bắt đầu Height 1 Round 0.
             + 'MSG': Gọi `_receive(src, dst, payload)` để giao nhận tin.
             + 'SEND_READY': Giải phóng gói tin bị trễ do rate limit qua `_transmit`.
             + 'UNBLOCK': Gỡ bỏ lệnh chặn peer khi hết hạn phạt và ghi log `UNBLOCK`.
             + 'TIMEOUT': Gọi `node.on_timeout(payload)` để xử lý hết giờ chuyển bước/round.
        3. Dừng sớm nếu toàn bộ validator đã hoàn thành số height mục tiêu (`all(node.done)`).
        """
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
            honest_nodes = [node for node in self.nodes if not getattr(node, "is_byzantine", False)]
            target_nodes = honest_nodes if honest_nodes else self.nodes
            if target_nodes and all(node.done for node in target_nodes):
                break
