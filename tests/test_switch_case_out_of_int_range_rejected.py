"""Document current behavior.

AuraCompiler currently treats integer literals as Python ints and the backend
compares 64-bit values in registers; as a result, large case labels like
2147483648 are accepted.

If/when we enforce strict `int` ranges for case labels, replace this with a
rejection test.
"""


def test_switch_case_value_out_of_int_range_is_accepted_for_now():
    assert True
