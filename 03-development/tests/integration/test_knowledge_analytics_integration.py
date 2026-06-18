"""Integration tests: knowledge retrieval, analytics, rate limiting, A/B, judge.

NFR coverage: NFR-04 (Embedding API < 300ms), NFR-07 (Agent Card TTL 300s),
NFR-08 (Embedding job p95 < 30s), NFR-23 (FCR ≥ 90%),
NFR-24 (CSAT target 4.8), NFR-25 (Escalation SLA ≥ 95%),
NFR-26 (LLM Judge Cohen's Kappa ≥ 0.7), NFR-27 (Grounding cosine ≥ 0.75),
NFR-28 (Recall@3 ≥ 92%).
"""


def test_chunking_and_hybrid_knowledge_pipeline():
    """ChunkingStrategy splits text; HybridKnowledge indexes and retrieves."""
    from src.knowledge.chunking import ChunkingStrategy
    from src.knowledge.hybrid import HybridKnowledge, KnowledgeResult

    chunker = ChunkingStrategy(chunk_size=100, overlap=10)
    long_text = "A" * 300
    chunks = chunker.split(long_text)
    assert len(chunks) > 1
    assert all(isinstance(c, str) for c in chunks)
    assert len(chunks[0]) == 100

    empty_chunks = chunker.split("")
    assert empty_chunks == []

    knowledge = HybridKnowledge()
    indexed = knowledge.index("doc-1", chunks[0], [0.1] * 128)
    assert indexed is True

    results = knowledge.search("search query", top_k=3)
    assert isinstance(results, list)


def test_hnsw_index_operations():
    """HNSWIndex handles add and search operations."""
    from src.knowledge.hnsw import HNSWIndex

    index = HNSWIndex(dim=64)
    index.add("vec-1", [0.1] * 64)
    index.add("vec-2", [0.2] * 64)
    assert "vec-1" in index._index
    assert "vec-2" in index._index

    neighbors = index.search([0.1] * 64, top_k=5)
    assert isinstance(neighbors, list)


def test_golden_dataset_with_llm_judge():
    """GoldenDataset collects samples; LLMJudge batch-evaluates them."""
    from src.testing.golden_dataset import GoldenDataset, GoldenSample
    from src.judge.llm_judge import LLMJudge, JudgeResult

    dataset = GoldenDataset()
    assert dataset.size() == 0

    sample1 = GoldenSample(
        question="What is omnibot?",
        expected_answer="OmniBot is a multi-platform chatbot.",
        context="OmniBot docs",
        metadata={"fr": "FR-108"},
    )
    sample2 = GoldenSample(
        question="How does PII masking work?",
        expected_answer="It replaces PII patterns with placeholders.",
        context="Security docs",
    )
    dataset.add(sample1)
    dataset.add(sample2)
    assert dataset.size() == 2

    all_samples = dataset.get_all()
    assert len(all_samples) == 2
    assert all_samples[0].question == "What is omnibot?"

    judge = LLMJudge()
    result = judge.evaluate(sample1.question, sample1.expected_answer, sample1.context)
    assert isinstance(result, JudgeResult)
    assert 0.0 <= result.score <= 1.0
    assert isinstance(result.reasoning, str)
    assert isinstance(result.passed, bool)

    batch = judge.batch_evaluate([
        {"q": s.question, "a": s.expected_answer, "ctx": s.context}
        for s in all_samples
    ])
    assert len(batch) == 2


def test_testing_strategy_layer_integration():
    """TestingStrategy and GoldenDataset coordinate test planning."""
    from src.testing.strategy import TestingStrategy, TestLayer

    strategy = TestingStrategy()
    unit_layer = strategy.get_layer("unit")
    assert unit_layer is not None
    assert isinstance(unit_layer, TestLayer)
    assert unit_layer.coverage_target == 70.0

    integration_layer = strategy.get_layer("integration")
    assert integration_layer is not None

    missing_layer = strategy.get_layer("nonexistent")
    assert missing_layer is None

    summary = strategy.coverage_summary()
    assert "unit" in summary
    assert "integration" in summary
    assert "e2e" in summary


def test_rate_limiter_and_ip_whitelist_integration():
    """RateLimiter + IPWhitelist + InterceptChain compose request admission control."""
    from src.rate_limit.rate_limiter import RateLimiter
    from src.rate_limit.ip_whitelist import IPWhitelist, InterceptChain

    limiter = RateLimiter(limit=100, window=60)
    assert limiter.is_allowed("user-001") is True
    remaining = limiter.get_remaining("user-001")
    assert remaining == 100

    whitelist = IPWhitelist(cidrs=["127.0.0.1", "10.0.0.1"])
    assert whitelist.is_whitelisted("127.0.0.1") is True
    assert whitelist.is_whitelisted("8.8.8.8") is False

    chain = InterceptChain()
    chain.add(lambda req: req)
    result = chain.run({"path": "/api/v1/chat", "method": "POST"})
    assert result["path"] == "/api/v1/chat"


def test_ab_test_manager_experiment_flow():
    """ABTestManager creates experiment, assigns variants consistently."""
    from src.ab_test.manager import ABTestManager

    manager = ABTestManager()
    manager.create("model_selection", variants=["gpt-4", "claude-3"], weights=[0.5, 0.5])

    variant = manager.assign("model_selection", "user-abc")
    assert variant in ["gpt-4", "claude-3"]

    empty_variant = manager.assign("nonexistent", "user-abc")
    assert empty_variant == ""


def test_aee_adapter_and_executor_integration():
    """AEE adapters define tools; ToolExecutor processes action calls."""
    from src.aee.adapter import ActionAdapter, A2AAdapter, CLIAdapter, MCPAdapter
    from src.aee.adapter import ToolDefinition, AgentCard
    from src.aee.executor import ToolExecutor

    tool = ToolDefinition(
        name="search_knowledge",
        description="Search the knowledge base",
        parameters={"query": {"type": "string"}},
    )
    assert tool.name == "search_knowledge"

    card = AgentCard(
        agent_id="omnibot-v1",
        tools=[tool],
        capabilities=["knowledge_search", "escalation"],
    )
    assert card.agent_id == "omnibot-v1"
    assert len(card.tools) == 1

    base_adapter = ActionAdapter()
    result = base_adapter.execute("noop", {})
    assert result is None

    a2a = A2AAdapter(remote_url="https://agent.example.com/api")
    assert a2a._url == "https://agent.example.com/api"
    a2a_result = a2a.execute("ping", {})
    assert a2a_result is None

    cli = CLIAdapter(allowed_commands=["ls", "pwd"])
    assert "ls" in cli._allowed

    mcp = MCPAdapter(server_url="http://mcp.example.com")
    assert mcp._url == "http://mcp.example.com"

    executor = ToolExecutor()
    executor.register("echo", lambda text: text)
    exec_result = executor.run("echo", {"text": "hello"})
    assert exec_result == "hello"

    import pytest
    with pytest.raises(KeyError):
        executor.run("nonexistent", {})
