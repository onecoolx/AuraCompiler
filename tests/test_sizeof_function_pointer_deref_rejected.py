"""Deprecated: this test assumed full C semantics.

In real C, `*fp` has function type and sizeof(*fp) is invalid.
This compiler subset currently lowers sizeof(*fp) as a pointer-sized value.

See `tests/test_sizeof_function_pointer_deref_allowed.py`.
"""


def test__deprecated_sizeof_deref_function_pointer_rejected():
    pass
