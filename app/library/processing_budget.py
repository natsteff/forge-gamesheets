"""Shared PDF rendering admission and bounded derived-file writes (Mac/Linux)."""

import fcntl
import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

MAX_REPRINT_BYTES = 250 * 1024 * 1024
MAX_PREVIEW_BYTES = 1024 * 1024
MAX_DERIVED_BYTES = 5 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 100 * 1024 * 1024
_RENDER_LOCK = Lock()


class ProcessingBudgetError(ValueError):
    """A render cannot proceed within its resource budget."""


@contextmanager
def rendering_slot(data_path: Path):
    """Serialize renderers in-process and across workers sharing this data root."""
    if not _RENDER_LOCK.acquire(timeout=5):
        raise ProcessingBudgetError("PDF processing is busy. Try again shortly.")
    try:
        root = data_path.resolve(strict=True)
        descriptor = os.open(
            root / ".pdf-processing.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ProcessingBudgetError("PDF processing lock is unavailable.")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ProcessingBudgetError(
                    "PDF processing is busy. Try again shortly."
                ) from error
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    finally:
        _RENDER_LOCK.release()


def check_storage_budget(data_path: Path, maximum_output: int) -> None:
    """Reserve worst-case output headroom; never delete files to make space."""
    root = data_path.resolve(strict=True)
    if shutil.disk_usage(root).free < MIN_FREE_BYTES + maximum_output:
        raise ProcessingBudgetError("Not enough free disk space for PDF processing.")
    used = 0
    for name in ("generated", "previews"):
        directory = root / name
        if directory.is_symlink():
            raise ProcessingBudgetError("Derived storage must not be a symbolic link.")
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            metadata = entry.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ProcessingBudgetError("Unexpected entry in derived storage.")
            used += metadata.st_size
    if used + maximum_output > MAX_DERIVED_BYTES:
        raise ProcessingBudgetError("The generated PDF/preview storage budget is full.")


class BoundedWriter:
    """File-like adapter with no name attribute (PyMuPDF must use write())."""

    def __init__(self, stream, limit: int):
        self.stream = stream
        self.limit = limit
        self.exceeded = False

    def write(self, content):
        if self.stream.tell() + len(content) > self.limit:
            self.exceeded = True
            raise ProcessingBudgetError("Generated output exceeds its size limit.")
        return self.stream.write(content)

    def seek(self, offset, whence=0):
        return self.stream.seek(offset, whence)

    def tell(self):
        return self.stream.tell()

    def flush(self):
        return self.stream.flush()

    def read(self, size=-1):
        return self.stream.read(size)


@contextmanager
def bounded_output(path: Path, limit: int):
    with path.open("x+b") as stream:
        writer = BoundedWriter(stream, limit)
        yield writer
        # Native codecs may translate/suppress callback exceptions. Never publish
        # a partial file even if the codec returns without propagating one.
        if writer.exceeded or os.fstat(stream.fileno()).st_size > limit:
            raise ProcessingBudgetError("Generated output exceeds its size limit.")
