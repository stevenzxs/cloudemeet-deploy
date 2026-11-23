"""No Docker/network: approved route and publication gate regressions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class DeliveryContractTests(unittest.TestCase):
    def test_runtime_ca_must_match_built_clients(self):
        m=load('transport',TOOLS/'offline-runtime/image_transport.py')
        with tempfile.TemporaryDirectory() as tmp:
            ca=Path(tmp)/'ca.crt';ca.write_text('invalid fixture')
            with self.assertRaises(ValueError):m.require_ca({'client_ca_sha256':'a'*64},ca)

    def test_new_compose_overlay_change_requires_migration(self):
        m=load('update',TOOLS/'offline-runtime/online_update.py')
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'old';new=Path(tmp)/'new';old.mkdir();new.mkdir()
            for root,value in ((old,'a'),(new,'b')):
                (root/'SHA256SUMS').write_text(value*64+'  docker-compose.yml\n')
                (root/'jitsi-base.yaml').write_text('{"services":{}}')
            with self.assertRaises(ValueError):m.require_configuration_compatible(old,new)
    def test_route_rejects_invalid_port_and_empty_credentials(self):
        m=load('route',TOOLS/'delivery-route.py')
        for origin in ('https://host:99999','https://@host','https://host:0','https://host with spaces'):
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                m.plan({'origin':origin})

    def test_publication_requires_exact_client_assignment(self):
        m=load('release',TOOLS/'joint-release.py')
        assignment={'versions':{'client_version':'1.0.21+r15'}}
        record={'version':'1.0.21+r15','versionAssignment':{'wrong':'other run'}}
        with self.assertRaises(ValueError):m.require_client_assignment(record,assignment)

    def test_offline_upgrade_does_not_rebind_existing_instance_tags(self):
        m=load('importer',TOOLS/'offline-runtime/deploy.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'images/api.tar.gz';archive.parent.mkdir();archive.write_bytes(b'archive')
            identity='sha256:'+'b'*64
            manifest={'architecture':'arm64','images':{'api':['same-tag',identity]},
                      'image_archives':{'api':{'tag':'same-tag','image_id':identity,'file':archive.name,
                                             'bytes':7,'sha256':'hash'}}}
            runner=Mock(return_value=Mock(returncode=1))
            # Upgrade imports must refuse local-tag conflicts before loading.
            runner.return_value=Mock(returncode=0,stdout=json.dumps([{'Id':'sha256:'+'c'*64,'Os':'linux','Architecture':'arm64'}]))
            verifier=Mock();verifier.sha256_file.return_value='hash'
            with self.assertRaises(ValueError):m.acquire_images(root,manifest,verifier,runner)
            self.assertFalse(any('load' in c.args[0] for c in runner.call_args_list))

    def test_offline_import_does_not_treat_inspection_failure_as_absence(self):
        m=load('importer',TOOLS/'offline-runtime/deploy.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'images/api.tar.gz';archive.parent.mkdir();archive.write_bytes(b'archive')
            manifest={'architecture':'amd64','images':{'api':['tag','sha256:'+'a'*64]},
                      'image_archives':{'api':{'tag':'tag','image_id':'sha256:'+'a'*64,
                                             'file':archive.name,'bytes':7,'sha256':'hash'}}}
            runner=Mock(side_effect=[Mock(returncode=1,stderr='Cannot connect to Docker daemon'),Mock(),
                Mock(stdout=json.dumps([{'Id':'sha256:'+'a'*64,'Os':'linux','Architecture':'amd64'}]))])
            verifier=Mock();verifier.sha256_file.return_value='hash'
            with self.assertRaises(ValueError):m.acquire_images(root,manifest,verifier,runner)
            self.assertFalse(any('load' in c.args[0] for c in runner.call_args_list))

    def test_image_transport_refuses_conflicting_package_tag(self):
        m=load('transport',TOOLS/'offline-runtime/image_transport.py')
        record={'status':'PUBLISHED_NOT_DEPLOYED','architecture':'amd64','batch':'batch','configuration_commit':'a'*40,
                'images':{s:{'reference':'ghcr.io/stevenzxs/cloudmeet-'+s+'@sha256:'+'a'*64,
                             'image_id':'sha256:'+str(i)*64,'platform':'linux/amd64'} for i,s in enumerate(m.SERVICES)}}
        manifest={'batch':'batch','deployment_commit':'a'*40,'architecture':'amd64',
                  'images':{s:['cloudmeet/'+s+':batch',v['image_id']] for s,v in record['images'].items()}}
        runner=Mock(return_value=Mock(returncode=0,stdout=json.dumps([{'Id':'sha256:'+'f'*64,'Os':'linux','Architecture':'amd64'}])))
        with self.assertRaises(ValueError):m.bind_local_tags(record,manifest,runner)
        self.assertFalse(any(c.args[0][:2]==['docker','tag'] for c in runner.call_args_list))
    def test_joint_publication_waits_for_both_builds(self):
        text=(TOOLS.parent/'.github/workflows/build-joint.yml').read_text()
        self.assertIn('needs: [version, server, clients]',text)
        self.assertIn('publish_images: false',text)
        self.assertIn('publish-release.yml',text)

    def test_archive_reread_rejects_payload_changed_after_checksumming(self):
        import io
        import tarfile
        m=load('material',TOOLS/'online-material.py')
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'material.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                for name,data in [('material/payload',b'changed'),('material/SHA256SUMS',b'0000  payload\n')]:
                    member=tarfile.TarInfo(name);member.size=len(data);tar.addfile(member,io.BytesIO(data))
            with self.assertRaises(ValueError):m.verify_archive(archive)

    def test_update_compose_uses_shared_sanitized_runtime(self):
        import shutil
        m=load('update',TOOLS/'offline-runtime/online_update.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'instance';root.mkdir()
            for name in ('target.py',):shutil.copyfile(TOOLS.parent/'config'/name,root/name)
            shutil.copyfile(TOOLS/'offline-runtime/start.py',root/'start.py')
            shutil.copyfile(TOOLS.parent/'config/target.env',root/'target.env')
            shutil.copyfile(TOOLS.parent/'config/jitsi.env',root/'jitsi.env')
            (root/'.env').write_text('JWT_APP_SECRET=a\nJICOFO_AUTH_PASSWORD=b\nJVB_AUTH_PASSWORD=c\nJITSI_ROLE_CHECK_SECRET=d\n')
            with patch.dict('os.environ',{'PUBLIC_URL':'https://attacker','COMPOSE_FILE':'evil'}):
                command,env=m.instance_context(root,'selected-project')
            self.assertNotEqual(env.get('PUBLIC_URL'),'https://attacker')
            self.assertNotIn('COMPOSE_FILE',env)
            self.assertIn('selected-project',command)

    def test_publication_refuses_asset_tampering_after_prepare(self):
        m=load('release',TOOLS/'joint-release.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'asset.apk').write_bytes(b'changed')
            (root/'prepared-assets.json').write_text(json.dumps({'asset.apk':'0'*64}))
            with self.assertRaises(ValueError):m.verify_prepared_assets(root)

    def test_online_material_real_archive_without_images_and_identity_preserved(self):
        import shutil
        import hashlib
        m=load('material',TOOLS/'online-material.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            shutil.copyfile(TOOLS/'offline-runtime/install.py',root/'install.py')
            manifest={'status':'PACKAGED','package_contract':1,'architecture':'amd64',
                      'compose':{'file':'bin/docker-compose','sha256':'a'*64},'requires':['engine'],
                      'images':{s:['tag-'+s,'sha256:'+str(i)*64] for i,s in enumerate(('gateway','app-web','api','web','prosody','jicofo','jvb'))},
                      'image_archives':{s:{} for s in ('gateway','app-web','api','web','prosody','jicofo','jvb')},
                      'version_assignment':{'fixture':'preserved'}}
            (root/'candidate.json').write_text(json.dumps(manifest))
            (root/'images').mkdir();(root/'images/large.tar.gz').write_bytes(b'image')
            (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in root.rglob('*') if p.is_file()))
            out=root.parent/'online';archive=m.assemble(root,out)
            self.assertFalse((out/'images').exists())
            self.assertEqual(json.loads((out/'candidate.json').read_text())['version_assignment'],manifest['version_assignment'])
            m.verify_archive(archive)
            with self.assertRaises(FileExistsError):m.assemble(root,out)

    def test_origin_binding_rejects_postbuild_endpoint_change(self):
        m=load('transport',TOOLS/'offline-runtime/image_transport.py')
        with self.assertRaises(ValueError):
            m.require_origin({'client_origin':'https://approved:8443'},'https://other:8443')
        m.require_origin({'client_origin':'https://approved:8443'},'https://approved:8443')

    def test_offline_export_refuses_dirty_configuration_before_docker(self):
        m=load('export',TOOLS/'offline-export.py')
        with patch.object(m.subprocess,'check_output',return_value=' M build-tools/offline-export.py\n'):
            with self.assertRaises(ValueError):m.require_clean_configuration()

    def test_public_material_rejects_target_secrets_and_symlinks(self):
        m=load('material',TOOLS/'online-material.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cert.tar.gz').write_bytes(b'private leaf key')
            with self.assertRaises(ValueError):m.require_public_source(root)

    def test_image_only_upgrade_rejects_new_configuration_even_when_patches_match(self):
        m=load('update',TOOLS/'offline-runtime/online_update.py')
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'old';new=Path(tmp)/'new';old.mkdir();new.mkdir()
            for root in (old,new):
                (root/'SHA256SUMS').write_text('a'*64+'  jitsi.env\n'+'b'*64+'  Caddyfile\n')
                (root/'jitsi-base.yaml').write_text(json.dumps({'name':root.name,'services':{'api':{'image':root.name,'environment':{'AUTH':'on'}}}}))
            m.require_configuration_compatible(old,new)
            (new/'jitsi-base.yaml').write_text(json.dumps({'services':{'api':{'environment':{'AUTH':'off'}}}}))
            with self.assertRaises(ValueError):m.require_configuration_compatible(old,new)

    def test_joint_server_reuse_has_required_publication_permission_ceiling(self):
        import re
        text=(TOOLS.parent/'.github/workflows/build-joint.yml').read_text()
        server=text.split('  server:',1)[1].split('  publish:',1)[0]
        # Called reusable workflow declares a conditional packages:write job;
        # its caller must grant that ceiling even with publish_images:false.
        self.assertIn('packages: write',server)

    def test_missing_parameters_prompt_and_do_not_select_first_install(self):
        m=load('route',TOOLS/'delivery-route.py')
        result=m.plan({})
        self.assertEqual(result['status'],'INPUT_REQUIRED')
        self.assertEqual(set(result['missing']),{'mode','server','origin'})
        with self.assertRaises(ValueError):m.plan({'mode':'reset','server':'host','origin':'https://example.com'})

    def test_upgrade_requires_explicit_instance_and_matching_client_origin(self):
        m=load('route',TOOLS/'delivery-route.py')
        with self.assertRaises(ValueError):
            m.plan({'mode':'upgrade','server':'host','origin':'https://other.example'},'https://example.com')
        result=m.plan({'mode':'upgrade','server':'host','origin':'https://example.com'})
        self.assertEqual(set(result['missing']),{'root','project','target_env'})

    def test_online_acquisition_never_loads_or_builds(self):
        m=load('image_transport',TOOLS/'offline-runtime/image_transport.py')
        images={s:{'reference':'ghcr.io/stevenzxs/cloudmeet-'+s+'@sha256:'+'a'*64,
                   'image_id':'sha256:'+'b'*64,'platform':'linux/amd64'} for s in m.SERVICES}
        record={'status':'PUBLISHED_NOT_DEPLOYED','architecture':'amd64','images':images}
        runner=Mock(return_value=Mock(stdout=json.dumps([{'Id':'sha256:'+'b'*64,'Os':'linux','Architecture':'amd64'}])))
        m.pull_images(record,runner)
        commands=[c.args[0] for c in runner.call_args_list]
        self.assertEqual(sum(c[:2]==['docker','pull'] for c in commands),7)
        self.assertFalse(any('load' in c or 'build' in c for c in commands))
        runner.reset_mock();record['images']['api']['reference']='evil:latest'
        with self.assertRaises(ValueError):m.pull_images(record,runner)
        runner.assert_not_called()


if __name__=='__main__':unittest.main()
