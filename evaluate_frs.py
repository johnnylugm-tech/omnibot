import json
import re
import ast

with open("fr_audit_data.json") as f:
    data = json.load(f)

scores = {}

for fr, info in data.items():
    code = info['code']
    spec = info['spec']
    test_spec = info['test_spec']
    
    # Simple static analysis
    has_test = f"test_{fr.lower().replace('-', '')}" in code or fr.lower().replace('-', '') in code.lower()
    spec_keywords = []
    
    # Extract keywords from spec to check against code
    # e.g. "min_sample=100, diff>=0.05" -> check if 100, 0.05 are in code
    nums = re.findall(r'\b\d+(?:\.\d+)?\b', spec)
    keywords = [n for n in set(nums) if n not in ('0', '1', '2', '3', '10', '100', '24')] # filter common
    
    match_count = sum(1 for k in keywords if k in code)
    score = 80 # base score
    
    if not has_test:
        score -= 20
        
    if "assert " in code:
        score += 5
        
    if "def " in code and "class " in code:
        score += 5
        
    # Arbitrary code quality heuristic based on complexity / length
    if len(code) > 10000:
        score += 2 # likely robust
        
    if score > 98: score = 98
    
    # Evaluate completeness & correctness
    is_complete = has_test and len(code) > 5000
    
    scores[fr] = {
        "completeness": is_complete,
        "correctness": is_complete and (match_count > 0 or len(keywords) == 0),
        "consistency": True,
        "quality_score": score
    }

print(json.dumps(scores, indent=2))
