#!/usr/bin/python3
"""Install a personal native layout and mod without editing shipped files."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 9):
        raise SystemExit('Python 3.9+ is required. On macOS run: /usr/bin/python3 install.py')
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='main', help='Layout to duplicate on first install')
    parser.add_argument('--layout', default='usage', help='Personal layout name')
    args = parser.parse_args()
    python = '/usr/bin/python3' if sys.platform == 'darwin' else sys.executable
    probe = subprocess.run([python, '-c', 'import sys; sys.exit(sys.version_info < (3, 9))'],
                           capture_output=True, text=True)
    if probe.returncode:
        raise SystemExit('Apple Python 3.9+ is required. Install or update Xcode Command Line Tools.')
    if not args.layout.replace('-', '').replace('_', '').isalnum():
        parser.error('Use letters, numbers, hyphens or underscores for layout names')
    home = Path(os.environ.get('HERDR_APP_HOME', str(Path.home() / '.config/herdr-app')))
    app = shutil.which('herdr-app') or '/Applications/Herdr.app/Contents/MacOS/Herdr'
    dest = home / 'mods/plan-usage'
    layout = home / 'layouts' / f'{args.layout}.json'
    record = PROJECT / 'installation.json'
    previous = json.loads(record.read_text()) if record.exists() else {}
    if dest.exists() and not (dest / 'herdr-usage-project.json').exists():
        raise SystemExit(f'Refusing to overwrite existing mod: {dest}')
    if layout.exists() and previous.get('layout') != str(layout):
        raise SystemExit(f'Refusing to overwrite existing layout: {layout}')
    # Validate the source before introducing it into the live app.
    subprocess.run([app, 'check', str(PROJECT / 'mods/plan-usage')], check=True)
    if not layout.exists():
        subprocess.run([app, 'do', 'layout.clone', json.dumps(dict(name=args.base, **{'as': args.layout}))], check=True)
    backup = PROJECT / 'backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    shutil.copy2(layout, backup / layout.name)
    if dest.exists():
        shutil.copytree(dest, backup / 'plan-usage')
    dest.mkdir(parents=True, exist_ok=True)
    for file in (PROJECT / 'mods/plan-usage').iterdir():
        if file.suffix in ('.js', '.json', '.svg'):
            shutil.copy2(file, dest / file.name)
    # Bundle the helper with the installed mod so moving the project won't break it.
    shutil.copy2(PROJECT / 'collector.py', dest / 'collector.py')
    shutil.copy2(PROJECT / 'google_api.py', dest / 'google_api.py')
    shutil.copy2(PROJECT / 'compat.py', dest / 'compat.py')
    (dest / 'runner.json').write_text(json.dumps(dict(python=python, collector=str(dest / 'collector.py')), indent=2) + '\n')
    (dest / 'herdr-usage-project.json').write_text(json.dumps(dict(project=str(PROJECT))) + '\n')
    tree = json.loads(layout.read_text())

    def visit(node):
        if node.get('id') == 'plan-usage-panel':
            node['min'] = 80
            return True
        return any(visit(child) for child in node.get('children', []))

    def sidebar(node):
        if node.get('id') == 'sidebar':
            return node
        for child in node.get('children', []):
            result = sidebar(child)
            if result is not None:
                return result

    if not visit(tree):
        host = sidebar(tree)
        if host is None:
            raise SystemExit('This layout has no sidebar. Choose a --base with a sidebar.')
        children = host['children']
        index = next((i for i, child in enumerate(children) if child.get('id') == 'sidebar-footer'), len(children))
        children.insert(index, dict(id='plan-usage-panel', type='block', size=dict(px=310),
                                    min=80, max=600, content=dict(mod='plan-usage')))
    host = sidebar(tree)
    if host and not any(child.get('id') == 'usage-sidebar-body' for child in host['children']):
        children = host['children']
        lists = next((child for child in children if child.get('id') == 'sidebar-lists'), None)
        panel = next((child for child in children if child.get('id') == 'plan-usage-panel'), None)
        if lists and panel:
            index = children.index(lists)
            lists['size'] = dict(weight=1)
            children.remove(lists)
            children.remove(panel)
            children.insert(index, dict(id='usage-sidebar-body', type='column', size=dict(weight=1),
                                        resizable=True, divider=dict(width=1, color='border'),
                                        children=[lists, panel]))
    layout.write_text(json.dumps(tree, indent=2) + '\n')
    record.write_text(json.dumps(dict(layout=str(layout), mod=str(dest), base=args.base), indent=2) + '\n')
    subprocess.run([app, 'check', str(dest)], check=True)
    subprocess.run([app, 'do', 'layout.switch', json.dumps(dict(name=args.layout))], check=True)
    print(f'Installed: {dest}\nLayout: {args.layout}\nBackup: {backup}')


if __name__ == '__main__':
    main()
