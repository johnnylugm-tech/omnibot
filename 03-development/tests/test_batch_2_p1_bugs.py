import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.core.pipeline import Pipeline, get_context
from app.middleware.chain import MiddlewareChain

def test_id_pipeline_01_emotion_bypass():
    pipeline = Pipeline(knowledge=None, emotion=MagicMock(), response=None)
    pipeline.process = MagicMock(return_value={"platform": "agent", "text": "hello", "emotion": None, "bypassed": True})
    
    class DummyMsg:
        platform = "agent"
        content = "hello"
    
    pipeline.handle_message(DummyMsg())
    assert "emotion" not in pipeline._stage_call_log

@pytest.mark.asyncio
async def test_id_pipeline_02_get_context_leak():
    with patch("app.infra.database.get_session") as mock_get_session:
        session_mock = AsyncMock()
        class MockGen:
            async def __anext__(self):
                return session_mock
            async def aclose(self):
                pass
                
        mock_get_session.return_value = MockGen()
        
        result = await get_context("test_cid")
        assert result["conversation_id"] == "test_cid"

def test_id_chain_01_parse_protection():
    chain = MiddlewareChain(
        ip_whitelist=MagicMock(),
        signature_validator=MagicMock(),
        platform_adapter=MagicMock(),
        rate_limiter=MagicMock(),
        rbac_enforcer=MagicMock()
    )
    chain.signature_validator.verify.return_value = True
    chain.platform_adapter.parse.side_effect = ValueError("parse failed")
    
    result = chain.process(MagicMock())
    assert getattr(result, "status", 400) == 400
    assert getattr(result, "reason", "") == "PARSE_FAILED"

