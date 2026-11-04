"""Independent BoundaryAndCLIContracts regression cases."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from src import execution
from src.common import sign
from src.main import validate_config
from tests.c_helpers import CHAIN, WORKSPACE, load_cfg, signed_tx
from tests.regression.fixtures import fast_cfg


class BoundaryAndCLIContracts(unittest.TestCase):
    def test_config_rejects_invalid_fault_model_and_account_names(self):
        cases = [dict(n=8, f=2), dict(n=True), dict(accounts=["Alice", "Alice"]),
                 dict(accounts=["Alice/child"]), dict(accounts=[""]), dict(heights=0),
                 dict(byzantine={"10": {"behavior": "silent"}}),
                 dict(byzantine={str(i): {"behavior": "silent"} for i in range(4)})]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_config(load_cfg(**change))

    def test_nested_sender_cannot_write_foreign_namespace(self):
        from tests.c_helpers import ACCOUNTS
        sender = "Alice/child"
        tx = replace(signed_tx(1), sender=sender, key="Alice/child/x")
        tx = replace(tx, sig=sign(ACCOUNTS["Alice"], "TX:" + CHAIN, tx.body()))
        state = execution.State()
        self.assertEqual(execution.apply_tx(state, tx, CHAIN, {sender: ACCOUNTS["Alice"].pk}), "not_owner")
        self.assertEqual(state.data, {})

    def _cli(self, cfg, config_path, log_path):
        config_path.write_text(json.dumps(cfg), encoding="utf-8")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-X", "utf8", "-B", "-m", "src.main", "--config", str(config_path),
                               "--log", str(log_path), "--twice"], cwd=WORKSPACE, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_incomplete_cli_fails_instead_of_reporting_deterministic_success(self):
        with tempfile.TemporaryDirectory(prefix="lab01-cli-") as folder:
            folder = Path(folder)
            result = self._cli(fast_cfg(t_end=0), folder / "config.json", folder / "run.log")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("INCOMPLETE", result.stderr)
            self.assertNotIn("OK:", result.stdout)
            self.assertNotIn("True", result.stdout)

    def test_twice_logs_match_across_independent_processes(self):
        with tempfile.TemporaryDirectory(prefix="lab01-cli-") as folder:
            folder = Path(folder)
            cfg = fast_cfg(accounts=["Alice"], txs_per_account=2)
            first = self._cli(cfg, folder / "config.json", folder / "one.log")
            second = self._cli(cfg, folder / "config.json", folder / "two.log")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("True", first.stdout)
            self.assertIn("OK: 2", first.stdout)
            self.assertEqual(first.stdout, second.stdout)
            logs = [(folder / name).read_bytes() for name in ("one.log", "one.second.log", "two.log", "two.second.log")]
            self.assertTrue(all(raw == logs[0] for raw in logs))
