import os
import ast
import pytest

def test_paladin_executes_before_pii():
    """Enforce SAD.md rule: paladin_executes_before_pii in pipeline.py."""
    with open("03-development/src/app/core/pipeline.py") as f:
        content = f.read()
    paladin_idx = content.find("self.paladin.check_input(content)")
    pii_idx = content.find("self.pii.mask(content)")
    assert paladin_idx != -1 and pii_idx != -1
    assert paladin_idx < pii_idx, "Paladin must execute before PII"

def test_infra_layer_isolation():
    """Enforce SAD.md rule: infra layer cannot import domain."""
    infra_dir = "03-development/src/app/infra"
    for root, _, files in os.walk(infra_dir):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file)) as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith(("app.core", "app.api", "app.services")):
                                raise AssertionError(f"Infra layer imports domain: {alias.name} in {file}")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith(("app.core", "app.api", "app.services")):
                            raise AssertionError(f"Infra layer imports domain: {node.module} in {file}")
