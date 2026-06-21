with open("03-development/src/app/core/knowledge.py", "r") as f:
    knowledge = f.read()

import re

# Find enqueue_embedding_job in knowledge.py
match = re.search(r'(# Hook for the async enqueue.*?def enqueue_embedding_job\(job: EmbeddingJob\) -> EmbeddingJob:.*?return job\n)', knowledge, re.DOTALL)
if match:
    enqueue_code = match.group(1)
    knowledge = knowledge.replace(enqueue_code, "")
    with open("03-development/src/app/core/knowledge.py", "w") as f:
        f.write(knowledge)
    
    with open("03-development/src/app/infra/jobs.py", "r") as f:
        jobs = f.read()
    
    # insert before the FR-77 reexports
    jobs = jobs.replace("from app.core.knowledge import", enqueue_code + "\n\nfrom app.core.knowledge import")
    with open("03-development/src/app/infra/jobs.py", "w") as f:
        f.write(jobs)
    print("Fixed enqueue_embedding_job")
else:
    print("Could not find enqueue_embedding_job in knowledge.py")

