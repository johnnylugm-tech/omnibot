import asyncio
import json
import os
import re
from datetime import datetime
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

REPO = os.environ.get('REPO', '/Users/johnny/projects/omnibot')
TS = os.environ.get('TIMESTAMP', datetime.now().strftime('%Y-%m-%d'))

HIGH_RISK = [
    { "name": "dst",           "path": "03-development/src/app/core/dst.py" },
    { "name": "knowledge",     "path": "03-development/src/app/core/knowledge.py" },
    { "name": "paladin",       "path": "03-development/src/app/core/paladin.py" },
    { "name": "rate_limit",    "path": "03-development/src/app/infra/rate_limit.py" },
    { "name": "redis_streams", "path": "03-development/src/app/infra/redis_streams.py" },
    { "name": "a2a_adapter",   "path": "03-development/src/app/services/aee/a2a_adapter.py" },
    { "name": "adapter",       "path": "03-development/src/app/services/aee/adapter.py" },
    { "name": "tool_executor", "path": "03-development/src/app/services/aee/tool_executor.py" },
    { "name": "cli_adapter",   "path": "03-development/src/app/services/aee/cli_adapter.py" },
    { "name": "mcp_adapter",   "path": "03-development/src/app/services/aee/mcp_adapter.py" },
    { "name": "llm_judge",     "path": "03-development/src/app/services/llm_judge.py" },
    { "name": "emotion",       "path": "03-development/src/app/core/emotion.py" },
]

STANDARD = [
    { "name": "ab_testing",         "path": "03-development/src/app/services/ab_testing.py" },
    { "name": "agent_card",         "path": "03-development/src/app/api/agent_card.py" },
    { "name": "alert_rules",        "path": "03-development/src/app/infra/alert_rules.py" },
    { "name": "api_response",       "path": "03-development/src/app/core/api_response.py" },
    { "name": "backup_strategy",    "path": "03-development/src/app/infra/backup_strategy.py" },
    { "name": "chain",              "path": "03-development/src/app/middleware/chain.py" },
    { "name": "chunking",           "path": "03-development/src/app/core/chunking.py" },
    { "name": "compose",            "path": "03-development/src/app/infra/compose.py" },
    { "name": "config",             "path": "app/infra/config.py" },
    { "name": "data_retention",     "path": "03-development/src/app/infra/data_retention.py" },
    { "name": "database",           "path": "03-development/src/app/infra/database.py" },
    { "name": "escalation",         "path": "03-development/src/app/services/escalation.py" },
    { "name": "grafana_dashboard",  "path": "03-development/src/app/infra/grafana_dashboard.py" },
    { "name": "ip_whitelist",       "path": "03-development/src/app/middleware/ip_whitelist.py" },
    { "name": "k8s_deployment",     "path": "03-development/src/app/infra/k8s_deployment.py" },
    { "name": "media",              "path": "03-development/src/app/services/media.py" },
    { "name": "migrations",         "path": "03-development/src/app/infra/migrations.py" },
    { "name": "observability",      "path": "03-development/src/app/infra/observability.py" },
    { "name": "pii",                "path": "03-development/src/app/core/pii.py" },
    { "name": "pipeline",           "path": "03-development/src/app/core/pipeline.py" },
    { "name": "prometheus_metrics", "path": "03-development/src/app/infra/prometheus_metrics.py" },
    { "name": "redis_security",     "path": "03-development/src/app/infra/redis_security.py" },
    { "name": "response_generator", "path": "03-development/src/app/core/response_generator.py" },
    { "name": "retraction",         "path": "03-development/src/app/core/retraction.py" },
    { "name": "retry",              "path": "03-development/src/app/infra/retry.py" },
    { "name": "rollback_strategy",  "path": "03-development/src/app/infra/rollback_strategy.py" },
    { "name": "schema",             "path": "03-development/src/app/infra/schema.py" },
    { "name": "tde",                "path": "03-development/src/app/infra/tde.py" },
    { "name": "tracing",            "path": "03-development/src/app/infra/tracing.py" },
    { "name": "unified_message",    "path": "03-development/src/app/core/unified_message.py" },
    { "name": "unified_response",   "path": "03-development/src/app/core/unified_response.py" },
    { "name": "vector_index",       "path": "03-development/src/app/infra/vector_index.py" },
    { "name": "websocket",          "path": "03-development/src/app/api/websocket.py" },
    { "name": "webui",              "path": "03-development/src/app/admin/webui.py" },
]

LENSES = {
    'correctness': 'Business logic errors, boundary conditions, null/empty handling, off-by-one, type mismatches, incorrect assumptions about input data.',
    'concurrency': 'Race conditions, thread safety, async/await issues, shared mutable state, lock ordering, ordering of side effects, lifecycle of long-lived objects across awaits.',
    'resilience':  'Error handling gaps, missing timeouts, broken fallbacks, resource leaks (files/sockets/connections), partial-failure handling, error swallowing.',
    'general':     'Any concrete, reachable bug — wrong return type, broken validation, dead branch, leaked resource, missing rollback, incorrect status code, PII leak, wrong default. No stylistic nits or hypotheticals.'
}

