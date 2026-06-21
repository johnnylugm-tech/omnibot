import os

# 1. Fix whatsapp.py
with open("03-development/src/app/api/adapters/whatsapp.py", "r") as f:
    content = f.read()

whatsapp_map = """
_WHATSAPP_TYPE_MAP: dict[str, str] = {
    "text": "TEXT",
    "image": "IMAGE",
    "audio": "AUDIO",
    "document": "FILE",
}
"""
# actually we need MessageType from app.core.models
# Let's just grab the original _WHATSAPP_TYPE_MAP
with open("03-development/src/app/api/webhooks.py", "r") as f:
    webhooks_content = f.read()
import re
match = re.search(r'(_WHATSAPP_TYPE_MAP: dict\[str, MessageType\] = \{.*?\n\})', webhooks_content, re.DOTALL)
if match:
    map_code = match.group(1)
    if map_code not in content:
        content = content.replace("class WhatsAppWebhookAdapter", map_code + "\n\nclass WhatsAppWebhookAdapter")
        with open("03-development/src/app/api/adapters/whatsapp.py", "w") as f:
            f.write(content)

# 2. Fix web.py
with open("03-development/src/app/api/adapters/web.py", "r") as f:
    content = f.read()
if "WebJwtVerifier" not in content[:500]:
    content = content.replace("from app.api.adapters.base import BaseWebhookAdapter", "from app.api.adapters.base import BaseWebhookAdapter\nfrom app.api.adapters.verifiers import WebJwtVerifier")
    with open("03-development/src/app/api/adapters/web.py", "w") as f:
        f.write(content)

# 3. Fix utils.py
with open("03-development/src/app/api/adapters/utils.py", "r") as f:
    content = f.read()
if "import base64 as _base64" not in content:
    content = content.replace("import base64", "import base64\nimport base64 as _base64")
    with open("03-development/src/app/api/adapters/utils.py", "w") as f:
        f.write(content)

# 4. Fix _register_webhook_routes(router)
if "_register_webhook_routes(router)" not in webhooks_content:
    webhooks_content += "\n_register_webhook_routes(router)\n"
    with open("03-development/src/app/api/webhooks.py", "w") as f:
        f.write(webhooks_content)

print("Applied fixes")
