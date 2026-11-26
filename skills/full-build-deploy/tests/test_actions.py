import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class ActionsTests(unittest.TestCase):
    def test_dispatch_forwards_explicit_approval_and_persists_it(self):
        import json
        import sys
        import tempfile
        path=Path(__file__).parents[1]/'tools'/'actions.py'
        spec=importlib.util.spec_from_file_location('actions_entry',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            token=Path(tmp)/'token';token.write_text('fixture');token.chmod(0o600)
            record=Path(tmp)/'task.json'
            argv=['actions.py','--token-file',str(token),'--record',str(record),'dispatch',
                  '--commit','a'*40,'--scope','joint','--expected-tls-mode','caddy-public-acme',
                  '--expected-origin','https://meet.example.com']
            with patch.object(sys,'argv',argv),patch.object(module,'api',side_effect=[{'object':{'sha':'a'*40}},{}]) as api:
                module.main()
            inputs=api.call_args.args[2]['inputs']
            self.assertEqual(inputs['expected_tls_mode'],'caddy-public-acme')
            self.assertEqual(inputs['expected_origin'],'https://meet.example.com')
            self.assertEqual(json.loads(record.read_text())['approved_tls_contract']['tls_mode'],'caddy-public-acme')

    def test_dispatch_never_accepts_manual_version(self):
        text=(Path(__file__).parents[1]/'tools'/'actions.py').read_text()
        self.assertNotIn("dispatch.add_argument('--version'", text)
        self.assertIn('build-joint.yml', text)
    def test_api_targets_only_reviewed_repository(self):
        path=Path(__file__).parents[1]/'tools'/'actions.py'
        spec=importlib.util.spec_from_file_location('actions_entry',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.urllib.request,'urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value=b'{"ok":true}'
            self.assertEqual(module.api('fixture-token','/actions/runs/123'),{'ok':True})
            req=request.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.github.com/repos/stevenzxs/cloudemeet-deploy/actions/runs/123')
            self.assertNotIn('fixture-token',req.full_url)


if __name__=='__main__':unittest.main()
