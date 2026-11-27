"""Exercise the complete shell report without updating apps or sending email."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

FAKE_MIDCLT = '''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
root=Path(os.environ['REPORT_TEST_ROOT'])
args=[x for x in sys.argv[1:] if x not in ('call','--job','-j')]
method=args.pop(0)
state=json.loads((root/'apps.json').read_text())
with (root/'calls.log').open('a') as f:f.write(method+' '+(args[0] if args and method!='mail.send' else '')+'\\n')
if method=='catalog.sync': print('null')
elif method=='app.query':
 if not args:result=state
 elif json.loads(args[0])[0][0]=='id':
  ids=json.loads(args[0])[0][2];result=[x for x in state if x['id'] in ids]
 else:result=[x for x in state if x['upgrade_available']]
 print(json.dumps(result))
elif method=='app.get_instance':print(json.dumps(next(x for x in state if x['id']==args[0])))
elif method=='app.upgrade_summary':print(json.dumps({'upgrade_human_version':'1.2.0_2','latest_human_version':'1.2.0_2','available_versions_for_upgrade':[]}))
elif method in ('app.start','app.stop','app.upgrade'):
 x=next(x for x in state if x['id']==args[0])
 if method=='app.start':x['state']='RUNNING'
 elif method=='app.stop':x['state']='STOPPED'
 else:
  if os.environ.get('REPORT_TEST_FAIL')=='1': print('simulated update failure',file=sys.stderr);sys.exit(1)
  x['upgrade_available']=False
 (root/'apps.json').write_text(json.dumps(state));print('null')
elif method=='mail.send':
 (root/'email.json').write_text(args[0]);print('null')
else:raise SystemExit('Unexpected method '+method)
'''


class ReportIntegration(unittest.TestCase):
    def run_case(self, manual=False, fail=False, source=False):
        with tempfile.TemporaryDirectory(prefix='report-test-', dir=ROOT) as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'; bin_dir.mkdir()
            fake = bin_dir / 'midclt'; fake.write_text(FAKE_MIDCLT); fake.chmod(0o700)
            for name in ['custom_app_changelog.py','custom-app-changelogs.json']:
                (root/name).write_bytes((ROOT/name).read_bytes())
            # Fully synthetic provenance and notes: tests must not depend on the
            # production version, Docker, GitHub availability, or NAS contents.
            fixture={'ebay-hunter-stack':{'name':'Hunter','services':{'hunter':{
                'image':'example/hunter:0.10.64','image_id':'sha256:fixture',
                'repository':'ValentineAlan/ebay-laptop-hunter','version':'0.10.64',
                'branch':'main','changelog_path':'CHANGELOG.md'}}}}
            (root/'capture-fixture.json').write_text(json.dumps(fixture))
            if source:
                (root/'github_app_update.py').write_text('''import sys,json
from pathlib import Path
root=Path(__file__).parent
if sys.argv[1]=='plan':
 print(json.dumps({'ebay-hunter-stack':{'pending':True}}))
else:
 state=json.loads((root/'capture-fixture.json').read_text())
 state['ebay-hunter-stack']['services']['hunter'].update(version='0.10.65',image_id='sha256:new')
 (root/'capture-fixture.json').write_text(json.dumps(state))
 with (root/'calls.log').open('a') as f:f.write('source.apply ebay-hunter-stack\\n')
''')
            injection='''
def capture(app):
    return read_json(ROOT / 'capture-fixture.json')[app]
def fixture_fetch(url):
    return '# Changelog\\n\\n## 0.10.65\\n\\n- New source release.\\n\\n## 0.10.64\\n\\n- Add crawlable buying categories.\\n\\n## 0.10.63\\n\\n- Previous release.\\n'
release_notes.__defaults__ = (fixture_fetch,)
report.__defaults__ = (fixture_fetch,)
'''
            helper=root/'custom_app_changelog.py'
            helper.write_text(helper.read_text().replace("if __name__ == '__main__':", injection+"\nif __name__ == '__main__':"))
            # Limit the integration fixture to Hunter; other native app logic is
            # covered by a synthetic packaging-only example below.
            config=json.loads((root/'custom-app-changelogs.json').read_text())
            config={k:v for k,v in config.items() if k=='ebay-hunter-stack'}
            (root/'custom-app-changelogs.json').write_text(json.dumps(config))
            subprocess.run(['python3',str(root/'custom_app_changelog.py'),'seed'],check=True)
            if manual:
                state=json.loads((root/'last-reported-custom-apps.json').read_text())
                state['ebay-hunter-stack']['services']['hunter']['version']='0.10.63'
                (root/'last-reported-custom-apps.json').write_text(json.dumps(state))
            apps=[{'id':'ebay-hunter-stack','name':'ebay-hunter-stack','custom_app':True,
                   'state':'STOPPED' if fail else 'RUNNING','version':'1.0.0','human_version':'1.0.0_custom',
                   'upgrade_available':not manual and not source,'metadata':{'title':'Custom App'}}]
            if not manual and not fail and not source:
                apps.append({'id':'native-example','name':'native-example','custom_app':False,
                             'state':'STOPPED','version':'1','human_version':'1.2.0_1','upgrade_available':True,
                             'metadata':{'title':'Native','name':'native','app_version':'1.2.0'}})
            if manual:
                # Full app.query output must not be passed as a single --argjson
                # argument. Real inventories can exceed Linux MAX_ARG_STRLEN.
                apps.append({'id':'unrelated-large-app','name':'unrelated-large-app','custom_app':False,
                             'state':'RUNNING','version':'1','human_version':'1','upgrade_available':False,
                             'metadata':{'description':'x'*200000}})
            (root/'apps.json').write_text(json.dumps(apps))
            script=(ROOT/'update-truenas-apps4.sh').read_text()
            script=script.replace('HELPER_DIR="/mnt/Decathlon/appdata/truenas-update-reporting"', 'HELPER_DIR="'+tmp+'"')
            script=script.replace('/var/run/update-truenas-apps.lock',tmp+'/test.lock')
            # Never rely on PATH interception: /tmp may be mounted noexec and
            # shell command lookup can bypass the fake executable. Invoke the
            # fake via Python using its absolute path at every call site.
            script=re.sub(r'\bmidclt\b', 'python3 '+str(fake), script)
            (root/'run.sh').write_text(script)
            env=dict(os.environ,PATH=str(bin_dir)+':'+os.environ['PATH'],REPORT_TEST_ROOT=tmp,
                     REPORT_TEST_FAIL='1' if fail else '0')
            subprocess.run(['bash',str(root/'run.sh')],env=env,check=True,timeout=150)
            payload=json.loads((root/'email.json').read_text())
            self.assertIn('<h1>TrueNAS app update report</h1>',payload['html'])
            self.assertNotIn('1.2.0_2\nunchanged',payload['text'])
            calls=(root/'calls.log').read_text()
            if source:
                self.assertIn('source.apply ebay-hunter-stack',calls)
                self.assertNotIn('app.upgrade ',calls)
                self.assertIn('GitHub application release installed and verified',payload['text'])
                self.assertIn('0.10.64 → 0.10.65',payload['text'])
                self.assertIn('New source release',payload['text'])
            elif manual:
                self.assertNotIn('app.upgrade ',calls)
                self.assertIn('Previously deployed change detected',payload['text'])
                self.assertIn('0.10.63 → 0.10.64',payload['text'])
                self.assertIn('crawlable buying categories',payload['text'])
            elif fail:
                self.assertIn('Update or state restoration failed',payload['text'])
                self.assertEqual(json.loads((root/'apps.json').read_text())[0]['state'],'STOPPED')
                self.assertIn('0 updated, 1 failed',payload['subject'])
            else:
                self.assertIn('TrueNAS packaging-only update',payload['text'])
                self.assertIn('No application/image change',payload['text'])
                self.assertIn('crawlable buying categories',payload['text'])
                self.assertEqual(json.loads((root/'apps.json').read_text())[1]['state'],'STOPPED')

    def test_pending_custom_and_native(self): self.run_case()
    def test_manual_deployment_without_pending_update(self): self.run_case(manual=True)
    def test_failure_restores_stopped_state(self): self.run_case(fail=True)
    def test_source_release_without_truenas_image_flag(self): self.run_case(source=True)


if __name__=='__main__':unittest.main()
