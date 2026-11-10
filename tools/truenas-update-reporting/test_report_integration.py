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
 print(json.dumps([x for x in state if x['upgrade_available']] if args else state))
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
    def run_case(self, manual=False, fail=False):
        with tempfile.TemporaryDirectory(prefix='report-test-', dir=ROOT) as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'; bin_dir.mkdir()
            fake = bin_dir / 'midclt'; fake.write_text(FAKE_MIDCLT); fake.chmod(0o700)
            for name in ['custom_app_changelog.py','custom-app-changelogs.json']:
                (root/name).write_bytes((ROOT/name).read_bytes())
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
                   'upgrade_available':not manual,'metadata':{'title':'Custom App'}}]
            if not manual and not fail:
                apps.append({'id':'native-example','name':'native-example','custom_app':False,
                             'state':'STOPPED','version':'1','human_version':'1.2.0_1','upgrade_available':True,
                             'metadata':{'title':'Native','name':'native','app_version':'1.2.0'}})
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
            calls=(root/'calls.log').read_text()
            if manual:
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


if __name__=='__main__':unittest.main()
