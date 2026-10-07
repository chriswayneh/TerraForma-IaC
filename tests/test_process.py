import os
import sys
import time

import pytest

from terraforma.process import run_bounded
from terraforma.sandbox import ValidationSandbox


def execute(tmp_path, script, **options):
    return run_bounded(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout=options.pop("timeout", 5),
        **options,
    )


def test_capture_both_streams_and_exit_status(tmp_path):
    result = execute(tmp_path, "import os; os.write(1,b'output'); os.write(2,b'error'); exit(7)")
    assert result.returncode == 7
    assert result.stdout == b"output" and result.stderr == b"error"
    assert result.failure is None


@pytest.mark.parametrize("descriptor", [1, 2])
def test_noisy_stream_fails_and_retains_only_bounded_prefix(tmp_path, descriptor):
    result = execute(
        tmp_path,
        f"import os; os.write({descriptor},b'x'*131072)",
        stream_limit=1024,
    )
    assert result.returncode == -1
    assert "output exceeded" in result.failure
    assert len(result.stdout) <= 1024 and len(result.stderr) <= 1024
    assert (result.stdout if descriptor == 1 else result.stderr) == b"x" * 1024


def test_exact_output_limit_is_allowed(tmp_path):
    result = execute(tmp_path, "import os; os.write(1,b'x'*1024)", stream_limit=1024)
    assert result.returncode == 0 and result.failure is None
    assert result.stdout == b"x" * 1024


def test_timeout_retains_partial_output_and_terminates_command(tmp_path):
    started = time.monotonic()
    result = execute(
        tmp_path,
        "import os,time; os.write(1,b'before timeout'); time.sleep(30)",
        timeout=1,
    )
    assert result.returncode == -1 and "timed out" in result.failure
    assert result.stdout == b"before timeout"
    assert time.monotonic() - started < 8


def test_simultaneous_streams_cannot_block_each_other(tmp_path):
    result = execute(
        tmp_path,
        "import os,threading; "
        "t=threading.Thread(target=lambda:os.write(1,b'a'*65536)); "
        "t.start(); os.write(2,b'b'*65536); t.join()",
        stream_limit=65536,
    )
    assert result.returncode == 0 and result.failure is None
    assert result.stdout == b"a" * 65536 and result.stderr == b"b" * 65536


def test_native_command_cannot_wait_for_terminal_input(tmp_path):
    result = execute(tmp_path, "import sys; print(repr(sys.stdin.read()))")
    assert result.returncode == 0 and result.stdout.strip() == b"''"


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_deadline_is_rejected_before_launch(tmp_path, timeout):
    with pytest.raises(ValueError):
        execute(tmp_path, "raise RuntimeError('must not run')", timeout=timeout)
    with pytest.raises(ValueError):
        ValidationSandbox("terraform {}", timeout=timeout)


def test_sandbox_output_overflow_cannot_report_success():
    with ValidationSandbox("terraform {}") as sandbox:
        code, output = sandbox._execute(
            [sys.executable, "-c", "import os; os.write(1,b'x'*1048576)"]
        )
    assert code == -1 and "output exceeded" in output
    assert len(output) < 513 * 1024
