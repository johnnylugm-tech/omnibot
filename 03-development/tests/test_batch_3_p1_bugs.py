from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from app.core.paladin import ClassificationResult, InjectionType, PALADINPipeline
from app.core.response import _attempt_windowed_delete, retract


def test_id_retraction_02_attempt_windowed_delete_checks_result():
    client_mock = MagicMock()
    # Return False instead of True
    client_mock.delete_message.return_value = False

    log_mock = MagicMock()
    result = _attempt_windowed_delete(
        platform="telegram",
        client=client_mock,
        message_id="msg123",
        sent_at=datetime.utcnow(),
        window=timedelta(seconds=100000),
        security_log_writer=log_mock
    )

    assert result.success is False
    assert result.method == "apology"
    log_mock.assert_called_once()

def test_id_retraction_03_unknown_platform_audit():
    log_mock = MagicMock()
    with pytest.raises(ValueError, match="Unknown platform"):
        retract(
            platform="unknown_abc",
            message_id="msg123",
            sent_at=datetime.utcnow(),
            security_log_writer=log_mock
        )
    log_mock.assert_called_once()

def test_id_paladin_15_retrospective_block_audit_failure():
    # If the writer fails, it still must return _blocked_result
    paladin = PALADINPipeline()

    def failing_writer(*args, **kwargs):
        raise RuntimeError("Disk full")

    paladin._security_log_writer = failing_writer

    verdict = ClassificationResult(
        is_injection=True,
        confidence=0.9,
        injection_type=InjectionType.DIRECT_PROMPT_INJECTION
    )

    result = paladin._handle_retrospective_block("test", verdict, "medium")
    assert result.is_blocked is True
    assert result.late_injection_detected is True
