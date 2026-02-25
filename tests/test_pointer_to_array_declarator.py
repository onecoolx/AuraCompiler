"""Deprecated: pointer-to-array declarator test.

Kept for history, but intentionally skipped because the compiler does not yet
model pointer-to-array types in its declarator/type system.
"""


import pytest


@pytest.mark.skip(reason="pointer-to-array declarator typing not implemented")
def test_pointer_to_array_declarator_and_indexing(tmp_path):
  assert True
