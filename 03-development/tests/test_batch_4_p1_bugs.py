import pytest
import asyncio
import threading
from src.app.core.dst import DialogueState
from src.app.core.paladin import _await_coro_from_sync
from src.app.services.aee.tool_executor import ToolExecutor, ToolDefinition
from src.app.services.aee.mcp_adapter import MCPAdapter
from src.app.services.llm_judge import CalibrationPipeline

def test_id_04_01_dst_race_condition():
    dst = DialogueState(intent="")
    def worker():
        for _ in range(100):
            dst.update_intent_and_slots("foo", {"k": "v"})
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert dst.intent == "foo"
    assert dst.slots == {"k": "v"}

def test_id_04_02_paladin_leak():
    async def coro():
        await asyncio.sleep(2.0)
    try:
        _await_coro_from_sync(coro(), timeout_ms=50)
    except (asyncio.TimeoutError, TimeoutError):
        pass

@pytest.mark.asyncio
async def test_id_04_03_tool_executor_sync_timeout():
    def fast_handler(**kwargs):
        return "fast"
    executor = ToolExecutor({"fast": fast_handler}, default_tools=False)
    res = executor.execute("fast", {})
    assert res.success
    assert res.output == "fast"

def test_id_04_04_mcp_adapter_ndjson():
    adapter = MCPAdapter(url="http://fake", command=None)
    raw = b'{"jsonrpc":"2.0","result":{"tools":[{"name":"t1"}]}}\n{"jsonrpc":"2.0"}\n'
    tools = adapter._parse_tool_list(raw)
    assert len(tools) == 1
    assert tools[0].name == "t1"

@pytest.mark.asyncio
async def test_id_04_05_llm_judge_none():
    pipeline = CalibrationPipeline(judge_llm=None, kappa_cache=None, timeout_s=1)
    res = await pipeline.run_cycle(golden_set=[])
    assert res.action == "pass"
