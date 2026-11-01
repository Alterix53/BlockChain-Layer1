"""
Kịch bản T8: Same Seed Rerun Twice - Tính tất định 100% (Mục 9.8 Đề bài & Đặc tả Lab 01)
Mục tiêu & Cơ sở kỹ thuật:
- Chứng minh tính tất định tuyệt đối (Strict Determinism) của hệ thống mô phỏng Tendermint BFT DES.
- Chạy lại cùng một cấu hình và hạt giống giả ngẫu nhiên (PRNG seed) phải cho kết quả:
  1. net1.logs == net2.logs: Trùng khớp 100% từng dòng log, từng ký tự, từng timestamp t.
  2. state_hash_1 == state_hash_2: Mã băm trạng thái cuối cùng của mọi validator trùng khớp từng byte.
  3. ledger_1 == ledger_2: Toàn bộ danh sách khối được chốt và thứ tự giao dịch hoàn toàn như nhau.
- Bốn yếu tố đảm bảo tính tất định:
  + Bộ sinh số ngẫu nhiên cô lập theo seed: random.Random(seed).
  + Chuẩn hóa dữ liệu Canonical Serialization với encode() độc lập nền tảng.
  + Sắp xếp từ điển (Sorted Dicts) khi tính state.hash().
  + Bộ đếm seq phá vỡ thế hòa (Tie-Breaking) trong hàng đợi ưu tiên của DES.
"""
import unittest
from src.byzantine import EquivocateProposer, Silent
from src.main import run_sim
from tests.c_helpers import (
    load_cfg,
    run_with_byzantine,
)


class TestT8Determinism(unittest.TestCase):
    def test_t8_default_config_rerun_twice(self):
        """
        Chạy 2 lần liên tiếp với cấu hình mặc định (seed 42).
        Khẳng định nhật ký sự kiện và state hash cuối cùng trùng khớp 100%.
        State hash chuẩn: 0b837be96db72e1f.
        """
        cfg1 = load_cfg(seed=42)
        net1 = run_sim(cfg1)

        cfg2 = load_cfg(seed=42)
        net2 = run_sim(cfg2)

        # 1. Khớp từng byte nhật ký log
        self.assertEqual(net1.logs, net2.logs,
                         "Nhật ký sự kiện DES giữa 2 lần chạy với seed 42 phải trùng khớp từng ký tự")

        # 2. Khớp state hash cuối cùng của tất cả các node
        state_hash_1 = net1.nodes[0].state.hash()
        state_hash_2 = net2.nodes[0].state.hash()
        self.assertEqual(state_hash_1, state_hash_2,
                         "State hash giữa 2 lần chạy phải bằng nhau tuyệt đối")
        self.assertEqual(state_hash_1.hex()[:16], "0b837be96db72e1f",
                         "State hash seed 42 phải đạt giá trị chuẩn 0b837be96db72e1f")

        # 3. Khớp toàn bộ ledger trên tất cả các validator
        for i in range(len(net1.nodes)):
            l1 = [b.hash() for b in net1.nodes[i].ledger]
            l2 = [b.hash() for b in net2.nodes[i].ledger]
            self.assertEqual(l1, l2, f"Ledger của node {net1.nodes[i].name} phải giống hệt giữa 2 lần chạy")

    def test_t8_multiple_arbitrary_seeds(self):
        """
        Kiểm tra tính tất định trên nhiều hạt giống khác nhau (seed 1, 99, 1337).
        """
        for seed in (1, 99, 1337):
            with self.subTest(seed=seed):
                cfg = load_cfg(seed=seed, heights=3)
                net1 = run_sim(cfg)
                net2 = run_sim(cfg)

                self.assertEqual(net1.logs, net2.logs,
                                 f"Logs phải trùng khớp tuyệt đối với seed {seed}")
                self.assertEqual(net1.nodes[0].state.hash(), net2.nodes[0].state.hash(),
                                 f"State hash phải trùng khớp tuyệt đối với seed {seed}")

    def test_t8_chaotic_pre_gst_network_determinism(self):
        """
        Kiểm tra tính tất định trong điều kiện mạng hỗn loạn trước GST (rớt gói, trễ lớn, đảo thứ tự).
        Dù mạng xảy ra nhiều biến cố ngẫu nhiên, PRNG có định hình vẫn mang lại kết quả đồng nhất tuyệt đối.
        """
        cfg = load_cfg(
            seed=77,
            gst=400,
            pre_gst_max_delay=80,
            pre_gst_drop_probability=0.1,
            pre_gst_reorder_probability=0.15,
            heights=4,
        )
        net1 = run_sim(cfg)
        net2 = run_sim(cfg)

        self.assertEqual(net1.logs, net2.logs,
                         "Logs phải trùng khớp trong điều kiện mạng hỗn loạn")
        self.assertEqual(net1.nodes[0].state.hash(), net2.nodes[0].state.hash(),
                         "State hash phải trùng khớp trong điều kiện mạng hỗn loạn")

    def test_t8_byzantine_adversary_determinism(self):
        """
        Kiểm tra tính tất định khi có validator Byzantine hoạt động trong mạng.
        """
        behaviors = {
            1: (EquivocateProposer, {"height": 1}),
            4: (Silent, {"mode": "all"}),
        }
        net1 = run_with_byzantine(behaviors, seed=123, heights=3)
        net2 = run_with_byzantine(behaviors, seed=123, heights=3)

        self.assertEqual(net1.logs, net2.logs,
                         "Logs phải trùng khớp khi có validator Byzantine")
        self.assertEqual(net1.nodes[0].state.hash(), net2.nodes[0].state.hash(),
                         "State hash phải trùng khớp khi có validator Byzantine")


if __name__ == "__main__":
    unittest.main()

