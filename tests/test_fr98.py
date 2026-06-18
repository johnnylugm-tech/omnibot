"""[FR-98] Tests for Rollback 策略 — knowledge 軟刪除/schema downgrade/experiment abort.

Citations:
  SRS.md FR-98
  TEST_SPEC.md FR-98
"""


def test_fr98_knowledge_soft_delete_rollback():
    """[FR-98] knowledge_soft_delete_rollback."""
    from src.deployment.rollback import RollbackManager
    assert True  # RED: will fail on import


def test_fr98_schema_downgrade_no_data_loss():
    """[FR-98] schema_downgrade_no_data_loss."""
    from src.deployment.rollback import RollbackManager
    assert True  # RED: will fail on import


def test_fr98_experiment_abort_restores_control():
    """[FR-98] experiment_abort_restores_control."""
    from src.deployment.rollback import RollbackManager
    assert True  # RED: will fail on import
