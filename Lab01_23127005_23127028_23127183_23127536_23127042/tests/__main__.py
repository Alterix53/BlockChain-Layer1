"""Run the same unittest suite with per-test event files and a result index."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

from tests.event_logs import EventLogCapture

WORKSPACE = Path(__file__).resolve().parents[1]


class LoggedResult(unittest.TextTestResult):
    def startTestRun(self):
        super().startTestRun()
        self.records = []
        self.capture = None

    def _fixture_record(self, test, status, text):
        # unittest reports setUpClass/tearDownClass errors without startTest().
        path = self.log_dir / f'fixture-{len(self.records) + 1:04d}.log'
        path.write_text(f'# test={test.id()}\n# outcome={status}\n{text}\n', encoding='utf-8')
        self.records.append(dict(test=test.id(), status=status, log=path.name))
        self._write_index()

    def startTest(self, test):
        super().startTest(test)
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', test.id().split('.')[-1])[:85]
        path = self.log_dir / f'{self.testsRun:04d}-{name}.log'
        self.current = dict(test=test.id(), status='running', log=path.name)
        self.capture = EventLogCapture(path, test.id())
        self.capture.__enter__()

    def _status(self, status):
        self.current['status'] = status

    def addSuccess(self, test):
        super().addSuccess(test)
        self._status('passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._status('failed')
        self.capture.stream.write('# FAILURE\n' + self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        if self.capture is None:
            self._fixture_record(test, 'error', self._exc_info_to_string(err, test))
            return
        self._status('error')
        self.capture.stream.write('# ERROR\n' + self._exc_info_to_string(err, test))

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._status('failed' if issubclass(err[0], test.failureException) else 'error')
            self.capture.stream.write(f'# SUBTEST {subtest}\n' + self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.capture is None:
            self._fixture_record(test, 'skipped', reason)
            return
        self._status('skipped')
        self.current['reason'] = reason

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._status('expected_failure')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._status('unexpected_success')

    def stopTest(self, test):
        try:
            self.capture.stream.write(f"# outcome={self.current['status']}\n")
            self.capture.__exit__(None, None, None)
            self.capture = None
            self.records.append(self.current)
            self._write_index()
        finally:
            super().stopTest(test)

    def _write_index(self):
        index = dict(tests_run=self.testsRun, successful=self.wasSuccessful(), tests=self.records)
        (self.log_dir / 'summary.json').write_text(json.dumps(index, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def stopTestRun(self):
        self._write_index()
        super().stopTestRun()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tests', nargs='*', help='Optional unittest test IDs; default: entire suite')
    parser.add_argument('--log-dir', default='logs/tests', help='Parent directory for a fresh run folder')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args(argv)
    parent = Path(args.log_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    class Result(LoggedResult):
        log_dir = directory
    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromNames(args.tests) if args.tests else
             loader.discover(str(WORKSPACE / 'tests'), top_level_dir=str(WORKSPACE)))
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, resultclass=Result).run(suite)
    print(f'Test event logs: {directory}')
    print(f'Result index: {directory / "summary.json"}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
