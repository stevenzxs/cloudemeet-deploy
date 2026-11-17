#!/usr/bin/env python3
"""Publish verified same-run archives, never rebuild or claim runtime acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

SERVICES=('gateway','app-web','api','web','prosody','jicofo','jvb')


def matches_config(manifest,image_id):
    return manifest.get('schemaVersion')==2 and manifest.get('config',{}).get('digest')==image_id


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def output(*args):
    return subprocess.check_output(args,text=True)


def require_absent(remote):
    probe=subprocess.run(['docker','manifest','inspect',remote],capture_output=True,text=True)
    if probe.returncode==0:raise ValueError('Refusing existing registry tag: '+remote)
    diagnostic=probe.stderr.strip()
    # Authentication/transport failures never establish absence, even if another
    # line happens to contain a generic "not found" phrase.
    if (any(word in diagnostic.lower() for word in ('unauthorized','denied','authentication','timeout','timed out'))
            or not any(word in diagnostic.lower() for word in ('manifest unknown','no such manifest'))):
        raise RuntimeError('Unable to establish registry tag absence: '+remote+'; '+diagnostic[:2000])


def push_exact(remote):
    """Retry only the observed blob-upload failure, without replacing a manifest."""
    for attempt in range(3):
        result=subprocess.run(['docker','push',remote],capture_output=True,text=True)
        print(result.stdout,end='',flush=True)
        print(result.stderr,end='',flush=True)
        if result.returncode==0:return
        diagnostic=(result.stdout+'\n'+result.stderr).lower()
        if (attempt==2 or 'unknown blob' not in diagnostic
                or any(word in diagnostic for word in ('denied','unauthorized','authentication'))):
            raise subprocess.CalledProcessError(result.returncode,result.args)
        # A failed upload may have committed a manifest. Never overwrite it on retry.
        require_absent(remote)
        time.sleep(5*(attempt+1))


def main():
    batch=os.environ['BATCH'];sha=os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,110}',batch):
        raise ValueError('Invalid batch')
    if os.environ['GITHUB_REPOSITORY']!='stevenzxs/cloudemeet-deploy':
        raise ValueError('Publication restricted to reviewed repository')
    records={}
    # Validate every archive before publishing any service.
    for service in SERVICES:
        root=Path('downloads')/('image-'+service+'-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'])
        record=json.loads((root/(service+'.json')).read_text())
        for key,expected in {'service':service,'batch':batch,'workflow_commit':sha,
                             'deployment_commit':sha,'run_id':os.environ['GITHUB_RUN_ID'],
                             'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                             'platform':'linux/'+os.environ['TARGET_ARCH']}.items():
            if record[key]!=expected: raise ValueError('Identity mismatch: '+service+'/'+key)
        archive=root/(service+'.tar.gz')
        if record['archive']!=archive.name or digest(archive)!=record['sha256']:
            raise ValueError('Archive mismatch: '+service)
        if record['tag']!='cloudmeet/'+service+':'+batch or record['source_dirty'] is not False:
            raise ValueError('Invalid build source/tag')
        subprocess.run(['docker','load','--input',str(archive)],check=True)
        image=json.loads(output('docker','image','inspect',record['tag']))[0]
        if (image['Id']!=record['image_id'] or image['Os']+'/'+image['Architecture']!=record['platform']
                or image['Config']['Labels']['org.opencontainers.image.revision']!=record['source']['commit']
                or image['Config']['Labels']['io.cloudmeet.batch']!=batch):
            raise ValueError('Loaded image mismatch: '+service)
        records[service]=record
    result={'batch':batch,'configuration_commit':sha,'architecture':os.environ['TARGET_ARCH'],
            'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'status':'PUBLISHING_NOT_COMPLETE','images':{},'runtime_acceptance':'NOT_RUN'}
    destination=Path('publication');destination.mkdir()
    (destination/'registry.json').write_text(json.dumps(result,indent=2)+'\n')
    for service,record in records.items():
        remote='ghcr.io/stevenzxs/cloudmeet-'+service+':'+batch
        # Do not overwrite an existing batch; distinguish missing from authentication/network errors.
        require_absent(remote)
        subprocess.run(['docker','tag',record['tag'],remote],check=True)
        push_exact(remote)
        descriptor=json.loads(output('docker','buildx','imagetools','inspect',remote,'--format','{{json .Manifest}}'))
        registry_digest=descriptor['digest']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',registry_digest): raise ValueError('Invalid digest')
        pinned=remote.split(':')[0]+'@'+registry_digest
        manifest=json.loads(output('docker','buildx','imagetools','inspect',pinned,'--raw'))
        if not matches_config(manifest,record['image_id']): raise ValueError('Registry config identity mismatch')
        result['images'][service]={'reference':pinned,'tag':remote,'image_id':record['image_id'],
                                  'source':record['source'],'platform':record['platform'],
                                  'archive_sha256':record['sha256']}
        (destination/'registry.json').write_text(json.dumps(result,indent=2)+'\n')
    result['status']='PUBLISHED_NOT_DEPLOYED'
    path=destination/'registry.json';path.write_text(json.dumps(result,indent=2)+'\n')
    (destination/'registry.json.sha256').write_text(digest(path)+'  registry.json\n')


if __name__=='__main__': main()
