import subprocess

from pycc.preprocessor import _parse_gcc_include_paths


def test_parse_gcc_include_paths_basic():
    stderr = """
#include <...> search starts here:
 /usr/local/include
 /usr/include/x86_64-linux-gnu
 /usr/include
End of search list.
"""
    assert _parse_gcc_include_paths(stderr) == [
        "/usr/local/include",
        "/usr/include/x86_64-linux-gnu",
        "/usr/include",
    ]


def test_parse_gcc_include_paths_ignores_framework_and_nonexistent_markers():
    stderr = """
#include <...> search starts here:
 /usr/include
 (framework directory)
End of search list.
"""
    assert _parse_gcc_include_paths(stderr) == ["/usr/include"]


def test_parse_gcc_include_paths_strips_annotations_and_reads_quote_block():
    stderr = """
#include "..." search starts here:
 /a/b (sysroot)
#include <...> search starts here:
 /usr/include
End of search list.
"""
    assert _parse_gcc_include_paths(stderr) == ["/a/b", "/usr/include"]
