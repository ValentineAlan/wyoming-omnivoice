#!/usr/bin/env python3
"""CI gate: runtime changes need a new version and versioned release notes."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys


def version(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(t, ast.Name) and t.id in ('APP_VERSION', 'VERSION') for t in node.targets):
                return node.value.value
    raise SystemExit('No application version constant found')


main_file = Path('app.py') if Path('app.py').exists() else Path('wyoming_omnivoice.py')
current = version(main_file.read_text())
metadata = json.loads(Path('app-release.json').read_text())
assert metadata.get('version') == current, 'app-release.json must match the runtime application version'
changelog = Path('CHANGELOG.md').read_text()
assert re.search(r'^## \[?v?' + re.escape(current) + r'(?:\]|\s|$)', changelog, re.M), \
    f'CHANGELOG.md needs a ## {current} release section'
if len(sys.argv) > 1 and sys.argv[1] and set(sys.argv[1]) != {'0'}:
    base = sys.argv[1]
    changed = subprocess.check_output(['git', 'diff', '--name-only', base, 'HEAD'], text=True).splitlines()
    runtime = [p for p in changed if '/' not in p and (p.endswith('.py') or p in ('requirements.lock', 'constraints.txt'))]
    if runtime:
        old = subprocess.check_output(['git', 'show', base + ':' + str(main_file)], text=True)
        assert version(old) != current, 'Runtime changes require a new application version; do not reuse release numbers'
        assert 'CHANGELOG.md' in changed, 'Runtime changes must update CHANGELOG.md in the same change'
print('Versioned changelog verified:', current)
