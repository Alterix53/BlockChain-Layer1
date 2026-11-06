"""Event observer and unittest result handling."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from src.sim import Net
from tests.__main__ import LoggedResult
from tests.c_helpers import RecordingNet
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
