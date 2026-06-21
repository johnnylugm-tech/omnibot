import ast
import subprocess

def get_logical_lines(source: str) -> int:
    try:
        parsed = ast.parse(source)
    except Exception:
        return len(source.splitlines())
        
    class DocstringRemover(ast.NodeTransformer):
        def _remove_docstring(self, node):
            self.generic_visit(node)
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                node.body = node.body[1:]
            return node
        def visit_Module(self, node): return self._remove_docstring(node)
        def visit_ClassDef(self, node): return self._remove_docstring(node)
        def visit_FunctionDef(self, node): return self._remove_docstring(node)
        def visit_AsyncFunctionDef(self, node): return self._remove_docstring(node)
        
    parsed = DocstringRemover().visit(parsed)
    try:
        unparsed = ast.unparse(parsed)
        return len(unparsed.splitlines())
    except Exception:
        return len(source.splitlines())

pre_source = subprocess.run(["git", "show", "818ec01^:03-development/src/app/admin/webui.py"], capture_output=True, text=True).stdout
post_source = subprocess.run(["git", "show", "818ec01:03-development/src/app/admin/webui.py"], capture_output=True, text=True).stdout

pre_lines = get_logical_lines(pre_source)
post_lines = get_logical_lines(post_source)

print(f"Pre logical lines: {pre_lines}")
print(f"Post logical lines: {post_lines}")
print(f"Net logical removed: {pre_lines - post_lines}")
