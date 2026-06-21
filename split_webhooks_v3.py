import ast
import os

filepath = "03-development/src/app/api/webhooks.py"
with open(filepath, "r") as f:
    source = f.read()

lines = source.split("\n")
tree = ast.parse(source)

first_def_line = min(n.lineno for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)))

header_lines = lines[:first_def_line-1]

def get_source(node):
    start = node.lineno - 1
    if hasattr(node, 'decorator_list') and node.decorator_list:
        start = node.decorator_list[0].lineno - 1
    end = getattr(node, 'end_lineno', len(lines))
    return "\n".join(lines[start:end])

nodes = {}
for node in tree.body:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
        nodes[node.name] = get_source(node)

keep_names = [
    "_b64url_encode", "_b64url_decode", "_verify_challenge",
    "_init_all", "_hash_token", "create_token", "list_tokens", "revoke_token",
    "validate_token", "agent_card", "_register_webhook_routes", "_add_stub_route",
    "_dummy_api_cohesion"
]

header = "\n".join(header_lines) + "\n"

# Only write webhooks.py content
webhooks_content = header + "\n"
webhooks_content += "from app.api.adapters.base import BaseWebhookAdapter\n"
webhooks_content += "from app.api.adapters.a2a import A2AAuthError, A2AAdapter\n"
webhooks_content += "from app.api.adapters.line import LineWebhookAdapter\n"
webhooks_content += "from app.api.adapters.messenger import MessengerWebhookAdapter\n"
webhooks_content += "from app.api.adapters.telegram import TelegramWebhookAdapter\n"
webhooks_content += "from app.api.adapters.web import WebAuthError, WebAdapter\n"
webhooks_content += "from app.api.adapters.whatsapp import WhatsAppWebhookAdapter\n"
webhooks_content += "from app.api.adapters.registry import WebhookRegistry\n"
webhooks_content += "from app.api.adapters.verifiers import LineWebhookVerifier, MessengerWebhookVerifier, TelegramWebhookVerifier, WebJwtVerifier, WhatsAppWebhookVerifier\n"
webhooks_content += "from app.api.adapters.utils import _b64url_encode, _b64url_decode, _verify_challenge\n\n"

for node in tree.body:
    if getattr(node, 'lineno', 0) < first_def_line:
        continue # Already in header
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        start = node.lineno - 1
        end = getattr(node, 'end_lineno', start + 1)
        webhooks_content += "\n".join(lines[start:end]) + "\n"
    elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
        if node.name in keep_names and node.name not in ["_b64url_encode", "_b64url_decode", "_verify_challenge"]:
            webhooks_content += nodes[node.name] + "\n\n"
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        start = node.lineno - 1
        end = getattr(node, 'end_lineno', start + 1)
        webhooks_content += "\n".join(lines[start:end]) + "\n"

with open(filepath, "w") as f:
    f.write(webhooks_content)

print("webhooks.py fixed!")
