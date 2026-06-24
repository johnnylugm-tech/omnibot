import ast
import os
from pathlib import Path

# Tests in this file use hard-coded relative paths to enforce SAD.md
# architectural constraints. The relative paths assume the project root as
# CWD, which is true for normal `pytest` runs but FALSE for mutmut's
# subprocess (mutmut rewrites pytest's rootdir to a temp workdir under
# /tmp/_mutmut_score.*).
#
# Resolve from this test file's location so the paths work in both:
#   - Normal pytest: tests/test_constraints.py → ../../03-development/...
#   - Mutmut workdir: copy of test_constraints.py → same resolve still hits
#     the project root because the harness copies the file to the workdir
#     with the same directory structure (.../tests/test_constraints.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE_PATH = _PROJECT_ROOT / "03-development" / "src" / "app" / "core" / "pipeline.py"
_INFRA_DIR = _PROJECT_ROOT / "03-development" / "src" / "app" / "infra"


def test_paladin_executes_before_pii():
    """Enforce SAD.md rule: paladin_executes_before_pii in pipeline.py."""
    content = _PIPELINE_PATH.read_text()
    paladin_idx = content.find("self.paladin.check_input(content)")
    pii_idx = content.find("self.pii.mask(content)")
    assert paladin_idx != -1 and pii_idx != -1
    assert paladin_idx < pii_idx, "Paladin must execute before PII"

def test_infra_layer_isolation():
    """Enforce SAD.md rule: infra layer cannot import domain."""
    for root, _, files in os.walk(_INFRA_DIR):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file)) as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith(("app.core", "app.api", "app.services")):
                                raise AssertionError(f"Infra layer imports domain: {alias.name} in {file}")
                    elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("app.core", "app.api", "app.services")):
                        raise AssertionError(f"Infra layer imports domain: {node.module} in {file}")
