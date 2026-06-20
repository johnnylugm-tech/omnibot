"""Quick AST inspection: confirm pii.py has imports right after from __future__."""
import ast

path = "/Users/johnny/projects/omnibot/03-development/src/app/core/pii.py"
with open(path) as f:
    src = f.read()

tree = ast.parse(src)
print("First 8 top-level statements:")
for i, node in enumerate(tree.body[:8]):
    print(f"  {i + 1}. {type(node).__name__}", end="")
    if hasattr(node, "name"):
        print(f" name={node.name!r}", end="")
    if hasattr(node, "names"):
        print(f" names={[n.name for n in node.names]!r}", end="")
    print()
