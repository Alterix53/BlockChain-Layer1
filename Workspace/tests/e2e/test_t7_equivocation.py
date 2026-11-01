"""
Kịch bản T7: Up to f Byzantine Validators Equivocate (Mục 9.7 Đề bài & Đặc tả Lab 01)
Mục tiêu & Cơ sở toán học:
- Chứng minh bằng thực nghiệm Định lý giao điểm Quorum (Quorum Intersection Theorem).
- Với n = 3f + 1 = 10, f = 3, Quorum Q = 2f + 1 = 7:
  Hai Quorum bất kỳ Q1 và Q2 giao nhau ít nhất:
  |Q1 ∩ Q2| >= 2Q - n = 2(7) - 10 = 4 validator.
- Do số lượng validator Byzantine tối đa là f = 3:
  |Q1 ∩ Q2 ∩ Honest| >= 4 - 3 = 1 validator trung thực.
- Validator trung thực này tuân thủ Quy tắc 1 & 2 (tối đa 1 vote PREVOTE/PRECOMMIT mỗi slot)
  và Quy tắc 7 (chỉ đếm 1 phiếu duy nhất từ mỗi voter).
  Do đó, hai block mâu thuẫn không bao giờ có thể cùng lúc thu thập đủ >= Q chữ ký PRECOMMIT.
- Kết quả: Không bao giờ xảy ra Fork giữa các node trung thực, đảm bảo tính Safety tuyệt đối.
- Chuỗi vẫn tiếp tục tiến lên, bảo đảm Liveness và các block được chốt đều có CommitCertificate hợp lệ.
"""
import unittest
from src.byzantine import EquivocateProposer, EquivocateVoter
from tests.c_helpers import (
    assert_honest_certificates,
    assert_honest_progress,
    assert_honest_safety,
    log_events,
    run_with_byzantine,
)


class TestT7Equivocation(unittest.TestCase):
    def test_t7_equivocating_proposer_broadcast(self):
        """
        Proposer Byzantine (V1 tại height 1 round 0) phát tán 2 block hợp lệ nhưng khác hash
        tới toàn bộ mạng.
        - Các node honest phát hiện hành vi đề xuất 2 mặt và ghi nhận log EQUIVOCATION.
        - Giữ block đến trước để prevote, nhưng lưu cả 2 body để nếu block kia đạt Quorum vẫn xử lý được.
        - Quorum Intersection Theorem đảm bảo không bao giờ xảy ra Fork.
        - Mạng vẫn chốt đủ 5 block trên mọi node honest.
        """
        behaviors = {1: (EquivocateProposer, {"height": 1})}
        byz_indices = {1}
        byz_names = {f"V{i}" for i in byz_indices}

        net = run_with_byzantine(behaviors, seed=42)

        # 1. Xác nhận Proposer V1 đã phát tán 2 đề xuất khác nhau
        byz_props = log_events(net, "BYZ_EQUIVOCATE_PROPOSAL", node="V1")
        self.assertTrue(len(byz_props) >= 1, "V1 phải ghi log BYZ_EQUIVOCATE_PROPOSAL")

        # 2. Xác nhận các node honest đã nhận cả 2 đề xuất và ghi log EQUIVOCATION
        equiv_events = [r for r in log_events(net, "EQUIVOCATION") if r.get("proposer") == "V1"]
        self.assertTrue(len(equiv_events) >= 1, "Phải có node honest ghi log EQUIVOCATION cho proposer V1")

        # 3. Định lý giao điểm Quorum: Không bao giờ có fork giữa các node honest
        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)

    def test_t7_equivocating_proposer_partitioned(self):
        """
        Proposer Byzantine cố tình chia rẽ mạng bằng cách gửi Block A cho nhóm 1 và Block B cho nhóm 2.
        - Nhờ Định lý giao điểm Quorum (Q = 7 > n/2 = 5), hai phân vùng không thể đồng thời đạt Quorum cho 2 block khác nhau.
        - Tuyệt đối không xảy ra FORK giữa các node trung thực.
        """
        groups = ([0, 2, 4, 6], [3, 5, 7, 8])
        behaviors = {1: (EquivocateProposer, {"groups": groups, "height": 1})}
        byz_indices = {1}
        byz_names = {f"V{i}" for i in byz_indices}

        net = run_with_byzantine(behaviors, seed=42)

        byz_props = log_events(net, "BYZ_EQUIVOCATE_PROPOSAL", node="V1")
        self.assertTrue(len(byz_props) >= 1, "V1 phải ghi log BYZ_EQUIVOCATE_PROPOSAL")

        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)

    def test_t7_up_to_f_equivocating_voters(self):
        """
        Tối đa f = 3 validator Byzantine (V3, V5, V7) gian lận hai mặt (EquivocateVoter),
        ký đồng thời cả 2 phiếu PREVOTE và PRECOMMIT mâu thuẫn gửi ra mạng.
        - Node honest áp dụng Quy tắc 7: Giữ lá phiếu đến trước, log EQUIVOCATION cho lá phiếu đến sau.
        - Nhờ giao điểm Quorum có ít nhất 1 node honest, không thể xảy ra tình trạng cả 2 block cùng đạt >= Q phiếu.
        - Đảm bảo Safety tuyệt đối và Liveness được duy trì.
        """
        byz_indices = {3, 5, 7}
        byz_names = {f"V{i}" for i in byz_indices}
        behaviors = {i: (EquivocateVoter, {}) for i in byz_indices}

        net = run_with_byzantine(behaviors, seed=42)

        # 1. Xác nhận các node Byzantine đã phát sinh hành vi gian lận bỏ phiếu
        for i in byz_indices:
            byz_votes = log_events(net, "BYZ_EQUIVOCATE_VOTE", node=f"V{i}")
            self.assertTrue(len(byz_votes) >= 1, f"V{i} phải ghi log BYZ_EQUIVOCATE_VOTE")

        # 2. Xác nhận các node honest đã phát hiện và ghi log EQUIVOCATION voter=V{i}
        for i in byz_indices:
            equiv_votes = [r for r in log_events(net, "EQUIVOCATION") if r.get("voter") == f"V{i}"]
            self.assertTrue(len(equiv_votes) >= 1, f"Phải có honest node phát hiện voter V{i} equivocation")

        # 3. Quorum Intersection Theorem bảo toàn Safety và Liveness
        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)

    def test_t7_coalition_proposer_and_voters(self):
        """
        Liên minh Byzantine phối hợp: 1 Proposer đề xuất 2 mặt (V1) kết hợp với 2 Voter bỏ phiếu 2 mặt (V4, V7).
        Tổng cộng đúng f = 3 node Byzantine (n=10, f=3, Q=7).
        - Toàn bộ 7 node honest duy trì tính nhất quán, không xảy ra chia cắt mạng.
        """
        byz_indices = {1, 4, 7}
        byz_names = {f"V{i}" for i in byz_indices}
        behaviors = {
            1: (EquivocateProposer, {"groups": ([0, 2, 3], [5, 6, 8]), "height": 1}),
            4: (EquivocateVoter, {}),
            7: (EquivocateVoter, {}),
        }

        net = run_with_byzantine(behaviors, seed=42)

        # Kiểm tra không xảy ra Fork và các chứng chỉ hoàn toàn hợp lệ
        assert_honest_safety(net.nodes, byz_names)
        assert_honest_progress(net.nodes, byz_names, 5)
        assert_honest_certificates(net.nodes, byz_names)


if __name__ == "__main__":
    unittest.main()
