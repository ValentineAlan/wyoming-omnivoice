#!/usr/bin/env python3
"""Read-only Docker provenance capture and custom-app release notes for TrueNAS."""
import argparse
import ast
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'custom-app-changelogs.json'
STATE = ROOT / 'last-reported-custom-apps.json'


def command(*args):
    return subprocess.check_output(args, timeout=45)


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def save_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    os.chmod(temp, 0o600)
    temp.replace(path)


def container_file(container, path):
    # docker cp also works for stopped containers; never execute application code.
    result = subprocess.run(['docker', 'cp', container + ':' + path, '-'],
                            capture_output=True, timeout=30)
    if result.returncode:
        return None
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        for member in archive:
            if member.isfile() and member.size <= 2_000_000:
                return archive.extractfile(member).read()
    return None


def source_version(data):
    for node in ast.parse(data).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(t, ast.Name) and t.id in ('APP_VERSION', 'VERSION')
                   for t in node.targets) and isinstance(node.value.value, str):
                return node.value.value
    return None


def capture(app):
    config = read_json(CONFIG, {}).get(app, {})
    ids = command('docker', 'ps', '-aq', '--filter',
                  'label=com.docker.compose.project=ix-' + app).decode().split()
    services = {}
    for container in ids:
        c = json.loads(command('docker', 'inspect', container))[0]
        cl = c['Config'].get('Labels') or {}
        if cl.get('com.docker.compose.oneoff', '').lower() == 'true':
            continue
        service = cl.get('com.docker.compose.service', c['Name'])
        if service in services:
            raise ValueError('Multiple containers for service ' + service)
        image = json.loads(command('docker', 'image', 'inspect', c['Image']))[0]
        labels = image['Config'].get('Labels') or {}
        spec = config.get('services', {}).get(service, {})
        source = spec.get('repository') or labels.get('org.opencontainers.image.source', '')
        source = source.removeprefix('https://github.com/').removesuffix('.git').strip('/')
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', source):
            source = ''
        item = {'image': c['Config']['Image'], 'image_id': c['Image'],
                'repository': source, 'version': labels.get('org.opencontainers.image.version'),
                'revision': labels.get('org.opencontainers.image.revision'),
                'changelog_path': spec.get('changelog_path', 'CHANGELOG.md'),
                'branch': spec.get('branch', 'main')}
        metadata_version = None
        if spec:
            data = container_file(container, '/usr/local/share/app-release.json')
            if data:
                metadata = json.loads(data)
                if metadata.get('repository') == source and isinstance(metadata.get('version'), str):
                    metadata_version = metadata['version']
                    item['version'] = metadata_version
        # Configured code probes take priority over inherited base-image version labels.
        if spec.get('version_files'):
            item['version'] = None
            for path in spec['version_files']:
                data = container_file(container, path)
                if data:
                    try:
                        version = source_version(data)
                    except (SyntaxError, ValueError, UnicodeError):
                        continue
                    if version:
                        item['version'] = version
                        item['source_hash'] = hashlib.sha256(data).hexdigest()
                        break
        known = spec.get('known_images', {}).get(c['Image'])
        if known:
            item['version'] = known['version']
        # A helper may not have its own release number. Do not inherit Ubuntu's version.
        if spec.get('no_version'):
            item['version'] = metadata_version
        services[service] = item
    return {'name': config.get('name', app), 'services': services}


def numeric_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+(?:\.\d+){1,3}', value):
        return None
    parts = tuple(map(int, value.lstrip('v').split('.')))
    return parts + (0,) * (4 - len(parts))


def sections(markdown):
    output = []
    current = None
    for line in markdown.splitlines():
        if line.startswith('## '):
            match = re.match(r'^## \[?(v?\d+(?:\.\d+){1,3})(?:\]|\s|$)', line)
            current = [match.group(1), [line]] if match else None
            if current:
                output.append(current)
        elif current:
            current[1].append(line)
    return [(version, '\n'.join(lines).strip()) for version, lines in output]


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'TrueNAS-custom-app-changelog'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Changelog response exceeds size limit')
        return data.decode('utf-8')


