"""CLI logging integration."""
import json
from pathlib import Path
import tempfile
import unittest
from tests.c_helpers import WORKSPACE, load_cfg
from tests.event_logs import EventLogCapture
import subprocess
import sys


class TestEventLogging(unittest.TestCase):
    def test_cli_trace_is_copied_before_temp_cleanup_and_return_code_preserved(self):
        original_run = subprocess.run
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            config, log, capture = temp / 'cfg.json', temp / 'cli.log', temp / 'events.log'
            config.write_text(json.dumps(load_cfg(t_end=0)), encoding='utf-8')
            with EventLogCapture(capture, 'incomplete-cli'):
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', 'src.main',
                                         '--config', str(config), '--log', str(log)],
                                        cwd=WORKSPACE, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn('INCOMPLETE', result.stderr)
            log.unlink()
            raw = capture.read_text(encoding='utf-8')
            self.assertIn('CLI returncode=1', raw)
            self.assertIn('ev=ROUND_START', raw)
            self.assertIn('INCOMPLETE', raw)
        self.assertIs(subprocess.run, original_run)

    def test_logged_entry_point_returns_same_success_and_writes_index(self):
        with tempfile.TemporaryDirectory() as temp:
            case = 'tests.regression.test_consensus.ConsensusContracts.test_duplicate_votes_do_not_supply_quorum'
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', 'tests',
                                     '--log-dir', temp, case], cwd=WORKSPACE,
                                    capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            indices = list(Path(temp).glob('run-*/summary.json'))
            self.assertEqual(len(indices), 1)
            index = json.loads(indices[0].read_text(encoding='utf-8'))
            self.assertTrue(index['successful'])
            self.assertEqual(index['tests_run'], 1)
            self.assertEqual(index['tests'][0]['test'], case)
            raw = (indices[0].parent / index['tests'][0]['log']).read_text(encoding='utf-8')
            self.assertIn('ev=ROUND_START', raw)
            self.assertIn('outcome=passed', raw)
