"""Target-only external certificate staging and strict endpoint verification."""
import hashlib
import ipaddress
import os
from pathlib import Path, PurePosixPath
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request


def origin_host(origin):
    value=urllib.parse.urlsplit(origin)
    if (value.scheme!='https' or not value.hostname or value.username or value.password
            or value.path or value.query or value.fragment or '\\' in origin
            or any(c.isspace() for c in origin)):
        raise ValueError('Expected HTTPS origin without path, query or credentials')
    if value.port is not None and not 1<=value.port<=65535:
        raise ValueError('Invalid origin port')
    return value.hostname


def unpack_certificate(archive,destination):
    """Never extract arbitrary archive paths or execute bundled scripts."""
    allowed={'ca.crt','server.crt','server.key','server.csr','extensions.cnf','certificate.json',
             'SHA256SUMS','cert-tool.py','README.md','replace-cert.sh','replace-fixed-cert.sh',
             'restart-verify-gateway.sh','rollback-cert.sh'}
    content={};top=None
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            parts=PurePosixPath(member.name).parts
            if member.isdir() and len(parts)==1 and parts[0] not in ('.','..','/'):
                continue
            if (not member.isfile() or len(parts)!=2 or parts[0] in ('.','..','/')
                    or parts[1] not in allowed or '\\' in member.name or member.size>1024*1024):
                raise ValueError('Unsafe certificate member: '+member.name)
            if top is None: top=parts[0]
            if top!=parts[0] or parts[1] in content:
                raise ValueError('Duplicate or mixed certificate roots')
            content[parts[1]]=tar.extractfile(member).read()
    required={'ca.crt','server.crt','server.key','certificate.json','SHA256SUMS'}
    if not required<=set(content): raise ValueError('Incomplete certificate bundle')
    seen=set()
    for line in content['SHA256SUMS'].decode().splitlines():
        digest,name=line.split('  ',1)
        if name in seen or name=='SHA256SUMS' or name not in content:
            raise ValueError('Invalid certificate checksum inventory')
        if hashlib.sha256(content[name]).hexdigest()!=digest:
            raise ValueError('Certificate checksum mismatch: '+name)
        seen.add(name)
    if seen!=set(content)-{'SHA256SUMS'}: raise ValueError('Unlisted certificate files')
    destination.mkdir(mode=0o700)
    for name,data in content.items():
        with (destination/name).open('xb') as output: output.write(data)
        (destination/name).chmod(0o600 if name.endswith('.key') else 0o644)


def validate(directory,origin):
    host=origin_host(origin)
    def openssl(*args):
        return subprocess.check_output(['openssl',*map(str,args)],stderr=subprocess.PIPE)
    try: ipaddress.ip_address(host); option='-verify_ip'
    except ValueError: option='-verify_hostname'
    openssl('verify','-CAfile',directory/'ca.crt','-purpose','sslserver',option,host,directory/'server.crt')
    openssl('x509','-in',directory/'server.crt','-checkend','86400','-noout')
    if openssl('x509','-in',directory/'server.crt','-pubkey','-noout')!=openssl(
            'pkey','-in',directory/'server.key','-pubout'):
        raise ValueError('External certificate/key mismatch')


def preflight(root,origin):
    origin_host(origin)
    with tempfile.TemporaryDirectory(prefix='cloudmeet-cert-') as tmp:
        out=Path(tmp)/'cert'
        unpack_certificate(root/'cert.tar.gz',out)
        validate(out,origin)


def activate(root,origin,command):
    """Install only external TLS; preserve internal TLS, secrets and CA volumes."""
    # Do not execute target-supplied code: transformation is from maintained package.
    config=root/'Caddyfile';original=config.read_bytes()
    text=original.decode()
    if text.count('tls internal')!=2:
        raise ValueError('Unsupported initial Caddyfile TLS layout')
    replacement='tls /config/cloudmeet-cert/first-install/server.crt /config/cloudmeet-cert/first-install/server.key'
    candidate=text.replace('tls internal',replacement)
    container=subprocess.check_output(command+['ps','-q','gateway'],universal_newlines=True).strip()
    if not container or '\n' in container: raise ValueError('Expected one gateway container')
    subprocess.run(['docker','exec',container,'mkdir','-p','/config/cloudmeet-cert/first-install'],check=True)
    for name in ('server.crt','server.key'):
        subprocess.run(['docker','cp',str(root/'cert'/name),container+':/config/cloudmeet-cert/first-install/'+name],check=True)
    subprocess.run(['docker','exec',container,'chmod','600','/config/cloudmeet-cert/first-install/server.key'],check=True)
    with (root/'Caddyfile.before-external-cert').open('xb') as backup: backup.write(original)
    config.write_bytes(candidate.encode())
    try:
        subprocess.run(['docker','exec',container,'caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],check=True)
    except Exception:
        config.write_bytes(original)
        raise
    subprocess.run(command+['restart','gateway'],check=True,timeout=90)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    context=ssl.create_default_context(cafile=str(root/'cert/ca.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=context))
    error=None
    for attempt in range(12):
        try:
            with opener.open(origin+'/cm/desktop/',timeout=10) as response:
                if not 200<=response.status<300: raise ValueError('Unexpected HTTP response')
            print('Strict external TLS and /cm/desktop/ response verified:',origin)
            return
        except Exception as failure:
            error=failure
            time.sleep(3)
    raise RuntimeError('External HTTPS verification failed; preserve instance and inspect: '+str(error))