async def gather_response(response):
    text = ""
    async for token in response:
        text += token
    return text

def extract_json(text):
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except Exception:
        return {}

async def run_phase_1():
    print("[Phase 1] Gather context")
    config = LocalAgentConfig(
        system_instructions="You are a CRG scout gathering scan context for an adversarial bug hunt on omnibot.",
        capabilities=CapabilitiesConfig()
    )
    prompt = f"""REPO: {REPO}

HIGH-RISK ({len(HIGH_RISK)} modules):
""" + "\n".join([f"- {m['name']}: {m['path']}" for m in HIGH_RISK]) + f"""

STANDARD ({len(STANDARD)} modules):
""" + "\n".join([f"- {m['name']}: {m['path']}" for m in STANDARD]) + f"""

INSTRUCTIONS:
1. For EACH file: mcp__code-review-graph__get_review_context_tool (include_source=true, max_depth=2, max_lines_per_file=250, repo_root="{REPO}")
2. For HIGH-RISK files — also call query_graph_tool pattern="callers_of" and "tests_for" on key functions.
3. Call list_flows_tool limit=10 for critical execution paths.

OUTPUT (markdown ≤5000 words): per-module key functions @line, public callers, test coverage gaps, suspicious patterns."""
    
    async with Agent(config) as scout:
        res = await scout.chat(prompt)
        return await gather_response(res)

async def hunt_agent(module, lens, context):
    print(f"  -> Hunting {module['name']} / {lens}")
    config = LocalAgentConfig(
        system_instructions=f"You are a bug-hunter with LENS='{lens}'. LENS FOCUS: {LENSES[lens]}",
        capabilities=CapabilitiesConfig()
    )
    prompt = f"""TARGET: {module['name']}
FILE: {REPO}/{module['path']}

SHARED CRG CONTEXT:
---
{context}
---

RULES:
1. Read the file FULLY at its absolute path above. Use mcp__code-review-graph__query_graph_tool (repo_root="{REPO}") for callers/callees/tests_for.
2. Only REACHABLE bugs — concrete failure scenario + line citation required.
3. No stylistic nits, no hypotheticals, no test code, no invented bugs.
4. Empty findings {{"findings":[]}} is valid.

OUTPUT strict JSON: {{"findings":[...]}}"""
    async with Agent(config) as hunter:
        res = await hunter.chat(prompt)
        text = await gather_response(res)
        return extract_json(text).get("findings", [])

async def verify_agent(finding, action):
    config = LocalAgentConfig(
        system_instructions=f"You are a {action} agent. Default is_real=false unless proven.",
        capabilities=CapabilitiesConfig()
    )
    if action == "REFUTE":
        prompt = f"""REFUTE this bug finding.
FINDING:
{json.dumps(finding, indent=2)}

Read {REPO}/{finding['file']}. Check: cited code at cited lines? Surrounding guards? Scenario reachable?
Cite line numbers in evidence.
OUTPUT strict JSON: {{"is_real": boolean, "refutation_attempt": string, "evidence": string, "severity_agrees": boolean}}"""
    else:
        prompt = f"""CONFIRM this bug finding independently.
FINDING:
{json.dumps(finding, indent=2)}

Read {REPO}/{finding['file']}; trace data flow; check tests_for. Confirm ONLY with concrete trigger + observed-vs-expected, citing line numbers.
OUTPUT strict JSON: {{"is_real": boolean, "refutation_attempt": string, "evidence": string, "severity_agrees": boolean}}"""

    async with Agent(config) as verifier:
        res = await verifier.chat(prompt)
        text = await gather_response(res)
        return extract_json(text)

async def verify_finding(finding):
    refute_task = verify_agent(finding, "REFUTE")
    confirm_task = verify_agent(finding, "CONFIRM")
    results = await asyncio.gather(refute_task, confirm_task)
    
    is_real_count = sum(1 for r in results if r.get("is_real"))
    
    def has_line_citation(v):
        evidence = str(v.get("evidence", "")) + " " + str(v.get("refutation_attempt", ""))
        return bool(re.search(r'(:\d+|line\s*\d+|L\d+)', evidence, re.IGNORECASE))
    
    confirmed = (is_real_count == 2) or (is_real_count == 1 and any(r.get("is_real") and has_line_citation(r) for r in results))
    finding["_confirmed"] = confirmed
    finding["_verifiers"] = results
    return finding

