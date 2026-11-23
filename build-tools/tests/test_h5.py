import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('h5', Path(__file__).parents[1]/'offline-runtime/h5.py')
h5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h5)


class H5Contract(unittest.TestCase):
    def test_real_staging_contract_writes_public_material_and_parent_version(self):
        from unittest.mock import patch
        import shutil
        spec=importlib.util.spec_from_file_location('h5_stage_contract',Path(__file__).parents[1]/'stage-h5.py')
        stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)/'repo';source=Path(tmp)/'source';out=Path(tmp)/'output'
            (repo/'config').mkdir(parents=True);(repo/'build-tools/offline-runtime').mkdir(parents=True)
            shutil.copyfile(Path(__file__).parents[1]/'offline-runtime/h5.py',repo/'build-tools/offline-runtime/h5.py')
            (repo/'config/h5-source.json').write_text(json.dumps({'commit':'a'*40,'baseline':'0.1.0'}))
            (repo/'config/client.env').write_text('SITE_SCHEME=https\nSITE_DOMAIN=example.com\nSITE_PORT=8443\n')
            for name in h5.PUBLIC_FILES:
                p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('public')
            (source/'.env').write_text('not for publication')
            out.mkdir()
            assignment={'request':{'sources':{'h5':'a'*40}},'versions':{'revision':15}}
            (out/'candidate.json').write_text(json.dumps({'deployment_commit':'b'*40,'version_assignment':assignment}))
            (out/'Caddyfile').write_text('(meeting_routes) {\n    @business path /cm /cm/*\n}\n')
            (out/'jitsi-base.yaml').write_text(json.dumps({'services':{'gateway':{'volumes':[]}}}))
            with patch.object(stage.subprocess,'check_output',side_effect=['a'*40,'','','b'*40,'']), patch.object(stage.subprocess,'run') as run:
                stage.stage(repo,source,out,assignment)
                self.assertEqual([c.args[0] for c in run.call_args_list],[['npm','ci','--ignore-scripts'],['npm','test']])
            manifest=json.loads((out/'candidate.json').read_text())
            h5.verify_package(out,manifest)
            self.assertEqual(manifest['h5_version'],'0.1.0+r15')
            self.assertEqual(manifest['client_origin'],'https://example.com:8443')
            self.assertFalse((out/'h5/public/.env').exists())
            self.assertIn('handle_path /cm/h5/*',(out/'Caddyfile').read_text())
            self.assertEqual(json.loads((out/'jitsi-base.yaml').read_text())['services']['gateway']['volumes'],['./h5-runtime:/srv/cloudmeet-h5:ro'])

    def test_staging_rejects_source_modified_by_native_tests(self):
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('h5_stage_mutation',Path(__file__).parents[1]/'stage-h5.py')
        stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);(repo/'config').mkdir()
            (repo/'config/h5-source.json').write_text(json.dumps({'commit':'a'*40}))
            assignment={'request':{'sources':{'h5':'a'*40}}}
            with patch.object(stage.subprocess,'check_output',side_effect=['a'*40,'',' M src/app.mjs']), patch.object(stage.subprocess,'run'):
                with self.assertRaisesRegex(ValueError,'changed during native tests'):
                    stage.stage(repo,repo/'source',repo/'output',assignment)

    def test_staging_rejects_parent_source_mismatch_before_npm(self):
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('h5_stage',Path(__file__).parents[1]/'stage-h5.py')
        stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);(repo/'config').mkdir()
            (repo/'config/h5-source.json').write_text(json.dumps({'commit':'a'*40}))
            with patch.object(stage.subprocess,'check_output',side_effect=['a'*40,'']), patch.object(stage.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'parent persistent'):
                    stage.stage(repo,repo/'source',repo/'output',{'request':{'sources':{'h5':'b'*40}}})
                run.assert_not_called()

    def test_h5_health_rejects_spa_fallback(self):
        from unittest.mock import patch
        from email.message import Message
        import io
        spec=importlib.util.spec_from_file_location('h5_health_update',Path(__file__).parents[1]/'offline-runtime/online_update.py')
        update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)
        response=io.BytesIO(b'wrong SPA homepage');response.status=200;response.headers=Message()
        class Opener:
            def open(self,*args,**kwargs):return response
        with patch.object(update.ssl,'create_default_context'), patch.object(update.urllib.request,'build_opener',return_value=Opener()):
            with self.assertRaisesRegex(ValueError,'served bytes'):
                update.h5_health('https://example.com',Path('ca.crt'),{'files':{'index.html':{'sha256':'0'*64}}})

    def test_upgrade_migration_preserves_explicit_target_certificate(self):
        before='(meeting_routes) {\n    @business path /cm /cm/*\n}\nhttps://:443 {\n tls /config/cloudmeet-cert/first-install/server.crt /config/cloudmeet-cert/first-install/server.key\n}\n'
        template=before.replace('tls /config/cloudmeet-cert/first-install/server.crt /config/cloudmeet-cert/first-install/server.key','tls internal')
        h5.require_gateway_delta(before,h5.gateway_caddy(template),first=True)
        with self.assertRaises(ValueError):
            h5.require_gateway_delta(before,h5.gateway_caddy(template).replace('/cm/*','/changed/*'),first=True)

    @unittest.skipIf(os.name=='nt','POSIX runtime link and permission contract')
    def test_atomic_activation_restore_and_gateway_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'public';source.mkdir()
            for name in h5.PUBLIC_FILES:
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('public')
            identity={'source_commit':'a'*40,'configuration_commit':'b'*40,'version_assignment':{'revision':9}}
            record=h5.describe(source,identity)
            runtime=root/'runtime'
            old_umask=os.umask(0o077)
            try:release=h5.prepare_release(runtime,source,record,'https://example.com')
            finally:os.umask(old_umask)
            self.assertEqual(runtime.stat().st_mode & 0o777,0o755)
            self.assertEqual((release/'src').stat().st_mode & 0o777,0o755)
            self.assertIsNone(h5.activate(runtime,release))
            self.assertEqual(os.readlink(runtime/'current'),'releases/'+release.name)
            h5.restore_pointer(runtime,None)
            self.assertFalse((runtime/'current').is_symlink())

    def test_only_exact_h5_gateway_migration_is_allowed(self):
        import copy
        old={'services':{'gateway':{'volumes':['./Caddyfile:/etc/caddy/Caddyfile:ro']},
                         'api':{'image':'old'}}}
        new=copy.deepcopy(old)
        new['services']['gateway']['volumes'].append('./h5-runtime:/srv/cloudmeet-h5:ro')
        h5.require_compose_delta(old,new,first=True)
        new['services']['api']['environment']={'INJECTED':'1'}
        with self.assertRaises(ValueError):h5.require_compose_delta(old,new,first=True)

    def test_prepare_release_is_immutable_and_runtime_config_is_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'material';source.mkdir()
            for name in h5.PUBLIC_FILES:
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('public')
            identity={'source_commit':'a'*40,'configuration_commit':'b'*40,
                      'version_assignment':{'revision':9}}
            record=h5.describe(source,identity)
            runtime=root/'runtime'
            release=h5.prepare_release(runtime,source,record,'https://118.193.36.35:8443')
            self.assertFalse((runtime/'current').exists())
            self.assertEqual(json.loads((release/'runtime-config.json').read_text()),
                             {'jitsiOrigin':'https://118.193.36.35:8443'})
            with self.assertRaises(ValueError):
                h5.prepare_release(runtime,source,record,'https://118.193.36.35:8443')
            with self.assertRaises(ValueError):
                h5.prepare_release(root/'bad',source,record,'http://example.com')

    def test_gateway_routing_preserves_existing_and_rejects_double_install(self):
        original='(meeting_routes) {\n    @business path /cm /cm/*\n}\n'
        updated=h5.gateway_caddy(original)
        self.assertLess(updated.index('handle_path /cm/h5/*'),updated.index('@business'))
        self.assertIn('Content-Type application/javascript',updated)
        self.assertIn('@business path /cm /cm/*',updated)
        with self.assertRaises(ValueError):h5.gateway_caddy(updated)
        with self.assertRaises(ValueError):h5.gateway_caddy('unrecognized')

    def test_public_inventory_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in h5.PUBLIC_FILES:
                file = root/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('public')
            identity = {'source_commit': 'a'*40, 'configuration_commit': 'b'*40,
                        'version_assignment': {'revision': 9}}
            record = h5.describe(root, identity)
            self.assertEqual(len(record['files']), 5)
            h5.verify(root, record, identity)
            (root/'src/core.mjs').write_text('changed')
            with self.assertRaises(ValueError):
                h5.verify(root, record, identity)

    def test_reject_extra_and_assignment_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in h5.PUBLIC_FILES:
                file = root/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('public')
            identity = {'source_commit': 'a'*40, 'configuration_commit': 'b'*40,
                        'version_assignment': {'revision': 9}}
            record = h5.describe(root, identity)
            with self.assertRaises(ValueError):
                h5.verify(root, record, dict(identity, version_assignment={}))
            (root/'.env').write_text('must not publish')
            with self.assertRaises(ValueError):
                h5.describe(root, identity)


if __name__ == '__main__':
    unittest.main()
