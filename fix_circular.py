import ast

filepath = "03-development/src/app/api/webhooks.py"
with open(filepath, "r") as f:
    source = f.read()

lines = source.split("\n")
tree = ast.parse(source)

utils_funcs = ["_b64url_encode", "_b64url_decode", "_verify_challenge"]
utils_code = "import base64\nimport hmac\nimport hashlib\nfrom fastapi import Request, HTTPException\n\n"

new_webhooks_lines = []

def get_source(node):
    start = node.lineno - 1
    if hasattr(node, 'decorator_list') and node.decorator_list:
        start = node.decorator_list[0].lineno - 1
    end = getattr(node, 'end_lineno', len(lines))
    return "\n".join(lines[start:end])

# Extract them
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in utils_funcs:
        utils_code += get_source(node) + "\n\n"

# Create utils.py
with open("03-development/src/app/api/adapters/utils.py", "w") as f:
    f.write(utils_code)

# Remove them from webhooks.py and add import
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in utils_funcs:
        # we will just replace the exact source with an empty string?
        source = source.replace(get_source(node), "")

# We also need to add the import to webhooks.py
import_stmt = "from app.api.adapters.utils import _b64url_encode, _b64url_decode, _verify_challenge\n"
# insert before the first adapter import
source = source.replace("from app.api.adapters.base", import_stmt + "from app.api.adapters.base")

with open(filepath, "w") as f:
    f.write(source)

# Now update a2a.py, web.py, messenger.py, verifiers.py
import os
for pyfile in os.listdir("03-development/src/app/api/adapters"):
    if pyfile.endswith(".py"):
        with open(f"03-development/src/app/api/adapters/{pyfile}", "r") as f:
            content = f.read()
        content = content.replace("from app.api.webhooks import _b64url_encode, _b64url_decode", "from app.api.adapters.utils import _b64url_encode, _b64url_decode")
        content = content.replace("from app.api.webhooks import _verify_challenge", "from app.api.adapters.utils import _verify_challenge")
        with open(f"03-development/src/app/api/adapters/{pyfile}", "w") as f:
            f.write(content)

print("Fixed circular import")
