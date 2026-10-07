import os
import stat
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.file_input import read_regular_bytes
from terraforma.plan_review import load_and_review
from terraforma.project import load_specification


def test_regular_input_reads_exact_bytes_and_only_one_over_limit(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b"\xef\xbb\xbf{}\r\n")
    assert read_regular_bytes(path, 7) == path.read_bytes()
    assert read_regular_bytes(path, 4) == b"\xef\xbb\xbf{}"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_fail_before_file_access(tmp_path, limit):
    with pytest.raises(ValueError, match="positive integer"):
        read_regular_bytes(tmp_path / "missing.json", limit)


@pytest.mark.parametrize("reader", [load_specification, load_and_review])
def test_directory_input_is_rejected_as_nonregular(tmp_path, reader):
    with pytest.raises(ValueError, match="regular file"):
        reader(tmp_path)


def test_opened_descriptor_is_rechecked_without_reading_replaced_input(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(b"private-marker")
    monkeypatch.setattr(os, "fstat", lambda descriptor: SimpleNamespace(st_mode=stat.S_IFIFO))
    with pytest.raises(ValueError, match="regular file"):
        read_regular_bytes(path, 64)
    path.unlink()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe required")
@pytest.mark.parametrize("reader", [load_specification, load_and_review])
def test_fifo_is_rejected_without_opening_it(tmp_path, monkeypatch, reader):
    path = tmp_path / "input.json"
    os.mkfifo(path)

    def forbidden(*args, **kwargs):
        raise AssertionError("A named pipe must not be opened")

    monkeypatch.setattr("builtins.open", forbidden)
    with pytest.raises(ValueError, match="regular file"):
        reader(path)


@pytest.mark.parametrize("command", ["generate", "review-plan"])
def test_cli_file_read_errors_omit_input_values(tmp_path, monkeypatch, command):
    path = tmp_path / "input.json"
    path.write_bytes(b"private-marker")
    monkeypatch.setattr(os, "fstat", lambda descriptor: SimpleNamespace(st_mode=stat.S_IFCHR))
    arguments = (
        ["generate", "--spec", str(path), "--dir", str(tmp_path / "output")]
        if command == "generate"
        else ["review-plan", "--file", str(path)]
    )
    result = CliRunner().invoke(main, arguments)
    assert result.exit_code != 0
    assert "private-marker" not in result.output
    assert not (tmp_path / "output").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe required")
def test_regular_file_replaced_by_fifo_during_open_does_not_block(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(b"{}")
    original_open = os.open

    def replace_before_open(name, flags, *args, **kwargs):
        assert flags & os.O_NONBLOCK
        path.unlink()
        os.mkfifo(path)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_before_open)
    with pytest.raises(ValueError, match="regular file"):
        read_regular_bytes(path, 64)
