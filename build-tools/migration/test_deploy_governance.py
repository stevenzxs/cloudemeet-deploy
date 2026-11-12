"""Current packaging routes and documentation; no Docker or legacy tools."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class GovernanceTests(unittest.TestCase):
    def test_current_inventory_is_complete(self):
        spec = importlib.util.spec_from_file_location('layout', ROOT / 'deploy/tools/check-deployment-layout.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(ROOT), [])
        self.assertTrue(module.validate_catalog({'schema_version': 1, 'routes': []}))

    def test_policy_and_current_files_are_documented(self):
        policy = (ROOT / 'deploy/AGENTS.md').read_text(encoding='utf-8')
        for name in ('package.sh', 'build-package.yml', 'sources.json', 'inputs.sha256',
                     'test_package.py', 'test_offline_installer.py', 'test_deploy_governance.py'):
            self.assertIn(name, policy)
        for value in ('唯一规范源', '不以安装测试作为进入release的条件', '不要求麒麟ISO',
                      '完整编译七服务', '未提交/未推送的本机改动不会自动进入runner'):
            self.assertIn(value, policy)

    def test_no_old_route_is_needed_by_new_orchestrator(self):
        script = (ROOT / 'deploy/build-tools/package.sh').read_text(encoding='utf-8')
        for value in ('build-tools-old', 'release-qualified', 'assemble-kylin', 'arm64-stack-lock'):
            self.assertNotIn(value, script)


if __name__ == '__main__':
    unittest.main()
