#!/usr/bin/env python3
"""Existing-instance image-only update. Preserve configuration, secrets and data."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.request
import ssl

SERVICES=('gateway','app-web','api','web','prosody','jicofo','jvb')


def validate_registry(record):
    if (record.get('status')!='PUBLISHED_NOT_DEPLOYED' or record.get('architecture')!='amd64'
            or set(record.get('images',{}))!=set(SERVICES)):
        raise ValueError('Complete amd64 seven-service publication required')
    for service,image in record['images'].items():
        if (not re.fullmatch('ghcr.io/stevenzxs/cloudmeet-'+service+r'@sha256:[0-9a-f]{64}',image['reference'])
                or not re.fullmatch(r'sha256:[0-9a-f]{64}',image['image_id'])
                or image['platform']!='linux/amd64'):
            raise ValueError('Unpinned or invalid image: '+service)


def image_override(record):
    return {'services':{s:{'image':record['images'][s]['reference'],'pull_policy':'never'} for s in SERVICES}}


def require_compatible_material(old,new):
    if not old.get('patches') or old.get('patches')!=new.get('patches'):
        raise ValueError('Image-only update requires identical reviewed external patches')


def capture(*args):
    return subprocess.check_output(args,stderr=subprocess.PIPE,text=True)


def compose(root,project):
    spec=importlib.util.spec_from_file_location('online_target',root/'target.py')
    target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
    os.environ.update(target.load_target(root/'target.env'))
    command=[str(root/'bin/docker-compose'),'--project-name',project,'--project-directory',str(root)]
    for name in ('jitsi.env','.env'):command+=['--env-file',str(root/name)]
    for name in ('jitsi-base.yaml','docker-compose.yml','source-images.yaml'):command+=['-f',str(root/name)]
    return command


def is_idle(stats):
    return isinstance(stats.get('conferences'),dict) and not stats['conferences']


def idle():
    # Existing JVB internal REST endpoint: fail closed if statistics unavailable.
    ids=capture('docker','ps','-q','--filter','label=com.docker.compose.project=cloudmeet-1124801-local-1',
                '--filter','label=com.docker.compose.service=jvb').split()
    if len(ids)!=1:raise ValueError('Expected exact existing JVB')
    stats=json.loads(capture('docker','exec',ids[0],'curl','--fail','--silent',
                            'http://127.0.0.1:8080/stats'))
    if not is_idle(stats):raise ValueError('Active meetings or unrecognized idle state')


def health(origin,ca):
    context=ssl.create_default_context(cafile=str(ca))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),
                                      urllib.request.HTTPSHandler(context=context))
    for path in ('/cm/desktop/','/mapi/actuator/health'):
        with opener.open(origin+path,timeout=15) as response:
            if response.status!=200:raise ValueError('HTTP health failed')
            if 'actuator' in path and json.load(response).get('status')!='UP':
                raise ValueError('API not UP')


def main():
    import fcntl
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--registry-sha256',required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--ca',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    os.umask(0o077)
    if hashlib.sha256(args.registry.read_bytes()).hexdigest()!=args.registry_sha256:
        raise ValueError('Untrusted registry manifest bytes')
    record=json.loads(args.registry.read_text());validate_registry(record)
    root=args.root.resolve();project='cloudmeet-1124801-local-1';origin='https://118.193.36.35:8443'
    if str(root)!='/opt/cloudmeet/11248.0.1':raise ValueError('Unreviewed instance path')
    command=compose(root,project)
    candidate_material=json.loads(args.candidate.read_text())
    require_compatible_material(json.loads((root/'candidate.json').read_text()),candidate_material)
    if candidate_material['batch']!=record['batch'] or candidate_material['deployment_commit']!=record['configuration_commit']:
        raise ValueError('New material/publication mismatch')
    old=json.loads(capture(*command,'config','--format','json'))
    if set(old['services'])!=set(SERVICES):raise ValueError('Unexpected existing service set')
    ids=capture(*command,'ps','-q').split()
    if len(ids)!=7:raise ValueError('Expected seven existing running containers')
    info=json.loads(capture('docker','inspect',*ids))
    for item in info:
        labels=item['Config']['Labels']
        if (labels['com.docker.compose.project']!=project or
                labels['com.docker.compose.project.working_dir']!=str(root)):
            raise ValueError('Container ownership mismatch')
    health(origin,args.ca);idle()
    print('Existing instance, strict TLS/API and idle state verified; apply =',args.apply)
    if not args.apply:return
    with (root/'.online-update.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for image in record['images'].values():
            subprocess.run(['docker','pull',image['reference']],check=True)
            actual=json.loads(capture('docker','image','inspect',image['reference']))[0]
            if actual['Id']!=image['image_id'] or actual['Os']+'/'+actual['Architecture']!=image['platform']:
                raise ValueError('Pulled image identity mismatch')
        idle()
        backup=root/'update-backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True,mode=0o700)
        target=root/'source-images.yaml'
        for name in ('source-images.yaml','jitsi-base.yaml','docker-compose.yml','Caddyfile','.env','target.env','jitsi.env'):
            shutil.copy2(root/name,backup/name)
            (backup/name).chmod(0o600)
        for db in (root/'data/api').glob('*.db'):
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as source:
                with sqlite3.connect(backup/db.name) as destination:source.backup(destination)
        rollback={'services':{x['Config']['Labels']['com.docker.compose.service']:
                             {'image':x['Image'],'pull_policy':'never'} for x in info}}
        (backup/'rollback-images.json').write_text(json.dumps(rollback))
        (backup/'registry.json').write_bytes(args.registry.read_bytes())
        override=backup/'new-images.json';override.write_text(json.dumps(image_override(record)))
        candidate=json.loads(capture(*command,'-f',str(override),'config','--format','json'))
        for service in SERVICES:
            before=dict(old['services'][service]);after=dict(candidate['services'][service])
            for key in ('image','pull_policy'):before.pop(key,None);after.pop(key,None)
            if before!=after:raise ValueError('Image update changed product configuration')
        try:
            target.write_text(json.dumps(image_override(record),indent=2)+'\n')
            subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True)
            for attempt in range(20):
                try:health(origin,args.ca);break
                except Exception:
                    if attempt==19:raise
                    time.sleep(5)
            running=json.loads(capture('docker','inspect',*capture(*command,'ps','-q').split()))
            if len(running)!=7:raise ValueError('Missing containers')
            for item in running:
                service=item['Config']['Labels']['com.docker.compose.service']
                if item['Image']!=record['images'][service]['image_id'] or not item['State']['Running']:
                    raise ValueError('Running image mismatch')
        except Exception:
            target.write_text(json.dumps(rollback))
            subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True)
            health(origin,args.ca)
            # Keep exact image-ID override until operator review; original bytes saved above.
            raise
        (backup/'result.json').write_text(json.dumps({'status':'UPDATED_TLS_API_VERIFIED',
            'batch':record.get('batch'),'not_verified':['media','client trust','roles','rollback drill']}))
        print('Updated seven images; TLS/API verified. Backup:',backup)


if __name__=='__main__':main()
