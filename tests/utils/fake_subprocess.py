"""Test helper: fake subprocess runner utilities.

Provides:
- make_completed_process(cmd, returncode=0, stdout='', stderr='') -> CompletedProcess-like
- FakeSubprocess: callable object mapping command signatures to CompletedProcess-like results

Usage example in tests:

    from tests.utils.fake_subprocess import make_completed_process, FakeSubprocess

    fake = FakeSubprocess()
    fake.when("tc qdisc show").then_stdout("htb 1:")
    engine.set_subprocess_runner(fake)

The FakeSubprocess supports simple substring matching of the joined cmd list.
"""
from __future__ import annotations
from typing import List, Tuple, Callable
import subprocess


def make_completed_process(cmd, returncode: int = 0, stdout: str = "", stderr: str = ""):
    try:
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    except Exception:
        class _Dummy:
            def __init__(self, args, rc, out, err):
                self.args = args
                self.returncode = rc
                self.stdout = out
                self.stderr = err

        return _Dummy(cmd, returncode, stdout, stderr)


class FakeSubprocess:
    """A small callable object to fake subprocess.run-like behavior.

    - Use when(...) to register expected command substrings and responses.
    - When called, it finds the first registered rule where the substring is in the joined command.
    - Returns a CompletedProcess-like object.
    """

    def __init__(self):
        self._rules: List[Tuple[str, Callable[[], subprocess.CompletedProcess]]] = []

    def when(self, cmd_substring: str):
        class _Then:
            def __init__(self, parent: FakeSubprocess, substr: str):
                self.parent = parent
                self.substr = substr

            def then_stdout(self, stdout: str, returncode: int = 0, stderr: str = ""):
                def factory():
                    return make_completed_process(self.substr, returncode=returncode, stdout=stdout, stderr=stderr)

                self.parent._rules.append((self.substr, factory))
                return self.parent

            def then_result(self, completed):
                def factory():
                    return completed

                self.parent._rules.append((self.substr, factory))
                return self.parent

        return _Then(self, cmd_substring)

    def __call__(self, cmd, **kwargs):
        # normalize cmd to a string for matching
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for substr, factory in self._rules:
            if substr in joined:
                return factory()
        # default: return a successful empty result
        return make_completed_process(cmd, 0, stdout="", stderr="")
