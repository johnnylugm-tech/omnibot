with open("03-development/src/app/api/webhooks.py") as f:
    code = f.read()
import ast
for node in ast.parse(code).body:
    if isinstance(node, ast.FunctionDef) and node.name == "_register_webhook_routes":
        start = node.lineno - 1
        end = getattr(node, 'end_lineno', start + 1)
        print("\n".join(code.split("\n")[start:end]))
