import os
import stat
from pathlib import Path


def read_regular_bytes(path: Path, maximum: int) -> bytes:
    if type(maximum) is not int or maximum <= 0:
        raise ValueError("The input byte limit must be a positive integer.")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Local JSON input must be a regular file.")

    def opener(name, flags):
        return os.open(name, flags | getattr(os, "O_NONBLOCK", 0))

    with open(path, "rb", opener=opener) as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Local JSON input must be a regular file.")
        return source.read(maximum + 1)
