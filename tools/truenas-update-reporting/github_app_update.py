#!/usr/bin/env python3
"""Opt-in, versioned GitHub source updates for existing TrueNAS Compose services."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

import custom_app_changelog as reporting

ROOT = Path(__file__).resolve().parent


def run(args, timeout=90):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Build output contains only public source; never print Compose config/env.
        raise RuntimeError(f'{args[0]} {args[1]} failed: {result.stderr[-3000:]}')
    return result.stdout


def inspect(container):
    return json.loads(run(['docker', 'inspect', container]))[0]


def container_for(app, service):
    ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=ix-' + app,
               '--filter', 'label=com.docker.compose.service=' + service]).split()
    if len(ids) != 1:
        raise ValueError(f'Expected exactly one container for {app}/{service}')
    return ids[0]


def plan():
    plans = {}
    for app, config in reporting.read_json(reporting.CONFIG, {}).items():
        spec = config.get('source_update')
        if not spec:
            continue
        service = spec['service']
        repo = config['services'][service]['repository']
        branch = spec.get('branch', 'main')
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[\w./-]+', branch):
            raise ValueError('Invalid configured GitHub repository/ref')
        remote = run(['git', 'ls-remote', 'https://github.com/' + repo + '.git', 'refs/heads/' + branch]).split()
        if not remote or not re.fullmatch(r'[0-9a-f]{40}', remote[0]):
            raise ValueError('Could not resolve GitHub branch')
        revision = remote[0]
        base = f'https://raw.githubusercontent.com/{repo}/{revision}/'
        release = json.loads(reporting.fetch(base + 'app-release.json'))
        version = release.get('version')
        if release.get('repository') != repo or not reporting.numeric_version(version):
            raise ValueError('Invalid release manifest')
        if version not in [v for v, _ in reporting.sections(reporting.fetch(base + 'CHANGELOG.md'))]:
            raise ValueError('Release has no exact versioned changelog section')
        current = reporting.capture(app)['services'][service].get('version')
        if not reporting.numeric_version(current):
            raise ValueError('Installed application version is unknown')
        if reporting.numeric_version(version) < reporting.numeric_version(current):
            raise ValueError('Refusing automatic application downgrade')
        plans[app] = dict(spec, repository=repo, revision=revision, version=version,
                          previous_version=current, pending=version != current)
    return plans


def identity(c):
    # Compare secrets without recording them in the deployment receipt or logs.
    values = {key: c['Config'].get(key) for key in ('Env', 'Cmd', 'Entrypoint', 'User')}
    values['Env'] = sorted(values['Env'] or [])
    values['mounts'] = sorted((m['Type'], m['Source'], m['Destination'], m['RW']) for m in c['Mounts'])
    values['ports'] = c['HostConfig'].get('PortBindings')
    values['network'] = c['HostConfig'].get('NetworkMode')
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def verify(app, spec, image_id, before):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = inspect(container_for(app, spec['service']))
        if identity(current) != identity(before):
            raise RuntimeError('Deployment changed environment, mounts, ports or runtime settings')
        if current['Image'] != image_id:
            raise RuntimeError('Deployed image does not match the built image')
        if current['State']['Running']:
            try:
                version = reporting.capture(app)['services'][spec['service']]['version']
                health = json.loads(reporting.fetch(spec['health_url']))
                if version == spec['version'] and health.get('status') == 'ok' and health.get('app_version') == version:
                    return current
            except (OSError, ValueError):
                pass
        time.sleep(2)
    raise RuntimeError('Expected application version/health was not verified within 90 seconds')


def apply(app, spec):
    if not spec['pending']:
        print('No newer GitHub application release; existing service preserved.')
        return
    before = inspect(container_for(app, spec['service']))
    observed = reporting.capture(app)['services'][spec['service']]['version']
    if observed != spec['previous_version']:
        raise ValueError('Installed version changed after release planning; rerun discovery')
    labels = before['Config']['Labels']
    if labels.get('com.docker.compose.project') != 'ix-' + app:
        raise ValueError('Compose project mismatch')
    files = labels['com.docker.compose.project.config_files'].split(',')
    compose = ['docker', 'compose', '-p', 'ix-' + app]
    for file in files:
        if not Path(file).is_absolute() or not Path(file).is_file():
            raise ValueError('Compose file missing')
        compose += ['-f', file]
    config = json.loads(run(compose + ['config', '--format', 'json']))
    service = config['services'][spec['service']]
    context = service.get('build', {}).get('context', '')
    expected = 'https://github.com/' + spec['repository'] + '.git#'
    if not context.startswith(expected):
        raise ValueError('Configured build context does not match the mapped repository')
    image_tag = service['image']
    repo_tag = image_tag.rsplit(':', 1)[0]
    version_tag = repo_tag + ':' + spec['version']
    rollback_tag = repo_tag + ':rollback-' + before['Image'].split(':')[1][:12]
    run(['docker', 'tag', before['Image'], rollback_tag])
    # Build the exact reviewed commit before changing the running container.
    run(['docker', 'build', '--build-arg', 'VCS_REF=' + spec['revision'],
         '--label', 'org.opencontainers.image.source=https://github.com/' + spec['repository'],
         '--label', 'org.opencontainers.image.version=' + spec['version'],
         '--label', 'org.opencontainers.image.revision=' + spec['revision'],
         '-f', spec.get('dockerfile', 'Dockerfile'), '-t', version_tag,
         expected + spec['revision']], timeout=1200)
    image_id = json.loads(run(['docker', 'image', 'inspect', version_tag]))[0]['Id']
    receipt = dict(app=app, service=spec['service'], version=spec['version'],
                   revision=spec['revision'], image_id=image_id, previous_image_id=before['Image'],
                   image_tag=image_tag, version_tag=version_tag, status='built')
    receipts = ROOT / 'deployments'
    receipts.mkdir(mode=0o700, exist_ok=True)
    receipt_path = receipts / f'{app}-{spec["version"]}-{time.time_ns()}.json'
    reporting.save_json(receipt_path, receipt)
    try:
        run(['docker', 'tag', image_id, image_tag])
        run(compose + ['up', '-d', '--no-build', '--pull', 'never', '--no-deps', spec['service']], timeout=300)
        verify(app, spec, image_id, before)
    except Exception:
        run(['docker', 'tag', before['Image'], image_tag])
        run(compose + ['up', '-d', '--no-build', '--pull', 'never', '--no-deps', spec['service']], timeout=300)
        restored = inspect(container_for(app, spec['service']))
        receipt['status'] = 'rolled_back' if restored['Image'] == before['Image'] and identity(restored) == identity(before) and restored['State']['Running'] else 'rollback_not_verified'
        reporting.save_json(receipt_path, receipt)
        raise
    receipt['status'] = 'verified'
    reporting.save_json(receipt_path, receipt)
    print(f'Verified {app}/{spec["service"]}: {spec["previous_version"]} -> {spec["version"]}; {image_id}; commit {spec["revision"]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'apply'])
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    if args.action == 'plan':
        print(json.dumps(plan()))
    else:
        path, app = args.args
        apply(app, reporting.read_json(path)[app])


if __name__ == '__main__':
    main()
