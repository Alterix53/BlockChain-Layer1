"""Logging must preserve assertions, failures and the original event collections."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.sim import Net
from tests.__main__ import LoggedResult
from tests.c_helpers import RecordingNet, WORKSPACE, load_cfg
from tests.event_logs import EventLogCapture


class TestEventLogging(unittest.TestCase):
    def test_observer_preserves_both_loggers_and_records_events_before_clear(self):
        original_real, original_unit = Net.log, RecordingNet.log
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.log'
            real = Net(dict(n=10, seed=1))
            fake = RecordingNet()
            with EventLogCapture(path, 'example'):
                real.log('V0', 'FINALIZE', height=1)
                fake.log('V1', 'REJECT', height=1, reason='example')
                fake.clear()
                self.assertEqual(real.logs, ['t=0 node=V0 ev=FINALIZE height=1'])
                self.assertEqual(fake.events, [])
            raw = path.read_text(encoding='utf-8')
            self.assertIn('network=1 t=0 node=V0 ev=FINALIZE height=1', raw)
            self.assertIn('network=2 t=0 node=V1 ev=REJECT height=1 reason=example', raw)
        self.assertIs(Net.log, original_real)
        self.assertIs(RecordingNet.log, original_unit)

    def test_result_retains_assertion_and_subtest_failures(self):
        class Failing(unittest.TestCase):
            def runTest(self):
                with self.subTest(case='negative-control'):
                    self.assertEqual(1, 2, 'must stay failed')
        with tempfile.TemporaryDirectory() as temp:
            class Result(LoggedResult): log_dir = Path(temp)
            result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=Result).run(Failing())
            self.assertFalse(result.wasSuccessful())
            self.assertEqual(len(result.failures), 1)
            index = json.loads((Path(temp) / 'summary.json').read_text(encoding='utf-8'))
            self.assertFalse(index['successful'])
            self.assertEqual(index['tests'][0]['status'], 'failed')
            raw = (Path(temp) / index['tests'][0]['log']).read_text(encoding='utf-8')
            self.assertIn('must stay failed', raw)
            self.assertIn('negative-control', raw)

    def test_class_setup_error_is_recorded_without_hiding_original_error(self):
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls): raise ValueError('broken-class-fixture')
            def test_not_reached(self): self.fail('not reached')
        with tempfile.TemporaryDirectory() as temp:
            class Result(LoggedResult): log_dir = Path(temp)
            result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=Result).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(Broken))
            self.assertEqual(len(result.errors), 1)
            self.assertFalse(result.wasSuccessful())
            index = json.loads((Path(temp) / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(index['tests'][0]['status'], 'error')
            self.assertIn('broken-class-fixture', (Path(temp) / index['tests'][0]['log']).read_text(encoding='utf-8'))

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
