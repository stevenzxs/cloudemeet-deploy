"""Mock-only installer checks: never call host systemctl or install binaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'release/install-docker.sh'


class InstallerTests(unittest.TestCase):
    def run_mock(self, arch='aarch64', uid='0', checksum=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'install-docker.sh'
            script.write_bytes(SCRIPT.read_bytes())
            (root / 'docker-27.3.1.tgz').write_bytes(b'mock archive')
            for name, body in {
                'id': f'echo {uid}',
                'uname': f'if [[ "$1" == -s ]]; then echo Linux; else echo {arch}; fi',
                'sha256sum': 'exit ' + ('0' if checksum else '1'),
                'systemctl': 'exit 0',
            }.items():
                command = root / name
                command.write_text('#!/bin/bash\n' + body + '\n')
                command.chmod(0o755)
            return subprocess.run(['bash', str(script)], env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH']}, capture_output=True, text=True)

    def test_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_wrong_architecture(self):
        result = self.run_mock(arch='x86_64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('aarch64', result.stderr)

    def test_requires_root(self):
        result = self.run_mock(uid='1000')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('root', result.stderr)

    def test_checksum_failure(self):
        result = self.run_mock(checksum=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA256', result.stderr)

    def test_guardrails_present(self):
        text = SCRIPT.read_text()
        for guard in ['/var/lib/docker', '/var/lib/containerd', '/etc/docker', 'list-unit-files', 'docker info', '27.3.1', 'sha256sum']:
            self.assertIn(guard, text)
        self.assertNotIn('curl ', text)
        self.assertNotIn('wget ', text)


if __name__ == '__main__':
    unittest.main()
