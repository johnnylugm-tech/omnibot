from .models import KnowledgeResult, ParentChunk, RAGFallback, VALID_SOURCES
from .hybrid import HybridKnowledge
from .generation import _call_llm_api, _build_sandwich_prompt, _call_llm_with_fallback, _compute_grounding_score, _llm_generate
from .escalation import _escalate

# Add standard aliases to match how it was exported
PRIMARY_LLM = "gpt-4o"
FALLBACK_LLM = "gemini-1.5-flash"
EMBEDDING_DIM = 1536
