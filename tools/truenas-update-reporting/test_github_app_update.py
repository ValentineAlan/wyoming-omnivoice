import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import github_app_update as updater


class SourceUpdates(unittest.TestCase):
    def make_plan(self, current='1.0.0', target='1.0.1', notes=True):
        config = {'test-app': {'source_update': {'service': 'hunter'},
                              'services': {'hunter': {'repository': 'owner/repo'}}}}
        def fetch(url):
            if url.endswith('app-release.json'):
                return json.dumps({'repository': 'owner/repo', 'version': target})
            return '# Changelog\n\n## ' + (target if notes else '0.1.0') + '\n\n- Change\n'
        with patch.object(updater.reporting, 'read_json', return_value=config), \
             patch.object(updater.reporting, 'fetch', side_effect=fetch), \
             patch.object(updater.reporting, 'capture', return_value={'services': {'hunter': {'version': current}}}), \
             patch.object(updater, 'run', return_value='a' * 40 + '\trefs/heads/main\n'):
            return updater.plan()['test-app']

    def test_discovers_version_without_truenas_flag(self):
        result = self.make_plan()
        self.assertTrue(result['pending'])
        self.assertEqual(result['revision'], 'a' * 40)

    def test_same_version_does_not_restart(self):
        result = self.make_plan(target='1.0.0')
        self.assertFalse(result['pending'])
        with patch.object(updater, 'run') as run:
            updater.apply('test-app', result)
            run.assert_not_called()

    def test_rejects_downgrade_unknown_version_and_missing_notes(self):
        for args in ({'target': '0.9.0'}, {'current': None}, {'notes': False}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.make_plan(**args)

    def test_runtime_identity_detects_environment_ports_and_mount_changes(self):
        before = {'Config': {'Env': ['SECRET=opaque'], 'Cmd': ['python', 'app.py']},
                  'Mounts': [{'Type': 'bind', 'Source': '/persistent', 'Destination': '/data', 'RW': True}],
                  'HostConfig': {'PortBindings': {'8080/tcp': [{'HostPort': '8080'}]}, 'NetworkMode': 'project_default'}}
        for change in ('env', 'port', 'mount'):
            after = copy.deepcopy(before)
            if change == 'env': after['Config']['Env'] = ['SECRET=different']
            if change == 'port': after['HostConfig']['PortBindings'] = {}
            if change == 'mount': after['Mounts'][0]['Source'] = '/wrong'
            self.assertNotEqual(updater.identity(before), updater.identity(after))

    def deployment(self, build_failure=False, verify_failure=False, wrong_context=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / 'compose.yaml'; compose.write_text('services: {}')
            before = {'Config': {'Labels': {'com.docker.compose.project': 'ix-test-app',
                                           'com.docker.compose.project.config_files': str(compose)}, 'Env': ['SECRET=opaque']},
                      'HostConfig': {}, 'Mounts': [], 'Image': 'sha256:old', 'State': {'Running': True}}
            spec = {'pending': True, 'service': 'hunter', 'version': '1.0.1', 'previous_version': '1.0.0',
                    'revision': 'a' * 40, 'repository': 'owner/repo', 'health_url': 'http://localhost/healthz'}
            commands = []
            def run(args, timeout=90):
                commands.append(args)
                if args[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'services': {'hunter': {'image': 'hunter:github-main',
                                      'build': {'context': 'https://github.com/' + ('wrong/repo' if wrong_context else 'owner/repo') + '.git#main'}}}})
                if args[1:3] == ['image', 'inspect']:
                    return '[{"Id":"sha256:new"}]'
                if args[1] == 'build' and build_failure:
                    raise RuntimeError('build failed')
                return ''
            with patch.object(updater, 'ROOT', root), patch.object(updater, 'container_for', return_value='container'), \
                 patch.object(updater.reporting, 'capture', return_value={'services': {'hunter': {'version': '1.0.0'}}}), \
                 patch.object(updater, 'inspect', return_value=before), patch.object(updater, 'run', side_effect=run), \
                 patch.object(updater, 'verify', side_effect=RuntimeError('health failed') if verify_failure else None):
                if build_failure or verify_failure or wrong_context:
                    with self.assertRaises((RuntimeError, ValueError)):
                        updater.apply('test-app', spec)
                else:
                    updater.apply('test-app', spec)
            receipts = [json.loads(p.read_text()) for p in (root / 'deployments').glob('*.json')]
            return commands, receipts

    def test_build_failure_never_restarts(self):
        commands, _ = self.deployment(build_failure=True)
        self.assertFalse(any('up' in c for c in commands))

    def test_source_mismatch_rejected_before_build(self):
        commands, _ = self.deployment(wrong_context=True)
        self.assertFalse(any('build' in c for c in commands))

    def test_failed_health_rolls_back_and_records_failure(self):
        commands, receipts = self.deployment(verify_failure=True)
        self.assertIn(['docker', 'tag', 'sha256:old', 'hunter:github-main'], commands)
        self.assertEqual(len([c for c in commands if 'up' in c]), 2)
        self.assertEqual(receipts[0]['status'], 'rolled_back')

    def test_success_pins_commit_updates_only_service_and_records_receipt(self):
        commands, receipts = self.deployment()
        build = next(c for c in commands if c[1] == 'build')
        self.assertEqual(build[-1], 'https://github.com/owner/repo.git#' + 'a' * 40)
        up = next(c for c in commands if 'up' in c)
        self.assertEqual(up[-7:], ['up', '-d', '--no-build', '--pull', 'never', '--no-deps', 'hunter'])
        self.assertEqual(receipts[0]['status'], 'verified')
        self.assertNotIn('opaque', json.dumps(receipts))


if __name__ == '__main__':
    unittest.main()
