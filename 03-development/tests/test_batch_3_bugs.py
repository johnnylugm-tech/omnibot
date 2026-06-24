import asyncio
import pytest
from unittest.mock import patch, MagicMock
from app.core.knowledge import batch_import_knowledge, _call_llm_api
from app.core import retraction

def test_id_knowledge_06_batch_import_failed_chunk_ids():
    entries = [{"content": "test1"}, {"content": "test2"}]
    with patch("app.infra.jobs.enqueue_embedding_job", side_effect=Exception("mock fail")):
        result = batch_import_knowledge(entries, is_batch=True)
    assert result.failed_count == 2
    assert len(result.failed_chunk_ids) == 2

@pytest.mark.asyncio
async def test_id_knowledge_08_double_failure():
    from app.core.knowledge import create_knowledge_with_chunks
    with patch("app.core.knowledge._embed_first_chunk", side_effect=TimeoutError("timeout")), \
         patch("app.infra.jobs.enqueue_embedding_job", side_effect=Exception("enqueue fail")):
        
        result = await create_knowledge_with_chunks(
            knowledge_id="test_kb",
            title="hello",
            content="hello",
            model="test-model"
        )
        assert result.fallback == "failed"

def test_id_knowledge_09_llm_timeout():
    import openai
    with patch("openai.Client") as mock_client:
        _call_llm_api("gpt-4o", "test")
        mock_client.assert_called_once()
        assert mock_client.call_args[1].get("timeout") == 0.45

def test_id_retraction_01_shim_exists():
    assert hasattr(retraction, "retract")
    assert hasattr(retraction, "RetractionResult")
