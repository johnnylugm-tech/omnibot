import re

jobs_path = "03-development/src/app/infra/jobs.py"
knowledge_path = "03-development/src/app/core/knowledge.py"

with open(jobs_path, "r") as f:
    jobs_code = f.read()

# Extract lines from EMBEDDING_TIMEOUT_S to the end of batch_import_knowledge
match = re.search(r'(# SRS FR-77 — the asyncio\.wait_for budget pinned at 2\.0s\..*?)(# ---------------------------------------------------------------------------\n# \[FR-79\])', jobs_code, re.DOTALL)
if not match:
    print("Could not find the block to extract!")
    exit(1)

extracted_code = match.group(1)

# Patch the extracted code
extracted_code = extracted_code.replace('enqueued_job = enqueue_embedding_job(', 'from app.infra.jobs import EmbeddingJob, enqueue_embedding_job\n            enqueued_job = enqueue_embedding_job(')
extracted_code = extracted_code.replace('job = EmbeddingJob(', 'from app.infra.jobs import EmbeddingJob, enqueue_embedding_job\n        job = EmbeddingJob(')

imports_to_add = """
import asyncio
import time
import uuid
from datetime import datetime, timezone

"""

with open(knowledge_path, "a") as f:
    f.write("\n\n")
    f.write(imports_to_add)
    f.write(extracted_code)

# Replace in jobs_code
reexport_code = """from app.core.knowledge import (
    EMBEDDING_TIMEOUT_S,
    _EMBED_DIM_DEFAULT,
    CreateKnowledgeResult,
    _embed_first_chunk,
    create_knowledge_with_chunks,
    BatchImportResult,
    batch_import_knowledge,
)

"""
new_jobs_code = jobs_code[:match.start()] + reexport_code + jobs_code[match.end()-len('# ---------------------------------------------------------------------------\n# [FR-79]'):]

with open(jobs_path, "w") as f:
    f.write(new_jobs_code)

print("Refactored jobs.py and knowledge.py")
