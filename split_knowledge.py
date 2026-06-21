import os

source_file = "03-development/src/app/core/knowledge.py"
with open(source_file, "r") as f:
    lines = f.readlines()

def get_block(start, end=None):
    if end is None:
        return "".join(lines[start-1:])
    return "".join(lines[start-1:end-1])

imports = "".join(lines[37:53])  # imports and VALID_SOURCES constant

models_content = imports + get_block(54, 124)
with open("03-development/src/app/core/knowledge/models.py", "w") as f:
    f.write(models_content)

hybrid_content = imports + "from .models import KnowledgeResult, ParentChunk, RAGFallback\n" + get_block(124, 559)
with open("03-development/src/app/core/knowledge/hybrid.py", "w") as f:
    f.write(hybrid_content)

generation_content = imports + "from .models import KnowledgeResult\n" + get_block(559, 733)
with open("03-development/src/app/core/knowledge/generation.py", "w") as f:
    f.write(generation_content)

escalation_content = imports + "from .models import KnowledgeResult\n" + get_block(733)
with open("03-development/src/app/core/knowledge/escalation.py", "w") as f:
    f.write(escalation_content)

init_content = """from .models import KnowledgeResult, ParentChunk, RAGFallback, VALID_SOURCES
from .hybrid import HybridKnowledge
from .generation import _call_llm_api, _build_sandwich_prompt, _call_llm_with_fallback, _compute_grounding_score, _llm_generate
from .escalation import _escalate

# Add standard aliases to match how it was exported
PRIMARY_LLM = "gpt-4o"
FALLBACK_LLM = "gemini-1.5-flash"
EMBEDDING_DIM = 1536
"""
with open("03-development/src/app/core/knowledge/__init__.py", "w") as f:
    f.write(init_content)

# Remove the old god object
os.remove(source_file)
print("Knowledge successfully split.")
