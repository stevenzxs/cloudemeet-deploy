import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CandidateEvidenceTests(unittest.TestCase):
    def test_api_isolated_smoke_has_resolvable_hostname_without_network_access(self):
        spec = importlib.util.spec_from_file_location('smoke', ROOT / 'tools/arm64-candidate-smoke.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        commands = []
        def output(*args):
            commands.append(args)
            if args[1] == 'inspect':
                return json.dumps([{'State': {'OOMKilled': False}, 'RestartCount': 0}]).encode()
            return b'container'
        with tempfile.TemporaryDirectory() as directory:
            module.EVIDENCE = Path(directory)
            with patch.object(module, 'run', side_effect=output), \
                    patch.object(module, 'wait_http'), \
                    patch.object(module, 'http', return_value=b'[{"roomName":"987654321"}]'), \
                    patch.object(module.subprocess, 'run'):
                module.smoke('api')
        starts = [args for args in commands if args[:3] == ('docker', 'run', '-d')]
        self.assertEqual(len(starts), 2)
        for args in starts:
            self.assertEqual(args[args.index('--network') + 1], 'none')
            self.assertEqual(args[args.index('--hostname') + 1], 'arm64-api-ci')
            self.assertIn('arm64-api-ci:127.0.0.1', args)
            self.assertNotIn('-p', args)

    def test_failure_diagnostics_redact_credentials_and_exclude_container_env(self):
        spec = importlib.util.spec_from_file_location('smoke', ROOT / 'tools/arm64-candidate-smoke.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'diagnose'), 'Failure diagnostics are missing')
        info = [{'State': {'Running': False, 'ExitCode': 1, 'OOMKilled': False, 'Error': ''},
                 'RestartCount': 0, 'Config': {'Env': ['SECRET=must-not-export']}}]
        def output(*args):
            if args[1] == 'inspect':
                return json.dumps(info).encode()
            return b'Boot failed token=secret-token known-fixture secret-token'
        with patch.object(module, 'run', side_effect=output):
            result = module.diagnose('container', ['known-fixture', 'secret-token'])
        text = json.dumps(result)
        self.assertNotIn('known-fixture', text)
        self.assertNotIn('secret-token', text)
        self.assertNotIn('must-not-export', text)
        self.assertEqual(result['state']['ExitCode'], 1)

    def test_wait_http_reports_last_probe_output(self):
        spec = importlib.util.spec_from_file_location('smoke', ROOT / 'tools/arm64-candidate-smoke.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        failure = subprocess.CalledProcessError(1, ['docker', 'exec'], output=b'container is not running')
        with patch.object(module, 'http', side_effect=failure), patch.object(module.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'container is not running'):
                module.wait_http('container', '/health', 9000)

    def test_source_manifest_covers_seven_pinned_sources(self):
        path = ROOT / 'tools/arm64-candidate-sources.json'
        self.assertTrue(path.exists(), 'Seven-service source manifest is missing')
        data = json.loads(path.read_text())
        self.assertEqual(set(data['services']), {'web', 'app-web', 'api', 'gateway', 'prosody', 'jicofo', 'jvb'})
        for source in data['services'].values():
            self.assertRegex(source['commit'], r'^[0-9a-f]{40}$')
        build = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(build.exists(), 'Native candidate builder is missing')
        text = build.read_text()
        self.assertIn('npm run verify', text)
        self.assertIn('mvn -B -ntp verify', text)
        self.assertIn('go test -race -short', text)
        self.assertNotIn('-DskipTests', text)
        self.assertNotIn("env['VITE_JITSI_SERVER'] =", text)

    def test_candidate_workflow_retains_only_explicit_outputs(self):
        text = (ROOT / '.github/workflows/arm64-smoke.yml').read_text()
        self.assertIn('service: [web, app-web, api, gateway]', text)
        self.assertIn('arm64-candidates/*.tar.gz', text)
        self.assertIn('arm64-candidates/*.json', text)
        self.assertIn('arm64-candidate-evidence.py prosody jicofo jvb', text)
        self.assertNotIn('packages: write', text)
        self.assertNotIn('arm64-evidence/**', text)

    def test_source_checkout_rejects_unexpected_commit(self):
        path = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(path.exists(), 'Native candidate builder is missing')
        spec = importlib.util.spec_from_file_location('candidate_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, 'run'), patch.object(module, 'capture', return_value=b'wrong\n'):
            with self.assertRaisesRegex(RuntimeError, 'Source identity mismatch'):
                module.checkout({'repository': 'https://github.com/example/source.git', 'commit': 'a' * 40}, Path('unused'))

    def test_container_builder_preserves_host_file_ownership_and_has_no_ports(self):
        path = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(path.exists(), 'Native candidate builder is missing')
        spec = importlib.util.spec_from_file_location('candidate_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.EVIDENCE = Path(directory)
            with patch.object(module.os, 'getuid', return_value=1001, create=True), \
                    patch.object(module.os, 'getgid', return_value=1001, create=True), patch.object(module, 'run') as execute:
                module.container_build('base@sha256:abc', Path(directory), 'npm ci', 'web')
            command = execute.call_args.args[0]
            self.assertIn('1001:1001', command)
            self.assertNotIn('-p', command)
            self.assertNotIn('--privileged', command)

    def load_module(self):
        path = ROOT / 'tools/arm64-candidate-evidence.py'
        self.assertTrue(path.exists(), 'Candidate evidence validator is missing')
        spec = importlib.util.spec_from_file_location('candidate_evidence', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_validate_rejects_wrong_platform_and_unpinned_source(self):
        module = self.load_module()
        source = {'commit': 'a' * 40, 'repository': 'https://github.com/example/source.git'}
        image = {'Os': 'linux', 'Architecture': 'arm64', 'Id': 'sha256:' + 'b' * 64}
        module.validate_identity(image, source)
        for field, value in [('Architecture', 'amd64'), ('Os', 'windows')]:
            with self.assertRaises(ValueError):
                module.validate_identity(dict(image, **{field: value}), source)
        with self.assertRaises(ValueError):
            module.validate_identity(image, dict(source, commit='main'))

    def test_archive_validation_rejects_tamper_and_missing_services(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'api.tar.gz'
            archive.write_bytes(b'candidate')
            record = {'service': 'api', 'archive': archive.name, 'size': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
            module.validate_archives([record], root, {'api'})
            with self.assertRaises(ValueError):
                module.validate_archives([record], root, {'api', 'web'})
            with self.assertRaises(ValueError):
                module.validate_archives([record, record], root, {'api'})
            with self.assertRaises(ValueError):
                module.validate_archives([dict(record, archive='../api.tar.gz')], root, {'api'})
            archive.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                module.validate_archives([record], root, {'api'})


if __name__ == '__main__':
    unittest.main()
