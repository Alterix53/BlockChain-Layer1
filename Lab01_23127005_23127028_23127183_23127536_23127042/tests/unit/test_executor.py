import unittest
from src.common import H, KeyPair, Tx, sign
from src.execution import State, apply_tx, apply_txs

CHAIN_ID = "testnet-lab01"


def create_signed_tx(acct_name: str, keypair: KeyPair, nonce: int, key: str, value: str, domain_override: str = None) -> Tx:
    """Tạo Tx và ký đúng chuẩn common.py (domain TX:chain_id)."""
    t = Tx(acct_name, nonce, key, value)
    domain = domain_override if domain_override is not None else ("TX:" + CHAIN_ID)
    sig = sign(keypair, domain, t.body())
    return Tx(*t.body(), sig=sig)


class TestExecutor(unittest.TestCase):
    """Tầng thực thi (phần D). Viết lại thành unittest để chạy chung lệnh của nhóm; nội dung giữ nguyên."""

    def test_valid_tx_execution(self):
        """Kiểm tra giao dịch hợp lệ cập nhật đúng dữ liệu và tăng nonce."""
        kp_alice = KeyPair(b"alice_seed")
        acct_pks = {"Alice": kp_alice.pk}
        state = State()

        tx = create_signed_tx("Alice", kp_alice, nonce=1, key="Alice/status", value="active")
        err = apply_tx(state, tx, CHAIN_ID, acct_pks)

        assert err is None
        assert state.data.get("Alice/status") == "active"
        assert state.nonces.get("Alice") == 1
        assert len(state.hash()) == 32

    def test_invalid_signature_rejection(self):
        """Kiểm tra chữ ký bị giả mạo hoặc ký sai khóa."""
        kp_alice = KeyPair(b"alice_seed")
        kp_eve = KeyPair(b"eve_seed")
        acct_pks = {"Alice": kp_alice.pk, "Eve": kp_eve.pk}
        state = State()

        # Eve ký nhưng mạo danh sender là Alice
        tx = create_signed_tx("Alice", kp_eve, nonce=1, key="Alice/status", value="hacked")
        err = apply_tx(state, tx, CHAIN_ID, acct_pks)

        assert err == "bad_tx_sig"

    def test_wrong_domain_rejection(self):
        """Kiểm tra từ chối chữ ký hợp lệ nhưng sai domain separation."""
        kp_alice = KeyPair(b"alice_seed")
        acct_pks = {"Alice": kp_alice.pk}
        state = State()

        # Ký dưới domain VOTE thay vì TX
        tx = create_signed_tx("Alice", kp_alice, nonce=1, key="Alice/data", value="val", domain_override="VOTE:" + CHAIN_ID)
        err = apply_tx(state, tx, CHAIN_ID, acct_pks)

        assert err == "bad_tx_sig"

    def test_unauthorized_namespace(self):
        """Kiểm tra Alice cố tình sửa dữ liệu trong namespace của Bob."""
        kp_alice = KeyPair(b"alice_seed")
        acct_pks = {"Alice": kp_alice.pk}
        state = State()

        # Alice ghi vào key 'Bob/...'
        tx = create_signed_tx("Alice", kp_alice, nonce=1, key="Bob/balance", value="1000")
        err = apply_tx(state, tx, CHAIN_ID, acct_pks)

        assert err == "not_owner"

    def test_nonce_rules_replay_and_gap(self):
        """Kiểm tra cơ chế nonce tuần tự: chống replay và chống gap."""
        kp_alice = KeyPair(b"alice_seed")
        acct_pks = {"Alice": kp_alice.pk}
        state = State()

        # 1. Nonce 1: Hợp lệ
        tx1 = create_signed_tx("Alice", kp_alice, nonce=1, key="Alice/msg", value="msg1")
        assert apply_tx(state, tx1, CHAIN_ID, acct_pks) is None
        assert state.nonces.get("Alice") == 1

        # 2. Replay Nonce 1: Bị từ chối do bad_nonce
        assert apply_tx(state, tx1, CHAIN_ID, acct_pks) == "bad_nonce"

        # 3. Nonce Gap: Gửi nonce = 3 khi nonce hiện tại mới là 1
        tx3 = create_signed_tx("Alice", kp_alice, nonce=3, key="Alice/msg", value="msg3")
        assert apply_tx(state, tx3, CHAIN_ID, acct_pks) == "bad_nonce"

        # 4. Nonce 2: Hợp lệ
        tx2 = create_signed_tx("Alice", kp_alice, nonce=2, key="Alice/msg", value="msg2")
        assert apply_tx(state, tx2, CHAIN_ID, acct_pks) is None
        assert state.nonces.get("Alice") == 2

    def test_deterministic_state_hash(self):
        """Kiểm tra tính tất định của state.hash() khi nạp dữ liệu khác thứ tự."""
        state_a = State()
        state_b = State()

        state_a.data = {"z_key": "1", "a_key": "2", "m_key": "3"}
        state_a.nonces = {"user_2": 10, "user_1": 5}

        state_b.data = {"m_key": "3", "a_key": "2", "z_key": "1"}
        state_b.nonces = {"user_1": 5, "user_2": 10}

        assert state_a.hash() == state_b.hash()


if __name__ == "__main__":
    unittest.main()
