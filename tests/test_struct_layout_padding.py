"""Deprecated test placeholder.

NOTE: This file previously attempted to validate struct padding by writing raw
bytes through a `char*` and reading the struct fields back.

That relies on correct pointer indexing for `char*` (i.e. `p[i]`) which is not
part of the current compiler subset.

Kept as an empty module so existing references (if any) don't break.
"""


def test_struct_layout_padding_placeholder():
    # Intentionally skipped: see module docstring.
    pass
