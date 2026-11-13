"""No Docker or service startup: regressions for unified release orchestration."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PackageTests(unittest.TestCase):
    def test_base_inspection_python_survives_shell_quoting(self):
        import os
        import subprocess
        import tempfile
        script = (ROOT/'build-tools/package.sh').read_text()
        command = script.split('docker image inspect "$ref" | ', 1)[1].split('\n    }', 1)[0]
        for arch in ('amd64', 'arm64'):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(['bash', '-c', 'ref=fixture; '+command],
                    input=json.dumps([{'Os':'linux','Architecture':arch,'Id':'sha256:fixture',
                                       'RepoDigests':['fixture@sha256:abc']}]),
                    env=dict(os.environ, TARGET_ARCH=arch, BASE_RECORDS=directory+'/bases'),
                    text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'fixture@sha256:abc')

    def test_native_architecture_contract(self):
        script = (ROOT/'build-tools/package.sh').read_text()
        self.assertIn('amd64) HOST_ARCH=x86_64; PACKAGE_ARCH=amd64; COMPOSE_ARCH=x86_64', script)
        self.assertNotIn('--platform linux/arm64', script)
        self.assertNotIn('GOARCH=arm64 go build', script)
        for name in ('java-service.Dockerfile', 'prosody-service.Dockerfile'):
            self.assertIn('03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575',
                          (ROOT/'build-tools/docker'/name).read_text())

    def test_render_command_preserves_validated_target_environment(self):
        import os
        import shutil
        import subprocess
        import tempfile
        script = (ROOT/'build-tools/package.sh').read_text(encoding='utf-8')
        render = script.split('# Rendering only: no daemon operation or application startup.\n', 1)[1]
        render = render.split('    python3 -B "$output/install.py"', 1)[0]
        for media in ('', '192.0.2.8'):
            with self.subTest(media=media), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root/'bin').mkdir()
                shutil.copyfile(ROOT/'config/target.py', root/'target.py')
                text = (ROOT/'config/target.env').read_text(encoding='utf-8')
                (root/'target.env').write_text(text.replace('MEDIA_HOST=', 'MEDIA_HOST='+media), encoding='utf-8')
                (root/'server.env.example').write_text('# No instance addresses here.\n')
                fake = root/'bin/docker-compose'
                fake.write_text('''#!/usr/bin/env python3
import os, sys
expected = {'SITE_HOST':'cloudmeet.internal', 'PUBLIC_URL':'https://cloudmeet.internal',
            'HTTPS_PORT':'8443', 'HTTP_PORT':'8080', 'MEDIA_PORT':'10000', 'JVB_PORT':'10000',
            'JVB_ADVERTISE_IPS':os.environ['EXPECTED_MEDIA'],
            'JITSI_ROLE_CHECK_SECRET':'RENDER_ONLY'}
for key, value in expected.items():
    assert os.environ.get(key) == value, (key, os.environ.get(key), value)
assert sys.argv[-2:] == ['config', '--quiet']
''')
                fake.chmod(0o755)
                env = dict(os.environ, EXPECTED_MEDIA=media)
                env.pop('JITSI_ROLE_CHECK_SECRET', None)
                command = '''set -euo pipefail
output=$1
target_exports=$(python3 -B "$output/target.py" "$output/target.env")
eval "$target_exports"
PUBLIC_ORIGIN=$PUBLIC_URL
''' + render
                result = subprocess.run(['bash', '-c', command, 'render-test', str(root)],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_single_manual_workflow_builds_all_seven_services(self):
        workflow = (ROOT / 'build-tools/build-package.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('branches: [ci/arm64-smoke]', workflow)
        self.assertIn('paths: [.github/workflows/build-package.yml]', workflow)
        self.assertIn('service: [gateway, app-web, api, web, prosody, jicofo, jvb]', workflow)
        self.assertIn("inputs.architecture == 'amd64'", workflow)
        self.assertIn('options: [arm64, amd64]', workflow)
        self.assertIn('needs: build', workflow)
        self.assertIn('github.run_attempt', workflow)
        self.assertNotIn('run-id:', workflow)
        self.assertNotIn('packages: write', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('continue-on-error', workflow)

    def test_orchestrator_has_no_legacy_or_cross_run_fallback(self):
        script = (ROOT / 'build-tools/package.sh').read_text(encoding='utf-8')
        for forbidden in ['arm64-stack-lock', 'import_images', 'verify-aarch64-product-runtime',
                          'arm64-integration.py', 'docker push', 'deploy/debug', 'build-tools-old']:
            self.assertNotIn(forbidden, script)
        for required in ['build_service', 'assemble_package', 'org.opencontainers.image.version',
                         'io.cloudmeet.batch', 'SOURCE_COMMIT', 'sha256sum', 'docker save',
                         'docker-compose-linux-$COMPOSE_ARCH', 'PACKAGED', 'Batch identity mismatch',
                         'Source identity mismatch', 'Archive integrity failure']:
            self.assertIn(required, script)

    def test_sources_are_complete_and_immutable(self):
        sources = json.loads((ROOT / 'build-tools/sources.json').read_text(encoding='utf-8'))
        self.assertEqual(set(sources['services']), {'gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb'})
        for source in [*sources['services'].values(), sources['lifecycle']]:
            self.assertTrue(source['repository'].startswith('https://github.com/'))
            self.assertRegex(source['commit'], r'^[0-9a-f]{40}$')

    def test_embedded_python_is_valid_and_checks_actual_image_archive(self):
        script = (ROOT / 'build-tools/package.sh').read_text(encoding='utf-8')
        for index, block in enumerate(re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)):
            compile(block, 'package.sh:python:' + str(index), 'exec')
        verifier = (ROOT / 'build-tools/offline-runtime/install.py').read_text(encoding='utf-8')
        self.assertIn('verifier.verify_image_archive(archive, record)', script)
        for requirement in ['tarfile.open(archive', 'org.opencontainers.image.version',
                            "config['architecture']", "config['os']", 'Image archive config mismatch']:
            self.assertIn(requirement, verifier)

    def test_archive_identity_is_read_from_bytes(self):
        import hashlib
        import importlib.util
        import io
        import tarfile
        import tempfile
        spec = importlib.util.spec_from_file_location('verifier', ROOT / 'build-tools/offline-runtime/install.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        record = {'tag': 'cloudmeet/web:batch', 'batch': 'batch', 'service': 'web',
                  'version': '1.0', 'deployment_commit': 'd' * 40, 'source': {'commit': 'a' * 40}}
        labels = {'io.cloudmeet.batch': 'batch', 'io.cloudmeet.service': 'web',
                  'io.cloudmeet.deployment': 'd' * 40, 'org.opencontainers.image.version': '1.0',
                  'org.opencontainers.image.revision': 'a' * 40}
        raw = json.dumps({'architecture': 'arm64', 'os': 'linux', 'config': {'Labels': labels}}).encode()
        record['image_id'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'image.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                for name, content in {'manifest.json': json.dumps([{'RepoTags': [record['tag']],
                        'Config': 'config.json', 'Layers': ['layer.tar']}]).encode(),
                        'config.json': raw, 'layer.tar': b'layer'}.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    tar.addfile(member, io.BytesIO(content))
            verifier.verify_image_archive(archive, record)
            for key, value in [('image_id', 'sha256:' + '0' * 64), ('batch', 'other'),
                               ('tag', 'cloudmeet/web:other')]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verifier.verify_image_archive(archive, dict(record, **{key: value}))

    def test_runtime_does_not_require_fabricated_installation_evidence(self):
        import importlib.util
        path = ROOT / 'build-tools/offline-runtime/install.py'
        spec = importlib.util.spec_from_file_location('verifier', path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        images = {service: ['cloudmeet/' + service + ':batch', 'sha256:' + str(i) * 64]
                  for i, service in enumerate(sorted(verifier.SERVICES), 1)}
        verifier.require_ready({'status': 'PACKAGED', 'package_contract': 1, 'architecture': 'arm64',
            'images': images, 'image_archives': {s: {} for s in images},
            'requires': ['Existing Docker Engine'],
            'compose': {'file': 'bin/docker-compose', 'sha256': 'a' * 64}})
        with self.assertRaises(ValueError):
            verifier.require_ready({'status': 'INCOMPLETE_NOT_FOR_INSTALL'})

    def test_amd64_assembly_python_contract(self):
        self.test_assembly_python_contract_with_synthetic_materials('amd64')

    def test_assembly_python_contract_with_synthetic_materials(self, architecture='arm64'):
        """Execute embedded generator on tiny fake archives; no Docker/product build."""
        import hashlib
        import io
        import os
        import shutil
        import sys
        import tarfile
        import tempfile
        from unittest.mock import patch
        script = (ROOT / 'build-tools/package.sh').read_text()
        block = re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)[2]
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            tools = repo / 'build-tools'
            tools.mkdir()
            shutil.copyfile(ROOT / 'build-tools/sources.json', tools / 'sources.json')
            sources = json.loads((tools / 'sources.json').read_text())
            (repo / 'config').mkdir()
            shutil.copyfile(ROOT / 'config/Caddyfile', repo / 'config/Caddyfile')
            for name in ('target.env','target.py','jitsi.env'):
                shutil.copyfile(ROOT/'config'/name,repo/'config'/name)
            out = repo / 'fixture'
            out.mkdir()
            (out / 'bin').mkdir()
            (out / 'bin/docker-compose').write_bytes(b'unit-test-fixture-not-executable')
            (out / 'images').mkdir()
            (out / 'provenance').mkdir()
            shutil.copytree(ROOT / 'patches', out / 'patches')
            for source in (ROOT / 'build-tools/offline-runtime').glob('*.py'):
                shutil.copyfile(source, out / source.name)
            for service in sources['services']:
                directory = repo / 'incoming' / service
                directory.mkdir(parents=True)
                labels = {'io.cloudmeet.batch': 'test-123-1', 'io.cloudmeet.service': service,
                          'io.cloudmeet.deployment': 'd' * 40, 'org.opencontainers.image.version': 'test',
                          'org.opencontainers.image.revision': sources['services'][service]['commit']}
                raw = json.dumps({'architecture': architecture, 'os': 'linux',
                                  'config': {'Labels': labels, 'User': '1000:1000'}}).encode()
                record = {'batch': 'test-123-1', 'version': 'test', 'run_id': '123', 'attempt': '1',
                          'deployment_commit': 'd' * 40, 'service': service, 'source': sources['services'][service],
                          'platform': 'linux/'+architecture, 'tag': 'cloudmeet/' + service + ':test-123-1',
                          'archive': service + '.tar.gz', 'image_id': 'sha256:' + hashlib.sha256(raw).hexdigest(),
                          'runtime_user': '1000:1000'}
                archive = directory / record['archive']
                with tarfile.open(archive, 'w:gz') as tar:
                    for name, data in {'manifest.json': json.dumps([{'Config': 'config.json',
                            'RepoTags': [record['tag']], 'Layers': ['layer.tar']}]).encode(),
                            'config.json': raw, 'layer.tar': b'fixture'}.items():
                        member = tarfile.TarInfo(name)
                        member.size = len(data)
                        tar.addfile(member, io.BytesIO(data))
                record.update(bytes=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
                (directory / (service + '.json')).write_text(json.dumps(record))
            env = {'PACKAGE_DIR': str(out), 'PUBLIC_ORIGIN': 'https://47.110.84.166:8443',
                   'HTTP_PORT': '8080', 'MEDIA_PORT': '10000', 'VERSION': 'test', 'BATCH': 'test-123-1',
                   'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'd' * 40,
                   'DEPLOYMENT_COMMIT': 'd' * 40, 'COMPOSE_URL': 'https://example.invalid/fixture',
                    'COMPOSE_VERSION': 'fixture', 'TARGET_ARCH': architecture,
                    'PACKAGE_ARCH': 'amd64' if architecture=='amd64' else 'aarch64',
                    'HOST_ARCH': 'x86_64' if architecture=='amd64' else 'aarch64'}
            with patch.dict(os.environ, env), patch.object(sys, 'argv', ['fixture', str(repo)]):
                exec(compile(block, 'assembly-fixture', 'exec'), {})
            manifest = json.loads((out / 'candidate.json').read_text())
            self.assertEqual(manifest['status'], 'PACKAGED')
            self.assertEqual(manifest['architecture'], architecture)
            self.assertEqual(manifest['target_profile'], 'linux-'+env['PACKAGE_ARCH']+'-existing-engine')
            target_spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location('fixture_target', repo/'config/target.py')
            target_module = __import__('importlib.util', fromlist=['util']).module_from_spec(target_spec)
            target_spec.loader.exec_module(target_module)
            self.assertEqual(manifest['origin'], target_module.load_target(repo/'config/target.env')['PUBLIC_URL'])
            self.assertNotIn('SITE_HOST=', (out/'server.env.example').read_text())
            compose = json.loads((out / 'jitsi-base.yaml').read_text())
            self.assertEqual(compose['services']['gateway']['ports'], ['${HTTPS_PORT:?required}:443', '${HTTP_PORT:?required}:80'])
            self.assertEqual(compose['services']['jvb']['ports'], ['${MEDIA_PORT:?required}:${JVB_PORT:?required}/udp'])
            self.assertIn('https://:443', (out / 'Caddyfile').read_text())
            self.assertNotIn('redir ', (out / 'Caddyfile').read_text())
            self.assertEqual(compose['services']['gateway']['environment']['PUBLIC_URL'], '${PUBLIC_URL:?required}')
            self.assertTrue((out / 'INSTALL.md').is_file())
            archive = repo / 'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(out, arcname='fixture')
            final_block = re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)[3]
            with patch.dict(os.environ, env), patch.object(sys, 'argv', ['fixture', str(archive)]):
                exec(compile(final_block, 'final-archive-fixture', 'exec'), {})
            self.assertEqual(json.loads((repo / 'package-evidence.json').read_text())['status'], 'PASS_MATERIALS_ONLY')

    def test_layout_inventory_matches_current_tools(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('layout', ROOT / 'tools/check-deployment-layout.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(ROOT.parent), [])
        self.assertIn('build-tools/package.sh', module.discover(ROOT))

    def test_instance_web_build_does_not_reuse_default_origin(self):
        script = (ROOT / 'build-tools/package.sh').read_text()
        self.assertIn('-e VITE_JITSI_SERVER=same-origin', script)
        self.assertIn("'build_overrides':{'VITE_JITSI_SERVER':'same-origin'}", script)
        self.assertNotIn('sed -i', script)


if __name__ == '__main__':
    unittest.main()
