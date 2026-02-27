"""Deprecated test.

Duplicate switch `case` labels are correctly rejected by IR generation.
See `tests/test_switch_duplicate_case_rejected_more.py`.
"""


def test_switch_duplicate_case_runtime_first_match_wins():
    # Kept only so older references don't break.
    # The actual expected behavior is rejection (compile error).
    assert True
