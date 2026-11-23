#!/usr/bin/env python3
"""Existing-instance update with bounded H5 gateway migration; preserve secrets/data."""
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
    if (record.get('status')!='PUBLISHED_NOT_DEPLOYED' or record.get('architecture') not in ('amd64','arm64')
            or set(record.get('images',{}))!=set(SERVICES)):
        raise ValueError('Complete seven-service publication required')
    for service,image in record['images'].items():
        if (not re.fullmatch('ghcr.io/stevenzxs/cloudmeet-'+service+r'@sha256:[0-9a-f]{64}',image['reference'])
                or not re.fullmatch(r'sha256:[0-9a-f]{64}',image['image_id'])
                or image['platform']!='linux/'+record['architecture']):
            raise ValueError('Unpinned or invalid image: '+service)


def image_override(record):
    return {'services':{s:{'image':record['images'][s]['reference'],'pull_policy':'never'} for s in SERVICES}}


def require_compatible_material(old,new):
    if not old.get('patches') or old.get('patches')!=new.get('patches'):
        raise ValueError('Image-only update requires identical reviewed external patches')


def require_configuration_compatible(old_root,new_root):
    def sums(root):
        return {name:checksum for checksum,name in
                (line.split('  ',1) for line in (root/'SHA256SUMS').read_text().splitlines())}
    old=sums(old_root);new=sums(new_root)
    new_manifest=json.loads((new_root/'candidate.json').read_text()) if (new_root/'candidate.json').exists() else {}
    h5_enabled='h5' in new_manifest
    names=('jitsi.env','docker-compose.yml','target.env','target.py','initialize.py') if h5_enabled else ('jitsi.env','Caddyfile','docker-compose.yml','target.env','target.py','initialize.py','start.py')
    for name in names:
        if (name in old or name in new) and old.get(name)!=new.get(name):
            raise ValueError('Image-only upgrade requires reviewed configuration migration: '+name)
    # Base Compose differs per batch only in project name and image identities.
    def normalized(root):
        data=json.loads((root/'jitsi-base.yaml').read_text());data.pop('name',None)
        for service in data.get('services',{}).values():service.pop('image',None)
        return data
    if h5_enabled:
        spec=importlib.util.spec_from_file_location('h5_compat',Path(__file__).with_name('h5.py'))
        h5=importlib.util.module_from_spec(spec);spec.loader.exec_module(h5)
        h5.verify_package(new_root,new_manifest)
        before=(old_root/'Caddyfile').read_text()
        first='/cm/h5/' not in before
        after=(new_root/'Caddyfile').read_text()
        h5.require_gateway_delta(before,after,first)
        h5.require_compose_delta(normalized(old_root),normalized(new_root),first)
    elif normalized(old_root)!=normalized(new_root):
        raise ValueError('Image-only upgrade requires reviewed Compose migration')


def capture(*args,env=None):
    return subprocess.check_output(args,stderr=subprocess.PIPE,text=True,env=env)


def instance_context(root,project,target_env=None):
    spec=importlib.util.spec_from_file_location('instance_start',root/'start.py')
    start=importlib.util.module_from_spec(spec);spec.loader.exec_module(start)
    command=start.compose_command(root,target_env)
    command[1:1]=['--project-name',project] if command[0]!='docker' else []
    if command[0]=='docker':command[2:2]=['--project-name',project]
    return command,start.runtime_environment(root,target_env)


def is_idle(stats):
    return isinstance(stats.get('conferences'),dict) and not stats['conferences']


def require_ownership(info,root,project):
    services=[]
    for item in info:
        labels=item.get('Config',{}).get('Labels',{})
        if (labels.get('com.docker.compose.project')!=project or
                labels.get('com.docker.compose.project.working_dir')!=str(root) or
                not item.get('State',{}).get('Running')):
            raise ValueError('Container ownership/running state mismatch')
        services.append(labels.get('com.docker.compose.service'))
    if len(services)!=7 or set(services)!=set(SERVICES):
        raise ValueError('Expected each selected service exactly once')


