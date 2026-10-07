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


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("ending", ["exit", "timeout", "overflow"])
def test_managed_child_stops_when_command_finishes(tmp_path, ending, nested):
    marker = tmp_path / "child-survived.txt"
    ready = tmp_path / "child-ready.txt"
    child = (
        "from pathlib import Path; import time; "
        f"Path({str(ready)!r}).write_text('ready', encoding='utf-8'); "
        "time.sleep(2); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    if nested:
        child = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
        )
    script = (
        "import subprocess,sys,time,os; from pathlib import Path; "
        "time.sleep(0.1); "
        f"child=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"ready=Path({str(ready)!r}); "
        "deadline=time.monotonic()+3\n"
        "while not ready.exists():\n"
        " if time.monotonic()>deadline: raise RuntimeError('child did not start')\n"
        " time.sleep(0.01)\n"
        "os.write(1,b'child started')\n"
    )
    if ending == "timeout":
        script += "time.sleep(30)"
    elif ending == "overflow":
        script += "os.write(2,b'x'*131072); time.sleep(30)"
    result = execute(tmp_path, script, timeout=1 if ending == "timeout" else 5, stream_limit=1024)
    assert ready.exists()
    assert result.stdout == b"child started"
    if ending == "exit":
        assert result.returncode == 0 and result.failure is None
    else:
        assert result.returncode == -1
        assert ("timed out" if ending == "timeout" else "output exceeded") in result.failure
    time.sleep(2.2)
    assert not marker.exists()


def test_launch_failure_releases_process_group(tmp_path):
    with pytest.raises(OSError):
        run_bounded(
            [str(tmp_path / "missing-command")],
            cwd=str(tmp_path),
            env=os.environ.copy(),
            timeout=1,
        )


def test_short_commands_keep_their_output_and_exit_code(tmp_path):
    for _ in range(20):
        result = execute(tmp_path, "print('complete'); exit(3)")
        assert result.returncode == 3
        assert result.stdout == (b"complete\r\n" if os.name == "nt" else b"complete\n")
        assert result.failure is None


def test_group_attachment_failure_stops_launched_parent(tmp_path, monkeypatch):
    from terraforma.process_group import ProcessGroup

    marker = tmp_path / "parent-survived.txt"

    def reject(self, process):
        raise OSError("attachment unavailable")

    monkeypatch.setattr(ProcessGroup, "attach", reject)
    with pytest.raises(OSError, match="attachment unavailable"):
        execute(
            tmp_path,
            "import time; from pathlib import Path; time.sleep(2); "
            f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')",
        )
    time.sleep(2.2)
    assert not marker.exists()
