#!/bin/bash
echo "1. auth.py _assign_role_route"
grep -n "caller_role" src/app/api/auth.py

echo "2. management.py _knowledge_list_route"
grep -n "role: str = Query" src/app/api/management.py

echo "3. media.py ClamAVScanner.scan"
grep -n "self._runner(file_bytes" src/app/services/media.py

echo "4. websocket.py verify_jwt magic string"
grep -n "valid-user-jwt" src/app/api/websocket.py

echo "5. auth.py _login_route body: dict"
grep -n "def _login_route" src/app/api/auth.py

echo "6. a2a.py verify_m2m_token bare except"
grep -n "except Exception" src/app/api/adapters/a2a.py

echo "7. ip_whitelist.py _resolve_ip tcp_client is None"
grep -n "tcp_client is None" src/app/middleware/ip_whitelist.py

echo "8. webui.py update_entry setattr"
grep -n "setattr(entry" src/app/admin/webui.py

echo "9. gdpr.py export_user_data CSV injection"
grep -n "csv_lines.append" src/app/admin/gdpr.py

echo "10. ab_testing.py _route_bucket int(weight)"
grep -n "int(weight)" src/app/services/ab_testing.py

echo "11. llm_judge.py _agreement_rate raw matches"
grep -n "matches / n" src/app/services/llm_judge.py

echo "12. mcp_adapter.py _execute_stdio_call missing reap"
grep -n -C 2 "stdout, stderr = proc.communicate" src/app/services/aee/mcp_adapter.py

echo "13. response.py format_for_platform missing a2a"
grep -n "if platform == \"agent\":" src/app/core/response.py

echo "15. chain.py reason=IP_BLOCKED"
grep -n "reason=\"IP_BLOCKED\"" src/app/middleware/chain.py

echo "16. knowledge.py HybridKnowledge._rule_match best=rows[0]"
grep -n "best = rows\[0\]" src/app/core/knowledge.py

echo "17. a2a_adapter.py execute HTTPStatusError"
grep -n "http_error:" src/app/services/aee/a2a_adapter.py

echo "18. cli_adapter.py timeout=None"
grep -n "communicate(timeout=timeout_seconds)" src/app/services/aee/cli_adapter.py

echo "19. mcp_adapter.py 65535"
grep -n "65535" src/app/services/aee/mcp_adapter.py
