import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


class TLSContract(unittest.TestCase):
    def setUp(self):
        path=ROOT/'build-tools/tls_contract.py'
        self.assertTrue(path.exists(), 'approved TLS gate is missing')
        spec=importlib.util.spec_from_file_location('tls_contract',path)
        self.policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.policy)
        self.public={'TLS_MODE':'caddy-public-acme','SITE_SCHEME':'https','SITE_DOMAIN':'meet.example.com','SITE_PORT':'443'}

    def test_public_config(self):
        self.assertEqual(self.policy.validate(self.public,'caddy-public-acme','https://meet.example.com')['tls_mode'],'caddy-public-acme')

    def test_missing_or_mismatched_approval(self):
        for mode,origin in [('', ''),('private-ca','https://meet.example.com'),('caddy-public-acme','https://other.example.com')]:
            with self.assertRaises(ValueError):self.policy.validate(self.public,mode,origin)

    def test_public_rejects_private_trust(self):
        with self.assertRaises(ValueError):self.policy.validate(dict(self.public,CLIENT_CA_FILE='ca.crt'),'caddy-public-acme','https://meet.example.com')

    def test_private_requires_ca(self):
        private=dict(self.public,TLS_MODE='private-ca')
        with self.assertRaises(ValueError):self.policy.validate(private,'private-ca','https://meet.example.com')
        self.policy.validate(dict(private,CLIENT_CA_FILE='ca.crt'),'private-ca','https://meet.example.com')

    def test_evidence_must_match_approval(self):
        contract=self.policy.validate(self.public,'caddy-public-acme','https://meet.example.com')
        self.policy.require_evidence(contract,'caddy-public-acme','https://meet.example.com',None)
        for mode,origin,ca in [('private-ca','https://meet.example.com','a'*64),(None,'https://meet.example.com',None),('caddy-public-acme','https://other.example.com',None),('caddy-public-acme','https://meet.example.com','a'*64)]:
            with self.assertRaises(ValueError):self.policy.require_evidence(contract,mode,origin,ca)

    def test_duplicate_config_rejected(self):
        with self.assertRaises(ValueError):self.policy.parse('TLS_MODE=private-ca\nTLS_MODE=caddy-public-acme')

    def test_all_reusable_calls_propagate_approval(self):
        import re
        directory=ROOT/'.github/workflows'
        for path in directory.glob('*.yml'):
            for job in re.split(r'(?m)^  [a-z][a-z_-]*:\s*$',path.read_text(encoding='utf-8')):
                if 'uses: ./.github/workflows/' in job:
                    for key in ('expected_tls_mode','expected_origin'):
                        self.assertIn('      '+key+': ${{ inputs.'+key+' }}',job,str(path))

    def test_allocation_gate_precedes_allocator(self):
        text=(ROOT/'.github/workflows/revision-allocation.yml').read_text()
        self.assertLess(text.index('python3 -B build-tools/tls_contract.py'),text.index('python3 -B build-tools/allocate-workflow.py'))

    def test_joint_prepare_fails_before_artifact_access_on_wrong_approval(self):
        import os
        import subprocess
        import sys
        env=dict(os.environ,EXPECTED_TLS_MODE='caddy-public-acme',EXPECTED_ORIGIN='https://wrong.example.com')
        result=subprocess.run([sys.executable,'-B',str(ROOT/'build-tools/joint-release.py'),'prepare'],
                              cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('differs from fixed config/client.env',result.stderr)

    def test_publication_rechecks_approval_and_records_no_deployment(self):
        text=(ROOT/'build-tools/joint-release.py').read_text()
        publication=text.split('def publish():',1)[1]
        self.assertLess(publication.index('approved_contract()'),publication.index("['gh','release','create'"))
        self.assertIn("record.get('approved_tls_contract')!=contract",publication)
        self.assertIn('NOT_DEPLOYED: publication does not change the live certificate',publication)


if __name__=='__main__':unittest.main()
