import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import BinaryIO

from terraforma.process_group import ProcessGroup


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    failure: str | None = None


def run_bounded(
    arguments: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    timeout: float,
    stream_limit: int = 512 * 1024,
) -> CommandResult:
    if (
        not math.isfinite(timeout)
        or timeout <= 0
        or type(stream_limit) is not int
        or stream_limit <= 0
    ):
        raise ValueError("Command timeout and output limit must be positive.")
    deadline = time.monotonic() + timeout
    group = ProcessGroup()
    process = None
    try:
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            shell=False,
            start_new_session=os.name != "nt",
        )
        group.attach(process)
    except BaseException:
        try:
            group.close()
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()
        raise
    buffers = [bytearray(), bytearray()]
    finished = [threading.Event(), threading.Event()]
    overflow = threading.Event()
    stop = threading.Event()
    read_failed = threading.Event()
    lock = threading.Lock()

    def drain(stream: BinaryIO, index: int) -> None:
        try:
            while not stop.is_set():
                chunk = stream.read(8192)
                if not chunk:
                    break
                with lock:
                    remaining = stream_limit - len(buffers[index])
                    buffers[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    break
        except OSError:
            read_failed.set()
        finally:
            stream.close()
            finished[index].set()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, 0), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, 1), daemon=True),
    ]
    failure = None
    try:
        for reader in readers:
            reader.start()
        while True:
            if overflow.is_set():
                failure = f"Command output exceeded the {stream_limit} byte limit per stream."
                break
            if read_failed.is_set():
                failure = "Unable to capture complete command output."
                break
            if process.poll() is not None:
                try:
                    group.close()
                except OSError:
                    failure = "Unable to clean up the command process group."
                    break
                if all(event.is_set() for event in finished):
                    break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = f"Command timed out after {timeout:g} seconds."
                break
            stop.wait(min(0.02, remaining))
    finally:
        try:
            group.close()
        except OSError:
            failure = "Unable to clean up the command process group."
        stop.set()
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            failure = "Command did not exit after termination was requested."
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=0.1)
    with lock:
        stdout, stderr = (bytes(buffer) for buffer in buffers)
    if overflow.is_set():
        failure = f"Command output exceeded the {stream_limit} byte limit per stream."
    elif read_failed.is_set() and failure is None:
        failure = "Unable to capture complete command output."
    return CommandResult(-1 if failure else process.returncode, stdout, stderr, failure)
