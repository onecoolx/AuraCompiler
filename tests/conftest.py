"""Shared pytest fixtures and hooks for the test suite."""
import os
import pytest

# Files that should never exist in the project root after tests.
_STALE_FILES = {"t.c", "a.out", "a.c", "t.o", "t.s", "t.i", "t"}

# Record project root at import time.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _cleanup_stale_files():
    """Remove stale scratch files from the project root after each test."""
    yield
    for name in _STALE_FILES:
        path = os.path.join(_PROJECT_ROOT, name)
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
