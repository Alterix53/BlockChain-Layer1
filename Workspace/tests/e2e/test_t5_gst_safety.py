"""
Kịch bản T5: Drop / Delay Before Synchrony - GST (Mục 9.5 Đề bài & Đặc tả Lab 01)
Điều kiện mạng:
- Mạng bán đồng bộ (Partial Synchrony): Trước mốc GST, mạng cực kỳ hỗn loạn (rớt gói, trễ lớn).
- Sau GST: Mạng ổn định, không rớt gói, độ trễ bị chặn bởi delta.
Kỳ vọng:
- Các gói tin rớt trước GST được ghi log rõ ràng: ev=DROP reason=pre_gst.
- Bất biến Safety tuyệt đối: Không bao giờ có 2 block khác nhau (khác hash) được commit
  ở cùng một chiều cao height giữa bất kỳ validator trung thực nào:
  Vforall h, |{ node.ledger[h].hash() | node honest }| <= 1.
- Mọi block được chốt đều có CommitCertificate hợp lệ với >= 2f + 1 chữ ký PRECOMMIT.
"""
import unittest
from src.main import run_sim
from tests.c_helpers import (
    assert_honest_certificates,
    assert_honest_safety,
    load_cfg,
    log_events,
)


class TestT5GstSafety(unittest.TestCase):
    def test_t5_pre_gst_drops_and_delays_preserve_safety(self):
        # Kiểm thử trên nhiều hạt giống ngẫu nhiên (seeds) để kiểm tra tính bền vững của Safety
        for seed in (42, 43, 44, 99):
            with self.subTest(seed=seed):
                cfg = load_cfg(
                    seed=seed,
                    gst=1500,
                    pre_gst_max_delay=200,
                    pre_gst_drop_probability=0.15,
                    pre_gst_reorder_probability=0.2,
                    delta=20,
                    heights=5,
                )
                net = run_sim(cfg)

                # 1. Kiểm tra sự kiện DROP trước GST
                drop_events = [r for r in log_events(net, "DROP") if r.get("reason") == "pre_gst"]
                self.assertTrue(len(drop_events) > 0, "Phải ghi nhận sự kiện DROP reason=pre_gst")

                # 2. Bất biến Safety tuyệt đối: Quét toàn bộ ledger của tất cả các node
                assert_honest_safety(net.nodes, set())
                assert_honest_certificates(net.nodes, set())

                # 3. Khẳng định không có 2 block khác nhau ở cùng height
                max_height = max(len(nd.ledger) for nd in net.nodes)
                for h in range(max_height):
                    committed_hashes = {
                        nd.ledger[h].hash()
                        for nd in net.nodes
                        if len(nd.ledger) > h
                    }
                    self.assertLessEqual(len(committed_hashes), 1,
                                         f"Phát hiện FORK ở height {h + 1}: {committed_hashes}")

    def test_t5_extreme_pre_gst_partition_safety(self):
        # Kiểm thử kịch bản rớt gói tin cực nặng (drop 40%) trước GST
        cfg = load_cfg(
            seed=7,
            gst=2000,
            pre_gst_max_delay=300,
            pre_gst_drop_probability=0.40,
            pre_gst_reorder_probability=0.30,
            delta=20,
            heights=3,
        )
        net = run_sim(cfg)

        # Mạng cực kỳ nhiễu loạn nhưng Safety không bao giờ bị vi phạm
        assert_honest_safety(net.nodes, set())
        assert_honest_certificates(net.nodes, set())


if __name__ == "__main__":
    unittest.main()

