"""Exact registry transport shared by first installation, upgrade and offline export."""
import json
from pathlib import Path
import re
import subprocess
import hashlib
import ssl
import urllib.request
import urllib.parse

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


def registry_manifest(reference):
    """Read exact public GHCR manifest bytes; never normalize JSON before hashing."""
    match=re.fullmatch(r'ghcr.io/(stevenzxs/cloudmeet-[a-z-]+)@(sha256:[0-9a-f]{64})',reference)
    if not match:raise ValueError('Invalid pinned public image')
    repository,digest=match.groups()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    query=urllib.parse.urlencode({'service':'ghcr.io','scope':'repository:'+repository+':pull'})
    with opener.open('https://ghcr.io/token?'+query,timeout=30) as response:
        token=json.loads(response.read(1024*1024))['token']
    request=urllib.request.Request('https://ghcr.io/v2/'+repository+'/manifests/'+digest,
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'})
    with opener.open(request,timeout=30) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Registry manifest too large')
    return raw


def require_local_image(item,actual):
    if actual['Os']+'/'+actual['Architecture']!=item['platform']:
        raise ValueError('Pulled image platform mismatch')
    if actual['Id']==item['image_id']:return actual['Id']
    # containerd image store (Docker 29) exposes manifest ID, not config ID.
    digest=item['reference'].split('@',1)[1]
    if (actual['Id']!=digest or actual.get('Descriptor',{}).get('digest')!=digest
            or item['reference'] not in actual.get('RepoDigests',[])):
        raise ValueError('Pulled image identity mismatch')
    raw=registry_manifest(item['reference'])
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError('Registry manifest digest mismatch')
    manifest=json.loads(raw)
    if manifest.get('schemaVersion')!=2 or manifest.get('config',{}).get('digest')!=item['image_id']:
        raise ValueError('Registry config identity mismatch')
    return actual['Id']


def pull_images(record,runner=subprocess.run):
    validate(record)
    identities={}
    for service,item in record['images'].items():
        runner(['docker','pull',item['reference']],check=True,timeout=600)
        actual=json.loads(runner(['docker','image','inspect',item['reference']],
                                check=True,capture_output=True,text=True,timeout=30).stdout)[0]
        identities[service]=require_local_image(item,actual)
    return identities


def bind_local_tags(record,manifest,runner=subprocess.run):
    require_material(record,manifest)
    for service,item in record['images'].items():
        local=runner(['docker','image','inspect',manifest['images'][service][0]],
                     capture_output=True,text=True,timeout=30)
        if local.returncode==0:
            info=json.loads(local.stdout)[0]
            require_local_image(item,info)
        elif 'No such image' not in (local.stderr or ''):
            raise ValueError('Cannot establish local image absence: '+service)
    # Preserve package bytes/Compose references; bind the verified digest to its exact tag.
    for service,item in record['images'].items():
        runner(['docker','tag',item['reference'],manifest['images'][service][0]],check=True,timeout=30)
