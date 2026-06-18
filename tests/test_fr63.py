"""[FR-63] Tests for ABTestManager — SHA-256 確定性 variant 分配.

Citations:
  SRS.md FR-63
  TEST_SPEC.md FR-63
"""


def test_fr63_sha256_same_user_same_experiment_same_variant():
    """[FR-63] sha256_same_user_same_experiment_same_variant."""
    from src.ab_test.manager import ABTestManager
    assert True  # RED: will fail on import


def test_fr63_variant_deterministic_cross_process():
    """[FR-63] variant_deterministic_cross_process."""
    from src.ab_test.manager import ABTestManager
    assert True  # RED: will fail on import


def test_fr63_hashlib_sha256_not_python_hash():
    """[FR-63] hashlib_sha256_not_python_hash."""
    from src.ab_test.manager import ABTestManager
    assert True  # RED: will fail on import
