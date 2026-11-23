#!/usr/bin/env python3
"""Publish same-run verified clients and online material; partial publication stays explicit."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def require_client_assignment(record,assignment):
    if record.get('versionAssignment')!=assignment:
        raise ValueError('Client allocation/configuration/source identity mismatch')


def verify_prepared_assets(root):
    inventory=json.loads((root/'prepared-assets.json').read_text())
    actual={p.name for p in root.iterdir() if p.is_file() and p.name!='prepared-assets.json'}
    if actual!=set(inventory):raise ValueError('Prepared asset inventory changed')
    for name,checksum in inventory.items():
        if Path(name).name!=name or digest(root/name)!=checksum:
            raise ValueError('Prepared asset bytes changed')


def prepare():
    assignment=json.loads(Path(os.environ['VERSION_RECORD']).read_text())
    from revision_versions import validate_record
    validate_record(assignment,json.loads(Path('config/version-policy.json').read_text()),
                    os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'])
    run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    destination=Path('release-assets');destination.mkdir()
    evidence=[];origins=set();cas=set()
    for target,platform,suffix in [('electron','windows','.msi'),('android','android','.apk')]:
        root=Path('client-downloads')/('client-'+target+'-'+run+'-'+attempt)
        records=list(root.rglob('build-evidence.json'))
        if len(records)!=1:raise ValueError('Expected one client evidence: '+target)
        path=records[0];record=json.loads(path.read_text());artifacts=record.get('artifacts',[])
        require_client_assignment(record,assignment)
        if (record.get('status')!='packaged-delivered' or len(artifacts)!=1
                or record.get('version')!=assignment['versions']['client_version']):
            raise ValueError('Client delivery identity mismatch')
        artifact=artifacts[0];checks=artifact['checks']
        if artifact['platform']!=platform:raise ValueError('Wrong client platform')
        for key in ['version','architecture','origin','ca']+(['signature'] if platform=='android' else []):
            if checks.get(key,{}).get('passed') is not True:raise ValueError('Missing client check: '+key)
        if platform=='windows' and (checks.get('signature') is not None or
                checks.get('signing',{}).get('status')!='unsigned' or checks['signing'].get('required') is not False):
            raise ValueError('Explicit unsigned Windows evidence required')
        origins.add(record['origin'])
        ca=record.get('ca',{}).get('sha256','')
        if len(ca)!=64:raise ValueError('Missing client CA identity')
        cas.add(ca)
        file=path.parent/artifact['file']
        if file.name!=artifact['file'] or file.suffix!=suffix or digest(file)!=artifact['sha256']:
            raise ValueError('Client file identity mismatch')
        shutil.copyfile(file,destination/file.name)
        shutil.copyfile(path,destination/(target+'-build-evidence.json'))
        evidence.append({'target':target,'sha256':artifact['sha256'],'file':file.name})
    if len(origins)!=1:raise ValueError('Client origins differ')
    if len(cas)!=1:raise ValueError('Client CA identities differ')
    archives=list(Path('server-downloads').glob('*-online.tar.gz'))
    if len(archives)!=1:raise ValueError('Exactly one online material archive required')
    for file in [archives[0],Path(str(archives[0])+'.sha256'),Path('server-downloads/setup.py'),Path('server-downloads/setup.py.sha256')]:
        shutil.copyfile(file,destination/file.name)
    for file in (archives[0],Path('server-downloads/setup.py')):
        expected=Path(str(file)+'.sha256').read_text().split()[0]
        if digest(file)!=expected:raise ValueError('Server asset checksum mismatch')
    import importlib.util
    spec=importlib.util.spec_from_file_location('online_material',Path(__file__).with_name('online-material.py'))
    material=importlib.util.module_from_spec(spec);spec.loader.exec_module(material)
    material.verify_archive(archives[0])
    import tarfile
    with tarfile.open(archives[0],'r:gz') as tar:
        candidates=[m for m in tar.getmembers() if m.name.endswith('/candidate.json')]
        if len(candidates)!=1:raise ValueError('Expected one server candidate')
        candidate=json.load(tar.extractfile(candidates[0]))
    if (candidate.get('version_assignment')!=assignment or candidate.get('deployment_commit')!=os.environ['GITHUB_SHA']
            or candidate.get('architecture')!=os.environ['TARGET_ARCH']
            or candidate.get('run_id')!=run or candidate.get('attempt')!=attempt
            or candidate.get('image_transport')!='registry' or candidate.get('batch')!=os.environ['BATCH']):
        raise ValueError('Server material identity mismatch')
    if candidate.get('client_origin')!=next(iter(origins)):
        raise ValueError('Server/client deployment origin differs')
    if candidate.get('client_ca_sha256')!=next(iter(cas)):
        raise ValueError('Server/client public CA differs')
    h5=candidate.get('h5',{})
    locked=json.loads(Path('config/h5-source.json').read_text())
    if (h5.get('source_commit')!=locked['commit'] or h5.get('configuration_commit')!=os.environ['GITHUB_SHA']
            or h5.get('version_assignment')!=assignment):
        raise ValueError('Joint publication requires same-batch H5')
    # Public static bytes are covered by the already verified complete archive inventory.
    (destination/'joint-evidence.json').write_text(json.dumps({'status':'PREPARED_NOT_PUBLISHED',
        'configuration_commit':os.environ['GITHUB_SHA'],'run_id':run,'attempt':attempt,
        'origin':origins.pop(),'version_assignment':assignment,'clients':evidence,
        'server_material':candidate},indent=2)+'\n')
    (destination/'prepared-assets.json').write_text(json.dumps({p.name:digest(p) for p in destination.iterdir() if p.is_file()},indent=2)+'\n')


def publish():
    root=Path('release-assets');record=json.loads((root/'joint-evidence.json').read_text())
    verify_prepared_assets(root)
    registry=json.loads(Path('publication/registry.json').read_text())
    if digest(Path('publication/registry.json'))!=Path('publication/registry.json.sha256').read_text().split()[0]:
        raise ValueError('Registry checksum mismatch')
    if (registry['status']!='PUBLISHED_NOT_DEPLOYED' or registry['version_assignment']!=record['version_assignment']
            or registry['configuration_commit']!=record['configuration_commit']):
        raise ValueError('Joint registry identity mismatch')
    import importlib.util
    spec=importlib.util.spec_from_file_location('release_transport',Path(__file__).parent/'offline-runtime/image_transport.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
    transport.require_material(registry,record['server_material'])
    for name in ('registry.json','registry.json.sha256'):
        shutil.copyfile(Path('publication')/name,root/name)
    record['status']='RELEASE_ASSETS_VERIFIED_NOT_DEPLOYED'
    (root/'joint-evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    (root/'prepared-assets.json').write_text(json.dumps({p.name:digest(p) for p in root.iterdir()
        if p.is_file() and p.name not in ('prepared-assets.json','SHA256SUMS')},indent=2)+'\n')
    (root/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(root.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    tag='cloudmeet-'+os.environ['BATCH']
    # Create a draft first: failed uploads must not expose an apparently complete release.
    subprocess.run(['gh','release','create',tag,'--repo',os.environ['GITHUB_REPOSITORY'],
                    '--target',os.environ['GITHUB_SHA'],'--draft','--title',tag,
                    '--notes','Seven-service registry + Electron unsigned / Android signed. Not deployed.'],check=True)
    subprocess.run(['gh','release','upload',tag,*[str(p) for p in sorted(root.iterdir())],
                    '--repo',os.environ['GITHUB_REPOSITORY']],check=True)
    subprocess.run(['gh','release','edit',tag,'--draft=false','--latest=false',
                    '--repo',os.environ['GITHUB_REPOSITORY']],check=True)
    import importlib.util
    spec=importlib.util.spec_from_file_location('delivery_route',Path(__file__).with_name('delivery-route.py'))
    route=importlib.util.module_from_spec(spec);spec.loader.exec_module(route)
    print(json.dumps(route.plan({'origin':record['origin']},record['origin']),ensure_ascii=False,indent=2))


if __name__=='__main__':
    if sys.argv[1:] == ['prepare']:prepare()
    elif sys.argv[1:] == ['publish']:publish()
    else:raise SystemExit('Usage: joint-release.py prepare|publish')
