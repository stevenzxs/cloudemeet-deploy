"""Exercise real archive/asset transformations; Docker and GitHub calls are mocked."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def hashfile(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def add_h5_fixture(root, manifest):
    shutil.copyfile(TOOLS/'offline-runtime/h5.py',root/'h5.py')
    h5=load('h5_fixture',root/'h5.py')
    public=root/'h5/public'
    for name in h5.PUBLIC_FILES:
        path=public/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('public fixture')
    manifest.setdefault('deployment_commit','a'*40)
    manifest.setdefault('version_assignment',{'fixture':'h5'})
    manifest['h5']=h5.describe(public,{'source_commit':'f'*40,
        'configuration_commit':manifest['deployment_commit'],'version_assignment':manifest['version_assignment']})


class DeliveryAssetTests(unittest.TestCase):
    def source(self,root):
        root.mkdir();(root/'provenance').mkdir()
        shutil.copyfile(TOOLS/'offline-runtime/install.py',root/'install.py')
        record={'status':'PUBLISHED_NOT_DEPLOYED','architecture':'amd64','batch':'batch',
                'configuration_commit':'a'*40,'images':{}}
        images={};self.configs={}
        for service in ('gateway','app-web','api','web','prosody','jicofo','jvb'):
            config=json.dumps({'os':'linux','architecture':'amd64','config':{'Labels':{
                'io.cloudmeet.batch':'batch','io.cloudmeet.service':service,'io.cloudmeet.deployment':'a'*40,
                'org.opencontainers.image.version':'version','org.opencontainers.image.revision':'b'*40}}}).encode()
            identity='sha256:'+hashlib.sha256(config).hexdigest();tag='cloudmeet/'+service+':batch'
            self.configs[tag]=config;images[service]=[tag,identity]
            record['images'][service]={'reference':'ghcr.io/stevenzxs/cloudmeet-'+service+'@sha256:'+'c'*64,
                                       'image_id':identity,'platform':'linux/amd64'}
            provenance={'service':service,'batch':'batch','deployment_commit':'a'*40,'version':'version',
                        'source':{'commit':'b'*40},'image_id':identity,'platform':'linux/amd64','tag':tag}
            (root/'provenance'/(service+'.json')).write_text(json.dumps(provenance))
        manifest={'status':'PACKAGED','package_contract':1,'architecture':'amd64','batch':'batch',
                  'deployment_commit':'a'*40,'compose':{'file':'bin/docker-compose','sha256':'a'*64},
                  'requires':['engine'],'image_transport':'registry','images':images}
        add_h5_fixture(root,manifest)
        (root/'candidate.json').write_text(json.dumps(manifest))
        (root/'SHA256SUMS').write_text(''.join(hashfile(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in root.rglob('*') if p.is_file()))
        return record

    def test_offline_export_preserves_registry_and_proves_archive_identity_without_build(self):
        m=load('export',TOOLS/'offline-export.py');commands=[]
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';record=self.source(source);out=Path(tmp)/'offline'
            def run(command,**kwargs):
                commands.append(command)
                if command[:2]!=['docker','save']:raise AssertionError(command)
                config=self.configs[command[-1]];name=hashlib.sha256(config).hexdigest()+'.json'
                with tarfile.open(command[3],'w') as tar:
                    for member,data in [(name,config),('layer.tar',b'layer'),('manifest.json',json.dumps([
                            {'Config':name,'RepoTags':[command[-1]],'Layers':['layer.tar']}]).encode())]:
                        info=tarfile.TarInfo(member);info.size=len(data);tar.addfile(info,io.BytesIO(data))
            transport=load('transport',TOOLS/'offline-runtime/image_transport.py')
            original=m.load
            with patch.object(m,'require_clean_configuration',return_value='d'*40),patch.object(m,'load',wraps=m.load) as loader,patch.object(m.subprocess,'run',side_effect=run):
                def modules(name,path):
                    if name=='export_transport':return transport
                    return original(name,path)
                loader.side_effect=modules
                with patch.object(transport,'pull_images') as pull,patch.object(transport,'bind_local_tags'):
                    archive=m.export(source,record,out)
                    pull.assert_called_once_with(record)
            manifest=json.loads((out/'candidate.json').read_text())
            self.assertEqual(manifest['offline_export_configuration_commit'],'d'*40)
            self.assertEqual(len(manifest['image_archives']),7)
            self.assertEqual(json.loads((out/'registry.json').read_text()),record)
            self.assertEqual(len(commands),7)
            load('material',TOOLS/'online-material.py').verify_archive(archive)
            self.assertEqual(hashfile(Path(tmp)/'setup.py'),hashfile(TOOLS/'setup.py'))
            self.assertEqual((Path(tmp)/'setup.py.sha256').read_text().split()[0],hashfile(TOOLS/'setup.py'))

    def test_joint_prepare_and_publish_do_not_accept_modified_client_asset(self):
        m=load('release',TOOLS/'joint-release.py')
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                assignment={'versions':{'client_version':'1.0.21+r15'}}
                Path('assignment.json').write_text(json.dumps(assignment));Path('config').mkdir()
                Path('config/version-policy.json').write_text('{}')
                Path('config/h5-source.json').write_text(json.dumps({'commit':'f'*40}))
                for target,platform,extension in [('electron','windows','.msi'),('android','android','.apk')]:
                    root=Path('client-downloads')/('client-'+target+'-100-1');root.mkdir(parents=True)
                    file=root/('client'+extension);file.write_bytes(target.encode())
                    checks={key:{'passed':True} for key in ('version','architecture','origin','ca','signature')}
                    if platform=='windows':checks.pop('signature');checks['signing']={'status':'unsigned','required':False}
                    evidence={'status':'packaged-delivered','version':'1.0.21+r15','versionAssignment':assignment,
                              'ca':{'sha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert((TOOLS.parent/'config/client-ca.crt').read_text())).hexdigest()},
                              'origin':'https://118.193.36.35:8443','artifacts':[{'file':file.name,'platform':platform,
                              'sha256':hashfile(file),'checks':checks}]}
                    (root/'build-evidence.json').write_text(json.dumps(evidence))
                source=Path('source');self.source(source)
                candidate=json.loads((source/'candidate.json').read_text())
                candidate.update(version_assignment=assignment,run_id='100',attempt='1')
                add_h5_fixture(source,candidate)
                (source/'candidate.json').write_text(json.dumps(candidate))
                (source/'SHA256SUMS').write_text(''.join(hashfile(p)+'  '+p.relative_to(source).as_posix()+'\n' for p in source.rglob('*') if p.is_file() and p.name!='SHA256SUMS'))
                Path('server-downloads').mkdir()
                load('material',TOOLS/'online-material.py').assemble(source,Path('server-downloads/batch-online'))
                Path('server-downloads/setup.py').write_text('fixture')
                Path('server-downloads/setup.py.sha256').write_text(hashfile(Path('server-downloads/setup.py'))+'  setup.py\n')
                environment={'VERSION_RECORD':'assignment.json','GITHUB_RUN_ID':'100','GITHUB_RUN_ATTEMPT':'1',
                             'GITHUB_SHA':'a'*40,'BATCH':'batch','TARGET_ARCH':'amd64'}
                with patch.dict(os.environ,environment),patch('revision_versions.validate_record'):
                    m.prepare()
                m.verify_prepared_assets(Path('release-assets'))
                Path('release-assets/client.apk').write_bytes(b'tampered')
                with patch.object(m.subprocess,'run') as run,self.assertRaises(ValueError):m.publish()
                run.assert_not_called()
            finally:os.chdir(previous)

    def test_failed_release_upload_keeps_draft_unpublished(self):
        import subprocess
        m=load('release',TOOLS/'joint-release.py')
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                root=Path('release-assets');root.mkdir();Path('publication').mkdir()
                record={'status':'PREPARED_NOT_PUBLISHED','configuration_commit':'a'*40,'version_assignment':{}}
                registry=self.source(Path('source'))
                record['server_material']=json.loads(Path('source/candidate.json').read_text())
                (root/'joint-evidence.json').write_text(json.dumps(record))
                (root/'prepared-assets.json').write_text(json.dumps({'joint-evidence.json':hashfile(root/'joint-evidence.json')}))
                registry.update(version_assignment={})
                Path('publication/registry.json').write_text(json.dumps(registry))
                Path('publication/registry.json.sha256').write_text(hashfile(Path('publication/registry.json'))+'  registry.json\n')
                with patch.dict(os.environ,{'BATCH':'batch','GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'owner/repo'}),patch.object(m.subprocess,'run',side_effect=[None,subprocess.CalledProcessError(1,'upload')]) as run:
                    with self.assertRaises(subprocess.CalledProcessError):m.publish()
                    self.assertEqual(run.call_count,2)
                    self.assertIn('--draft',run.call_args_list[0].args[0])
                    self.assertFalse(any('edit' in c.args[0] for c in run.call_args_list))
            finally:os.chdir(previous)

    def test_successful_release_retains_valid_final_asset_inventory(self):
        m=load('release',TOOLS/'joint-release.py')
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                root=Path('release-assets');root.mkdir();Path('publication').mkdir()
                record={'status':'PREPARED_NOT_PUBLISHED','configuration_commit':'a'*40,
                        'version_assignment':{},'origin':'https://example.com'}
                registry=self.source(Path('source'))
                record['server_material']=json.loads(Path('source/candidate.json').read_text())
                registry.update(version_assignment={})
                (root/'joint-evidence.json').write_text(json.dumps(record))
                (root/'prepared-assets.json').write_text(json.dumps({'joint-evidence.json':hashfile(root/'joint-evidence.json')}))
                Path('publication/registry.json').write_text(json.dumps(registry))
                Path('publication/registry.json.sha256').write_text(hashfile(Path('publication/registry.json'))+'  registry.json\n')
                with patch.dict(os.environ,{'BATCH':'batch','GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'owner/repo'}),patch.object(m.subprocess,'run') as run:
                    m.publish()
                self.assertEqual(run.call_count,3)
                inventory=json.loads((root/'prepared-assets.json').read_text())
                for name,checksum in inventory.items():self.assertEqual(hashfile(root/name),checksum)
            finally:os.chdir(previous)

    def test_release_refuses_registry_with_different_material_image(self):
        m=load('release',TOOLS/'joint-release.py')
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                root=Path('release-assets');root.mkdir();Path('publication').mkdir()
                registry=self.source(Path('source'))
                candidate=json.loads(Path('source/candidate.json').read_text())
                record={'status':'PREPARED_NOT_PUBLISHED','configuration_commit':'a'*40,
                        'version_assignment':{},'server_material':candidate,'origin':'https://example.com'}
                (root/'joint-evidence.json').write_text(json.dumps(record))
                (root/'prepared-assets.json').write_text(json.dumps({'joint-evidence.json':hashfile(root/'joint-evidence.json')}))
                registry.update(version_assignment={})
                registry['images']['api']['image_id']='sha256:'+'f'*64
                Path('publication/registry.json').write_text(json.dumps(registry))
                Path('publication/registry.json.sha256').write_text(hashfile(Path('publication/registry.json'))+'  registry.json\n')
                with patch.dict(os.environ,{'BATCH':'batch','GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'owner/repo'}),patch.object(m.subprocess,'run') as run:
                    with self.assertRaises(ValueError):m.publish()
                    run.assert_not_called()
            finally:os.chdir(previous)
