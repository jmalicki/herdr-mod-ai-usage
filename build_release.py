#!/usr/bin/python3
"""Build a source-only release ZIP from an explicit list of public files."""
import argparse
import hashlib
from pathlib import Path
import re
import zipfile

PROJECT = Path(__file__).resolve().parent
FILES = (
    'VERSION', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'collector.py', 'google_api.py', 'compat.py', 'install.py',
    'mods/plan-usage/main.js', 'mods/plan-usage/preferences.js',
    'mods/plan-usage/mod.json', 'mods/plan-usage/check.svg',
)


def build(name, version, output):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name):
        raise ValueError('Release name must contain only letters, digits, hyphens and underscores')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Expected a semantic version such as 0.1.0')
    output.mkdir(parents=True, exist_ok=True)
    stem = f'{name}-{version}'
    archive = output / f'{stem}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for relative in FILES:
            package.write(PROJECT / relative, f'{stem}/{relative}')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')
    return archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='herdr-mod-ai-usage')
    parser.add_argument('--version', default=(PROJECT / 'VERSION').read_text().strip())
    parser.add_argument('--output', type=Path, default=PROJECT / 'dist')
    args = parser.parse_args()
    print(build(args.name, args.version.removeprefix('v'), args.output))


if __name__ == '__main__':
    main()