def idle(project):
    # Existing JVB internal REST endpoint: fail closed if statistics unavailable.
    ids=capture('docker','ps','-q','--filter','label=com.docker.compose.project='+project,
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


def h5_health(origin, ca, record):
    context=ssl.create_default_context(cafile=str(ca))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),
                                      urllib.request.HTTPSHandler(context=context))
    for name, expected in record['files'].items():
        with opener.open(origin+'/cm/h5/'+name,timeout=15) as response:
            if response.status!=200 or hashlib.sha256(response.read()).hexdigest()!=expected['sha256']:
                raise ValueError('H5 served bytes differ from approved material')
            if name.endswith('.mjs') and response.headers.get_content_type()!='application/javascript':
                raise ValueError('H5 module MIME type mismatch')
    with opener.open(origin+'/cm/h5/runtime-config.json',timeout=15) as response:
        if json.load(response)!={'jitsiOrigin':origin}:
            raise ValueError('H5 public runtime origin mismatch')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--registry-sha256',required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--verify-origin',required=True)
    parser.add_argument('--target-env',type=Path,required=True)
    parser.add_argument('--offline-package',type=Path,help='Explicit offline upgrade; never pulls')
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--ca',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    import fcntl
    os.umask(0o077)
    if hashlib.sha256(args.registry.read_bytes()).hexdigest()!=args.registry_sha256:
        raise ValueError('Untrusted registry manifest bytes')
    record=json.loads(args.registry.read_text());validate_registry(record)
    root=args.root.resolve();project=args.project;origin=args.verify_origin
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}',project):raise ValueError('Invalid Compose project')
    spec=importlib.util.spec_from_file_location('origin_certificate',Path(__file__).with_name('certificate.py'))
    cert=importlib.util.module_from_spec(spec);spec.loader.exec_module(cert)
    cert.origin_host(origin)
    command,environment=instance_context(root,project,args.target_env.absolute())
    candidate_material=json.loads(args.candidate.read_text())
    require_compatible_material(json.loads((root/'candidate.json').read_text()),candidate_material)
    require_configuration_compatible(root,args.candidate.resolve().parent)
    if candidate_material['batch']!=record['batch'] or candidate_material['deployment_commit']!=record['configuration_commit']:
        raise ValueError('New material/publication mismatch')
    spec=importlib.util.spec_from_file_location('image_transport',Path(__file__).with_name('image_transport.py'))
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
    transport.require_material(record,candidate_material)
    transport.require_origin(candidate_material,origin)
    transport.require_ca(candidate_material,args.ca)
    spec=importlib.util.spec_from_file_location('new_material_verifier',Path(__file__).with_name('install.py'))
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.verify_checksums(args.candidate.resolve().parent);verifier.require_ready(candidate_material)
    h5_module=None
    if 'h5' in candidate_material:
        spec=importlib.util.spec_from_file_location('h5_update',Path(__file__).with_name('h5.py'))
        h5_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(h5_module)
        h5_module.verify_package(args.candidate.resolve().parent,candidate_material)
    offline=None
    if args.offline_package:
        offline=args.offline_package.resolve()
        if args.candidate.resolve()!=offline/'candidate.json':raise ValueError('Offline candidate must belong to package')
        spec=importlib.util.spec_from_file_location('offline_verifier',Path(__file__).with_name('install.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        verifier.verify_checksums(offline);verifier.require_ready(candidate_material)
        if candidate_material.get('image_transport')=='registry':raise ValueError('Offline upgrade requires image archives')
    old=json.loads(capture(*command,'config','--format','json',env=environment))
    if set(old['services'])!=set(SERVICES):raise ValueError('Unexpected existing service set')
    ids=capture(*command,'ps','-q',env=environment).split()
    if len(ids)!=7:raise ValueError('Expected seven existing running containers')
    info=json.loads(capture('docker','inspect',*ids))
    require_ownership(info,root,project)
    health(origin,args.ca);idle(project)
    print('Existing instance, strict TLS/API and idle state verified; apply =',args.apply)
    if not args.apply:return
    with (root/'.online-update.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if offline:
            spec=importlib.util.spec_from_file_location('offline_import',Path(__file__).with_name('deploy.py'))
            importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
            for service in SERVICES:
                provenance=json.loads((offline/'provenance'/(service+'.json')).read_text())
                verifier.verify_image_archive(offline/'images'/provenance['archive'],provenance)
            importer.acquire_images(offline,candidate_material,verifier,subprocess.run)
        else:
            transport.pull_images(record)
        idle(project)
        backup=root/'update-backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True,mode=0o700)
        target=root/'source-images.yaml'
        for name in ('source-images.yaml','jitsi-base.yaml','docker-compose.yml','Caddyfile','.env','target.env','jitsi.env'):
            shutil.copy2(root/name,backup/name)
            (backup/name).chmod(0o600)
        shutil.copy2(args.target_env,backup/'external-target.env')
        (backup/'external-target.env').chmod(0o600)
        for db in (root/'data/api').glob('*.db'):
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as source:
                with sqlite3.connect(backup/db.name) as destination:source.backup(destination)
        rollback={'services':{x['Config']['Labels']['com.docker.compose.service']:
                             {'image':x['Image'],'pull_policy':'never'} for x in info}}
        (backup/'rollback-images.json').write_text(json.dumps(rollback))
        (backup/'registry.json').write_bytes(args.registry.read_bytes())
        replacement=image_override(record)
        if offline:
            replacement={'services':{s:{'image':record['images'][s]['image_id'],'pull_policy':'never'} for s in SERVICES}}
        override=backup/'new-images.json';override.write_text(json.dumps(replacement))
        candidate=json.loads(capture(*command,'-f',str(override),'config','--format','json',env=environment))
        for service in SERVICES:
            before=dict(old['services'][service]);after=dict(candidate['services'][service])
            for key in ('image','pull_policy'):before.pop(key,None);after.pop(key,None)
            if before!=after:raise ValueError('Image update changed product configuration')
        previous_h5=None
        h5_switched=False
        try:
            if h5_module:
                new_root=args.candidate.resolve().parent
                release=h5_module.prepare_release(root/'h5-runtime',new_root/'h5/public',candidate_material['h5'],origin)
                previous_h5=h5_module.activate(root/'h5-runtime',release)
                h5_switched=True
                # Only the verified route addition and readonly parent mount may change.
                # Preserve instance project name and all existing service settings.
                if '/cm/h5/' not in (root/'Caddyfile').read_text():
                    (root/'Caddyfile').write_text(h5_module.gateway_caddy((root/'Caddyfile').read_text()))
                    base=json.loads((root/'jitsi-base.yaml').read_text())
                    base['services']['gateway']['volumes'].append('./h5-runtime:/srv/cloudmeet-h5:ro')
                    (root/'jitsi-base.yaml').write_text(json.dumps(base,indent=2)+'\n')
            target.write_text(json.dumps(replacement,indent=2)+'\n')
            subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True,env=environment)
            for attempt in range(20):
                try:health(origin,args.ca);break
                except Exception:
                    if attempt==19:raise
                    time.sleep(5)
            running=json.loads(capture('docker','inspect',*capture(*command,'ps','-q',env=environment).split()))
            require_ownership(running,root,project)
            for item in running:
                service=item['Config']['Labels']['com.docker.compose.service']
                if item['Image']!=record['images'][service]['image_id'] or not item['State']['Running']:
                    raise ValueError('Running image mismatch')
            if h5_module:
                h5_health(origin,args.ca,candidate_material['h5'])
        except Exception:
            if h5_switched:
                h5_module.restore_pointer(root/'h5-runtime',previous_h5)
                for name in ('Caddyfile','jitsi-base.yaml'):
                    shutil.copy2(backup/name,root/name)
            target.write_text(json.dumps(rollback))
            subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True,env=environment)
            health(origin,args.ca)
            # Keep exact image-ID override until operator review; original bytes saved above.
            raise
        (backup/'result.json').write_text(json.dumps({'status':'UPDATED_TLS_API_VERIFIED',
            'batch':record.get('batch'),'not_verified':['media','client trust','roles','rollback drill']}))
        print('Updated seven images and included H5 if present; TLS/API/static bytes verified. Backup:',backup)


if __name__=='__main__':main()
