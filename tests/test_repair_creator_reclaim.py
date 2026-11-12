import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('repair', Path(__file__).parents[1]/'tools/repair-creator-reclaim.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class RepairTests(unittest.TestCase):
    def test_enable_preserves_secret_and_admin_setting(self):
        text = ('host_transfer_enabled = true;\nhost_reclaim_enabled = false;\n'
                'host_role_check_secret = "unchanged";\nhost_transfer_admin_recovery_enabled = false;\n')
        result = repair.updated_config(text)
        self.assertIn('host_reclaim_enabled = true;', result)
        self.assertIn('host_reclaim_url = "https://gateway:9443/internal/host-role/v1/reclaim";', result)
        self.assertIn('host_role_check_secret = "unchanged";', result)
        self.assertIn('host_transfer_admin_recovery_enabled = false;', result)
        self.assertEqual(repair.updated_config(result), result)

    def test_reject_disabled_transfer_or_duplicate(self):
        for text in ['host_transfer_enabled = false;',
                     'host_transfer_enabled = true;\nhost_reclaim_enabled = false;\nhost_reclaim_enabled = true;']:
            with self.assertRaises(ValueError):
                repair.updated_config(text)


if __name__ == '__main__':
    unittest.main()
