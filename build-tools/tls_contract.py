"""Approval assertions, never an alternative source of product configuration."""
import json
import os
from pathlib import Path
import urllib.parse


def parse(text):
    result={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);key=key.strip()
        if key in result:raise ValueError('Duplicate client configuration: '+key)
        result[key]=value.strip()
    return result


def validate(config,expected_mode,expected_origin):
    if expected_mode not in ('private-ca','caddy-public-acme') or not expected_origin:
        raise ValueError('Explicit approved TLS mode and origin required before allocation')
    port=int(config['SITE_PORT'])
    if not 1<=port<=65535:raise ValueError('Invalid site port')
    origin=config['SITE_SCHEME']+'://'+config['SITE_DOMAIN']+(':'+str(port) if port!=443 else '')
    parsed=urllib.parse.urlsplit(origin)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in origin)
            or '\\' in origin):raise ValueError('Invalid HTTPS origin')
    mode=config.get('TLS_MODE')
    if mode!=expected_mode or origin!=expected_origin:
        raise ValueError('Approved TLS mode/origin differs from fixed config/client.env')
    if mode=='caddy-public-acme':
        import ipaddress
        try:ipaddress.ip_address(parsed.hostname)
        except ValueError:pass
        else:raise ValueError('Public ACME requires DNS hostname')
        if port!=443 or '.' not in parsed.hostname or config.get('CLIENT_CA_FILE'):
            raise ValueError('Public ACME requires DNS HTTPS/443 without private trust')
    elif not config.get('CLIENT_CA_FILE'):raise ValueError('Private mode requires client CA file')
    return {'tls_mode':mode,'origin':origin}


def approved_contract():
    root=Path(__file__).resolve().parents[1]
    return validate(parse((root/'config/client.env').read_text(encoding='utf-8')),
                    os.environ.get('EXPECTED_TLS_MODE'),os.environ.get('EXPECTED_ORIGIN'))


def require_evidence(contract,mode,origin,ca):
    if mode!=contract['tls_mode'] or origin!=contract['origin']:
        raise ValueError('Final material differs from approved TLS contract')
    if mode=='caddy-public-acme' and ca is not None:
        raise ValueError('Public material contains private CA trust')


if __name__=='__main__':print(json.dumps(approved_contract(),sort_keys=True))
