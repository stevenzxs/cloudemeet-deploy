"""Exact registry transport shared by first installation, upgrade and offline export."""
import json
from pathlib import Path
import re
import subprocess
import hashlib
import ssl

SERVICES=('gateway','app-web','api','web','prosody','jicofo','jvb')


def require_origin(manifest,origin):
    if manifest.get('client_origin') and manifest['client_origin']!=origin:
        raise ValueError('Deployment origin differs from built clients')


def require_ca(manifest,path):
    expected=manifest.get('client_ca_sha256')
    if expected:
        try:actual=hashlib.sha256(ssl.PEM_cert_to_DER_cert(Path(path).read_text(encoding='ascii'))).hexdigest()
        except (ValueError,UnicodeError) as error:raise ValueError('Invalid target public CA') from error
        if actual!=expected:raise ValueError('Target CA differs from built client trust')


def validate(record):
    if (record.get('status')!='PUBLISHED_NOT_DEPLOYED'
            or record.get('architecture') not in ('amd64','arm64')
            or set(record.get('images',{}))!=set(SERVICES)):
        raise ValueError('Complete pinned seven-service publication required')
    for service,item in record['images'].items():
        if (not re.fullmatch('ghcr.io/stevenzxs/cloudmeet-'+service+r'@sha256:[0-9a-f]{64}',item.get('reference',''))
                or not re.fullmatch(r'sha256:[0-9a-f]{64}',item.get('image_id',''))
                or item.get('platform')!='linux/'+record['architecture']):
            raise ValueError('Invalid registry image: '+service)


def require_material(record,manifest):
    validate(record)
    if (record.get('batch')!=manifest.get('batch')
            or record.get('configuration_commit')!=manifest.get('deployment_commit')
            or record['architecture']!=manifest.get('architecture')):
        raise ValueError('Publication/material identity mismatch')
    if set(manifest.get('images',{}))!=set(SERVICES):
        raise ValueError('Incomplete material image set')
    for service,item in record['images'].items():
        if manifest['images'][service][1]!=item['image_id']:
            raise ValueError('Material image identity mismatch: '+service)


def pull_images(record,runner=subprocess.run):
    validate(record)
    for item in record['images'].values():
        runner(['docker','pull',item['reference']],check=True,timeout=600)
        actual=json.loads(runner(['docker','image','inspect',item['reference']],
                                check=True,capture_output=True,text=True,timeout=30).stdout)[0]
        if (actual['Id']!=item['image_id']
                or actual['Os']+'/'+actual['Architecture']!=item['platform']):
            raise ValueError('Pulled image identity mismatch')


def bind_local_tags(record,manifest,runner=subprocess.run):
    require_material(record,manifest)
    for service,item in record['images'].items():
        local=runner(['docker','image','inspect',manifest['images'][service][0]],
                     capture_output=True,text=True,timeout=30)
        if local.returncode==0:
            info=json.loads(local.stdout)[0]
            if info['Id']!=item['image_id'] or info['Os']+'/'+info['Architecture']!=item['platform']:
                raise ValueError('Refusing conflicting package tag: '+service)
        elif 'No such image' not in (local.stderr or ''):
            raise ValueError('Cannot establish local image absence: '+service)
    # Preserve package bytes/Compose references; bind the verified digest to its exact tag.
    for service,item in record['images'].items():
        runner(['docker','tag',item['reference'],manifest['images'][service][0]],check=True,timeout=30)