async def run_phase_2(context):
    print("[Phase 2] Hunt")
    tasks = []
    for m in HIGH_RISK:
        for lens in ['correctness', 'concurrency', 'resilience']:
            tasks.append(hunt_agent(m, lens, context))
    for m in STANDARD:
        tasks.append(hunt_agent(m, 'general', context))
    
    results = await asyncio.gather(*tasks)
    raw_findings = []
    for res in results:
        if isinstance(res, list):
            raw_findings.extend(res)
        elif res:
            raw_findings.append(res)
    print(f"Hunt: {len(raw_findings)} raw findings.")
    return raw_findings

async def run_phase_3(raw_findings):
    print("[Phase 3] Verify")
    tasks = [verify_finding(f) for f in raw_findings]
    judged = await asyncio.gather(*tasks)
    confirmed = [f for f in judged if f.get("_confirmed")]
    refuted = [f for f in judged if not f.get("_confirmed")]
    print(f"Verify: {len(confirmed)} confirmed / {len(refuted)} refuted of {len(raw_findings)}")
    return judged, confirmed, refuted

async def run_phase_4(raw_findings, confirmed, refuted):
    print("[Phase 4] Synthesize")
    per_mod_seq = {}
    findings_out = []
    for f in confirmed + refuted:
        mod = f.get('module', 'unknown')
        per_mod_seq[mod] = per_mod_seq.get(mod, 0) + 1
        confirm_v = next((v for v in f.get('_verifiers', []) if v.get('is_real')), {})
        refute_v = next((v for v in f.get('_verifiers', []) if not v.get('is_real')), {})
        
        status_info = {"status": "open"} if f.get('_confirmed') else {"status": "refuted", "refute_evidence": refute_v.get('refutation_attempt', refute_v.get('evidence', 'no verifier confirmed'))}
        
        findings_out.append({
            "id": f"{mod}#{per_mod_seq[mod]}",
            "module": mod,
            "lens": f.get('lens'),
            "severity": f.get('severity'),
            "title": f.get('title'),
            "description": f.get('description'),
            "file": f.get('file'),
            "line_start": f.get('line_start'),
            "line_end": f.get('line_end'),
            "code_snippet": f.get('code_snippet', ''),
            "reasoning": f.get('reasoning'),
            "suggested_fix": f.get('suggested_fix'),
            "confidence": f.get('confidence'),
            "confirmed": f.get('_confirmed'),
            "verify_evidence": confirm_v.get('evidence', ''),
            "resolution": status_info
        })
        
    report_json = {
        "generated_at": TS,
        "targets_hr": [m['name'] for m in HIGH_RISK],
        "targets_std": [m['name'] for m in STANDARD],
        "lenses": list(LENSES.keys()),
        "raw_count": len(raw_findings),
        "confirmed_count": len(confirmed),
        "refuted_count": len(refuted),
        "findings": findings_out
    }
    
    os.makedirs(f"{REPO}/.methodology", exist_ok=True)
    with open(f"{REPO}/.methodology/bug_hunt_report.json", "w") as f:
        json.dump(report_json, f, indent=2)

    config = LocalAgentConfig(
        system_instructions="You are a report writing agent.",
        capabilities=CapabilitiesConfig()
    )
    md_path = f"03-development/.audit/bug-report-{TS}.md"
    
    compact_findings = [{k: v for k, v in f.items() if k != 'code_snippet'} for f in findings_out]
    
    prompt = f"""Write a concise markdown bug report in Traditional Chinese (繁體中文，稱呼讀者「老闆」).

REPO: {REPO}
REPORT PATH: {REPO}/{md_path}
RAW: {len(raw_findings)}  CONFIRMED: {len(confirmed)}  REFUTED: {len(refuted)}
HIGH_RISK (3-lens): {', '.join(m['name'] for m in HIGH_RISK)}
STANDARD (general): {', '.join(m['name'] for m in STANDARD)}

FINDINGS (already verified):
{json.dumps(compact_findings, indent=2)}

STRUCTURE (≤2000 words):
# 漏洞掃描報告
## 1. 掃描摘要 — module×severity 表、掃描覆蓋範圍（HR×3-lens + STD×general）
## 2. 確認的 Bugs — severity 降序：模組/file:line、問題、觸發條件、修復建議
## 3. 被反駁的 Findings — 一句理由（每條）
## 4. 修復優先順序 — P0/P1/P2 分級
## 5. 掃描方法

語氣客觀；引 file:line；不貼 >6 行代碼。用 Write tool 寫入 REPORT PATH。
最後提醒：confirmed critical/high 需逐條 resolved 或 refuted 後 Gate 3 adversarial_review 才放行。"""

    print("Writing markdown report...")
    async with Agent(config) as writer:
        res = await writer.chat(prompt)
        await gather_response(res)

    print(f"Done! Report saved to {md_path}")

async def main():
    context = await run_phase_1()
    raw_findings = await run_phase_2(context)
    judged, confirmed, refuted = await run_phase_3(raw_findings)
    await run_phase_4(raw_findings, confirmed, refuted)

if __name__ == "__main__":
    asyncio.run(main())
