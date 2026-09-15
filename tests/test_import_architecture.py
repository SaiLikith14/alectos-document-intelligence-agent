import ast
from pathlib import Path


def test_db_base_does_not_import_model_modules():
    source = Path('app/db/base.py').read_text()
    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)

    assert not any(name.startswith('app.models') for name in imported_modules)
