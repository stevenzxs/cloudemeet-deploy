import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class ActionsTests(unittest.TestCase):
    def test_dispatch_never_accepts_manual_version(self):
        text=(Path(__file__).parents[1]/'actions.py').read_text()
        self.assertNotIn("dispatch.add_argument('--version'", text)
        self.assertIn('build-joint.yml', text)
    def test_api_targets_only_reviewed_repository(self):
        path=Path(__file__).parents[1]/'actions.py'
        spec=importlib.util.spec_from_file_location('actions_entry',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.urllib.request,'urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value=b'{"ok":true}'
            self.assertEqual(module.api('fixture-token','/actions/runs/123'),{'ok':True})
            req=request.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.github.com/repos/stevenzxs/cloudemeet-deploy/actions/runs/123')
            self.assertNotIn('fixture-token',req.full_url)


if __name__=='__main__':unittest.main()
