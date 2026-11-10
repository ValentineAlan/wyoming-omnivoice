import unittest
from custom_app_changelog import numeric_version, sections, release_notes, report, source_version, email_payload

LOG = '''# Changelog
## Unreleased
- Do not report this.
## 1.3.0
- Future change.
## [1.2.0] - 2026-11-10
- New voice support.
## 1.1.0
- Faster startup.
## 1.0.0
- Initial version.
'''


def item(version, image='sha256:a'):
    return {'version': version, 'image_id': image, 'image': 'example:test',
            'repository': 'owner/repo', 'branch': 'main'}


class NotesTests(unittest.TestCase):
    def test_runtime_version_extraction_does_not_execute(self):
        self.assertEqual(source_version('raise RuntimeError("never execute")\nAPP_VERSION="0.10.64"'), '0.10.64')

    def test_only_installed_version_range(self):
        text = release_notes(item('1.0.0'), item('1.2.0', 'sha256:b'), lambda _: LOG)
        self.assertIn('Faster startup', text)
        self.assertIn('New voice', text)
        self.assertNotIn('Future change', text)
        self.assertNotIn('Do not report', text)
        self.assertNotIn('Initial version', text)

    def test_same_version_context(self):
        text = release_notes(item('1.2.0'), item('1.2.0'), lambda _: LOG)
        self.assertIn('context, not new changes', text)
        self.assertNotIn('Faster startup', text)

    def test_same_version_different_image_warns(self):
        text = release_notes(item('1.2.0'), item('1.2.0', 'sha256:b'), lambda _: LOG)
        self.assertIn('without an application version change', text)

    def test_rollback(self):
        text = release_notes(item('1.2.0'), item('1.1.0', 'sha256:b'), lambda _: LOG)
        self.assertIn('rollback', text)
        self.assertNotIn('New voice', text)

    def test_no_fake_notes_on_network_failure(self):
        def fail(_):
            raise OSError('offline')
        text = release_notes(item('1.0.0'), item('1.2.0'), fail)
        self.assertIn('could not be verified', text)
        self.assertIn('github.com/owner/repo', text)

    def test_placeholder_not_application_version(self):
        self.assertIsNone(numeric_version('1.0.0_custom'))
        self.assertIsNone(numeric_version('latest'))

    def test_dependency_and_application_reported_separately(self):
        before = {'services': {'hunter': item('1.2.0'), 'browser': item('1.0.0')}}
        after = {'services': {'hunter': item('1.2.0'), 'browser': item('1.1.0', 'sha256:b')}}
        text = report(before, after, lambda _: LOG)
        self.assertIn('#### hunter', text)
        self.assertIn('#### browser', text)
        self.assertIn('No application/image change', text)
        self.assertIn('Application changes in the installed version range', text)

    def test_html_email_formats_and_sanitizes(self):
        data = email_payload('Test', '# Heading\n\n**Bold**\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n[good](https://github.com/owner/repo)')
        self.assertIn('<h1>Heading</h1>', data['html'])
        self.assertIn('<strong>Bold</strong>', data['html'])
        self.assertNotIn('<script>', data['html'])
        self.assertNotIn('href="javascript:', data['html'])
        self.assertIn('href="https://github.com/owner/repo"', data['html'])
        self.assertIn('**Bold**', data['text'])


if __name__ == '__main__':
    unittest.main()
