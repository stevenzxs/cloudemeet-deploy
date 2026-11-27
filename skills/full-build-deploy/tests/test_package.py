"""No Docker or service startup: regressions for unified release orchestration."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]


class PackageTests(unittest.TestCase):
    def test_assemble_config_references_resolve(self):
        # Regression guard: r46-r51 assemble runs failed because config files were
        # referenced from the skill but never copied into it.
        script = (ROOT / 'scripts/package.sh').read_text(encoding='utf-8')
        refs = set(re.findall(r"skill_root/'config/([A-Za-z0-9_.-]+)'", script))
        refs |= set(re.findall(r"skill_root/'config'/([A-Za-z0-9_-]+\.[A-Za-z0-9]+)(?![\w\[])", script))
        missing = sorted(name for name in refs if not (ROOT / 'config' / name).is_file())
        self.assertEqual(missing, [])

    def test_mgr_delivery_is_not_discarded(self):
        script = (ROOT/'scripts/package.sh').read_text(encoding='utf-8')
        self.assertIn("repo/'incoming/jitsi-mgr/build-evidence.json'", script)
        self.assertIn("manifest['jitsi_mgr']", script)
        self.assertIn("configs['jitsi-mgr']", script)
        self.assertIn('initialize_jitsi_mgr(root)',
                      (ROOT/'runtime/initialize.py').read_text())

    def test_mgr_material_gate_rejects_missing_payload(self):
        import importlib.util
        import tempfile
        import sys
        spec = importlib.util.spec_from_file_location('mgr_verifier', ROOT/'runtime/install.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'jitsi-mgr'):
                module.verify_jitsi_mgr(Path(directory), {}, {})

    def test_mgr_payload_tamper_and_runtime_rejected(self):
        import tempfile
        from test_delivery_assets import add_mgr_fixture, load
        module=load('mgr_verify',ROOT/'runtime/install.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest={'images':{s:['tag-'+s,'id'] for s in module.SERVICES}}
            add_mgr_fixture(root,manifest)
            compose=json.loads((root/'jitsi-base.yaml').read_text())
            module.verify_jitsi_mgr(root,manifest,compose)
            compose['services']['jitsi-mgr']['ports']=['8080:8080']
            with self.assertRaisesRegex(ValueError,'jitsi-mgr'):
                module.verify_jitsi_mgr(root,manifest,compose)
            compose['services']['jitsi-mgr'].pop('ports')
            (root/'artifacts/jitsi-mgr.jar').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'jitsi-mgr'):
                module.verify_jitsi_mgr(root,manifest,compose)

    def test_mgr_target_initialization_without_network_or_secret_output(self):
        import tempfile, subprocess, contextlib, io
        from unittest.mock import patch
        from test_delivery_assets import load
        module=load('mgr_initialize',ROOT/'tools/init-jitsi-mgr.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);module.DEPLOY_ROOT=root
            module.JITSI_MGR_DATA=root/'data/jitsi-mgr';module.KEYS_DIR=module.JITSI_MGR_DATA/'keys'
            output=io.StringIO()
            def fake_openssl(command, **kwargs):
                Path(command[-1]).write_text('-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----\n')
                return subprocess.CompletedProcess(command,0)
            with contextlib.redirect_stdout(output), patch.object(module.subprocess,'run',side_effect=fake_openssl) as openssl:
                module.main()
            private=module.KEYS_DIR/'jwt-private.pem'
            self.assertIn('BEGIN PRIVATE KEY',private.read_text())
            self.assertEqual(openssl.call_args_list[0].args[0][:3],['openssl','genpkey','-algorithm'])
            self.assertIn('0o600', (ROOT/'tools/init-jitsi-mgr.py').read_text())
            secret=(root/'.env').read_text().split('=',1)[1].strip()
            self.assertNotIn(secret,output.getvalue())
            before=private.read_bytes()
            with self.assertRaises((ValueError,FileExistsError)):module.main()
            self.assertEqual(private.read_bytes(),before)

    def test_base_inspection_python_survives_shell_quoting(self):
        import os
        import subprocess
        import tempfile
        import sys
        script = (ROOT/'scripts/package.sh').read_text()
        command = script.split('docker image inspect "$ref" | python3 -c \'', 1)[1].split("' \"$ref\"", 1)[0]
        for arch in ('amd64', 'arm64'):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable,'-c',command,'fixture'],
                    input=json.dumps([{'Os':'linux','Architecture':arch,'Id':'sha256:fixture',
                                       'RepoDigests':['fixture@sha256:abc']}]),
                    env=dict(os.environ, TARGET_ARCH=arch, BASE_RECORDS=directory+'/bases',
                             HOST_ARCH='x86_64' if arch=='amd64' else 'aarch64'),
                    text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'fixture@sha256:abc')

    def test_native_architecture_contract(self):
        script = (ROOT/'scripts/package.sh').read_text()
        self.assertIn('amd64) HOST_ARCH=x86_64; PACKAGE_ARCH=amd64; COMPOSE_ARCH=x86_64', script)
        self.assertNotIn('--platform linux/arm64', script)
        self.assertNotIn('GOARCH=arm64 go build', script)
        for name in ('java-service.Dockerfile', 'prosody-service.Dockerfile'):
            self.assertIn('03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575',
                          (ROOT/'docker'/name).read_text())

    def test_render_command_preserves_validated_target_environment(self):
        import importlib.util
        import tempfile
        spec=importlib.util.spec_from_file_location('target_config',ROOT/'config/target.py')
        target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
        contract={'origin':'https://meet.example:8443','scheme':'https','host':'meet.example','port':8443,'addresses':['203.0.113.8']}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'provenance').mkdir()
            (root/'provenance/origin-contract.json').write_text(json.dumps(contract))
            (root/'target.env').write_text('SITE_SCHEME=https\nHTTPS_PORT=8443\nHTTP_PORT=8080\nMEDIA_PORT=10000\nMEDIA_HOST=\n')
            values=target.resolve_target(root)
        self.assertEqual(values['PUBLIC_URL'],contract['origin'])
        self.assertEqual(values['SITE_HOST'],contract['host'])

    def test_single_manual_workflow_builds_all_seven_services(self):
        workflow = (REPO / '.github/workflows/build-package.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow)
        self.assertIn('revision-allocation.yml', workflow)
        self.assertIn('service: [gateway, app-web, api, jitsi-mgr, web, prosody, jicofo, jvb]', workflow)
        self.assertIn("inputs.architecture == 'amd64'", workflow)
        self.assertIn('options: [arm64, amd64]', workflow)
        self.assertIn('needs: [version, build]', workflow)
        self.assertIn('github.run_attempt', workflow)
        self.assertNotIn('run-id:', workflow)
        self.assertNotIn('packages: write', workflow.split('jobs:',1)[0])
        self.assertEqual(workflow.count('packages: write'),1)
        self.assertIn('needs: [version, build, package]',workflow)
        self.assertEqual(re.findall(r'secrets\.([A-Z0-9_]+)',workflow),[])
        h5=workflow.split('repository: stevenzxs/jitsi-weixin',1)[1].split('- name:',1)[0]
        self.assertIn('ref: ${{ steps.h5.outputs.commit }}',h5)
        self.assertIn('persist-credentials: false',h5)
        self.assertNotIn('continue-on-error', workflow)

    def test_orchestrator_has_no_legacy_or_cross_run_fallback(self):
        script = (ROOT / 'scripts/package.sh').read_text(encoding='utf-8')
        for forbidden in ['arm64-stack-lock', 'import_images', 'verify-aarch64-product-runtime',
                          'arm64-integration.py', 'docker push', 'deploy/debug', 'build-tools-old',
                          "repo/'build-tools/", "repo/'config/"]:
            self.assertNotIn(forbidden, script)
        for required in ['build_service', 'assemble_package', 'org.opencontainers.image.version',
                         'io.cloudmeet.batch', 'SOURCE_COMMIT', 'sha256sum', 'docker save',
            'docker-compose-linux-$COMPOSE_ARCH', 'PACKAGED', 'Batch identity mismatch',
                         'Source identity mismatch', 'Archive integrity failure']:
            self.assertIn(required, script)

    def test_sources_are_complete_and_immutable(self):
        sources = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(set(sources['services']), {'gateway', 'app-web', 'api', 'jitsi-mgr', 'web', 'prosody', 'jicofo', 'jvb'})
        for source in [*sources['services'].values(), sources['lifecycle']]:
            self.assertTrue(source['repository'].startswith('https://github.com/'))
            self.assertRegex(source['commit'], r'^[0-9a-f]{40}$')

    def test_jitsi_mgr_source_pin_matches_reviewed_java_and_react_tree(self):
        sources = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(sources['services']['jitsi-mgr']['repository'],
                         'https://github.com/stevenzxs/jitsi-mgr.git')
        # This reviewed tree contains jitsi-mgr-app/pom.xml and
        # jitsi-mgr-frontend/package-lock.json and the JJWT 0.12 parser repair.
        self.assertEqual(sources['services']['jitsi-mgr']['commit'],
                         '174c03cad23ab87c7ca2c1b999edc799dfd2c50a')

    def test_embedded_python_is_valid_and_checks_actual_image_archive(self):
        script = (ROOT / 'scripts/package.sh').read_text(encoding='utf-8')
        for index, block in enumerate(re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)):
            compile(block, 'package.sh:python:' + str(index), 'exec')
        verifier = (ROOT / 'runtime/install.py').read_text(encoding='utf-8')
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
        spec = importlib.util.spec_from_file_location('verifier', ROOT / 'runtime/install.py')
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
        path = ROOT / 'runtime/install.py'
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
        script = (ROOT / 'scripts/package.sh').read_text()
        block = next(b for b in re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)
                     if 'records={}' in b and "manifest={'status':'PACKAGED'" in b)
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            tools = repo / 'skill' / 'tools'
            tools.mkdir(parents=True)
            # Synthetic staging entry only: generator fixture has no Git/npm source checkout.
            # Real staging identity and rejection cases are tested separately.
            (tools/'stage-h5.py').write_text('''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[3])))
import h5
out=Path(sys.argv[3])
public=out/'h5/public'
for name in h5.PUBLIC_FILES:
    path=public/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
manifest=json.loads((out/'candidate.json').read_text())
manifest['h5']=h5.describe(public,{'source_commit':'f'*40,'configuration_commit':manifest['deployment_commit'],'version_assignment':manifest['version_assignment']})
(out/'candidate.json').write_text(json.dumps(manifest))
caddy=out/'Caddyfile';caddy.write_text(h5.gateway_caddy(caddy.read_text()))
base=out/'jitsi-base.yaml';data=json.loads(base.read_text());data['services']['gateway']['volumes'].append('./h5-runtime:/srv/cloudmeet-h5:ro');base.write_text(json.dumps(data))
''')
            shutil.copyfile(ROOT / 'sources.json', tools / 'sources.json')
            shutil.copyfile(ROOT / 'tools/network-audit.py', tools / 'network-audit.py')
            (tools/'network-audit.py').write_text('''from pathlib import Path
def audit(root, rendered=None): return {'errors': []}
def write_report(report, output):
    path=Path(output);path.mkdir(parents=True,exist_ok=True);(path/'network-audit.json').write_text('{}')
''',encoding='utf-8')
            sources = json.loads((tools / 'sources.json').read_text())
            (repo / 'config').mkdir()
            (repo/'config/jitsi.env').write_text('CONFIG=./data/jitsi\nJVB_AUTH_USER=jvb\nJICOFO_AUTH_USER=focus\nENABLE_AUTH=1\nAUTH_TYPE=jwt\nJWT_APP_ID=zhsz\nJWT_ALLOW_EMPTY=1\nENABLE_AUTO_OWNER=0\nXMPP_MUC_MODULES=muc_jwt_owner\nENABLE_XMPP_WEBSOCKET=1\nBOSH_RELATIVE=1\nENABLE_P2P=0\nTZ=Asia/Shanghai\n',encoding='utf-8')
            (repo/'config/jitsi-mgr.env').write_text('JITSI_MGR_PROFILE=prod\nJITSI_MGR_DB_URL=jdbc:h2:file:/app/data/test\nJITSI_MGR_DB_USER=sa\n',encoding='utf-8')
            (repo/'skill').mkdir(exist_ok=True)
            shutil.copyfile(ROOT/'sources.json',repo/'skill/sources.json')
            shutil.copytree(ROOT/'config',repo/'skill/config',ignore=shutil.ignore_patterns('jitsi-mgr.env'))
            shutil.copytree(ROOT/'patches',repo/'skill/patches')
            shutil.copytree(ROOT/'runtime',repo/'skill/runtime')
            (repo/'skill/config/jitsi.env').write_text('CONFIG=./data/jitsi\nJVB_AUTH_USER=jvb\nJICOFO_AUTH_USER=focus\nENABLE_AUTH=1\nAUTH_TYPE=jwt\nJWT_APP_ID=zhsz\nJWT_ALLOW_EMPTY=1\nENABLE_AUTO_OWNER=0\nXMPP_MUC_MODULES=muc_jwt_owner\nENABLE_XMPP_WEBSOCKET=1\nBOSH_RELATIVE=1\nENABLE_P2P=0\nTZ=Asia/Shanghai\n',encoding='utf-8')
            # Public runtime configuration is owned by the repository, not bundled
            # under skills/full-build-deploy/config. Do not let a duplicate mask path bugs.
            (repo/'skill/config/jitsi.env').unlink()
            shutil.copyfile(ROOT/'config/target.py',repo/'skill/config/target.py')
            (repo/'skill/config/Caddyfile').write_text('https://:443 {\n tls internal\n}\n',encoding='utf-8')
            shutil.copyfile(ROOT/'tools/init-jitsi-mgr.py',tools/'init-jitsi-mgr.py')
            out = repo / 'fixture'
            out.mkdir()
            (out / 'bin').mkdir()
            # Test-only normalized renderer, no daemon or product build.
            (out / 'bin/docker-compose').write_text(r'''#!/usr/bin/env python3
import json, os, re, sys
data=json.load(open(sys.argv[2]))
def expand(value):
    return re.sub(r'\$\{([A-Z_]+)(?::[^}]*)?\}',lambda m: os.environ.get(m[1],''),value)
for name,cfg in data['services'].items():
    cfg['environment']={k:expand(v) for k,v in cfg.get('environment',{}).items()}
    cfg['ports']=[dict(zip(('published','target'),expand(p).split('/')[0].split(':')),protocol='udp' if p.endswith('/udp') else 'tcp') for p in cfg.get('ports',[])]
print(json.dumps(data))
''')
            (out / 'bin/docker-compose').chmod(0o755)
            (out / 'images').mkdir()
            (out / 'provenance').mkdir()
            shutil.copyfile(tools/'sources.json',out/'provenance/sources.json')
            assignment = {'fixture': 'test-only allocation'}
            version_record = repo / 'version-assignment.json'
            version_record.write_text(json.dumps(assignment))
            shutil.copytree(ROOT / 'patches', out / 'patches')
            for source in (ROOT / 'runtime').glob('*.py'):
                shutil.copyfile(source, out / source.name)
            shutil.copyfile(ROOT/'config/target.py',out/'target.py')
            for service in sources['services']:
                directory = repo / 'incoming' / service
                directory.mkdir(parents=True)
                if service == 'jitsi-mgr':
                    payload=directory/'artifacts'
                    (payload/'jitsi-mgr-ui').mkdir(parents=True)
                    (payload/'jitsi-mgr.jar').write_bytes(b'jar fixture')
                    (payload/'jitsi-mgr-ui/index.html').write_text('fixture')
                    mgr={'service':service,'batch':'test-123-1','version':'test',
                         'run_id':'123','attempt':'1','deployment_commit':'d'*40,
                         'architecture':architecture,'source_commit':sources['services'][service]['commit'],
                         'version_assignment':assignment,
                         'files':{p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in payload.rglob('*') if p.is_file()}}
                    (directory/'build-evidence.json').write_text(json.dumps(mgr))
                    continue
                labels = {'io.cloudmeet.batch': 'test-123-1', 'io.cloudmeet.service': service,
                          'io.cloudmeet.deployment': 'd' * 40, 'org.opencontainers.image.version': 'test',
                          'org.opencontainers.image.revision': sources['services'][service]['commit']}
                raw = json.dumps({'architecture': architecture, 'os': 'linux',
                                  'config': {'Labels': labels, 'User': '1000:1000'}}).encode()
                record = {'batch': 'test-123-1', 'version': 'test', 'run_id': '123', 'attempt': '1',
                          'deployment_commit': 'd' * 40, 'service': service, 'source': sources['services'][service],
                          'platform': 'linux/'+architecture, 'tag': 'cloudmeet/' + service + ':test-123-1',
                          'archive': service + '.tar.gz', 'image_id': 'sha256:' + hashlib.sha256(raw).hexdigest(),
                          'runtime_user': '1000:1000', 'version_assignment': assignment}
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
            origin_contract={'origin':'https://meet.example:8443','scheme':'https','host':'meet.example',
                             'port':8443,'addresses':['203.0.113.8'],'tls_mode':'private-ca','client_ca_file':'client-ca.crt'}
            (repo/'origin-contract.json').write_text(json.dumps(origin_contract))
            (repo/'skill').mkdir(exist_ok=True)
            env = {'PACKAGE_DIR': str(out), 'PUBLIC_ORIGIN': origin_contract['origin'],
                   'MEDIA_HOST':'', 'HTTPS_PORT':'8443',
                    'ORIGIN_CONTRACT':str(repo/'origin-contract.json'), 'SKILL_ROOT':str(repo/'skill'),
                    'ORIGIN_CONTRACT_JSON':json.dumps(origin_contract),
                   'HTTP_PORT': '8080', 'MEDIA_PORT': '10000', 'VERSION': 'test', 'BATCH': 'test-123-1',
                   'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'd' * 40,
                   'DEPLOYMENT_COMMIT': 'd' * 40, 'COMPOSE_URL': 'https://example.invalid/fixture',
                    'COMPOSE_VERSION': 'fixture', 'TARGET_ARCH': architecture,
                    'PACKAGE_ARCH': 'amd64' if architecture=='amd64' else 'aarch64',
                     'HOST_ARCH': 'x86_64' if architecture=='amd64' else 'aarch64',
                     'VERSION_RECORD': str(version_record)}
            with patch.dict(os.environ, env), patch.object(sys, 'argv', ['fixture', str(repo)]), \
                    patch('subprocess.run', side_effect=lambda command, **kwargs: __import__('subprocess').CompletedProcess(command,0,stdout='',stderr='')):
                with patch('subprocess.check_output', return_value=b'{"services":{}}'):
                    exec(compile(block, 'assembly-fixture', 'exec'), {})
            manifest = json.loads((out / 'candidate.json').read_text())
            self.assertEqual(manifest['status'], 'PACKAGED')
            self.assertEqual(manifest['version_assignment'], assignment)
            self.assertEqual(manifest['architecture'], architecture)
            self.assertEqual((out/'jitsi.env').read_text(encoding='utf-8'),
                             (repo/'config/jitsi.env').read_text(encoding='utf-8'))
            self.assertEqual(manifest['target_profile'], 'linux-'+env['PACKAGE_ARCH']+'-existing-engine')
            target_spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location('fixture_target', repo/'skill/config/target.py')
            target_module = __import__('importlib.util', fromlist=['util']).module_from_spec(target_spec)
            target_spec.loader.exec_module(target_module)
            self.assertEqual(manifest['origin'], origin_contract['origin'])
            self.assertEqual(manifest['origin_contract'], origin_contract)
            self.assertEqual(json.loads((out/'provenance/origin-contract.json').read_text()), origin_contract)
            self.assertEqual(target_module.resolve_target(out)['PUBLIC_URL'], origin_contract['origin'])
            external=repo/'external-target.env'
            external.write_text('SITE_SCHEME=https\nHTTPS_PORT=8443\nHTTP_PORT=8080\nMEDIA_PORT=10000\nMEDIA_HOST=\n')
            self.assertEqual(target_module.resolve_target(out,external)['PUBLIC_URL'],origin_contract['origin'])
            self.assertNotIn('SITE_HOST=', (out/'server.env.example').read_text())
            compose = json.loads((out / 'jitsi-base.yaml').read_text())
            self.assertEqual(compose['services']['gateway']['ports'], ['${HTTPS_PORT:?required}:443', '${HTTP_PORT:?required}:80'])
            self.assertEqual(compose['services']['jvb']['ports'], ['${MEDIA_PORT:?required}:${JVB_PORT:?required}/udp'])
            self.assertIn('https://:443', (out / 'Caddyfile').read_text())
            self.assertEqual(compose['services']['gateway']['environment']['PUBLIC_URL'], '${PUBLIC_URL:?required}')
            self.assertTrue((out / 'INSTALL.md').is_file())
            archive = repo / 'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(out, arcname='fixture')
            final_block = next(b for b in re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S)
                               if 'tarfile.open' in b and 'PASS_MATERIALS_ONLY' in b)
            with patch.dict(os.environ, env), patch.object(sys, 'argv', ['fixture', str(archive)]):
                exec(compile(final_block, 'final-archive-fixture', 'exec'), {})
            self.assertEqual(json.loads((repo / 'package-evidence.json').read_text())['status'], 'PASS_MATERIALS_ONLY')

    def test_layout_inventory_matches_current_tools(self):
        self.assertTrue((ROOT/'scripts/package.sh').is_file())
        self.assertTrue((ROOT/'tools/network-audit.py').is_file())

    def test_instance_web_build_does_not_reuse_default_origin(self):
        script = (ROOT / 'scripts/package.sh').read_text()
        self.assertIn('-e VITE_JITSI_SERVER=same-origin', script)
        self.assertIn("'build_overrides':{'VITE_JITSI_SERVER':'same-origin'}", script)
        self.assertNotIn('sed -i', script)


if __name__ == '__main__':
    unittest.main()
