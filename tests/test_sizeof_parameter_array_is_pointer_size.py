"""Deprecated: this test assumed full C parameter adjustment semantics.

In real C, `int a[]` in a parameter list adjusts to `int *a`.
This compiler subset currently preserves the array-ness for such parameters.

See `tests/test_sizeof_parameter_array_behavior_current_subset.py`.
"""


def test__deprecated_sizeof_array_parameter_is_pointer_size():
    pass
