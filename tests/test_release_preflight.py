"""Preflight must remain independent of image builds and qualification claims."""
from pathlib import Path
import unittest


class PreflightTests(unittest.TestCase):
    def test_native_read_only_probe_and_honest_result(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows/aarch64-release-preflight.yml').read_text()
        for value in ['ubuntu-24.04-arm', 'PREFLIGHT_ONLY_NOT_QUALIFIED',
                      '/dev/kvm', 'qemu-system-aarch64', 'workflow_dispatch',
                      'retention-days: 14']:
            self.assertIn(value, text)
        for forbidden in ['docker build', 'docker load', 'docker pull',
                          'READY_FOR_INSTALL', 'deploy/debug', 'secrets.']:
            self.assertNotIn(forbidden, text)

    def test_probe_does_not_acquire_or_boot_os_media(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows/aarch64-release-preflight.yml').read_text()
        for value in ['.iso', '-accel tcg', 'apt-get install', 'MEDIA_BOOT_ONLY_NOT_QUALIFIED']:
            self.assertNotIn(value, text)

    def test_workflow_only_changes_do_not_trigger_source_build(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows/arm64-smoke.yml').read_text()
        self.assertNotIn('  push:', text)


if __name__ == '__main__':
    unittest.main()
