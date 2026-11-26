import importlib.util
from pathlib import Path
import unittest

REPO=Path(__file__).resolve().parents[3]
ROOT=REPO/'skills/full-build-deploy'


class TLSContract(unittest.TestCase):
    def setUp(self):
        path=ROOT/'tools/tls_contract.py'
        self.assertTrue(path.exists(), 'approved TLS gate is missing')
        spec=importlib.util.spec_from_file_location('tls_contract',path)
        self.policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.policy)
        self.public={'TLS_MODE':'caddy-public-acme','SITE_SCHEME':'https','SITE_DOMAIN':'meet.example.com','SITE_PORT':'443'}

    def test_public_config(self):
        result=self.policy.validate(self.public,'caddy-public-acme','https://other.example.com')
        self.assertEqual(result['tls_mode'],'caddy-public-acme')
        self.assertEqual(result['origin'],'https://other.example.com')

    def test_missing_or_mismatched_approval(self):
        for mode,origin in [('', ''),('unknown','https://meet.example.com')]:
            with self.assertRaises(ValueError):self.policy.validate(self.public,mode,origin)

    def test_public_rejects_private_trust(self):
        result=self.policy.validate(dict(self.public,CLIENT_CA_FILE='ca.crt'),'caddy-public-acme','https://other.example.com')
        self.assertIsNone(result['client_ca_file'])

    def test_private_requires_ca(self):
        private=dict(self.public,TLS_MODE='private-ca')
        self.policy.validate(private,'private-ca','https://meet.example.com')
        self.policy.validate(dict(private,CLIENT_CA_FILE='ca.crt'),'private-ca','https://other.example.com')

    def test_private_ip_origin_and_explicit_https_port(self):
        private=dict(self.public,TLS_MODE='private-ca',CLIENT_CA_FILE='ca.crt')
        for origin in ('https://192.0.2.7:8443','https://[2001:db8::7]:9443'):
            result=self.policy.validate(private,'private-ca',origin)
            self.assertEqual(result['origin'],origin)
            self.assertEqual(result['site_port'],origin.rsplit(':',1)[1])
        with self.assertRaisesRegex(ValueError,'Public ACME'):
            self.policy.validate(self.public,'caddy-public-acme','https://example.com:8443')

    def test_evidence_must_match_approval(self):
        contract=self.policy.validate(self.public,'caddy-public-acme','https://meet.example.com')
        self.policy.require_evidence(contract,'caddy-public-acme','https://meet.example.com',None)
        for mode,origin,ca in [('private-ca','https://meet.example.com','a'*64),(None,'https://meet.example.com',None),('caddy-public-acme','https://other.example.com',None),('caddy-public-acme','https://meet.example.com','a'*64)]:
            with self.assertRaises(ValueError):self.policy.require_evidence(contract,mode,origin,ca)

    def test_duplicate_config_rejected(self):
        with self.assertRaises(ValueError):self.policy.parse('TLS_MODE=private-ca\nTLS_MODE=caddy-public-acme')

    def test_all_reusable_calls_propagate_approval(self):
        import re
        directory=REPO/'.github/workflows'
        for path in directory.glob('*.yml'):
            for job in re.split(r'(?m)^  [a-z][a-z_-]*:\s*$',path.read_text(encoding='utf-8')):
                if 'uses: ./.github/workflows/' in job:
                    for key in ('expected_tls_mode','expected_origin'):
                        self.assertIn('      '+key+': ${{ inputs.'+key+' }}',job,str(path))

    def test_allocation_gate_precedes_allocator(self):
        text=(REPO/'.github/workflows/revision-allocation.yml').read_text()
        self.assertLess(text.index('tools/tls_contract.py'),text.index('tools/allocate-workflow.py'))

    def test_joint_prepare_fails_before_artifact_access_on_wrong_approval(self):
        import os
        import subprocess
        import sys
        import json
        contract={'origin':'https://meet.example.com','tls_mode':'caddy-public-acme',
                  'scheme':'https','host':'meet.example.com','port':443,
                  'site_domain':'meet.example.com','site_scheme':'https','site_port':'443',
                  'client_ca_file':None,'addresses':['192.0.2.8']}
        env=dict(os.environ,EXPECTED_TLS_MODE='caddy-public-acme',EXPECTED_ORIGIN='https://wrong.example.com',
                 ORIGIN_CONTRACT_JSON=json.dumps(contract))
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/joint-release.py'),'prepare'],
                              cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('differs from approved origin contract',result.stderr)

    def test_publication_rechecks_approval_and_records_no_deployment(self):
        text=(ROOT/'tools/joint-release.py').read_text()
        publication=text.split('def publish():',1)[1]
        self.assertLess(publication.index('approved_contract()'),publication.index("['gh','release','create'"))
        self.assertIn("record.get('approved_tls_contract')!=contract",publication)
        self.assertIn('NOT_DEPLOYED: publication does not change the live certificate',publication)


if __name__=='__main__':unittest.main()