def release_notes(old, new, loader=fetch):
    repo = new.get('repository')
    if not repo:
        return 'No verified source repository is configured for this service.'
    link = 'https://github.com/' + repo
    path = new.get('changelog_path', 'CHANGELOG.md')
    ref = new.get('revision') or new.get('branch', 'main')
    # Only full source revisions are trusted as immutable references.
    if not re.fullmatch(r'[0-9a-f]{40}', ref):
        ref = new.get('branch', 'main')
    history = f'{link}/blob/{ref}/{path}'
    old_v, new_v = numeric_version(old.get('version')), numeric_version(new.get('version'))
    changed = old.get('image_id') != new.get('image_id') or old.get('source_hash') != new.get('source_hash')
    try:
        text = loader(f'https://raw.githubusercontent.com/{repo}/{ref}/{path}')
        matches = []
        if new_v:
            if old_v and old_v < new_v:
                matches = [body for v, body in sections(text) if old_v < numeric_version(v) <= new_v]
                title = 'Application changes in the installed version range:'
            else:
                matches = [body for v, body in sections(text) if numeric_version(v) == new_v]
                title = 'Installed release notes (context, not new changes in this run):'
            if matches:
                warning = ''
                if changed and old_v == new_v:
                    warning = ('The image/code changed without an application version change; '
                               'these notes cannot identify the exact change.\n\n')
                if old_v and old_v > new_v:
                    warning = 'Application version decreased (rollback).\n\n'
                return warning + title + '\n\n' + '\n\n'.join(matches) + f'\n\n[GitHub changelog]({history})'
    except (urllib.error.URLError, ValueError, UnicodeError, TimeoutError, OSError):
        pass
    a, b = old.get('revision', ''), new.get('revision', '')
    if a and b and a != b and all(re.fullmatch(r'[0-9a-f]{40}', v) for v in (a, b)):
        try:
            comparison = json.loads(loader(f'https://api.github.com/repos/{repo}/compare/{a}...{b}'))
            if comparison.get('status') == 'ahead':
                commits = comparison.get('commits', [])
                lines = [f"- {c['commit']['message'].splitlines()[0]} ([commit]({c['html_url']}))" for c in commits[:30]]
                return 'Source commit notes (no matching release notes found):\n\n' + '\n'.join(lines) + f'\n\n[Full comparison]({link}/compare/{a}...{b})'
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError):
            pass
    return ('Matching release notes could not be verified for the installed version. '
            'No unrelated latest-release notes have been substituted.\n\n'
            f'[Source repository]({link}) · [Release history]({link}/releases) · [Changelog]({history})')


def report(before, after, loader=fetch):
    lines = ['### Custom application and image changes', '']
    old_services, new_services = before.get('services', {}), after.get('services', {})
    if not new_services:
        return 'Custom-app release metadata is unavailable; no deployed version could be verified.'
    for name, new in sorted(new_services.items()):
        old = old_services.get(name, {})
        same = bool(old) and all(old.get(k) == new.get(k) for k in ('image_id', 'source_hash', 'revision', 'version'))
        lines += [f'#### {name}', '', f"- Application version: {old.get('version') or 'unknown'} → {new.get('version') or 'unknown'}",
                  f"- Image: `{new['image']}`", f"- Installed image ID: `{new['image_id']}`",
                  '- Change: ' + ('No application/image change; existing build redeployed or checked.' if same else 'Installed image or application metadata changed.'), '',
                  release_notes(old, new, loader), '']
    for name in sorted(old_services.keys() - new_services.keys()):
        lines += [f'- Service removed: {name}']
    return '\n'.join(lines)


class SafeHTML(HTMLParser):
    tags = {'p','br','hr','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em','code','pre','blockquote','a','table','thead','tbody','tr','th','td'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            return
        attr = ''
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith(('https://', 'http://')):
                attr = ' href="' + html.escape(href, quote=True) + '"'
        self.parts.append('<' + tag + attr + '>')
    def handle_endtag(self, tag):
        if tag in self.tags:
            self.parts.append('</' + tag + '>')
    def handle_data(self, data):
        self.parts.append(html.escape(data))


def email_payload(subject, text):
    import markdown
    parser = SafeHTML()
    parser.feed(markdown.markdown(html.escape(text), extensions=['tables', 'fenced_code']))
    return {'subject': subject, 'text': text,
            'html': '<html><body><div style="font-family:Arial,sans-serif;max-width:900px">' + ''.join(parser.parts) + '</div></body></html>'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['capture', 'report', 'mail', 'seed', 'changed', 'commit'])
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    if args.action == 'capture':
        save_json(args.args[1], capture(args.args[0]))
    elif args.action == 'report':
        before = read_json(args.args[0], {})
        after = read_json(args.args[1], {})
        print(report(before, after))
    elif args.action == 'mail':
        print(json.dumps(email_payload(args.args[0], Path(args.args[1]).read_text())))
    elif args.action in ('seed', 'changed'):
        state = read_json(STATE, {})
        current = {app: capture(app) for app in read_json(CONFIG, {})}
        if args.action == 'seed':
            save_json(STATE, current)
        else:
            print(json.dumps([app for app, value in current.items() if app in state and state[app] != value]))
    elif args.action == 'commit':
        state = read_json(STATE, {})
        state[args.args[0]] = read_json(args.args[1])
        save_json(STATE, state)


if __name__ == '__main__':
    main()
