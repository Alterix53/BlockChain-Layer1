"""Optional test-only event observer; never alters simulator logs or assertions."""
from contextlib import ExitStack
from pathlib import Path
import subprocess
from unittest import mock

from src.sim import Net
from tests.c_helpers import RecordingNet


class EventLogCapture:
    def __init__(self, path, test_id):
        self.path = Path(path)
        self.test_id = test_id
        self.networks = []
        self.stack = ExitStack()

    def __enter__(self):
        self.stream = self.stack.enter_context(self.path.open('w', encoding='utf-8'))
        self.stream.write(f'# test={self.test_id}\n')
        try:
            for cls, field in ((Net, 'logs'), (RecordingNet, 'events')):
                original = cls.log
                def observed(net, *args, _original=original, _field=field, **kwargs):
                    result = _original(net, *args, **kwargs)
                    row = getattr(net, _field)[-1]
                    line = row if isinstance(row, str) else ' '.join(f'{k}={v}' for k, v in row.items())
                    self._event(net, line)
                    return result
                self.stack.enter_context(mock.patch.object(cls, 'log', observed))
            original_run = subprocess.run
            def observed_run(*args, **kwargs):
                result = original_run(*args, **kwargs)
                command = args[0] if args else kwargs.get('args')
                if isinstance(command, (list, tuple)) and '--log' in command:
                    index = command.index('--log')
                    if index + 1 < len(command):
                        path = Path(command[index + 1])
                        if not path.is_absolute():
                            path = Path(kwargs.get('cwd') or Path.cwd()) / path
                        self.stream.write(f'# CLI returncode={result.returncode}\n')
                        for output in (path, path.with_name(path.stem + '.second' + path.suffix)):
                            if output.is_file():
                                self.stream.write(f'# CLI file={output.name}\n')
                                self.stream.write(output.read_text(encoding='utf-8'))
                        for label in ('stdout', 'stderr'):
                            value = getattr(result, label, None)
                            if value:
                                if isinstance(value, bytes): value = value.decode('utf-8', errors='replace')
                                self.stream.write(f'# CLI {label}\n{value}\n')
                return result
            self.stack.enter_context(mock.patch.object(subprocess, 'run', observed_run))
        except BaseException:
            self.stack.close()
            raise
        return self

    def _event(self, net, line):
        if not any(net is existing for existing in self.networks):
            self.networks.append(net)
        number = next(i for i, existing in enumerate(self.networks, 1) if net is existing)
        # The prefix distinguishes multiple simulator instances in a T8 test.
        self.stream.write(f'network={number} {line}\n')

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)
