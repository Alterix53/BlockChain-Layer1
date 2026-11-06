"""Safety and progress assertions against synthetic ledgers."""
import unittest
from types import SimpleNamespace
from tests.c_helpers import assert_honest_safety, assert_honest_progress


class TestSafetyChecker(unittest.TestCase):
    """Kiểm chính hàm kiểm safety bằng ledger giả (không phải fork của mạng thật)."""

    @staticmethod
    def fake(idx, *hashes):
        blocks = [SimpleNamespace(header=SimpleNamespace(height=h + 1), hash=lambda x=x: x)
                  for h, x in enumerate(hashes)]
        return SimpleNamespace(idx=idx, name=f"V{idx}", ledger=blocks)

    def test_same_chain_ok(self):
        assert_honest_safety([self.fake(0, b"A"), self.fake(1, b"A")], set())

    def test_fork_detected_even_with_empty_ledger(self):
        # main.check_safety lấy min độ dài ledger = 0 nên bỏ sót ca này
        nodes = [self.fake(0, b"A"), self.fake(1, b"B"), self.fake(2)]
        with self.assertRaisesRegex(AssertionError, "FORK"):
            assert_honest_safety(nodes, set())

    def test_byzantine_ledger_ignored(self):
        assert_honest_safety([self.fake(0, b"A"), self.fake(1, b"B")], {"V1"})

    def test_progress_detects_stalled_honest(self):
        with self.assertRaisesRegex(AssertionError, "chưa chốt đủ"):
            assert_honest_progress([self.fake(0, b"A"), self.fake(1)], set(), heights=1)
